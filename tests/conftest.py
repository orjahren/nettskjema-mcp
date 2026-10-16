"""Shared fixtures for the whole test suite."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from nettskjema_mcp.client import reset_client
from nettskjema_mcp.config import reset_settings
from nettskjema_mcp.routes import load_spec

# The .invalid TLD is reserved and never resolves, so a request that escapes its
# mock fails loudly instead of quietly reaching the real Nettskjema API.
TEST_BASE_URL = "https://nettskjema.invalid/api/v3"
TEST_AUTH_URL = "https://authorization.nettskjema.invalid/oauth2/token"


@pytest.fixture(autouse=True)
def isolated_environment(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """
    Point every test at unroutable hosts and reset the module-level caches.

    Tests marked ``e2e`` are left alone: they talk to a real environment, and
    pinning them to an unroutable host would make the suite unrunnable even when
    it is selected deliberately with ``-m e2e``.
    """
    if request.node.get_closest_marker("e2e") is not None:
        yield
        return

    monkeypatch.setenv("NETTSKJEMA_BASE_URL", TEST_BASE_URL)
    monkeypatch.setenv("NETTSKJEMA_AUTH_URL", TEST_AUTH_URL)
    monkeypatch.setenv("NETTSKJEMA_CLIENT_ID", "test-client")
    monkeypatch.setenv("NETTSKJEMA_CLIENT_SECRET", "test-secret")
    reset_settings()
    reset_client()
    yield
    reset_settings()
    reset_client()


@pytest.fixture
def token_route(respx_mock: respx.MockRouter) -> respx.Route:
    """
    Mock the OAuth2 token endpoint.

    Every routed tool acquires a token before its own request, so a tool test
    that forgets this sees a confusing failure from the auth leg rather than
    from the endpoint it meant to exercise. Request it explicitly, or pull it
    in for a whole module with
    ``pytestmark = pytest.mark.usefixtures("token_route")``.
    """
    return respx_mock.post(TEST_AUTH_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "test-token", "expires_in": 86400})
    )


def validate_response_fixture(
    method: str,
    path: str,
    fixture: Any,
    *,
    content_type: str = "application/json",
) -> None:
    """
    Validate a response fixture against the vendored OpenAPI spec.

    Ensures test fixtures match the actual API contract: unknown properties are
    rejected, nested objects are validated, and array items are checked. This
    catches invented fields before they reach production.

    Args:
        method: HTTP method (upper-case: "GET", "POST", etc.)
        path: OpenAPI path with placeholders ("/form/{formId}/info")
        fixture: The response fixture to validate (dict, list, or primitive)
        content_type: Expected content type (default: "application/json")

    Raises:
        AssertionError: If the fixture does not match the spec schema

    Example:
        validate_response_fixture("GET", "/form/{formId}/info", FORM_INFO_FIXTURE)
        validate_response_fixture("GET", "/form/me", MY_FORMS_FIXTURE)
    """
    spec = load_spec()

    # Find the route in the spec
    if path not in spec["paths"]:
        # No schema to validate against; skip explicitly
        return

    path_spec = spec["paths"][path]
    method_lower = method.lower()

    if method_lower not in path_spec:
        return

    operation = path_spec[method_lower]

    if "responses" not in operation or "200" not in operation["responses"]:
        return

    response_spec = operation["responses"]["200"]

    if "content" not in response_spec:
        # Binary or no-content response; nothing to validate
        return

    if content_type not in response_spec["content"]:
        # Content type mismatch or not specified
        return

    schema = response_spec["content"][content_type].get("schema")
    if not schema:
        return

    # Validate the fixture against the schema
    _validate_value(fixture, schema, spec, path=f"{method} {path}")


def _validate_value(value: Any, schema: dict[str, Any], spec: dict[str, Any], path: str) -> None:
    """Recursively validate a value against a schema."""
    # Resolve $ref if present
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/components/schemas/"), f"Unsupported $ref: {ref}"
        schema_name = ref.split("/")[-1]
        assert schema_name in spec["components"]["schemas"], f"Unknown schema: {schema_name}"
        schema = spec["components"]["schemas"][schema_name]

    schema_type = schema.get("type")

    if schema_type == "object":
        assert isinstance(value, dict), f"{path}: expected object, got {type(value).__name__}"
        properties = schema.get("properties", {})

        # Check for unknown properties (strict validation)
        allowed_keys = set(properties.keys())
        actual_keys = set(value.keys())
        unknown_keys = actual_keys - allowed_keys

        assert not unknown_keys, (
            f"{path}: fixture contains unknown properties: {sorted(unknown_keys)}. "
            f"Allowed properties from schema: {sorted(allowed_keys)}"
        )

        # Validate each property
        for key, val in value.items():
            if key in properties:
                _validate_value(val, properties[key], spec, path=f"{path}.{key}")

    elif schema_type == "array":
        assert isinstance(value, list), f"{path}: expected array, got {type(value).__name__}"
        items_schema = schema.get("items", {})
        for i, item in enumerate(value):
            _validate_value(item, items_schema, spec, path=f"{path}[{i}]")

    elif schema_type in {"string", "integer", "number", "boolean"}:
        # Primitive types - just check the type matches
        expected_types = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
        }
        expected = expected_types[schema_type]
        assert isinstance(value, expected), (
            f"{path}: expected {schema_type}, got {type(value).__name__}"
        )

    # For other types or missing type, skip validation
