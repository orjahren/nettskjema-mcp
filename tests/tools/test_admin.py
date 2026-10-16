"""Tests for admin tools: TSD/Educloud activation and image upload/download."""

import base64
import inspect
import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from nettskjema_mcp.routes import REGISTRY
from nettskjema_mcp.tools.admin import (
    activate_educloud,
    activate_tsd,
    get_image,
    upload_image,
)
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

# Fixture for the upload image response (string map). The spec declares
# {"type": "object", "additionalProperties": {"type": "string"}}, so the schema
# permits any string-valued key. The key names here ("imageId", "url") are
# illustrative placeholders; the validator pins only the value type, not the names.
UPLOAD_IMAGE_RESPONSE = {"imageId": "abc-123-def-456", "url": "https://example.com/image.jpg"}

# Sample image content (fake PNG header + some bytes)
IMAGE_CONTENT = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 50


async def test_activate_tsd_sends_body(respx_mock: respx.MockRouter) -> None:
    """activate_tsd() sends projectName and token in the request body."""
    url = f"{TEST_BASE_URL}/form/123/activate/tsd"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200))

    await activate_tsd(form_id=123, project_name="test-project", token="test-token")

    assert route.call_count == 1
    request = route.calls.last.request
    body = json.loads(request.content)
    assert body["projectName"] == "test-project"
    assert body["token"] == "test-token"


async def test_activate_tsd_returns_success_marker_on_200(respx_mock: respx.MockRouter) -> None:
    """activate_tsd() returns a success marker when the API returns 200 with no body."""
    url = f"{TEST_BASE_URL}/form/123/activate/tsd"
    respx_mock.post(url).mock(return_value=httpx.Response(200))

    result = await activate_tsd(form_id=123, project_name="proj", token="tok")

    parsed = json.loads(result)
    assert parsed == {"status": "success", "httpStatus": 200}


async def test_activate_educloud_sends_body(respx_mock: respx.MockRouter) -> None:
    """activate_educloud() sends projectName and token in the request body."""
    url = f"{TEST_BASE_URL}/form/456/activate/educloud"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200))

    await activate_educloud(form_id=456, project_name="edu-project", token="edu-token")

    assert route.call_count == 1
    request = route.calls.last.request
    body = json.loads(request.content)
    assert body["projectName"] == "edu-project"
    assert body["token"] == "edu-token"


async def test_activate_educloud_returns_success_marker_on_200(
    respx_mock: respx.MockRouter,
) -> None:
    """activate_educloud() returns a success marker when the API returns 200 with no body."""
    url = f"{TEST_BASE_URL}/form/456/activate/educloud"
    respx_mock.post(url).mock(return_value=httpx.Response(200))

    result = await activate_educloud(form_id=456, project_name="proj", token="tok")

    parsed = json.loads(result)
    assert parsed == {"status": "success", "httpStatus": 200}


async def test_upload_image_sends_base64_body(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    """upload_image() sends the file as base64-encoded JSON string in the body."""
    url = f"{TEST_BASE_URL}/image"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=UPLOAD_IMAGE_RESPONSE))

    test_file = tmp_path / "test.png"
    test_file.write_bytes(IMAGE_CONTENT)

    await upload_image(file_path=str(test_file))

    assert route.call_count == 1
    request = route.calls.last.request
    # The body should be a JSON string containing base64
    body = json.loads(request.content)
    assert isinstance(body, str)
    # Verify it's valid base64 and decodes to our original content
    decoded = base64.b64decode(body)
    assert decoded == IMAGE_CONTENT


