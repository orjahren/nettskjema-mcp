# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Error types for Nettskjema API interactions."""

from fastmcp.exceptions import ToolError

from nettskjema_mcp.config import get_settings

# Error detail is rendered into a model's context, so it must stay bounded. A
# validation failure on a large form can carry hundreds of field errors, and a
# single message can itself be arbitrarily long.
MAX_FIELD_ERRORS_RENDERED = 20
MAX_FIELD_ERROR_LENGTH = 200

# The backend's own `message` field is the most likely place for an unbounded
# body to arrive, so it is capped here, where it is lifted out of the response.
# Deliberately larger than client.ERROR_BODY_EXCERPT_LIMIT: the client composes
# "HTTP <status> <reason> from <route>: <bounded excerpt>" and hands the result
# in as the message, and that composed string must survive intact.
MAX_MESSAGE_LENGTH = 1000


def trim_excerpt(text: str, limit: int) -> str:
    """
    Collapse whitespace and trim text to a bounded single-line excerpt.

    Args:
        text: The text to trim.
        limit: Maximum number of characters to keep.

    Returns:
        A single-line excerpt, suffixed with a marker when it was trimmed.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit]}… (truncated)"


class NettskjemaError(Exception):
    """Base exception for Nettskjema API errors."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        field_errors: dict[str, list[str]] | None = None,
        force_cleanup_errors: dict[str, list[str]] | None = None,
    ) -> None:
        """
        Initialize a Nettskjema error.

        Args:
            message: Human-readable error description.
            status: HTTP status code that triggered this error.
            field_errors: Per-field validation errors, if any.
            force_cleanup_errors: Errors that force_cleanup=True would override, if any.
        """
        super().__init__(message)
        self.message = message
        self.status = status
        self.field_errors = field_errors or {}
        self.force_cleanup_errors = force_cleanup_errors or {}

    def __str__(self) -> str:
        """
        Render the error with field-level detail, bounded.

        Field errors come from the backend and are otherwise unbounded in both
        count and length, so they are capped the same way response-body excerpts
        are. Anything left out is counted rather than silently dropped.

        Force-cleanup errors are rendered separately after ordinary errors, as
        they are actionable: a model that sees them knows there is a retry available
        with force_cleanup=True.
        """
        parts = [self.message]
        rendered = 0
        omitted = 0
        for field, errors in self.field_errors.items():
            for error in errors:
                if rendered >= MAX_FIELD_ERRORS_RENDERED:
                    omitted += 1
                    continue
                name = trim_excerpt(str(field), MAX_FIELD_ERROR_LENGTH)
                detail = trim_excerpt(str(error), MAX_FIELD_ERROR_LENGTH)
                parts.append(f"{name} → {detail}")
                rendered += 1
        if omitted:
            parts.append(f"… and {omitted} more field error(s) not shown.")

        # Render force-cleanup errors distinctly, sharing the same cap
        if self.force_cleanup_errors:
            parts.append("The following errors can be overridden with force_cleanup=True:")
            for field, errors in self.force_cleanup_errors.items():
                for error in errors:
                    if rendered >= MAX_FIELD_ERRORS_RENDERED:
                        omitted += 1
                        continue
                    name = trim_excerpt(str(field), MAX_FIELD_ERROR_LENGTH)
                    detail = trim_excerpt(str(error), MAX_FIELD_ERROR_LENGTH)
                    parts.append(f"{name} → {detail}")
                    rendered += 1

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


def _extract_field_errors(errors_obj: object) -> dict[str, list[str]]:
    """
    Extract per-field errors from an ErrorMessage.errors object.

    The vendored spec documents errors as an object with additionalProperties
    mapping field names to arrays of error messages. The spec also shows two
    special properties (empty, all) that are not field errors and must be skipped.

    Args:
        errors_obj: The errors value from an ErrorMessage response body.

    Returns:
        A dict mapping field names to arrays of error messages. Empty if the
        value is not a dict or contains no valid field errors.
    """
    if not isinstance(errors_obj, dict):
        return {}

    field_errors: dict[str, list[str]] = {}
    for key, value in errors_obj.items():
        # Skip the spec's special properties that are not field errors
        if key in ("empty", "all"):
            continue
        # Only include entries whose value is a list of strings
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            field_errors[key] = value

    return field_errors


