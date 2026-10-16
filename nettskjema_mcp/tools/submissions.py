# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Submission tools: read submissions, deliver a response, and delete responses.

Two of the deletes differ by one character. ``DELETE /form/{formId}/submission``
removes the submissions whose ids are in its (required) body;
``DELETE /form/{formId}/submissions`` is ``deleteAllSubmissions`` in the spec,
summarised there as "Delete all submissions", and its body is optional. The tool
names and the first line of both docstrings carry that distinction, because the
paths themselves do not carry it legibly.

``delete_all_submissions`` deliberately exposes **no** id parameter. The spec
gives the plural operation an optional array body but documents it as deleting
all submissions, and never says the ids narrow anything — the singular operation
is what exists for a scoped delete. A parameter that looks like it limits the
blast radius but may not is worse than no parameter at all, so the tool sends no
body, which the spec permits.
"""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.errors import BadRequestError
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool
from nettskjema_mcp.validation import validate_body

GET_SUBMISSION = Route("GET", "/form/submission/{submissionId}")
LIST_MY_SUBMISSIONS = Route("GET", "/form/submission/me")
GET_SUBMISSION_PDF = Route("GET", "/form/submission/{submissionId}/pdf")
GET_SUBMISSION_METADATA = Route("GET", "/form/{formId}/submission-metadata")
GET_POSTPONED_SUBMISSION_METADATA = Route("GET", "/form/{formId}/submission-metadata-postponed")
DELIVER_SUBMISSION = Route("POST", "/form/{formId}/submission")
DELIVER_SUBMISSION_FOR_INVITATION = Route("POST", "/form/invitation/{invitationId}/submission")
DELETE_SUBMISSIONS = Route("DELETE", "/form/{formId}/submission")
DELETE_ALL_SUBMISSIONS = Route("DELETE", "/form/{formId}/submissions")


def _deliver_body(
    answers: list[dict[str, object]], metadata: dict[str, object] | None
) -> dict[str, object]:
    """
    Assemble and validate a DeliverSubmissionDTO body.

    Args:
        answers: The answers to deliver, each a ClientAnswerDTO object.
        metadata: Optional delivery metadata, a DeliverMetadataDTO object. Left
            out of the body entirely when None, rather than sent as null.

    Returns:
        The request body: ``{"answers": [...]}`` plus ``metadata`` when given.

    Raises:
        BadRequestError: If the body does not match the vendored schema.
    """
    body: dict[str, object] = {"answers": answers}
    if metadata is not None:
        body["metadata"] = metadata
    # strict=False: an answer may well have been read back from get_submission,
    # and rejecting a field the API itself produced would leave the caller no way
    # to re-deliver it. Types, enums and formats are still checked.
    validate_body("DeliverSubmissionDTO", body, strict=False)
    return body


@tool(annotations={"readOnlyHint": True})
@endpoint(GET_SUBMISSION)
async def get_submission(submission_id: int) -> str:
    """
    Get a single submission with its answers and metadata.

    Args:
        submission_id: The submission's numeric ID.

    Returns:
        The submission as JSON, with two properties: answers (an array of answer
        objects) and submissionMetadata (an object with submission-level metadata).
    """
    return dump(await get_client().json(GET_SUBMISSION, path={"submissionId": submission_id}))


@tool(annotations={"readOnlyHint": True})
@endpoint(LIST_MY_SUBMISSIONS)
async def list_my_submissions() -> str:
    """
    List all submissions made by the authenticated API client.

    Returns:
        An array of submission summary objects as JSON. Each object includes
        submissionId, form (with title), createdDate, modifiedDate, and delivered
        (boolean).
    """
    return dump(await get_client().json(LIST_MY_SUBMISSIONS))


@tool()
@endpoint(GET_SUBMISSION_PDF)
async def get_submission_pdf(submission_id: int, output_path: str | None = None) -> str:
    """
    Download a submission as a PDF file.

    The PDF is written to disk, not returned inline: a multi-megabyte PDF as
    base64 is not useful to a model. The returned path is absolute and
    tilde-expanded. An existing file at the output path is silently overwritten,
    and its mode is preserved. A new file (whether from output_path or a temp file)
    is created with mode 0600 (readable only by the current user).

    When output_path is omitted, a temporary file is created in the system temp
    directory with a .pdf suffix. The temporary file persists after this call
    returns and is left on disk for the caller to use or delete.

    Args:
        submission_id: The submission's numeric ID.
        output_path: Destination file path. When omitted, a temporary file is
            created in the system temp directory. The path may contain ~ for the
            home directory and may be relative (it will be resolved to an absolute
            path).

    Returns:
        A JSON object with path (the absolute path to the written file), bytes
        (the number of bytes written), and mediaType (the content type from the
        response, typically application/pdf).
    """
    return dump(
        await get_client().binary(
            GET_SUBMISSION_PDF, path={"submissionId": submission_id}, output_path=output_path
        )
    )


@tool(annotations={"readOnlyHint": True})
@endpoint(GET_SUBMISSION_METADATA)
async def get_submission_metadata(
    form_id: int,
    submission_ids_greater_than: int | None = None,
    optimize_for_large_data: bool | None = None,
    max_rows: int | None = None,
) -> str:
    """
    Stream all submission metadata for a form, as newline-delimited JSON.

    Returns metadata without answers: use this for bulk export of submission-level
    fields or to find which submissions exist before fetching their answers. This
    streams NDJSON (one JSON object per line), so a large form's metadata is never
    held whole in memory. The result is capped at max_rows to bound context size:
    check the returned truncated field to see if more data exists.

    Distinct from get_postponed_submission_metadata, which returns postponed
    submission metadata only. The relationship between the two result sets (whether
    this endpoint includes or excludes postponed submissions) is not specified by
    the API documentation.

    Args:
        form_id: The form's numeric ID.
        submission_ids_greater_than: Only include submissions with IDs above this value.
        optimize_for_large_data: Request optimization for large datasets.
        max_rows: Maximum number of rows to return. Defaults to this MCP server's
            configured limit (1000). When the cap is reached, truncated is set to
            true and reason is "rowCap". The caller may raise this limit arbitrarily
            by passing a larger value.

    Returns:
        A JSON object with rows (an array of SubmissionMetadataDTO objects),
        rowCount (the number returned), truncated (boolean), and reason (string or
        null, distinguishing a row cap from an incomplete final line). Each row
        includes submissionId, formId, createdDate, modifiedDate, anonymous,
        answerTime, deliveryDestination, forwardedTo, invited, person,
        respondentEmail, respondentName, and submissionSignatureState.
    """
    return dump(
        await get_client().ndjson(
            GET_SUBMISSION_METADATA,
            path={"formId": form_id},
            query={
                "submission-ids-greater-than": submission_ids_greater_than,
                "optimize-for-large-data": optimize_for_large_data,
            },
            max_rows=max_rows,
        )
    )


@tool(annotations={"readOnlyHint": True})
@endpoint(GET_POSTPONED_SUBMISSION_METADATA)
async def get_postponed_submission_metadata(
    form_id: int,
    submission_ids_greater_than: int | None = None,
    max_rows: int | None = None,
) -> str:
    """
    Stream postponed submission metadata for a form, as newline-delimited JSON.

    This endpoint returns the same metadata structure as get_submission_metadata,
    but only for postponed submissions. The result is streamed as NDJSON and capped
    at max_rows to bound context size.

    Distinct from get_submission_metadata: this endpoint returns postponed submission
    metadata only, while that one returns all submission metadata for the form.

    Args:
        form_id: The form's numeric ID.
        submission_ids_greater_than: Only include submissions with IDs above this value.
        max_rows: Maximum number of rows to return. Defaults to this MCP server's
            configured limit (1000). When the cap is reached, truncated is set to
            true and reason is "rowCap". The caller may raise this limit arbitrarily
            by passing a larger value.

    Returns:
        A JSON object with rows (an array of SubmissionMetadataDTO objects),
        rowCount (the number returned), truncated (boolean), and reason (string or
        null). Each row includes submissionId, formId, createdDate, modifiedDate,
        anonymous, answerTime, deliveryDestination, forwardedTo, invited, person,
        respondentEmail, respondentName, and submissionSignatureState.
    """
    return dump(
        await get_client().ndjson(
            GET_POSTPONED_SUBMISSION_METADATA,
            path={"formId": form_id},
            query={"submission-ids-greater-than": submission_ids_greater_than},
            max_rows=max_rows,
        )
    )


@tool()
@endpoint(DELIVER_SUBMISSION)
async def submit_form(
    form_id: int,
    answers: list[dict[str, object]],
    metadata: dict[str, object] | None = None,
) -> str:
    """
    Deliver a response to a form, as the authenticated API client.

    This submits a real answer to a real form: it adds a row to the form's
    collected data, and the form's owner sees it alongside human responses.
    There is no draft or preview mode here. Use submit_form_for_invitation
    instead when answering on behalf of a specific invitation.

    Each answer is checked against the vendored ClientAnswerDTO schema before
    the request is sent, so a bad enum value or a mistyped field fails without
    reaching the form. A field the snapshot does not declare is passed through
    to the API, which has the final say.

    Args:
        form_id: The form's numeric ID.
        answers: The answers to deliver, one object per answered element. The
            schema declares answerId, answerOptionIds, answered, date, datetime,
            id, ids, questionId, text, time, type and unAnswered; every one is
            optional. type must be one of SINGLE_OPTION, MULTIPLE_OPTIONS, TEXT,
            FILE, DATE_TIME, DATE, TIME or NOT_PROVIDED, and date, datetime and
            time are ISO 8601 strings.
        metadata: Optional delivery metadata. The schema declares elapsedTime
            (integer) and tsdRespondent (an object with personal_identifier,
            provider, representation, sub, task_id and user_name). Omitted from
            the request entirely when not given.

    Returns:
        The response body as JSON. The spec declares this 200 as an object with
        no declared properties, so no particular field is part of the contract:
        read what comes back rather than expecting a specific key. A response
        with no body is reported as {"status": "success", "httpStatus": <code>}.
    """
    return dump(
        await get_client().json(
            DELIVER_SUBMISSION, path={"formId": form_id}, body=_deliver_body(answers, metadata)
        )
    )


@tool()
@endpoint(DELIVER_SUBMISSION_FOR_INVITATION)
async def submit_form_for_invitation(
    invitation_id: int,
    answers: list[dict[str, object]],
    metadata: dict[str, object] | None = None,
) -> str:
    """
    Deliver a response to the form a given invitation was issued for.

    Same delivery as submit_form, addressed by invitation rather than by form:
    the response is recorded against that invitation, so the form's owner can
    see which invited respondent answered. The invitation is identified by its
    own numeric id, not by the form's. This submits a real answer to a real
    form; there is no draft or preview mode.

    Each answer is checked against the vendored ClientAnswerDTO schema before
    the request is sent. A field the snapshot does not declare is passed through
    to the API, which has the final say.

    Args:
        invitation_id: The invitation's numeric ID. This is not a form ID.
        answers: The answers to deliver, one object per answered element. The
            schema declares answerId, answerOptionIds, answered, date, datetime,
            id, ids, questionId, text, time, type and unAnswered; every one is
            optional. type must be one of SINGLE_OPTION, MULTIPLE_OPTIONS, TEXT,
            FILE, DATE_TIME, DATE, TIME or NOT_PROVIDED, and date, datetime and
            time are ISO 8601 strings.
        metadata: Optional delivery metadata. The schema declares elapsedTime
            (integer) and tsdRespondent (an object with personal_identifier,
            provider, representation, sub, task_id and user_name). Omitted from
            the request entirely when not given.

    Returns:
        The response body as JSON. The spec declares this 200 as an object with
        no declared properties, so no particular field is part of the contract:
        read what comes back rather than expecting a specific key. A response
        with no body is reported as {"status": "success", "httpStatus": <code>}.
    """
    return dump(
        await get_client().json(
            DELIVER_SUBMISSION_FOR_INVITATION,
            path={"invitationId": invitation_id},
            body=_deliver_body(answers, metadata),
        )
    )


@tool(annotations={"destructiveHint": True})
@endpoint(DELETE_SUBMISSIONS)
async def delete_submissions(form_id: int, submission_ids: list[int]) -> str:
    """
    Delete ONLY the listed responses to a form. Other responses are left alone.

    This is the scoped delete, and the one to use whenever specific responses
    are meant: it removes exactly the submissions whose ids are given, and
    nothing else. Do not confuse it with delete_all_submissions, which deletes
    every response the form has and takes no id list. Deleted responses are
    gone; the API offers no undo for them.

    Get submission ids from get_submission_metadata or list_my_submissions. An
    empty list is refused rather than sent, because what the API would do with
    an empty body here is not specified and the cost of guessing wrong is a
    form's data.

    Args:
        form_id: The form's numeric ID.
        submission_ids: The ids of the submissions to delete. Must not be empty.
            These are submission ids, not form ids.

    Returns:
        A success marker as JSON: {"status": "success", "httpStatus": <code>}.
        The spec declares no response body for this operation.

    Raises:
        BadRequestError: If submission_ids is empty. No request is issued.
    """
    if not submission_ids:
        raise BadRequestError(
            "submission_ids is empty, so there is nothing to delete. The API does not "
            "specify what an empty list means here, and this tool will not guess with a "
            "form's responses. Pass the submission ids to delete, or call "
            "delete_all_submissions if you really mean to delete every response."
        )

    # The body is the bare array: [1, 2, 3], not {"submissionIds": [1, 2, 3]}.
    return dump(
        await get_client().json(DELETE_SUBMISSIONS, path={"formId": form_id}, body=submission_ids)
    )


@tool(annotations={"destructiveHint": True})
@endpoint(DELETE_ALL_SUBMISSIONS)
async def delete_all_submissions(form_id: int) -> str:
    """
    Delete EVERY response the form has ever collected. This CANNOT be undone.

    There is no id list and no partial form of this call: the whole dataset goes,
    for every respondent, and the API offers no undo and no trash can for
    submissions. Confirm with the user before calling it. To remove particular
    responses, use delete_submissions, which takes submission ids and leaves the
    rest of the form's data in place.

    The spec's plural operation accepts an optional array body, but documents the
    operation as deleting all submissions and never says the ids narrow it. This
    tool therefore sends no body and offers no id parameter, rather than a
    parameter that looks like it limits the damage and may not.

    Args:
        form_id: The form whose responses are to be deleted, all of them.

    Returns:
        A success marker as JSON: {"status": "success", "httpStatus": <code>}.
        The spec declares no response body for this operation.
    """
    # No body: the spec marks the request body optional on this operation.
    return dump(await get_client().json(DELETE_ALL_SUBMISSIONS, path={"formId": form_id}))
