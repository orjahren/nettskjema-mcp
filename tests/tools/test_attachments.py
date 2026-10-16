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
    "segments": [{"start": 0.0, "end": 2.5, "text": "This is a transcription."}],
}
TRANSCRIBED_TXT_RESPONSE = "This is a transcription."
TRANSCRIBED_VTT_RESPONSE = """WEBVTT

00:00:00.000 --> 00:00:02.500
This is a transcription."""

# Fixture for the upload's 200 response (string map). The spec declares
# {"type": "object", "additionalProperties": {"type": "string"}}, so the schema
# permits any string-valued key. The key names here ("fileId", "status") are
# illustrative placeholders; the validator pins only the value type, not the names.
UPLOAD_SUCCESS_RESPONSE = {"fileId": "abc123", "status": "uploaded"}

# Binary content with NUL and invalid UTF-8 to pin fidelity
ATTACHMENT_CONTENT = b"\x00\xff\xfe fake \xc3\x28 audio file content"


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
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=ATTACHMENT_CONTENT))

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
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=ATTACHMENT_CONTENT))

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
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

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
    # The mock returns an empty dict as the 200 body
    assert parsed == {}

    # Verify request details
    request = route.calls.last.request
    assert request.content == ATTACHMENT_CONTENT


async def test_upload_derives_filename_and_filesize_from_the_file(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() derives filename and fileSize from the file."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

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
        return_value=httpx.Response(200, json={})
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
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

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
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

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
    json_route = respx_mock.get(f"{TEST_BASE_URL}/submission/attachment/123/transcribed/json").mock(
        return_value=httpx.Response(200, json=TRANSCRIBED_JSON_RESPONSE)
    )
    txt_route = respx_mock.get(f"{TEST_BASE_URL}/submission/attachment/123/transcribed/txt").mock(
        return_value=httpx.Response(200, text=TRANSCRIBED_TXT_RESPONSE)
    )
    vtt_route = respx_mock.get(f"{TEST_BASE_URL}/submission/attachment/123/transcribed/vtt").mock(
        return_value=httpx.Response(200, text=TRANSCRIBED_VTT_RESPONSE)
    )

    # Test JSON format
    result_json = await get_attachment_transcription(123, format="json")
    assert json_route.call_count == 1
    assert txt_route.call_count == 0
    assert vtt_route.call_count == 0
    parsed = json.loads(result_json)
    assert parsed["text"] == "This is a transcription."

    # Test TXT format
    result_txt = await get_attachment_transcription(123, format="txt")
    assert txt_route.call_count == 1
    parsed_txt = json.loads(result_txt)
    assert parsed_txt["text"] == TRANSCRIBED_TXT_RESPONSE
    assert parsed_txt["truncated"] is False

    # Test VTT format
    result_vtt = await get_attachment_transcription(123, format="vtt")
    assert vtt_route.call_count == 1
    parsed_vtt = json.loads(result_vtt)
    assert parsed_vtt["text"] == TRANSCRIBED_VTT_RESPONSE
    assert parsed_vtt["truncated"] is False


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


async def test_upload_validates_model_before_sending(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() validates model against TranscribeDTO."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    with pytest.raises(ToolError) as excinfo:
        await upload_submission_attachment(
            submission_id=1,
            question_id=42,
            file_path=str(test_file),
            attachment_token="test-token",
            model="unknown_model",
        )

    assert route.call_count == 0
    error_msg = str(excinfo.value)
    assert "model_auto" in error_msg or "TranscribeDTO" in error_msg


async def test_upload_validates_language_before_sending(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() validates language against TranscribeDTO."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    with pytest.raises(ToolError) as excinfo:
        await upload_submission_attachment(
            submission_id=1,
            question_id=42,
            file_path=str(test_file),
            attachment_token="test-token",
            language="invalid_lang",
        )

    assert route.call_count == 0
    error_msg = str(excinfo.value)
    assert "TranscribeDTO" in error_msg or "language" in error_msg


async def test_upload_rejects_token_with_control_characters(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() rejects tokens with CR, LF, or NUL."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    with pytest.raises(ToolError) as excinfo:
        await upload_submission_attachment(
            submission_id=1,
            question_id=42,
            file_path=str(test_file),
            attachment_token="sekret\nX-Evil: 1",
        )

    assert route.call_count == 0
    error_msg = str(excinfo.value)
    assert "control characters" in error_msg
    # The token value must not appear in the error message
    assert "sekret" not in error_msg
    assert "X-Evil" not in error_msg


@pytest.mark.parametrize(
    "param_name,param_value,query_key,query_value",
    [
        ("model", "model_auto", "model", "model_auto"),
        ("language", "en", "language", "en"),
        ("diarize", True, "diarize", "true"),
        ("translate_to_english", True, "translate-to-english", "true"),
    ],
)
async def test_upload_query_parameters(
    respx_mock: respx.MockRouter,
    tmp_path: Path,
    param_name: str,
    param_value: object,
    query_key: str,
    query_value: str,
) -> None:
    """upload_submission_attachment() sends all transcription options as query params."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json={}))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    await upload_submission_attachment(
        submission_id=1,
        question_id=42,
        file_path=str(test_file),
        attachment_token="test-token",
        **{param_name: param_value},
    )

    assert route.call_count == 1
    request = route.calls.last.request
    query_params = dict(request.url.params)
    assert query_params[query_key] == query_value


async def test_upload_returns_200_response_body(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    """upload_submission_attachment() returns the 200 response body verbatim."""
    url = f"{TEST_BASE_URL}/form/submission/1/attachment"
    route = respx_mock.put(url).mock(return_value=httpx.Response(200, json=UPLOAD_SUCCESS_RESPONSE))

    test_file = tmp_path / "upload.mp3"
    test_file.write_bytes(ATTACHMENT_CONTENT)

    result = await upload_submission_attachment(
        submission_id=1,
        question_id=42,
        file_path=str(test_file),
        attachment_token="test-token",
    )

    assert route.call_count == 1
    parsed = json.loads(result)
    assert parsed == UPLOAD_SUCCESS_RESPONSE
