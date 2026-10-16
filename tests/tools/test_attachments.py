"""Tests for attachment tools."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from nettskjema_mcp.routes import REGISTRY
from nettskjema_mcp.tools.attachments import (
    get_answer_attachment,
    get_attachment_transcription,
    retranscribe_attachment,
    upload_submission_attachment,
)
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

# Sample response fixtures
TRANSCRIBED_JSON_RESPONSE = {
    "text": "This is a transcription.",
    "segments": [
        {"start": 0.0, "end": 2.5, "text": "This is a transcription."}
    ],
}
TRANSCRIBED_TXT_RESPONSE = "This is a transcription."
TRANSCRIBED_VTT_RESPONSE = """WEBVTT

00:00:00.000 --> 00:00:02.500
This is a transcription."""

ATTACHMENT_CONTENT = b"fake audio file content"


async def test_get_answer_attachment_writes_to_file(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """get_answer_attachment() downloads the attachment to disk."""
    url = f"{TEST_BASE_URL}/form/submission/attachment/123"
    route = respx_mock.get(url).mock(
        return_value=httpx.Response(
            200,
            content=ATTACHMENT_CONTENT,
            headers={"content-type": "audio/mpeg"},
        )
    )

    output_file = tmp_path / "attachment.mp3"
    result = await get_answer_attachment(123, output_path=str(output_file))

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["path"] == str(output_file.resolve())
    assert parsed["bytes"] == len(ATTACHMENT_CONTENT)
    assert output_file.read_bytes() == ATTACHMENT_CONTENT


async def test_get_answer_attachment_preserves_an_existing_files_mode(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """get_answer_attachment() preserves the mode of an existing file."""
    url = f"{TEST_BASE_URL}/form/submission/attachment/123"
    respx_mock.get(url).mock(
        return_value=httpx.Response(200, content=ATTACHMENT_CONTENT)
    )

    output_file = tmp_path / "existing.mp3"
    output_file.write_bytes(b"old content")
    output_file.chmod(0o644)

    await get_answer_attachment(123, output_path=str(output_file))

    # Mode should be preserved
    assert (output_file.stat().st_mode & 0o777) == 0o644


async def test_get_answer_attachment_expands_a_tilde_path(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """get_answer_attachment() expands ~ to the home directory."""
    url = f"{TEST_BASE_URL}/form/submission/attachment/123"
    respx_mock.get(url).mock(
        return_value=httpx.Response(200, content=ATTACHMENT_CONTENT)
    )

    monkeypatch.setenv("HOME", str(tmp_path))

    result = await get_answer_attachment(123, output_path="~/test_attachment.mp3")

    parsed = json.loads(result)
    expected_path = tmp_path / "test_attachment.mp3"
    assert parsed["path"] == str(expected_path)
    assert expected_path.exists()


async def test_upload_submission_attachment_sends_file_content(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() uploads the file content."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(204))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    result = await upload_submission_attachment(
        submission_id=1,
        question_id=42,
        file_path=str(test_file),
        attachment_token="test-token-value",
    )

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed["status"] == "success"
    assert parsed["httpStatus"] == 204

    # Verify request details
    request = route.calls.last.request
    assert request.content == ATTACHMENT_CONTENT


async def test_upload_derives_filename_and_filesize_from_the_file(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() derives filename and fileSize from the file."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(204))

    test_file = tmp_path / "my-recording.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    await upload_submission_attachment(
        submission_id=1,
        question_id=42,
        file_path=str(test_file),
        attachment_token="test-token",
    )

    assert route.call_count == 1
    request = route.calls.last.request
    query_params = dict(request.url.params)
    assert query_params["filename"] == "my-recording.mp3"
    assert query_params["fileSize"] == str(len(ATTACHMENT_CONTENT))
    assert query_params["questionId"] == "42"


async def test_upload_rejects_a_missing_file(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    """upload_submission_attachment() raises ToolError for a missing file."""
    missing_file = tmp_path / "does-not-exist.mp3"
    route = respx_mock.put(f"{TEST_BASE_URL}/form/submission/1/attachment").mock(
        return_value=httpx.Response(204)
    )

    with pytest.raises(ToolError) as excinfo:
        await upload_submission_attachment(
            submission_id=1,
            question_id=42,
            file_path=str(missing_file),
            attachment_token="test-token",
        )

    assert route.call_count == 0
    assert "does not exist" in str(excinfo.value)


async def test_upload_sends_the_attachment_token_header(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() sends the X-nettskjema-attachment-token header."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(204))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    await upload_submission_attachment(
        submission_id=1,
        question_id=42,
        file_path=str(test_file),
        attachment_token="secret-token-value",
    )

    assert route.call_count == 1
    request = route.calls.last.request
    assert request.headers["X-nettskjema-attachment-token"] == "secret-token-value"


async def test_upload_sends_the_hyphenated_query_key(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() sends translate-to-english as hyphenated query key."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(204))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    await upload_submission_attachment(
        submission_id=1,
        question_id=42,
        file_path=str(test_file),
        attachment_token="test-token",
        translate_to_english=True,
    )

    assert route.call_count == 1
    request = route.calls.last.request
    query_params = dict(request.url.params)
    assert query_params["translate-to-english"] == "true"


async def test_get_attachment_transcription_selects_the_route_by_format(
    respx_mock: respx.MockRouter,
) -> None:
    """get_attachment_transcription() selects the correct route based on format."""
    json_route = respx_mock.get(
        f"{TEST_BASE_URL}/submission/attachment/123/transcribed/json"
    ).mock(return_value=httpx.Response(200, json=TRANSCRIBED_JSON_RESPONSE))
    txt_route = respx_mock.get(
        f"{TEST_BASE_URL}/submission/attachment/123/transcribed/txt"
    ).mock(return_value=httpx.Response(200, json=TRANSCRIBED_TXT_RESPONSE))
    vtt_route = respx_mock.get(
        f"{TEST_BASE_URL}/submission/attachment/123/transcribed/vtt"
    ).mock(return_value=httpx.Response(200, json=TRANSCRIBED_VTT_RESPONSE))

    # Test JSON format
    result_json = await get_attachment_transcription(123, format="json")
    assert json_route.call_count == 1
    assert txt_route.call_count == 0
    assert vtt_route.call_count == 0
    parsed = json.loads(result_json)
    assert parsed["text"] == "This is a transcription."

    # Test TXT format
    await get_attachment_transcription(123, format="txt")
    assert txt_route.call_count == 1

    # Test VTT format
    await get_attachment_transcription(123, format="vtt")
    assert vtt_route.call_count == 1


async def test_get_attachment_transcription_declares_all_three_routes() -> None:
    """get_attachment_transcription() registers all three route variants."""
    assert len(REGISTRY["get_attachment_transcription"]) == 3


async def test_retranscribe_attachment_sends_the_dto_key_names(
    respx_mock: respx.MockRouter,
) -> None:
    """retranscribe_attachment() maps Python names to DTO property names."""
    url = f"{TEST_BASE_URL}/submission/attachment/123/retranscribe"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json={}))

    await retranscribe_attachment(
        answer_attachment_id=123,
        diarize=True,
        translate_to_english=True,
    )

    assert route.call_count == 1
    request = route.calls.last.request
    body = json.loads(request.content)
    assert body["isDiarizeEnabled"] is True
    assert body["isTranslateToEnglishEnabled"] is True
    # Python names should NOT appear in the body
    assert "diarize" not in body
    assert "translate_to_english" not in body


async def test_retranscribe_rejects_an_unknown_model(respx_mock: respx.MockRouter) -> None:
    """retranscribe_attachment() rejects an unknown model before sending."""
    url = f"{TEST_BASE_URL}/submission/attachment/123/retranscribe"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError) as excinfo:
        await retranscribe_attachment(
            answer_attachment_id=123,
            model="unknown_model",
        )

    assert route.call_count == 0
    # The error should mention the allowed models
    error_msg = str(excinfo.value)
    assert "model_auto" in error_msg or "TranscribeDTO" in error_msg


async def test_retranscribe_rejects_an_unknown_language(
    respx_mock: respx.MockRouter,
) -> None:
    """retranscribe_attachment() rejects an unknown language before sending."""
    url = f"{TEST_BASE_URL}/submission/attachment/123/retranscribe"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError) as excinfo:
        await retranscribe_attachment(
            answer_attachment_id=123,
            language="invalid_lang",
        )

    assert route.call_count == 0
    # The error should mention validation failure
    error_msg = str(excinfo.value)
    assert "TranscribeDTO" in error_msg or "language" in error_msg
