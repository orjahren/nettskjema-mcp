"""Submission read tools: fetch individual submissions, list user's submissions, and export metadata."""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool

GET_SUBMISSION = Route("GET", "/form/submission/{submissionId}")
LIST_MY_SUBMISSIONS = Route("GET", "/form/submission/me")
GET_SUBMISSION_PDF = Route("GET", "/form/submission/{submissionId}/pdf")
GET_SUBMISSION_METADATA = Route("GET", "/form/{formId}/submission-metadata")
GET_POSTPONED_SUBMISSION_METADATA = Route("GET", "/form/{formId}/submission-metadata-postponed")


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
        submissionId, form (with formId and title), createdDate, modifiedDate, and
        delivered (boolean).
    """
    return dump(await get_client().json(LIST_MY_SUBMISSIONS))


@tool(annotations={"readOnlyHint": True})
@endpoint(GET_SUBMISSION_PDF)
async def get_submission_pdf(submission_id: int, output_path: str | None = None) -> str:
    """
    Download a submission as a PDF file.

    The PDF is written to disk, not returned inline: a multi-megabyte workbook as
    base64 is not useful to a model. The returned path is absolute and
    tilde-expanded. An existing file at the output path is silently overwritten.

    Args:
        submission_id: The submission's numeric ID.
        output_path: Destination file path. When omitted, a temporary file is
            created in the system temp directory with a .pdf suffix. The path may
            contain ~ for the home directory.

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
    Stream submission metadata for a form, as newline-delimited JSON.

    Returns metadata without answers: use this for bulk export of submission-level
    fields or to find which submissions exist before fetching their answers. This
    streams NDJSON (one JSON object per line), so a large form's metadata is never
    held whole in memory. The result is capped at max_rows (default 1000) to bound
    context size: check the returned truncated field to see if more data exists.

    Distinct from get_postponed_submission_metadata: this endpoint returns metadata
    for delivered (non-postponed) submissions.

    Args:
        form_id: The form's numeric ID.
        submission_ids_greater_than: Only include submissions with IDs above this value.
        optimize_for_large_data: Request optimization for large datasets.
        max_rows: Maximum number of rows to return. Defaults to the server's
            configured limit (1000). When the cap is reached, truncated is set to
            true and reason is "rowCap".

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

    Postponed submissions are those that have been started but not delivered. This
    endpoint returns the same metadata structure as get_submission_metadata, but
    only for postponed submissions. The result is streamed as NDJSON and capped at
    max_rows (default 1000).

    Distinct from get_submission_metadata: this endpoint returns metadata only for
    postponed (non-delivered) submissions, while that one returns delivered submissions.

    Args:
        form_id: The form's numeric ID.
        submission_ids_greater_than: Only include submissions with IDs above this value.
        max_rows: Maximum number of rows to return. Defaults to the server's
            configured limit (1000). When the cap is reached, truncated is set to
            true and reason is "rowCap".

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