async def test_upload_image_sends_filename_in_query(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_image() sends the filename as a query parameter."""
    url = f"{TEST_BASE_URL}/image"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=UPLOAD_IMAGE_RESPONSE))

    test_file = tmp_path / "myimage.png"
    test_file.write_bytes(IMAGE_CONTENT)

    await upload_image(file_path=str(test_file))

    assert route.call_count == 1
    request = route.calls.last.request
    query_params = dict(request.url.params)
    assert query_params["filename"] == "myimage.png"


async def test_upload_image_returns_response_body(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_image() returns the 200 response body verbatim."""
    url = f"{TEST_BASE_URL}/image"
    respx_mock.post(url).mock(return_value=httpx.Response(200, json=UPLOAD_IMAGE_RESPONSE))

    test_file = tmp_path / "test.png"
    test_file.write_bytes(IMAGE_CONTENT)

    result = await upload_image(file_path=str(test_file))

    parsed = json.loads(result)
    assert parsed == UPLOAD_IMAGE_RESPONSE


async def test_upload_image_rejects_nonexistent_file(tmp_path: Path) -> None:
    """upload_image() rejects a file that does not exist."""
    nonexistent = tmp_path / "does-not-exist.png"

    with pytest.raises(ToolError) as excinfo:
        await upload_image(file_path=str(nonexistent))

    error_msg = str(excinfo.value)
    assert "does not exist" in error_msg.lower()


async def test_upload_image_rejects_directory(tmp_path: Path) -> None:
    """upload_image() rejects a directory path."""
    directory = tmp_path / "testdir"
    directory.mkdir()

    with pytest.raises(ToolError) as excinfo:
        await upload_image(file_path=str(directory))

    error_msg = str(excinfo.value)
    assert "not a file" in error_msg.lower() or "directory" in error_msg.lower()


async def test_get_image_writes_to_file(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    """get_image() downloads the image to disk."""
    url = f"{TEST_BASE_URL}/image/abc-123-def-456"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=IMAGE_CONTENT,
            headers={"content-type": "image/png"},
        )
    )

    output_file = tmp_path / "downloaded.png"
    result = await get_image(image_id="abc-123-def-456", output_path=str(output_file))

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["path"] == str(output_file.resolve())
    assert parsed["bytes"] == len(IMAGE_CONTENT)
    assert parsed["mediaType"] == "image/png"
    assert output_file.read_bytes() == IMAGE_CONTENT


async def test_get_image_preserves_an_existing_files_mode(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """get_image() preserves the mode of an existing file."""
    url = f"{TEST_BASE_URL}/image/test-id"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=IMAGE_CONTENT))

    output_file = tmp_path / "existing.png"
    output_file.write_bytes(b"old content")
    output_file.chmod(0o644)

    await get_image(image_id="test-id", output_path=str(output_file))

    # Mode should be preserved
    assert (output_file.stat().st_mode & 0o777) == 0o644


async def test_get_image_expands_a_tilde_path(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """get_image() expands ~ to the home directory."""
    url = f"{TEST_BASE_URL}/image/test-id"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=IMAGE_CONTENT))

    monkeypatch.setenv("HOME", str(tmp_path))
    output_file = tmp_path / "image.png"

    result = await get_image(image_id="test-id", output_path="~/image.png")

    parsed = json.loads(result)
    assert parsed["path"] == str(output_file.resolve())
    assert output_file.exists()


async def test_get_image_creates_temp_file_when_no_output_path(
    respx_mock: respx.MockRouter,
) -> None:
    """get_image() creates a temp file when output_path is omitted."""
    url = f"{TEST_BASE_URL}/image/test-id"
    respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=IMAGE_CONTENT,
            headers={"content-type": "image/jpeg"},
        )
    )

    result = await get_image(image_id="test-id")

    parsed = json.loads(result)
    path = Path(parsed["path"])
    assert path.exists()
    assert path.read_bytes() == IMAGE_CONTENT
    assert parsed["bytes"] == len(IMAGE_CONTENT)
    # Clean up the temp file
    path.unlink()


async def test_get_image_new_file_has_mode_0600(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """get_image() creates new files with mode 0600."""
    url = f"{TEST_BASE_URL}/image/test-id"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=IMAGE_CONTENT))

    output_file = tmp_path / "new-image.png"
    await get_image(image_id="test-id", output_path=str(output_file))

    # New file should have mode 0600
    assert (output_file.stat().st_mode & 0o777) == 0o600


async def test_get_image_temp_file_has_mode_0600(respx_mock: respx.MockRouter) -> None:
    """get_image() creates temp files with mode 0600."""
    url = f"{TEST_BASE_URL}/image/test-id"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=IMAGE_CONTENT))

    result = await get_image(image_id="test-id")

    parsed = json.loads(result)
    path = Path(parsed["path"])
    # Temp file should have mode 0600
    assert (path.stat().st_mode & 0o777) == 0o600
    # Clean up
    path.unlink()


async def test_get_image_accepts_non_numeric_id(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """get_image() accepts non-numeric IDs (the spec types it as string, not int)."""
    # Use an ID that would fail if coerced to int
    image_id = "a/b"
    url = f"{TEST_BASE_URL}/image/a%2Fb"  # URL-encoded
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, content=IMAGE_CONTENT))

    output_file = tmp_path / "image.png"
    await get_image(image_id=image_id, output_path=str(output_file))

    assert route.call_count == 1
    assert output_file.exists()


