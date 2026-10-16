"""Error types for Nettskjema API interactions."""

from nettskjema_mcp.config import get_settings


class ToolError(Exception):
    """Error to be raised by MCP tool implementations."""


class NettskjemaError(Exception):
    """Base exception for Nettskjema API errors."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        field_errors: dict[str, list[str]] | None = None,
    ) -> None:
        """
        Initialize a Nettskjema error.

        Args:
            message: Human-readable error description.
            status: HTTP status code that triggered this error.
            field_errors: Per-field validation errors, if any.
        """
        super().__init__(message)
        self.message = message
        self.status = status
        self.field_errors = field_errors or {}

    def __str__(self) -> str:
        """Render the error with field-level detail."""
        parts = [self.message]
        for field, errors in self.field_errors.items():
            for error in errors:
                parts.append(f"{field} → {error}")
        return "\n".join(parts)


class BadRequestError(NettskjemaError):
    """Client sent invalid data (HTTP 400)."""


class AuthenticationError(NettskjemaError):
    """Authentication failed or token invalid (HTTP 401)."""


class ForbiddenError(NettskjemaError):
    """Authenticated but not authorized (HTTP 403)."""


class NotFoundError(NettskjemaError):
    """Resource not found (HTTP 404)."""


class MethodNotAllowedError(NettskjemaError):
    """HTTP method not allowed for this endpoint (HTTP 405)."""


class ConflictError(NettskjemaError):
    """Request conflicts with current state (HTTP 409)."""


class UpstreamError(NettskjemaError):
    """Upstream service failed (HTTP 502)."""


class PartialSuccessError(NettskjemaError):
    """Multi-status response with partial success (HTTP 207)."""


_STATUS_MAP: dict[int, type[NettskjemaError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    405: MethodNotAllowedError,
    409: ConflictError,
    502: UpstreamError,
    207: PartialSuccessError,
}


def error_for_status(status: int, body: object) -> NettskjemaError:
    """
    Create an appropriate exception for an HTTP error response.

    Args:
        status: HTTP status code.
        body: Response body (dict, str, or None).

    Returns:
        A NettskjemaError subclass instance appropriate for the status code.
    """
    message = "Request failed"
    field_errors: dict[str, list[str]] | None = None

    # Extract message and field errors from body if it's a dict
    if isinstance(body, dict):
        message = body.get("message", message)
        if "errorKeysAndErrorMessages" in body:
            field_errors = body["errorKeysAndErrorMessages"]
    elif isinstance(body, str):
        message = body

    # Special handling for 403: guide users to permission settings
    if status == 403:
        client_id = get_settings().client_id or "<client_id>"
        message = (
            f"Access forbidden. Ensure {client_id}@apiclient has the required "
            "permissions in Nettskjema. Go to the form → Settings → Permissions → "
            "Editing permissions and add the client."
        )

    error_class = _STATUS_MAP.get(status, NettskjemaError)
    return error_class(message, status=status, field_errors=field_errors)


def to_tool_error(exc: NettskjemaError) -> ToolError:
    """
    Convert a NettskjemaError to an MCP ToolError.

    Args:
        exc: The exception to convert.

    Returns:
        A ToolError instance with the exception message.
    """
    return ToolError(str(exc))
