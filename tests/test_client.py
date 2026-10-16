"""Tests for the pooled Nettskjema HTTP client."""

import os
import stat
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import respx

from nettskjema_mcp import client as client_module
from nettskjema_mcp.client import (
    NO_CONTENT_RESULT,
    NettskjemaClient,
    aclose_client,
    dump,
    get_client,
)
from nettskjema_mcp.config import Settings
from nettskjema_mcp.errors import (
    BadRequestError,
    NotFoundError,
    PartialSuccessError,
    UpstreamError,
)
from nettskjema_mcp.routes import Route

BASE_URL = "https://nettskjema.invalid/api/v3"
AUTH_URL = "https://authorization.nettskjema.invalid/oauth2/token"

FORM_INFO = Route("GET", "/form/{formId}/info")
FORM_SETTINGS = Route("PATCH", "/form/{formId}/settings")
DELETE_FORMS = Route("DELETE", "/form")
ANSWERS = Route("GET", "/form/{formId}/answers")
EXCEL_REPORT = Route("GET", "/form/{formId}/excel-report")
SPSS_SYNTAX = Route("GET", "/form/{formId}/spss-syntax")

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Routes are asserted on explicitly; several tests deliberately expect zero calls.
pytestmark = pytest.mark.respx(assert_all_called=False)


@pytest.fixture
def settings() -> Settings:
    """Settings pointing at the unroutable test hosts."""
    return Settings(
        base_url=BASE_URL,
        auth_url=AUTH_URL,
        client_id="test-client",
        client_secret="test-secret",
        timeout=5.0,
        log_level="INFO",
        max_answer_rows=1000,
        max_text_chars=1000000,
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[NettskjemaClient]:
    """A client bound to the test settings, closed after the test."""
    instance = NettskjemaClient(settings)
    try:
        yield instance
    finally:
        await instance.aclose()


@pytest.fixture(autouse=True)
def token_route(respx_mock: respx.MockRouter) -> respx.Route:
    """Mock the OAuth2 token endpoint for every test in this module."""
    return respx_mock.post(AUTH_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "test-token", "expires_in": 86400})
    )


class _FailingStream(httpx.AsyncByteStream):
    """A stream that delivers one chunk and then drops, like a severed connection."""

    def __init__(self, first_chunk: bytes) -> None:
        self._first_chunk = first_chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._first_chunk
        raise httpx.ReadError("the connection was dropped mid-body")

    async def aclose(self) -> None:
        """Nothing to release."""