async def test_tokens_are_not_logged(
    respx_mock: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    """TSD and Educloud tokens never appear in log records at any level."""
    tsd_url = f"{TEST_BASE_URL}/form/100/activate/tsd"
    edu_url = f"{TEST_BASE_URL}/form/200/activate/educloud"

    respx_mock.post(tsd_url).mock(return_value=httpx.Response(200))
    respx_mock.post(edu_url).mock(return_value=httpx.Response(200))

    # Capture logs at DEBUG level
    with caplog.at_level(logging.DEBUG):
        await activate_tsd(form_id=100, project_name="tsd-proj", token="secret-tsd-token")
        await activate_educloud(form_id=200, project_name="edu-proj", token="secret-edu-token")

    # Check that tokens do not appear in any log record
    all_logs = " ".join(record.message for record in caplog.records)
    assert "secret-tsd-token" not in all_logs
    assert "secret-edu-token" not in all_logs


async def test_tokens_not_in_error_messages(respx_mock: respx.MockRouter) -> None:
    """TSD and Educloud tokens never appear in error messages."""
    tsd_url = f"{TEST_BASE_URL}/form/100/activate/tsd"
    edu_url = f"{TEST_BASE_URL}/form/200/activate/educloud"

    # Make the requests fail
    respx_mock.post(tsd_url).mock(
        return_value=httpx.Response(
            400,
            json={"message": "Invalid project", "errors": {"projectName": ["is invalid"]}},
        )
    )
    respx_mock.post(edu_url).mock(
        return_value=httpx.Response(
            403,
            json={"message": "Forbidden", "errors": {}},
        )
    )

    # Test TSD activation failure
    with pytest.raises(ToolError) as excinfo:
        await activate_tsd(form_id=100, project_name="bad-proj", token="secret-tsd-token")

    assert "secret-tsd-token" not in str(excinfo.value)

    # Test Educloud activation failure
    with pytest.raises(ToolError) as excinfo:
        await activate_educloud(form_id=200, project_name="bad-proj", token="secret-edu-token")

    assert "secret-edu-token" not in str(excinfo.value)


async def test_tokens_not_in_returned_dict(respx_mock: respx.MockRouter) -> None:
    """TSD and Educloud tokens never appear in the returned tool result."""
    tsd_url = f"{TEST_BASE_URL}/form/100/activate/tsd"
    edu_url = f"{TEST_BASE_URL}/form/200/activate/educloud"

    respx_mock.post(tsd_url).mock(return_value=httpx.Response(200))
    respx_mock.post(edu_url).mock(return_value=httpx.Response(200))

    # Test TSD activation success
    result = await activate_tsd(form_id=100, project_name="tsd-proj", token="secret-tsd-token")
    assert "secret-tsd-token" not in result
    assert "tsd-proj" not in result  # project name also should not be echoed

    # Test Educloud activation success
    result = await activate_educloud(form_id=200, project_name="edu-proj", token="secret-edu-token")
    assert "secret-edu-token" not in result
    assert "edu-proj" not in result  # project name also should not be echoed


async def test_activate_tsd_declares_its_route() -> None:
    """activate_tsd() must declare its route in the registry."""
    assert "activate_tsd" in REGISTRY
    routes = REGISTRY["activate_tsd"]
    assert len(routes) == 1
    route = list(routes)[0]
    assert route.method == "POST"
    assert "/activate/tsd" in route.path


async def test_activate_educloud_declares_its_route() -> None:
    """activate_educloud() must declare its route in the registry."""
    assert "activate_educloud" in REGISTRY
    routes = REGISTRY["activate_educloud"]
    assert len(routes) == 1
    route = list(routes)[0]
    assert route.method == "POST"
    assert "/activate/educloud" in route.path


async def test_upload_image_declares_its_route() -> None:
    """upload_image() must declare its route in the registry."""
    assert "upload_image" in REGISTRY
    routes = REGISTRY["upload_image"]
    assert len(routes) == 1
    route = list(routes)[0]
    assert route.method == "POST"
    assert route.path == "/image"


async def test_get_image_declares_its_route() -> None:
    """get_image() must declare its route in the registry."""
    assert "get_image" in REGISTRY
    routes = REGISTRY["get_image"]
    assert len(routes) == 1
    route = list(routes)[0]
    assert route.method == "GET"
    assert "/image/" in route.path


async def test_activation_parameters_are_required() -> None:
    """project_name and token must be required Python parameters (no defaults)."""
    tsd_sig = inspect.signature(activate_tsd)
    assert tsd_sig.parameters["project_name"].default == inspect.Parameter.empty
    assert tsd_sig.parameters["token"].default == inspect.Parameter.empty

    edu_sig = inspect.signature(activate_educloud)
    assert edu_sig.parameters["project_name"].default == inspect.Parameter.empty
    assert edu_sig.parameters["token"].default == inspect.Parameter.empty


async def test_image_id_is_str() -> None:
    """image_id must be typed as str (the spec declares it as string, not int)."""
    sig = inspect.signature(get_image)
    assert sig.parameters["image_id"].annotation is str
