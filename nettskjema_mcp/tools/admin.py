"""Admin tools: TSD and Educloud activation, and image upload/download.

The TSD and Educloud activation tokens are credentials, exactly like the OAuth
access token and the attachment token: never in a log record at any level, never
in an exception message, never in a returned dict.

Image uploads read the entire file into memory, base64-encode it (adding roughly a
third again on top of the file size), and httpx then serialises the result — several
times the file size resident at peak, with no cap.

The POST /image endpoint declares its body as {"type": "string", "format": "byte"}
under application/json — a JSON string holding base64. This module sends the file
as a base64-encoded JSON string, per the published schema. The actual server may
expect raw bytes instead; whether it accepts the JSON string or rejects it with a
decode error is an open question that can only be settled end-to-end.
"""

import base64
from pathlib import Path

from nettskjema_mcp.client import dump, get_client
from nettskjema_mcp.errors import NotFoundError
from nettskjema_mcp.routes import Route, endpoint
from nettskjema_mcp.server import tool
from nettskjema_mcp.validation import validate_body

ACTIVATE_TSD = Route("POST", "/form/{formId}/activate/tsd")
ACTIVATE_EDUCLOUD = Route("POST", "/form/{formId}/activate/educloud")
UPLOAD_IMAGE = Route("POST", "/image")
GET_IMAGE = Route("GET", "/image/{imageId}")


@tool()
@endpoint(ACTIVATE_TSD)
async def activate_tsd(form_id: int, project_name: str, token: str) -> str:
    """
    Activate TSD (Services for Sensitive Data) for a form.

    The token parameter is a credential that authorizes activating TSD for the
    named project. It must be kept as secure as the OAuth2 access token and is
    never logged or included in error messages.

    The API returns 200 with no response body on success.

    Args:
        form_id: The form's numeric ID.
        project_name: The TSD project name.
        token: The TSD activation token (credential, never logged).

    Returns:
        A success marker as JSON: {"status": "success", "httpStatus": 200}.
    """
    body = {
        "projectName": project_name,
        "token": token,
    }
    validate_body("ActivateFormDTO", body)

    result = await get_client().json(
        ACTIVATE_TSD,
        path={"formId": form_id},
        body=body,
    )
    return dump(result)


@tool()
@endpoint(ACTIVATE_EDUCLOUD)
async def activate_educloud(form_id: int, project_name: str, token: str) -> str:
    """
    Activate Educloud for a form.

    The token parameter is a credential that authorizes activating Educloud for
    the named project. It must be kept as secure as the OAuth2 access token and
    is never logged or included in error messages.

    The API returns 200 with no response body on success.

    Args:
        form_id: The form's numeric ID.
        project_name: The Educloud project name.
        token: The Educloud activation token (credential, never logged).

    Returns:
        A success marker as JSON: {"status": "success", "httpStatus": 200}.
    """
    body = {
        "projectName": project_name,
        "token": token,
    }
    validate_body("ActivateFormDTO", body)

    result = await get_client().json(
        ACTIVATE_EDUCLOUD,
        path={"formId": form_id},
        body=body,
    )
    return dump(result)


@tool()
@endpoint(UPLOAD_IMAGE)
async def upload_image(file_path: str) -> str:
    """
    Upload an image to the API, returning a response with string keys and values.

    The entire file is read into memory, base64-encoded, and sent as a JSON string
    in the request body, per the published OpenAPI schema ({"type": "string",
    "format": "byte"} under application/json). The filename is derived from the
    file itself and sent as a query parameter.

    The body format is most likely a Spring Boot serialisation artefact where a
    byte[] parameter was rendered as format: byte. The actual server may expect
    raw bytes; whether it accepts the JSON string can only be settled end-to-end.

    Args:
        file_path: Path to the image file to upload. May be relative or contain ~.

    Returns:
        A JSON object with string keys and string values (the spec declares
        {"type": "object", "additionalProperties": {"type": "string"}} and names
        no specific properties).
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

    # Read the file and base64-encode it
    content = path.read_bytes()
    encoded = base64.b64encode(content).decode("ascii")
    filename = path.name

    # Send as a JSON string (per the spec's format: byte declaration)
    result = await get_client().json(
        UPLOAD_IMAGE,
        query={"filename": filename},
        body=encoded,
    )
    return dump(result)


@tool()
@endpoint(GET_IMAGE)
async def get_image(image_id: str, output_path: str | None = None) -> str:
    """
    Download an image to a file, written to disk.

    The image is streamed to disk and never inlined. The returned path is absolute
    and tilde-expanded. An existing file at the output path is silently overwritten,
    and its mode is preserved. A new file (whether from output_path or a temp file)
    is created with mode 0600 (readable only by the current user).

    When output_path is omitted, a temporary file is created in the system temp
    directory with a suffix derived from the response's media type. The temporary
    file persists after this call returns and is left on disk for the caller to
    use or delete.

    The spec declares the response as */* (any media type), so the actual content
    type is reported as received.

    Args:
        image_id: The image's ID (a string, often but not always a UUID).
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
            GET_IMAGE,
            path={"imageId": image_id},
            output_path=output_path,
        )
    )
