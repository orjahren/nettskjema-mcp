"""Tests for export tools."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from nettskjema_mcp.tools.exports import (
    export_form_csv,
    export_form_excel,
    get_spss_syntax,
    upload_codebook,
)
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

# CSV and SPSS are text exports
CSV_EXPORT = "Column1;Column2;Column3\nValue1;Value2;Value3\nValue4;Value5;Value6"
SPSS_SYNTAX = "DATA LIST FILE='data.csv' / id 1-5 name 6-20.\nEXECUTE."


async def test_export_form_csv_returns_envelope(respx_mock: respx.MockRouter) -> None:
    """export_form_csv() GETs /form/{formId}/csv-report and returns envelope."""
    url = f"{TEST_BASE_URL}/form/1/csv-report"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            text=CSV_EXPORT,
            headers={"content-type": "text/csv"},
        )
    )

    result = await export_form_csv(1)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["text"] == CSV_EXPORT
    assert parsed["truncated"] is False
    assert parsed["reason"] is None
    assert parsed["totalChars"] == len(CSV_EXPORT)
    # Verify no query params when optimize_for_large_data is None
    assert route.calls.last.request.url.query == b""


async def test_export_form_csv_passes_optimize_for_large_data(respx_mock: respx.MockRouter) -> None:
    """export_form_csv() passes optimize-for-large-data query param when given."""
    url = f"{TEST_BASE_URL}/form/1/csv-report?optimize-for-large-data=true"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, text=CSV_EXPORT))

    result = await export_form_csv(1, optimize_for_large_data=True)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["text"] == CSV_EXPORT


async def test_export_form_csv_truncates_at_max_chars(respx_mock: respx.MockRouter) -> None:
    """export_form_csv() truncates at max_chars, cutting at last newline."""
    url = f"{TEST_BASE_URL}/form/1/csv-report"
    large_csv = "Header\n" + ("Row1;Row2;Row3\n" * 1000)
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, text=large_csv))

    result = await export_form_csv(1, max_chars=100)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["truncated"] is True
    assert parsed["reason"] == "charCap"
    assert parsed["totalChars"] == len(large_csv)
    assert len(parsed["text"]) <= 100
    # Verify it cut at a newline
    assert parsed["text"].endswith("\n")


async def test_export_form_csv_writes_to_file_when_output_path_given(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """export_form_csv() with output_path writes to disk instead of returning text."""
    url = f"{TEST_BASE_URL}/form/1/csv-report"
    csv_bytes = CSV_EXPORT.encode("utf-8")
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=csv_bytes,
            headers={"content-type": "text/csv"},
        )
    )

    output_file = tmp_path / "export.csv"
    result = await export_form_csv(1, output_path=str(output_file))

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["path"] == str(output_file.resolve())
    assert parsed["bytes"] == len(csv_bytes)
    assert output_file.read_bytes() == csv_bytes


async def test_export_form_csv_to_file_sets_mode_0600(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """export_form_csv() with output_path sets mode 0600 on a new file."""
    url = f"{TEST_BASE_URL}/form/1/csv-report"
    csv_bytes = CSV_EXPORT.encode("utf-8")
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=csv_bytes))

    output_file = tmp_path / "export.csv"
    await export_form_csv(1, output_path=str(output_file))

    # Check file mode - mask with 0o777 to ignore file type bits
    assert (output_file.stat().st_mode & 0o777) == 0o600


async def test_export_form_csv_to_file_expands_tilde(
    respx_mock: respx.MockRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """export_form_csv() with output_path expands ~ to home directory."""
    url = f"{TEST_BASE_URL}/form/1/csv-report"
    csv_bytes = CSV_EXPORT.encode("utf-8")
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=csv_bytes))

    # Point HOME at tmp_path for this test
    monkeypatch.setenv("HOME", str(tmp_path))

    result = await export_form_csv(1, output_path="~/test_export.csv")

    parsed = json.loads(result)
    expected_path = tmp_path / "test_export.csv"
    assert parsed["path"] == str(expected_path)
    assert expected_path.exists()
    # Clean up
    expected_path.unlink()


async def test_export_form_excel_writes_file_and_returns_path(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """export_form_excel() writes Excel file to disk and returns path info."""
    url = f"{TEST_BASE_URL}/form/1/excel-report"
    excel_content = b"PK\x03\x04fake excel content"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=excel_content,
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
        )
    )

    output_file = tmp_path / "export.xlsx"
    result = await export_form_excel(1, output_path=str(output_file))

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["path"] == str(output_file.resolve())
    assert parsed["bytes"] == len(excel_content)
    assert (
        parsed["mediaType"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert output_file.read_bytes() == excel_content


async def test_export_form_excel_without_output_path_creates_temp_file(
    respx_mock: respx.MockRouter,
) -> None:
    """export_form_excel() without output_path creates a temp file."""
    url = f"{TEST_BASE_URL}/form/1/excel-report"
    excel_content = b"PK\x03\x04fake excel content"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=excel_content,
            headers={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
        )
    )

    result = await export_form_excel(1)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert "path" in parsed
    assert parsed["bytes"] == len(excel_content)
    # Verify the temp file was created
    temp_file = Path(parsed["path"])
    assert temp_file.exists()
    assert temp_file.read_bytes() == excel_content
    # Verify temp file is mode 0600
    assert (temp_file.stat().st_mode & 0o777) == 0o600
    # Clean up
    temp_file.unlink()


async def test_export_form_excel_passes_optimize_for_large_data(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """export_form_excel() passes optimize-for-large-data query param when given."""
    url = f"{TEST_BASE_URL}/form/1/excel-report?optimize-for-large-data=true"
    excel_content = b"PK\x03\x04fake excel content"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, content=excel_content))

    output_file = tmp_path / "export.xlsx"
    await export_form_excel(1, output_path=str(output_file), optimize_for_large_data=True)

    assert route.call_count == 1


async def test_export_form_excel_sets_mode_0600_on_new_file(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """export_form_excel() sets mode 0600 on a newly created file."""
    url = f"{TEST_BASE_URL}/form/1/excel-report"
    excel_content = b"PK\x03\x04fake excel content"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=excel_content))

    output_file = tmp_path / "export.xlsx"
    await export_form_excel(1, output_path=str(output_file))

    # Check file mode - mask with 0o777 to ignore file type bits
    assert (output_file.stat().st_mode & 0o777) == 0o600


async def test_export_form_excel_preserves_existing_file_mode(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """export_form_excel() preserves the mode of an existing file."""
    url = f"{TEST_BASE_URL}/form/1/excel-report"
    excel_content = b"PK\x03\x04fake excel content"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=excel_content))

    # Create existing file with mode 0644
    output_file = tmp_path / "existing.xlsx"
    output_file.write_bytes(b"old content")
    output_file.chmod(0o644)

    await export_form_excel(1, output_path=str(output_file))

    # Mode should be preserved
    assert (output_file.stat().st_mode & 0o777) == 0o644
    # Content should be replaced
    assert output_file.read_bytes() == excel_content


async def test_export_form_excel_expands_tilde(
    respx_mock: respx.MockRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """export_form_excel() expands ~ to home directory."""
    url = f"{TEST_BASE_URL}/form/1/excel-report"
    excel_content = b"PK\x03\x04fake excel content"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=excel_content))

    # Point HOME at tmp_path for this test
    monkeypatch.setenv("HOME", str(tmp_path))

    result = await export_form_excel(1, output_path="~/test_export.xlsx")

    parsed = json.loads(result)
    expected_path = tmp_path / "test_export.xlsx"
    assert parsed["path"] == str(expected_path)
    assert expected_path.exists()
    # Clean up
    expected_path.unlink()


async def test_get_spss_syntax_returns_envelope(respx_mock: respx.MockRouter) -> None:
    """get_spss_syntax() GETs /form/{formId}/spss-syntax and returns envelope."""
    url = f"{TEST_BASE_URL}/form/1/spss-syntax"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            text=SPSS_SYNTAX,
            headers={"content-type": "text/plain"},
        )
    )

    result = await get_spss_syntax(1)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["text"] == SPSS_SYNTAX
    assert parsed["truncated"] is False
    assert parsed["reason"] is None
    assert parsed["totalChars"] == len(SPSS_SYNTAX)
    # Verify path but no query params
    assert route.calls.last.request.url.path == "/api/v3/form/1/spss-syntax"
    assert route.calls.last.request.url.query == b""


async def test_get_spss_syntax_truncates_at_max_chars(respx_mock: respx.MockRouter) -> None:
    """get_spss_syntax() truncates at max_chars, cutting at last newline."""
    url = f"{TEST_BASE_URL}/form/1/spss-syntax"
    large_syntax = "DATA LIST\n" + ("LINE\n" * 1000)
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, text=large_syntax))

    result = await get_spss_syntax(1, max_chars=50)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["truncated"] is True
    assert parsed["reason"] == "charCap"
    assert parsed["totalChars"] == len(large_syntax)
    assert len(parsed["text"]) <= 50
    # Verify it cut at a newline
    assert parsed["text"].endswith("\n")


async def test_upload_codebook_sends_all_three_maps(respx_mock: respx.MockRouter) -> None:
    """upload_codebook() PUTs all three required maps in the CodebookDTO body."""
    url = f"{TEST_BASE_URL}/form/1/codebook"
    route = respx_mock.put(url).mock(return_value=httpx.Response(200))

    element_map = {"1": "ext_element_1", "2": "ext_element_2"}
    sub_element_map = {"10": "ext_sub_10", "11": "ext_sub_11"}
    answer_option_map = {"100": "ext_option_100", "101": "ext_option_101"}

    result = await upload_codebook(
        form_id=1,
        element_ids_and_external_element_ids_map=element_map,
        sub_element_ids_and_external_element_ids_map=sub_element_map,
        answer_option_ids_and_external_answer_option_ids_map=answer_option_map,
    )

    assert route.call_count == 1
    # Verify the body shape
    request_body = json.loads(route.calls.last.request.content)
    assert request_body == {
        "elementIdsAndExternalElementIdsMap": element_map,
        "subElementIdsAndExternalElementIdsMap": sub_element_map,
        "answerOptionIdsAndExternalAnswerOptionIdsMap": answer_option_map,
    }
    # Verify success marker returned
    parsed = json.loads(result)
    assert parsed == {"status": "success", "httpStatus": 200}
