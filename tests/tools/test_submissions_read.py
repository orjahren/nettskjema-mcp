"""Tests for submission read tools."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from nettskjema_mcp.tools.submissions import (
    get_postponed_submission_metadata,
    get_submission,
    get_submission_metadata,
    get_submission_pdf,
    list_my_submissions,
)
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

SUBMISSION = {
    "answers": [{"answerId": 1, "textAnswer": "Test"}],
    "submissionMetadata": {"submissionId": 123, "formId": 1},
}
MY_SUBMISSIONS = [
    {
        "submissionId": 1,
        "form": {"title": "Test Form"},
        "createdDate": "2024-01-01T00:00:00Z",
        "modifiedDate": "2024-01-01T00:00:00Z",
        "delivered": True,
    }
]


async def test_get_submission(respx_mock: respx.MockRouter) -> None:
    """get_submission() GETs /form/submission/{submissionId} and returns the dumped body."""
    url = f"{TEST_BASE_URL}/form/submission/123"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=SUBMISSION))

    result = await get_submission(123)

    assert route.call_count == 1
    assert json.loads(result) == SUBMISSION
    assert route.calls.last.request.url == url


async def test_list_my_submissions(respx_mock: respx.MockRouter) -> None:
    """list_my_submissions() GETs /form/submission/me and returns the dumped body."""
    url = f"{TEST_BASE_URL}/form/submission/me"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=MY_SUBMISSIONS))

    result = await list_my_submissions()

    assert route.call_count == 1
    assert json.loads(result) == MY_SUBMISSIONS
    assert route.calls.last.request.url == url


async def test_get_submission_pdf_writes_a_file_and_returns_its_path(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """get_submission_pdf() writes a PDF to the output path and returns the result."""
    url = f"{TEST_BASE_URL}/form/submission/123/pdf"
    pdf_content = b"%PDF-1.4\ntest pdf content"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=pdf_content,
            headers={"content-type": "application/pdf"},
        )
    )

    output_file = tmp_path / "submission.pdf"
    result = await get_submission_pdf(123, output_path=str(output_file))

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["path"] == str(output_file.resolve())
    assert parsed["bytes"] == len(pdf_content)
    assert parsed["mediaType"] == "application/pdf"
    assert output_file.read_bytes() == pdf_content


async def test_get_submission_pdf_without_output_path_creates_temp_file(
    respx_mock: respx.MockRouter,
) -> None:
    """get_submission_pdf() without output_path creates a temp file and returns its path."""
    url = f"{TEST_BASE_URL}/form/submission/123/pdf"
    pdf_content = b"%PDF-1.4\ntest pdf content"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=pdf_content,
            headers={"content-type": "application/pdf"},
        )
    )

    result = await get_submission_pdf(123)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert "path" in parsed
    assert parsed["bytes"] == len(pdf_content)
    assert parsed["mediaType"] == "application/pdf"
    # Verify the file exists and has the correct content
    path = Path(parsed["path"])
    assert path.exists()
    assert path.read_bytes() == pdf_content
    # Clean up
    path.unlink()


async def test_submission_metadata_is_parsed_as_ndjson(respx_mock: respx.MockRouter) -> None:
    """get_submission_metadata() streams NDJSON and parses it into rows."""
    url = f"{TEST_BASE_URL}/form/123/submission-metadata"
    ndjson_content = (
        '{"submissionId": 1, "formId": 123, "createdDate": "2024-01-01T00:00:00Z"}\n'
        '{"submissionId": 2, "formId": 123, "createdDate": "2024-01-02T00:00:00Z"}\n'
    )
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    result = await get_submission_metadata(123)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["rowCount"] == 2
    assert parsed["truncated"] is False
    assert len(parsed["rows"]) == 2
    assert parsed["rows"][0]["submissionId"] == 1
    assert parsed["rows"][1]["submissionId"] == 2


async def test_submission_metadata_reports_truncation(respx_mock: respx.MockRouter) -> None:
    """get_submission_metadata() with max_rows caps the rows and marks truncated."""
    url = f"{TEST_BASE_URL}/form/123/submission-metadata"
    ndjson_content = (
        "\n".join([f'{{"submissionId": {i}, "formId": 123}}' for i in range(1, 6)]) + "\n"
    )
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    result = await get_submission_metadata(123, max_rows=2)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["rowCount"] == 2
    assert parsed["truncated"] is True
    assert parsed["reason"] == "rowCap"


async def test_submission_metadata_with_query_parameters(respx_mock: respx.MockRouter) -> None:
    """get_submission_metadata() passes query parameters correctly."""
    url = (
        f"{TEST_BASE_URL}/form/123/submission-metadata"
        "?submission-ids-greater-than=100&optimize-for-large-data=true"
    )
    ndjson_content = '{"submissionId": 101, "formId": 123}\n'
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    await get_submission_metadata(
        123, submission_ids_greater_than=100, optimize_for_large_data=True
    )

    assert route.call_count == 1
    assert str(route.calls.last.request.url) == url


async def test_postponed_metadata_is_parsed_as_ndjson(respx_mock: respx.MockRouter) -> None:
    """get_postponed_submission_metadata() streams NDJSON and parses it into rows."""
    url = f"{TEST_BASE_URL}/form/123/submission-metadata-postponed"
    ndjson_content = '{"submissionId": 1, "formId": 123, "createdDate": "2024-01-01T00:00:00Z"}\n'
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    result = await get_postponed_submission_metadata(123)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["rowCount"] == 1
    assert parsed["truncated"] is False
    assert len(parsed["rows"]) == 1
    assert parsed["rows"][0]["submissionId"] == 1


async def test_postponed_metadata_with_query_parameters(respx_mock: respx.MockRouter) -> None:
    """get_postponed_submission_metadata() passes query parameters correctly."""
    url = f"{TEST_BASE_URL}/form/123/submission-metadata-postponed?submission-ids-greater-than=50"
    ndjson_content = '{"submissionId": 51, "formId": 123}\n'
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    await get_postponed_submission_metadata(123, submission_ids_greater_than=50)

    assert route.call_count == 1
    assert str(route.calls.last.request.url) == url


async def test_submission_metadata_exactly_max_rows_not_truncated(
    respx_mock: respx.MockRouter,
) -> None:
    """get_submission_metadata() with exactly max_rows rows reports truncated=false."""
    url = f"{TEST_BASE_URL}/form/123/submission-metadata"
    # Exactly 3 rows, max_rows=3
    ndjson_content = (
        "\n".join([f'{{"submissionId": {i}, "formId": 123}}' for i in range(1, 4)]) + "\n"
    )
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    result = await get_submission_metadata(123, max_rows=3)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["rowCount"] == 3
    assert parsed["truncated"] is False
    assert parsed["reason"] is None


async def test_get_submission_pdf_relative_path_resolved_to_absolute(
    respx_mock: respx.MockRouter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_submission_pdf() with relative output_path returns an absolute path."""
    url = f"{TEST_BASE_URL}/form/submission/123/pdf"
    pdf_content = b"%PDF-1.4\ntest pdf content"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=pdf_content,
            headers={"content-type": "application/pdf"},
        )
    )

    # Change to tmp_path so relative paths resolve there
    monkeypatch.chdir(tmp_path)
    result = await get_submission_pdf(123, output_path="relative.pdf")

    assert route.call_count == 1
    parsed = json.loads(result)
    returned_path = Path(parsed["path"])
    assert returned_path.is_absolute()
    assert returned_path.name == "relative.pdf"
    assert returned_path.exists()
    assert returned_path.read_bytes() == pdf_content
