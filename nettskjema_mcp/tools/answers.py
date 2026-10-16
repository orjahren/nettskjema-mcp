# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Answer export tools: stream form answers as newline-delimited JSON."""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool

GET_FORM_ANSWERS = Route("GET", "/form/{formId}/answers")


@tool(annotations={"readOnlyHint": True})
@endpoint(GET_FORM_ANSWERS)
async def get_form_answers(
    form_id: int,
    element_ids: list[int] | None = None,
    submission_ids_greater_than: int | None = None,
    optimize_for_large_data: bool | None = None,
    max_rows: int | None = None,
) -> str:
    """
    Stream all answers for a form, as newline-delimited JSON.

    This exports every answer on the form, one JSON object per line (NDJSON), so a
    large form's answers are never held whole in memory. Filter by element_ids to
    export only specific questions. The result is capped at max_rows (default 1000)
    to bound context size: check the returned truncated field to see if more data
    exists. When truncated is true, the reason field distinguishes a hit row cap
    ("rowCap") from a connection that closed mid-line ("incompleteFinalLine").

    Args:
        form_id: The form's numeric ID.
        element_ids: List of element IDs to filter by. When provided, only answers
            for these elements are returned. Sent as repeated query parameters
            (element-ids=1&element-ids=2&...).
        submission_ids_greater_than: Only include answers from submissions with
            IDs above this value.
        optimize_for_large_data: Request optimization for large datasets.
        max_rows: Maximum number of rows to return. Defaults to this MCP server's
            configured limit (1000). When the cap is reached, truncated is set to
            true and reason is "rowCap". The caller may raise this limit arbitrarily
            by passing a larger value.

    Returns:
        A JSON object with rows (an array of AnswerDTO objects), rowCount (the
        number returned), truncated (boolean), and reason (string or null). Each
        row includes answerId, submissionId, formId, elementId, subElementId,
        elementType, textAnswer, answerOptionIds, externalElementId,
        externalAnswerOptionIds, correct, createdDate, modifiedDate, attachment
        (an AnswerAttachmentDTO object with answerAttachmentId, filename, mediaType,
        and size), answerAttachmentId, filename, mediaType, and size.
    """
    return dump(
        await get_client().ndjson(
            GET_FORM_ANSWERS,
            path={"formId": form_id},
            query={
                "element-ids": element_ids,
                "submission-ids-greater-than": submission_ids_greater_than,
                "optimize-for-large-data": optimize_for_large_data,
            },
            max_rows=max_rows,
        )
    )
