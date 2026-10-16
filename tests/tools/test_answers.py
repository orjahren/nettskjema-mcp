"""Tests for answer export tools."""

import json

import httpx
import pytest
import respx

from nettskjema_mcp.tools.answers import get_form_answers
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]


async def test_get_form_answers_uses_the_element_ids_parameter(
    respx_mock: respx.MockRouter,
) -> None:
    """get_form_answers() sends element-ids as repeated query parameters."""
    url = f"{TEST_BASE_URL}/form/123/answers?element-ids=1&element-ids=2&element-ids=3"
    ndjson_content = '{"answerId": 1, "elementId": 1, "textAnswer": "Test"}\n'
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    await get_form_answers(123, element_ids=[1, 2, 3])

    assert route.call_count == 1
    # Verify the URL has the correct query parameters
    request_url = str(route.calls.last.request.url)
    assert "element-ids=1" in request_url
    assert "element-ids=2" in request_url
    assert "element-ids=3" in request_url


async def test_get_form_answers_reports_truncation(respx_mock: respx.MockRouter) -> None:
    """get_form_answers() with max_rows caps the rows and marks truncated."""
    url = f"{TEST_BASE_URL}/form/123/answers"
    ndjson_content = (
        "\n".join([f'{{"answerId": {i}, "elementId": 1, "formId": 123}}' for i in range(1, 6)])
        + "\n"
    )
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    result = await get_form_answers(123, max_rows=2)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["rowCount"] == 2
    assert parsed["truncated"] is True
    assert parsed["reason"] == "rowCap"
    assert '"truncated": true' in result


async def test_get_form_answers_parses_ndjson(respx_mock: respx.MockRouter) -> None:
    """get_form_answers() streams NDJSON and parses it into rows."""
    url = f"{TEST_BASE_URL}/form/123/answers"
    ndjson_content = (
        '{"answerId": 1, "elementId": 1, "textAnswer": "Answer 1"}\n'
        '{"answerId": 2, "elementId": 2, "textAnswer": "Answer 2"}\n'
        '{"answerId": 3, "elementId": 3, "answerOptionIds": [1, 2]}\n'
    )
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    result = await get_form_answers(123)

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["rowCount"] == 3
    assert parsed["truncated"] is False
    assert len(parsed["rows"]) == 3
    assert parsed["rows"][0]["answerId"] == 1
    assert parsed["rows"][1]["textAnswer"] == "Answer 2"
    assert parsed["rows"][2]["answerOptionIds"] == [1, 2]


async def test_get_form_answers_with_all_query_parameters(respx_mock: respx.MockRouter) -> None:
    """get_form_answers() passes all query parameters correctly."""
    url = (
        f"{TEST_BASE_URL}/form/123/answers"
        "?element-ids=5&element-ids=10"
        "&submission-ids-greater-than=100"
        "&optimize-for-large-data=true"
    )
    ndjson_content = '{"answerId": 1, "elementId": 5, "submissionId": 101}\n'
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    await get_form_answers(
        123,
        element_ids=[5, 10],
        submission_ids_greater_than=100,
        optimize_for_large_data=True,
    )

    assert route.call_count == 1
    request_url = str(route.calls.last.request.url)
    assert "element-ids=5" in request_url
    assert "element-ids=10" in request_url
    assert "submission-ids-greater-than=100" in request_url
    assert "optimize-for-large-data=true" in request_url


async def test_get_form_answers_without_optional_params(respx_mock: respx.MockRouter) -> None:
    """get_form_answers() with no optional parameters omits query parameters."""
    url = f"{TEST_BASE_URL}/form/123/answers"
    ndjson_content = '{"answerId": 1, "elementId": 1}\n'
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ndjson_content,
            headers={"content-type": "application/x-ndjson"},
        )
    )

    await get_form_answers(123)

    assert route.call_count == 1
    assert route.calls.last.request.url == url
