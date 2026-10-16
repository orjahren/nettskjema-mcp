"""Attachment download, upload, and transcription tools.

Attachment uploads stream the entire file into memory as bytes before sending,
because the API requires the fileSize as a query parameter derived from the file.
A long audio recording awaiting transcription can be tens of megabytes; the whole
file is held in RAM during the upload.

The attachment token authorizes writing to someone else's submission. It is a
credential and must never appear in a log line, an exception message, or a
returned dict — the same rule the access token and the client secret already have.
"""

from pathlib import Path
from typing import Literal

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.errors import NotFoundError
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool
from nettskjema_mcp.validation import validate_body

ANSWER_ATTACHMENT = Route("GET", "/form/submission/attachment/{answerAttachmentId}")
UPLOAD_ATTACHMENT = Route("PUT", "/form/submission/{submissionId}/attachment")
TRANSCRIBED_JSON = Route("GET", "/submission/attachment/{answerAttachmentId}/transcribed/json")
TRANSCRIBED_TXT = Route("GET", "/submission/attachment/{answerAttachmentId}/transcribed/txt")
TRANSCRIBED_VTT = Route("GET", "/submission/attachment/{answerAttachmentId}/transcribed/vtt")
RETRANSCRIBE = Route("POST", "/submission/attachment/{answerAttachmentId}/retranscribe")


@tool()
@endpoint(ANSWER_ATTACHMENT)
async def get_answer_attachment(
    answer_attachment_id: int, output_path: str | None = None
) -> str:
    """
    Download an answer attachment to a file, written to disk.

    The attachment is streamed to disk and never inlined: a multi-megabyte audio
    recording as base64 is useless to a model. The returned path is absolute and
    tilde-expanded. An existing file at the output path is silently overwritten,
    and its mode is preserved. A new file (whether from output_path or a temp file)
    is created with mode 0600 (readable only by the current user).

    When output_path is omitted, a temporary file is created in the system temp
    directory with a suffix derived from the response's media type. The temporary
    file persists after this call returns and is left on disk for the caller to
    use or delete.

    Args:
        answer_attachment_id: The attachment's numeric ID.
        output_path: Destination file path. When omitted, a temporary file is
            created in the system temp directory. The path may contain ~ for the
            home directory and may be relative (it will be resolved to an absolute
            path).

    Returns:
        A JSON object with path (the absolute path to the written file), bytes
        (the number of bytes written), and mediaType (the content type from the
        response).
    """
    return dump(
        await get_client().binary(
            ANSWER_ATTACHMENT,
            path={"answerAttachmentId": answer_attachment_id},
            output_path=output_path,
        )
    )


@tool(annotations={"destructiveHint": True})
@endpoint(UPLOAD_ATTACHMENT)
async def upload_submission_attachment(
    submission_id: int,
    question_id: int,
    file_path: str,
    attachment_token: str,
    model: str | None = None,
    language: str | None = None,
    diarize: bool | None = None,
    translate_to_english: bool | None = None,
) -> str:
    """
    Upload an attachment to a submission question, optionally requesting transcription.

    The entire file is read into memory before uploading because the API requires
    fileSize as a query parameter. The filename and fileSize are derived from the
    file itself rather than accepted as parameters, so they cannot drift out of sync.
    An audio recording awaiting transcription can be tens of megabytes; the whole
    file is held in RAM during the upload.

    The attachment token comes from the attachmentToken field in the response body
    of POST /form/{formId}/submission. It authorizes writing to someone else's
    submission and must be kept as secure as the access token itself.

    The spec does not document what happens when the named questionId already has an
    attachment. An upload may silently replace a respondent's file.

    Transcription options apply only when the uploaded file is audio or video. The
    six supported models are: model_auto, nb_whisper_large_semantic,
    nb_whisper_large_verbatim, openai_whisper_large_v3, openai_whisper_large_v2,
    and KBLab-large. The language parameter accepts 100+ language codes; passing an
    unknown code raises BadRequestError naming the allowed values. The diarize flag
    requests speaker identification, and translate_to_english requests translation
    to English after transcription.

    Args:
        submission_id: The submission's numeric ID.
        question_id: The question (form element) ID to attach the file to.
        file_path: Path to the file to upload. May be relative or contain ~.
        attachment_token: The attachment token from the submission creation
            response. Authorizes writing to this submission.
        model: Transcription model. Defaults to the API's own default (model_auto).
        language: Language code for transcription (e.g., "en", "no", "auto").
        diarize: Request speaker identification in the transcription.
        translate_to_english: Request translation to English after transcription.

    Returns:
        A success marker as JSON: {"status": "success", "httpStatus": <code>}.
        The spec declares no response body for this operation.
    """
    # Expand and resolve the path, then check the file exists
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise NotFoundError(
            f"Cannot upload {file_path!r}: the file does not exist. "
            "Check the path and try again."
        )
    if not path.is_file():
        raise NotFoundError(
            f"Cannot upload {file_path!r}: that path is not a file (it may be a directory)."
        )

    # Read the entire file into memory
    content = path.read_bytes()
    filename = path.name
    file_size = len(content)

    # Build the query parameters, mapping Python names to the API's hyphenated form
    query: dict[str, object] = {
        "questionId": question_id,
        "filename": filename,
        "fileSize": file_size,
    }
    if model is not None:
        query["model"] = model
    if language is not None:
        query["language"] = language
    if diarize is not None:
        query["diarize"] = diarize
    if translate_to_english is not None:
        query["translate-to-english"] = translate_to_english

    # Send the upload with the attachment token header
    return dump(
        await get_client().json(
            UPLOAD_ATTACHMENT,
            path={"submissionId": submission_id},
            query=query,
            content=content,
            headers={"X-nettskjema-attachment-token": attachment_token},
        )
    )


