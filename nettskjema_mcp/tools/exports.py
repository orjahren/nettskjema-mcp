"""Export tools: CSV, Excel, SPSS syntax, and codebook upload.

CSV and SPSS exports return text in an envelope with a size signal and truncation
flag. The result is capped at max_chars to bound context size: check the returned
truncated field to see if the full text was cut. Excel exports write to disk
instead, returning the file path, byte count and media type the same way
``get_submission_pdf`` does.

The codebook upload carries ``destructiveHint`` because its semantics are unknown:
the spec documents neither whether the upload replaces the stored mapping or
merges into it, nor what happens to an entry you omit.
"""

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool
from nettskjema_mcp.validation import validate_body

CSV_REPORT = Route("GET", "/form/{formId}/csv-report")
EXCEL_REPORT = Route("GET", "/form/{formId}/excel-report")
SPSS_SYNTAX = Route("GET", "/form/{formId}/spss-syntax")
CODEBOOK = Route("PUT", "/form/{formId}/codebook")


@tool()
@endpoint(CSV_REPORT)
async def export_form_csv(
    form_id: int,
    output_path: str | None = None,
    optimize_for_large_data: bool | None = None,
    max_chars: int | None = None,
) -> str:
    """
    Export a form's submission data as CSV.

    The spec's summary describes the response as a CSV text file with semicolon (;)
    as the delimiter. When output_path is provided, the file is written to disk
    (mode 0600 for a new file) and the result reports the path, byte count and
    media type. When output_path is omitted, the text is returned as JSON with a
    size signal and truncation flag. The result is capped at max_chars (default
    1,000,000) to bound context size: check the truncated field to see if the full
    export was cut.

    Args:
        form_id: The form's numeric ID.
        output_path: Destination file path. When provided, the CSV is written to
            disk and path/bytes/mediaType are returned instead of the text. The
            path may contain ~ for the home directory and may be relative (it will
            be resolved to an absolute path). An existing file is overwritten and
            its mode is preserved; a new file is created with mode 0600.
        optimize_for_large_data: Request optimization for large datasets.
        max_chars: Maximum characters to return when output_path is omitted.
            Defaults to this MCP server's configured limit (1,000,000). When the
            cap is reached, the text is cut at the last complete newline before the
            limit and truncated is set to true. The caller may raise this limit
            arbitrarily by passing a larger value. Ignored when output_path is
            provided.

    Returns:
        When output_path is provided: a JSON object with path (the absolute path
        to the written file), bytes (the number of bytes written), and mediaType
        (the content type from the response).
        When output_path is omitted: a JSON object with text (the CSV, possibly
        truncated at the last newline), truncated (boolean), reason (string or
        null, "charCap" when the cap was hit), and totalChars (the full size
        before truncation).
    """
    if output_path is not None:
        # Write to disk
        return dump(
            await get_client().binary(
                CSV_REPORT,
                path={"formId": form_id},
                query={"optimize-for-large-data": optimize_for_large_data},
                output_path=output_path,
            )
        )

    # Return text in envelope
    result = await get_client().text(
        CSV_REPORT,
        path={"formId": form_id},
        query={"optimize-for-large-data": optimize_for_large_data},
        max_chars=max_chars,
    )
    return dump(result)


@tool()
@endpoint(EXCEL_REPORT)
async def export_form_excel(
    form_id: int, output_path: str | None = None, optimize_for_large_data: bool | None = None
) -> str:
    """
    Export a form's submission data to a file, written to disk.

    The spec documents this route's response as an Excel file. The file is
    streamed to disk and never inlined: a multi-megabyte spreadsheet as base64 is
    useless to a model. The returned path is absolute and tilde-expanded. An
    existing file at the output path is silently overwritten, and its mode is
    preserved. A new file (whether from output_path or a temp file) is created
    with mode 0600 (readable only by the current user).

    When output_path is omitted, a temporary file is created in the system temp
    directory with a suffix derived from the response's media type. The temporary
    file persists after this call returns and is left on disk for the caller to
    use or delete.

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
        response).
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
async def get_spss_syntax(form_id: int, max_chars: int | None = None) -> str:
    """
    Get SPSS syntax for a form's submission data.

    The spec documents this route's response as an SPSS syntax file. The syntax
    is returned as JSON with a size signal and truncation flag. The result is
    capped at max_chars (default 1,000,000) to bound context size: check the
    truncated field to see if the full syntax was cut.

    Args:
        form_id: The form's numeric ID.
        max_chars: Maximum characters to return. Defaults to this MCP server's
            configured limit (1,000,000). When the cap is reached, the text is cut
            at the last complete newline before the limit and truncated is set to
            true. The caller may raise this limit arbitrarily by passing a larger
            value.

    Returns:
        A JSON object with text (the SPSS syntax, possibly truncated at the last
        newline), truncated (boolean), reason (string or null, "charCap" when the
        cap was hit), and totalChars (the full size before truncation).
    """
    result = await get_client().text(SPSS_SYNTAX, path={"formId": form_id}, max_chars=max_chars)
    return dump(result)


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

    The spec does not document whether omitted entries are preserved or deleted.
    Send the complete mapping you want the form to have: include every element,
    sub-element and answer option whose external id you want to keep or set.
    Omitting an entry has undefined effect and may delete that mapping.

    Each map is validated against the CodebookDTO schema before the request is
    sent. All three maps are required by the schema: send an empty dict for any
    map you do not need to populate.

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
