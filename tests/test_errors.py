"""Tests for error handling module."""

import pytest
from fastmcp.exceptions import ToolError as FastMCPToolError

from nettskjema_mcp.errors import (
    MAX_FIELD_ERROR_LENGTH,
    MAX_FIELD_ERRORS_RENDERED,
    MAX_MESSAGE_LENGTH,
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
from nettskjema_mcp.routes import load_spec


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
        "errors": {"title": ["must not be blank"]},
    }
    exc = error_for_status(400, body)
    assert exc.field_errors == {"title": ["must not be blank"]}
    assert "title" in str(exc) and "must not be blank" in str(exc)


# Every rendered error must fit this budget, whatever the backend sends. It is
# the sum of the parts: one message (MAX_MESSAGE_LENGTH plus a trim marker) and
# MAX_FIELD_ERRORS_RENDERED lines, each a field name and a message both capped at
# MAX_FIELD_ERROR_LENGTH. 1014 + 20 * 432 + the omitted-count line is ~9.7 kB.
MAX_RENDERED_ERROR_LENGTH = 10_000


def test_whole_rendered_error_fits_the_context_budget() -> None:
    """A huge backend message plus a hundred field errors stay inside the budget."""
    body = {
        "message": "x" * 50_000,
        "errors": {f"field{n}": ["y" * 500] for n in range(100)},
    }

    rendered = str(error_for_status(400, body))

    assert len(rendered) < MAX_RENDERED_ERROR_LENGTH


def test_rendered_error_budget_holds_for_long_field_names() -> None:
    """The budget survives the worst case: every name and message oversized too."""
    body = {
        "message": "x" * 50_000,
        "errors": {"n" * 2000 + str(i): ["y" * 2000] for i in range(100)},
    }

    rendered = str(error_for_status(400, body))

    assert len(rendered) < MAX_RENDERED_ERROR_LENGTH


def test_backend_message_is_bounded() -> None:
    """The backend's own message field must not bypass the excerpt cap."""
    exc = error_for_status(400, {"message": "x" * 50_000})

    rendered = str(exc)

    assert len(rendered) < MAX_MESSAGE_LENGTH + 100
    assert rendered.endswith("(truncated)")


def test_string_body_is_bounded() -> None:
    """A plain-string body is capped the same way a dict message is."""
    exc = error_for_status(502, "z" * 50_000)

    assert len(str(exc)) < MAX_MESSAGE_LENGTH + 100


def test_malformed_field_errors_do_not_crash_rendering() -> None:
    """A non-dict errors value is ignored rather than breaking __str__."""
    exc = error_for_status(400, {"message": "bad", "errors": "not a dict"})

    assert str(exc) == "bad"
    assert exc.field_errors == {}


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


def test_error_keys_are_grounded_in_the_vendored_spec() -> None:
    """
    The keys we read from error bodies must match the vendored ErrorMessage schema.

    This test prevents drift: the code reads errors and confirmForceCleanupErrors
    from response bodies, and those keys must be documented in the spec. A key
    that is not in the schema would always come back empty in production.
    """
    spec = load_spec()
    error_message_schema = spec["components"]["schemas"]["ErrorMessage"]
    properties = set(error_message_schema.get("properties", {}).keys())

    # The keys error_for_status and _field_errors read from ErrorMessage bodies
    assert "message" in properties
    assert "errors" in properties
    assert "confirmForceCleanupErrors" in properties


def test_force_cleanup_errors_are_rendered_distinctly() -> None:
    """confirmForceCleanupErrors are rendered separately with actionable guidance."""
    body = {
        "message": "Settings validation failed",
        "errors": {"title": ["must not be blank"]},
        "confirmForceCleanupErrors": {"openFrom": ["conflicts with existing data"]},
    }
    exc = error_for_status(400, body)

    rendered = str(exc)

    # Ordinary errors are rendered
    assert "title" in rendered
    assert "must not be blank" in rendered

    # Force-cleanup errors are rendered distinctly
    assert "force_cleanup=True" in rendered
    assert "openFrom" in rendered
    assert "conflicts with existing data" in rendered