async def test_path_and_query_parameters_are_applied(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """Path placeholders are substituted and None query values are dropped."""
    route = respx_mock.get(f"{BASE_URL}/form/42/info").mock(
        return_value=httpx.Response(200, json={"formId": 42})
    )

    result = await client.json(
        FORM_INFO,
        path={"formId": 42},
        query={"includeElements": True, "language": "nb", "omitted": None},
    )

    assert result == {"formId": 42}
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.url.path == "/api/v3/form/42/info"
    assert request.url.params["includeElements"] == "true"
    assert request.url.params["language"] == "nb"
    assert "omitted" not in request.url.params


async def test_bearer_token_is_sent(
    client: NettskjemaClient, respx_mock: respx.MockRouter, token_route: respx.Route
) -> None:
    """Every request carries the bearer token from the token provider."""
    route = respx_mock.get(f"{BASE_URL}/form/1/info").mock(
        return_value=httpx.Response(200, json={})
    )

    await client.json(FORM_INFO, path={"formId": 1})

    assert token_route.call_count == 1
    assert route.calls[0].request.headers["authorization"] == "Bearer test-token"


async def test_bare_array_body_is_sent_unwrapped(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """A list body serialises as a bare JSON array, not wrapped in an object."""
    route = respx_mock.delete(f"{BASE_URL}/form").mock(return_value=httpx.Response(204))

    await client.json(DELETE_FORMS, body=[1, 2, 3])

    request = route.calls[0].request
    assert request.content == b"[1,2,3]"
    assert request.headers["content-type"] == "application/json"


async def test_204_returns_a_success_marker(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """An empty 204 response yields a stable success marker, not None."""
    respx_mock.delete(f"{BASE_URL}/form").mock(return_value=httpx.Response(204))

    result = await client.json(DELETE_FORMS, body=[1])

    assert result == {"status": "success", "httpStatus": 204}
    assert result == NO_CONTENT_RESULT


async def test_empty_body_marker_reports_the_actual_status(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """A bodiless 201 must not claim to be a 204."""
    respx_mock.post(f"{BASE_URL}/form").mock(return_value=httpx.Response(201))

    result = await client.json(Route("POST", "/form"), body={"title": "New form"})

    assert result == {"status": "success", "httpStatus": 201}


async def test_non_json_success_body_raises_upstream_error(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """A 200 serving an HTML login page is a failure, not a successful result."""
    html = "<html><body><h1>Log in to continue</h1>" + "<p>filler</p>" * 200 + "</body></html>"
    respx_mock.get(f"{BASE_URL}/form/9/info").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=html)
    )

    with pytest.raises(UpstreamError) as excinfo:
        await client.json(FORM_INFO, path={"formId": 9})

    message = str(excinfo.value)
    assert excinfo.value.status == 200
    assert "not JSON" in message
    assert "Log in to continue" in message
    assert len(message) < 1000


async def test_207_raises_partial_success_with_the_body_detail(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """207 is a 2xx, so it must be detected explicitly and surfaced as an error."""
    respx_mock.patch(f"{BASE_URL}/form/7/settings").mock(
        return_value=httpx.Response(
            207,
            json={"applied": ["title"], "rejected": ["respondentGroup"]},
        )
    )

    with pytest.raises(PartialSuccessError) as excinfo:
        await client.json(FORM_SETTINGS, path={"formId": 7}, body={"title": "New title"})

    assert excinfo.value.status == 207
    message = str(excinfo.value)
    assert "respondentGroup" in message
    assert "207" in message


async def test_error_status_maps_to_the_typed_exception(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """A JSON error body maps to the typed exception and keeps the server message."""
    respx_mock.get(f"{BASE_URL}/form/9/info").mock(
        return_value=httpx.Response(404, json={"message": "Form 9 was not found"})
    )

    with pytest.raises(NotFoundError) as excinfo:
        await client.json(FORM_INFO, path={"formId": 9})

    assert excinfo.value.status == 404
    assert "Form 9 was not found" in str(excinfo.value)


async def test_non_json_error_body_still_raises_the_typed_exception(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """Review Focus 2: an HTML 502 page must not produce a JSONDecodeError."""
    html = (
        "<html><head><title>502 Bad Gateway</title></head><body>\n"
        "<h1>Bad Gateway</h1>\n" + "<p>padding padding padding</p>\n" * 200 + "</body></html>"
    )
    respx_mock.get(f"{BASE_URL}/form/9/info").mock(
        return_value=httpx.Response(502, headers={"content-type": "text/html"}, text=html)
    )

    with pytest.raises(UpstreamError) as excinfo:
        await client.json(FORM_INFO, path={"formId": 9})

    message = str(excinfo.value)
    assert excinfo.value.status == 502
    assert "502" in message
    assert "Bad Gateway" in message
    # The excerpt is bounded so an error page cannot flood the model's context.
    assert len(message) < 1000
    assert len(message) < len(html)


async def test_error_body_excerpt_is_bounded(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """The excerpt helper trims long bodies and marks them as trimmed."""
    excerpt = client_module.excerpt("x" * 5000)
    assert len(excerpt) <= client_module.ERROR_BODY_EXCERPT_LIMIT + 32
    assert excerpt.endswith("(truncated)")


async def test_ndjson_parses_one_object_per_line(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """Each NDJSON line becomes one row."""
    respx_mock.get(f"{BASE_URL}/form/5/answers").mock(
        return_value=httpx.Response(200, text='{"id": 1}\n{"id": 2}\n{"id": 3}\n')
    )

    result = await client.ndjson(ANSWERS, path={"formId": 5})

    assert result == {
        "rows": [{"id": 1}, {"id": 2}, {"id": 3}],
        "rowCount": 3,
        "truncated": False,
        "reason": None,
    }


async def test_ndjson_caps_rows_and_marks_truncated(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """Review Focus 4: hitting max_rows stops the stream and reports truncation."""
    body = "".join(f'{{"id": {n}}}\n' for n in range(1, 6))
    respx_mock.get(f"{BASE_URL}/form/5/answers").mock(return_value=httpx.Response(200, text=body))

    result = await client.ndjson(ANSWERS, path={"formId": 5}, max_rows=2)

    assert result["rowCount"] == 2
    assert result["rows"] == [{"id": 1}, {"id": 2}]
    assert result["truncated"] is True
    assert result["reason"] == "rowCap"


async def test_ndjson_default_cap_comes_from_settings(
    respx_mock: respx.MockRouter, settings: Settings
) -> None:
    """With no max_rows the cap is settings.max_answer_rows."""
    capped = replace(settings, max_answer_rows=3)
    body = "".join(f'{{"id": {n}}}\n' for n in range(1, 10))
    respx_mock.get(f"{BASE_URL}/form/5/answers").mock(return_value=httpx.Response(200, text=body))

    instance = NettskjemaClient(capped)
    try:
        result = await instance.ndjson(ANSWERS, path={"formId": 5})
    finally:
        await instance.aclose()

    assert result["rowCount"] == 3
    assert result["truncated"] is True
    assert result["reason"] == "rowCap"


async def test_ndjson_skips_blank_lines(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """Blank lines are ignored and do not count toward rowCount."""
    respx_mock.get(f"{BASE_URL}/form/5/answers").mock(
        return_value=httpx.Response(200, text='{"id": 1}\n\n   \n{"id": 2}\n\n')
    )

    result = await client.ndjson(ANSWERS, path={"formId": 5})

    assert result == {
        "rows": [{"id": 1}, {"id": 2}],
        "rowCount": 2,
        "truncated": False,
        "reason": None,
    }


async def test_ndjson_reports_a_truncated_final_line(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """Review Focus 5: a cut-off final line is reported, never silently dropped."""
    respx_mock.get(f"{BASE_URL}/form/5/answers").mock(
        return_value=httpx.Response(200, text='{"id": 1}\n{"id": 2}\n{"id": 3')
    )

    result = await client.ndjson(ANSWERS, path={"formId": 5})

    assert result["rows"] == [{"id": 1}, {"id": 2}]
    assert result["rowCount"] == 2
    assert result["truncated"] is True
    assert result["reason"] == "incompleteFinalLine"


async def test_ndjson_raises_the_typed_exception_on_error_status(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """A streamed request still maps error statuses to typed exceptions."""
    respx_mock.get(f"{BASE_URL}/form/5/answers").mock(
        return_value=httpx.Response(404, json={"message": "No such form"})
    )

    with pytest.raises(NotFoundError):
        await client.ndjson(ANSWERS, path={"formId": 5})


async def test_ndjson_translates_a_mid_stream_transport_failure(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """A connection dropped mid-body raises UpstreamError, not a raw httpx error."""
    respx_mock.get(f"{BASE_URL}/form/5/answers").mock(
        return_value=httpx.Response(200, stream=_FailingStream(b'{"id": 1}\n{"id": 2}\n'))
    )

    with pytest.raises(UpstreamError) as excinfo:
        await client.ndjson(ANSWERS, path={"formId": 5})

    assert "ReadError" in str(excinfo.value)


async def test_binary_writes_to_output_path_and_reports_size(
    client: NettskjemaClient, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """binary streams to the requested path and reports path, size and media type."""
    payload = b"PK\x03\x04" + b"spreadsheet-bytes" * 64
    respx_mock.get(f"{BASE_URL}/form/3/excel-report").mock(
        return_value=httpx.Response(
            200, content=payload, headers={"content-type": f"{XLSX_MEDIA_TYPE}; charset=binary"}
        )
    )
    target = tmp_path / "report.xlsx"

    result = await client.binary(EXCEL_REPORT, path={"formId": 3}, output_path=str(target))

    assert result == {
        "path": str(target),
        "bytes": len(payload),
        "mediaType": XLSX_MEDIA_TYPE,
    }
    assert target.read_bytes() == payload


async def test_binary_without_output_path_writes_to_a_temp_file(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """With no output_path the body lands in a temp file whose path is returned."""
    payload = b"%PDF-1.7 fake pdf"
    respx_mock.get(f"{BASE_URL}/form/3/excel-report").mock(
        return_value=httpx.Response(
            200, content=payload, headers={"content-type": "application/pdf"}
        )
    )

    result = await client.binary(EXCEL_REPORT, path={"formId": 3})

    written = Path(str(result["path"]))
    try:
        assert written.is_file()
        assert written.read_bytes() == payload
        assert result["bytes"] == len(payload)
        assert result["mediaType"] == "application/pdf"
    finally:
        written.unlink(missing_ok=True)


async def test_binary_translates_a_mid_stream_transport_failure(
    client: NettskjemaClient, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """A dropped download raises UpstreamError and leaves no partial file behind."""
    respx_mock.get(f"{BASE_URL}/form/3/excel-report").mock(
        return_value=httpx.Response(
            200,
            stream=_FailingStream(b"PK\x03\x04half-a-workbook"),
            headers={"content-type": XLSX_MEDIA_TYPE},
        )
    )
    target = tmp_path / "report.xlsx"

    with pytest.raises(UpstreamError) as excinfo:
        await client.binary(EXCEL_REPORT, path={"formId": 3}, output_path=str(target))

    assert "ReadError" in str(excinfo.value)
    # A half-written export must not be left looking like a complete one.
    assert not target.exists()


async def test_binary_keeps_an_existing_file_when_the_request_fails(
    client: NettskjemaClient, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """Cleanup only removes files we wrote: a failure before writing touches nothing."""
    respx_mock.get(f"{BASE_URL}/form/3/excel-report").mock(
        return_value=httpx.Response(404, json={"message": "No such form"})
    )
    target = tmp_path / "report.xlsx"
    target.write_bytes(b"an earlier export")

    with pytest.raises(NotFoundError):
        await client.binary(EXCEL_REPORT, path={"formId": 3}, output_path=str(target))

    assert target.read_bytes() == b"an earlier export"


async def test_binary_rejects_a_missing_parent_directory(
    client: NettskjemaClient,
    respx_mock: respx.MockRouter,
    token_route: respx.Route,
    tmp_path: Path,
) -> None:
    """Review Focus 3: the parent check happens before the request is issued."""
    route = respx_mock.get(f"{BASE_URL}/form/3/excel-report").mock(
        return_value=httpx.Response(200, content=b"never used")
    )
    target = tmp_path / "no-such-dir" / "report.xlsx"

    with pytest.raises(BadRequestError) as excinfo:
        await client.binary(EXCEL_REPORT, path={"formId": 3}, output_path=str(target))

    assert str(target) in str(excinfo.value)
    assert route.call_count == 0
    # Nothing at all happened: not even the token was fetched.
    assert token_route.call_count == 0


async def test_binary_rejects_an_unwritable_parent_directory(
    client: NettskjemaClient, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """A parent that exists but is not writable is rejected before the request."""
    route = respx_mock.get(f"{BASE_URL}/form/3/excel-report").mock(
        return_value=httpx.Response(200, content=b"never used")
    )
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    readonly.chmod(stat.S_IRUSR | stat.S_IXUSR)
    target = readonly / "report.xlsx"

    try:
        if os.access(readonly, os.W_OK):  # pragma: no cover - running as root
            pytest.skip("process can write to a read-only directory")
        with pytest.raises(BadRequestError) as excinfo:
            await client.binary(EXCEL_REPORT, path={"formId": 3}, output_path=str(target))
        assert str(target) in str(excinfo.value)
        assert route.call_count == 0
    finally:
        readonly.chmod(stat.S_IRWXU)


async def test_text_returns_the_body_in_envelope(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """text returns an envelope with the text and metadata."""
    syntax = "GET DATA\n  /TYPE=TXT\n  /FILE='answers.csv'\n.\n\n"
    respx_mock.get(f"{BASE_URL}/form/3/spss-syntax").mock(
        return_value=httpx.Response(200, text=syntax, headers={"content-type": "text/plain"})
    )

    result = await client.text(SPSS_SYNTAX, path={"formId": 3})

    assert isinstance(result, dict)
    assert result["text"] == syntax
    assert result["truncated"] is False
    assert result["reason"] is None
    assert result["totalChars"] == len(syntax)


async def test_text_rejects_max_chars_less_than_one(client: NettskjemaClient) -> None:
    """text raises BadRequestError when max_chars is less than 1."""
    with pytest.raises(BadRequestError) as excinfo:
        await client.text(SPSS_SYNTAX, path={"formId": 1}, max_chars=0)

    assert "max_chars must be at least 1" in str(excinfo.value)


async def test_missing_path_parameter_raises_bad_request(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """An unsubstituted placeholder is a caller error, not a request to the API."""
    route = respx_mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(BadRequestError) as excinfo:
        await client.json(FORM_INFO)

    assert "formId" in str(excinfo.value)
    assert route.call_count == 0


async def test_token_endpoint_transport_failure_is_translated(
    client: NettskjemaClient, respx_mock: respx.MockRouter, token_route: respx.Route
) -> None:
    """A connection failure reaching the token endpoint must not leak httpx."""
    token_route.mock(side_effect=httpx.ConnectError("no route to host"))

    with pytest.raises(UpstreamError) as excinfo:
        await client.json(FORM_INFO, path={"formId": 1})

    assert "ConnectError" in str(excinfo.value)


async def test_get_client_returns_one_pooled_instance() -> None:
    """get_client caches a single instance per process; aclose_client clears it."""
    first = get_client()
    assert get_client() is first

    await aclose_client()
    second = get_client()
    try:
        assert second is not first
    finally:
        await aclose_client()


async def test_aclose_client_is_safe_without_a_cached_client() -> None:
    """Closing when nothing was created is a no-op, not an error."""
    client_module.reset_client()
    await aclose_client()
    await aclose_client()


async def test_json_rejects_body_and_content_together(client: NettskjemaClient) -> None:
    """json raises BadRequestError when both body and content are provided."""
    with pytest.raises(BadRequestError) as excinfo:
        await client.json(
            FORM_INFO,
            path={"formId": 1},
            body={"some": "json"},
            content=b"raw bytes",
        )

    assert "body and content are mutually exclusive" in str(excinfo.value)


async def test_json_merges_headers_without_dropping_authorization(
    client: NettskjemaClient, respx_mock: respx.MockRouter
) -> None:
    """json merges extra_headers on top of defaults without replacing Authorization."""
    route = respx_mock.get(f"{BASE_URL}/form/1/info").mock(
        return_value=httpx.Response(200, json={"formId": 1})
    )

    await client.json(
        FORM_INFO,
        path={"formId": 1},
        headers={"X-Custom-Header": "test-value"},
    )

    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-token"
    assert request.headers["X-Custom-Header"] == "test-value"
    assert request.headers["Accept"] == "application/json"


async def test_json_rejects_authorization_replacement(client: NettskjemaClient) -> None:
    """json raises BadRequestError when headers tries to replace Authorization."""
    with pytest.raises(BadRequestError) as excinfo:
        await client.json(
            FORM_INFO,
            path={"formId": 1},
            headers={"Authorization": "Bearer fake-token"},
        )

    assert "Cannot replace the Authorization header" in str(excinfo.value)


async def test_json_rejects_lowercase_authorization_replacement(client: NettskjemaClient) -> None:
    """json raises BadRequestError when headers tries to replace authorization (lowercase)."""
    with pytest.raises(BadRequestError) as excinfo:
        await client.json(
            FORM_INFO,
            path={"formId": 1},
            headers={"authorization": "Bearer fake-token"},
        )

    assert "Cannot replace the Authorization header" in str(excinfo.value)


def test_dump_renders_readable_json() -> None:
    """dump pretty-prints with real Unicode characters, not escapes."""
    rendered = dump({"title": "Spørreskjema", "ids": [1, 2]})
    assert "Spørreskjema" in rendered
    assert "\n  " in rendered
