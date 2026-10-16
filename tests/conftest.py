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


# Known legitimate exemptions from fixture validation
FIXTURE_VALIDATION_EXEMPTIONS: dict[tuple[str, str], str] = {
    # (METHOD, path) -> reason
    # Example: ("GET", "/some/route"): "Binary response with no schema"
}


def validate_response_fixture(method: str, path: str, fixture: Any) -> None:
    """
    Validate a response fixture against the vendored OpenAPI spec.

    Auto-detects content type from the spec and validates strictly: unknown
    properties are rejected, nested objects are checked recursively, and missing
    routes or schemas fail loudly rather than silently skipping.

    Args:
        method: HTTP method (upper-case: "GET", "POST", etc.)
        path: OpenAPI path with placeholders ("/form/{formId}/info")
        fixture: The response fixture to validate (dict, list, or primitive)

    Raises:
        AssertionError: If the fixture does not match the spec schema, or if
            the route/method/schema cannot be resolved

    Example:
        validate_response_fixture("GET", "/form/{formId}/info", FORM_INFO)
    """
    spec = load_spec()

    # Check if this route is exempted
    if (method, path) in FIXTURE_VALIDATION_EXEMPTIONS:
        return

    # Route must exist in spec
    assert path in spec["paths"], (
        f"{method} {path}: route not found in spec. "
        f"Check for typos or add to FIXTURE_VALIDATION_EXEMPTIONS with reason."
    )

    path_spec = spec["paths"][path]
    method_lower = method.lower()

    # Method must exist on route
    assert method_lower in path_spec, (
        f"{method} {path}: method not found on route in spec. "
        f"Available methods: {sorted(k for k in path_spec.keys() if k in {'get', 'post', 'put', 'patch', 'delete'})}"
    )

    operation = path_spec[method_lower]

    # Must have a 200 response
    assert "responses" in operation and "200" in operation["responses"], (
        f"{method} {path}: no 200 response defined in spec"
    )

    response_spec = operation["responses"]["200"]

    # Must have content (i.e., not a 204 No Content)
    assert "content" in response_spec, f"{method} {path}: response has no content (likely 204)"

    content = response_spec["content"]

    # Auto-detect content type: prefer application/json, then */* , then take the first
    content_type: str | None = None
    if "application/json" in content:
        content_type = "application/json"
    elif "*/*" in content:
        content_type = "*/*"
    elif len(content) == 1:
        content_type = list(content.keys())[0]
    else:
        # Multiple content types and neither JSON nor */* - cannot auto-detect
        raise AssertionError(
            f"{method} {path}: multiple content types in spec and cannot auto-detect. "
            f"Available: {sorted(content.keys())}"
        )

    # Content type must have a schema
    schema = content[content_type].get("schema")
    assert schema is not None, f"{method} {path}: content type {content_type} has no schema in spec"

    # Validate the fixture against the schema
    _validate_value(fixture, schema, spec, path=f"{method} {path}")


def _validate_value(value: Any, schema: dict[str, Any], spec: dict[str, Any], path: str) -> None:
    """Recursively validate a value against a schema."""
    # Resolve $ref if present
    if "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/components/schemas/"), f"{path}: unsupported $ref: {ref}"
        schema_name = ref.split("/")[-1]
        assert schema_name in spec["components"]["schemas"], (
            f"{path}: schema {schema_name} not found in spec"
        )
        schema = spec["components"]["schemas"][schema_name]

    schema_type = schema.get("type")

    if schema_type == "object":
        assert isinstance(value, dict), f"{path}: expected object, got {type(value).__name__}"
        properties = schema.get("properties", {})
        additional_properties = schema.get("additionalProperties")

        # Determine which keys are allowed
        if additional_properties is not None and additional_properties is not False:
            # additionalProperties is defined (and not False): validate all properties
            for key, val in value.items():
                if key in properties:
                    _validate_value(val, properties[key], spec, path=f"{path}.{key}")
                else:
                    # Key not in properties, validate against additionalProperties
                    _validate_value(val, additional_properties, spec, path=f"{path}.{key}")
        else:
            # additionalProperties is False or not defined: strict mode
            # Only properties defined in 'properties' are allowed
            allowed_keys = set(properties.keys())
            actual_keys = set(value.keys())
            unknown_keys = actual_keys - allowed_keys

            assert not unknown_keys, (
                f"{path}: fixture contains unknown properties: {sorted(unknown_keys)}. "
                f"Allowed properties from schema: {sorted(allowed_keys)}"
            )

            # Validate each defined property
            for key, val in value.items():
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