def error_for_success_body(where: str, status: int, body: object) -> PartialSuccessError | None:
    """
    Build the error for a clean 2xx whose body reports that the change was rejected.

    A few routes declare their success response as ErrorMessage: the status only
    says the request was understood, and the body says whether anything was
    applied. ``error_for_status`` cannot fire on them, because nothing about the
    status is wrong — 207 is the only 2xx it treats as a failure, and these
    answer 200. Without this check the rejection is handed to the model as an
    ordinary result and reads as success.

    An absent or empty ``errors`` on such a route is a genuine success and stays
    one. The predicate is "carries at least one real field error", not "has an
    errors key": ``_extract_field_errors`` already drops the Spring MultiValueMap
    artefacts (``empty``, ``all``) and any value that is not a list of strings,
    so ``{"errors": {"empty": true}}`` and ``{"errors": {}}`` both pass.

    Args:
        where: The route, as "<METHOD> <path>", for the message.
        status: The HTTP status actually received.
        body: The decoded response body.

    Returns:
        A PartialSuccessError when the body reports field errors, otherwise None.
    """
    if not isinstance(body, dict):
        return None

    field_errors = _extract_field_errors(body.get("errors")) or None
    force_cleanup_errors = _extract_field_errors(body.get("confirmForceCleanupErrors")) or None
    if field_errors is None and force_cleanup_errors is None:
        return None

    raw_message = body.get("message")
    detail = (
        trim_excerpt(str(raw_message), MAX_MESSAGE_LENGTH)
        if raw_message
        else "the response carried no message"
    )
    return PartialSuccessError(
        f"{where} answered HTTP {status}, but its body reports that the change was not "
        f"applied: {detail}",
        status=status,
        field_errors=field_errors,
        force_cleanup_errors=force_cleanup_errors,
    )


def error_for_status(status: int, body: object) -> NettskjemaError:
    """
    Create an appropriate exception for an HTTP error response.

    The message is bounded here rather than at the call site, because this is the
    one point every error body passes through on its way into an exception.

    Args:
        status: HTTP status code.
        body: Response body (dict, str, or None).

    Returns:
        A NettskjemaError subclass instance appropriate for the status code.
    """
    message = "Request failed"
    field_errors: dict[str, list[str]] | None = None
    force_cleanup_errors: dict[str, list[str]] | None = None

    # Extract message and field errors from body if it's a dict
    if isinstance(body, dict):
        raw_message = body.get("message")
        if raw_message:
            message = trim_excerpt(str(raw_message), MAX_MESSAGE_LENGTH)

        # Extract field errors from the errors object (ErrorMessage schema)
        errors_obj = body.get("errors")
        if errors_obj is not None:
            field_errors = _extract_field_errors(errors_obj)
            if not field_errors:
                field_errors = None

        # Extract force-cleanup errors (ErrorMessage.confirmForceCleanupErrors)
        cleanup_obj = body.get("confirmForceCleanupErrors")
        if cleanup_obj is not None:
            force_cleanup_errors = _extract_field_errors(cleanup_obj)
            if not force_cleanup_errors:
                force_cleanup_errors = None

    elif isinstance(body, str):
        message = trim_excerpt(body, MAX_MESSAGE_LENGTH)

    # Special handling for 403: guide users to permission settings
    if status == 403:
        client_id = get_settings().client_id or "<client_id>"
        message = (
            f"Access forbidden. Ensure {client_id}@apiclient has the required "
            "permissions in Nettskjema. Go to the form → Settings → Permissions → "
            "Editing permissions and add the client."
        )

    error_class = _STATUS_MAP.get(status, NettskjemaError)
    return error_class(
        message, status=status, field_errors=field_errors, force_cleanup_errors=force_cleanup_errors
    )


def to_tool_error(exc: NettskjemaError) -> ToolError:
    """
    Convert a NettskjemaError to an MCP ToolError.

    Args:
        exc: The exception to convert.

    Returns:
        A ToolError instance with the exception message.
    """
    return ToolError(str(exc))
