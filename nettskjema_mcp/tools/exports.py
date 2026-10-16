"""Export tools: CSV, Excel, SPSS syntax, and codebook upload.

CSV and SPSS exports return plain text verbatim, with no size limit: a large
form's export goes straight into the model's context. Excel exports write to
disk instead, returning the file path, byte count and media type the same way
``get_submission_pdf`` does.

The codebook upload replaces the form's entire element-to-external-id mapping,
so it carries ``destructiveHint`` even though the spec declares it as a PUT with
a clean 200 — PUT is replace semantics on this API.
"""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool
from nettskjema_mcp.validation import validate_body

CSV_REPORT = Route("GET", "/form/{formId}/csv-report")
EXCEL_REPORT = Route("GET", "/form/{formId}/excel-report")
SPSS_SYNTAX = Route("GET", "/form/{formId}/spss-syntax")
CODEBOOK = Route("PUT", "/form/{formId}/codebook")


@tool(annotations={"readOnlyHint": True})
@endpoint(CSV_REPORT)
async def export_form_csv(form_id: int, optimize_for_large_data: bool | None = None) -> str:
    """
    Export a form's submission data as CSV text.

    The CSV is returned as plain text, verbatim from the API, with semicolon (;)
    as the delimiter. Large exports go straight into the model's context without
    size limit or truncation: a form with thousands of responses produces a
    correspondingly large CSV. Use export_form_excel with an output_path if you
    need a large export written to disk instead.

    Args:
        form_id: The form's numeric ID.
        optimize_for_large_data: Request optimization for large datasets.

    Returns:
        The CSV text as a plain string. The response carries no JSON wrapper and
        is not truncated or summarized. A large export is returned whole.
    """
    return await get_client().text(
        CSV_REPORT,
        path={"formId": form_id},
        query={"optimize-for-large-data": optimize_for_large_data},
    )


@tool(annotations={"readOnlyHint": True})
@endpoint(EXCEL_REPORT)
async def export_form_excel(
    form_id: int, output_path: str | None = None, optimize_for_large_data: bool | None = None
) -> str:
    """
    Export a form's submission data as an Excel workbook, written to disk.

    The workbook is streamed to a file and never inlined: a multi-megabyte
    spreadsheet as base64 is useless to a model. The returned path is absolute
    and tilde-expanded. An existing file at the output path is silently
    overwritten, and its mode is preserved. A new file (whether from output_path
    or a temp file) is created with mode 0600 (readable only by the current user).

    When output_path is omitted, a temporary file is created in the system temp
    directory with an appropriate suffix. The temporary file persists after this
    call returns and is left on disk for the caller to use or delete.

    Args:
        form_id: The form's numeric ID.
        output_path: Destination file path. When omitted, a temporary file is
            created in the system temp directory. The path may contain ~ for the
            home directory and may be relative (it will be resolved to an absolute
            path).
        optimize_for_large_data: Request optimization for large datasets.

    Returns:
        A JSON object with path (the absolute path to the written file), bytes
        (the number of bytes written), and mediaType (the content type from the
        response, typically the Excel MIME type).
    """
    return dump(
        await get_client().binary(
            EXCEL_REPORT,
            path={"formId": form_id},
            query={"optimize-for-large-data": optimize_for_large_data},
            output_path=output_path,
        )
    )


@tool(annotations={"readOnlyHint": True})
@endpoint(SPSS_SYNTAX)
async def get_spss_syntax(form_id: int) -> str:
    """
    Get SPSS syntax for a form's submission data.

    The syntax is returned as plain text, verbatim from the API. This is SPSS
    command syntax for loading and analyzing the form's data, not the data itself.
    The text goes straight into the model's context with no size limit or truncation.

    Args:
        form_id: The form's numeric ID.

    Returns:
        The SPSS syntax as a plain string. The response carries no JSON wrapper
        and is not truncated or summarized.
    """
    return await get_client().text(SPSS_SYNTAX, path={"formId": form_id})


@tool(annotations={"destructiveHint": True})
@endpoint(CODEBOOK)
async def upload_codebook(
    form_id: int,
    element_ids_and_external_element_ids_map: dict[str, str],
    sub_element_ids_and_external_element_ids_map: dict[str, str],
    answer_option_ids_and_external_answer_option_ids_map: dict[str, str],
) -> str:
    """
    Upload a codebook mapping form elements to external identifiers.

    This replaces the form's entire codebook: any element, sub-element or answer
    option not included in one of the three maps loses its external id mapping.
    The operation is a PUT with replace semantics, so it carries destructiveHint
    even though the spec declares a clean 200 response.

    Each map is validated against the CodebookDTO schema before the request is
    sent. All three maps are required by the schema: to clear a map, pass an
    empty dict.

    Args:
        form_id: The form's numeric ID.
        element_ids_and_external_element_ids_map: A mapping of element IDs (as
            strings) to their external IDs.
        sub_element_ids_and_external_element_ids_map: A mapping of sub-element
            IDs (as strings) to their external IDs.
        answer_option_ids_and_external_answer_option_ids_map: A mapping of
            answer option IDs (as strings) to their external IDs.

    Returns:
        A success marker as JSON: {"status": "success", "httpStatus": <code>}.
        The spec declares no response body for this operation.
    """
    body = {
        "elementIdsAndExternalElementIdsMap": element_ids_and_external_element_ids_map,
        "subElementIdsAndExternalElementIdsMap": sub_element_ids_and_external_element_ids_map,
        "answerOptionIdsAndExternalAnswerOptionIdsMap": answer_option_ids_and_external_answer_option_ids_map,
    }
    validate_body("CodebookDTO", body)
    return dump(await get_client().json(CODEBOOK, path={"formId": form_id}, body=body))