@tool(annotations={"readOnlyHint": True})
@endpoint(TRANSCRIBED_JSON, TRANSCRIBED_TXT, TRANSCRIBED_VTT)
async def get_attachment_transcription(
    answer_attachment_id: int, format: Literal["json", "txt", "vtt"] = "json"
) -> str:
    """
    Get the transcription of an attachment in JSON, plain text, or WebVTT format.

    The attachment must have been uploaded with transcription options for this to
    return meaningful results. A file uploaded without transcription, or a file
    that is not audio or video, has no transcription to retrieve.

    Args:
        answer_attachment_id: The attachment's numeric ID.
        format: The format to retrieve: "json" (detailed with timestamps), "txt"
            (plain text), or "vtt" (WebVTT subtitle format).

    Returns:
        The transcription in the requested format, as a JSON string.
    """
    route_map = {
        "json": TRANSCRIBED_JSON,
        "txt": TRANSCRIBED_TXT,
        "vtt": TRANSCRIBED_VTT,
    }
    selected_route = route_map[format]
    result = await get_client().json(
        selected_route,
        path={"answerAttachmentId": answer_attachment_id},
    )
    return dump(result)


@tool(annotations={"destructiveHint": True})
@endpoint(RETRANSCRIBE)
async def retranscribe_attachment(
    answer_attachment_id: int,
    model: str | None = None,
    language: str | None = None,
    diarize: bool | None = None,
    translate_to_english: bool | None = None,
) -> str:
    """
    Retranscribe an existing attachment with new transcription options.

    The API overwrites the existing transcription. The attachment must be audio or
    video; retranscribing a non-media file or a file that was never transcribed has
    undefined effect.

    The six supported models are: model_auto, nb_whisper_large_semantic,
    nb_whisper_large_verbatim, openai_whisper_large_v3, openai_whisper_large_v2,
    and KBLab-large. The language parameter accepts 100+ language codes; passing an
    unknown code raises BadRequestError naming the allowed values. The diarize flag
    requests speaker identification, and translate_to_english requests translation
    to English after transcription.

    Args:
        answer_attachment_id: The attachment's numeric ID.
        model: Transcription model. Defaults to the API's own default (model_auto).
        language: Language code for transcription (e.g., "en", "no", "auto").
        diarize: Request speaker identification in the transcription.
        translate_to_english: Request translation to English after transcription.

    Returns:
        The API's response as JSON. The spec declares no response body schema.
    """
    # Build the request body, mapping Python names to the DTO's property names
    body: dict[str, object] = {}
    if model is not None:
        body["model"] = model
    if language is not None:
        body["language"] = language
    if diarize is not None:
        body["isDiarizeEnabled"] = diarize
    if translate_to_english is not None:
        body["isTranslateToEnglishEnabled"] = translate_to_english

    # Validate against TranscribeDTO before sending
    validate_body("TranscribeDTO", body)

    result = await get_client().json(
        RETRANSCRIBE,
        path={"answerAttachmentId": answer_attachment_id},
        body=body,
    )
    return dump(result)
