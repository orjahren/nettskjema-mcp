"""Tests for error handling module."""

import pytest
from fastmcp.exceptions import ToolError as FastMCPToolError

from nettskjema_mcp.errors import (
    MAX_FIELD_ERROR_LENGTH,
    MAX_FIELD_ERRORS_RENDERED,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    MethodNotAllowedError,
    NettskjemaError,
    NotFoundError,
    PartialSuccessError,
    UpstreamError,
    error_for_status,
    to_tool_error,
)


@pytest.mark.parametrize(
    "status,cls",
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, ForbiddenError),
        (404, NotFoundError),
        (405, MethodNotAllowedError),
        (409, ConflictError),
        (502, UpstreamError),
        (207, PartialSuccessError),
    ],
)
def test_status_maps_to_exception(status: int, cls: type[NettskjemaError]) -> None:
    """HTTP status codes should map to specific exception types."""
    assert isinstance(error_for_status(status, {}), cls)


def test_field_errors_are_preserved() -> None:
    """Field-level validation errors should be extracted and preserved."""
    body = {
        "message": "Validation error",
        "errorKeysAndErrorMessages": {"title": ["must not be blank"]},
    }
    exc = error_for_status(400, body)
    assert exc.field_errors == {"title": ["must not be blank"]}
    assert "title" in str(exc) and "must not be blank" in str(exc)


def test_field_errors_are_capped_in_count() -> None:
    """Only a bounded number of field errors are rendered; the rest are counted."""
    total = MAX_FIELD_ERRORS_RENDERED + 7
    exc = BadRequestError(
        "Validation failed",
        status=400,
        field_errors={f"field{n}": ["must not be blank"] for n in range(total)},
    )

    text = str(exc)

    assert text.count(" → ") == MAX_FIELD_ERRORS_RENDERED
    assert "and 7 more field error(s) not shown." in text


def test_field_errors_are_capped_in_length() -> None:
    """A single enormous field message is trimmed rather than rendered whole."""
    exc = BadRequestError(
        "Validation failed",
        status=400,
        field_errors={"title": ["y" * 5000]},
    )

    text = str(exc)

    assert "(truncated)" in text
    assert len(text) < MAX_FIELD_ERROR_LENGTH + 100


def test_forbidden_names_the_permission_step() -> None:
    """403 errors should guide users to the permission configuration step."""
    text = str(error_for_status(403, {}))
    assert "@apiclient" in text
    assert "Editing permissions" in text


def test_unmapped_status_falls_back_to_base_error() -> None:
    """Unmapped status codes should return the base NettskjemaError."""
    assert type(error_for_status(418, {})) is NettskjemaError


def test_to_tool_error_returns_fastmcp_tool_error() -> None:
    """to_tool_error should return fastmcp.exceptions.ToolError."""
    exc = error_for_status(400, {"message": "bad request"})
    tool_error = to_tool_error(exc)
    assert isinstance(tool_error, FastMCPToolError)
    assert str(exc) in str(tool_error)
