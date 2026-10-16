"""Payload validation against vendored OpenAPI schemas."""

import copy
import re
from functools import lru_cache
from typing import Any

import jsonschema  # type: ignore[import-untyped]
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from nettskjema_mcp.errors import BadRequestError
from nettskjema_mcp.routes import load_spec


def _sanitize_schema_for_python_re(schema: dict[str, Any]) -> None:
    r"""
    Remove pattern constraints that use regex features unsupported by Python's re module.

    OpenAPI schemas may contain PCRE patterns with features like \p{L} (Unicode properties)
    that Python's re module doesn't support. We remove these patterns to avoid validation
    errors. The backend will still validate these patterns, so this is a quality-of-life
    fix for local validation, not a correctness issue.

    Args:
        schema: The schema dict to sanitize (will be mutated in place).
    """

    def has_unsupported_pattern(pattern: str) -> bool:
        """Check if a pattern contains features unsupported by Python re."""
        # Test for Unicode property escapes like \p{L}, \P{L}
        if r"\p{" in pattern or r"\P{" in pattern:
            return True
        # Try to compile it - if it fails, it's unsupported
        try:
            re.compile(pattern)
            return False
        except re.error:
            return True

    def walk(obj: Any) -> None:
        """Recursively walk the schema and remove unsupported patterns."""
        if isinstance(obj, dict):
            if "pattern" in obj and isinstance(obj["pattern"], str):
                if has_unsupported_pattern(obj["pattern"]):
                    # Remove the unsupported pattern - the backend will still validate it
                    del obj["pattern"]
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(schema)


@lru_cache(maxsize=1)
def _build_registry() -> Registry[Any]:
    """
    Build a referencing registry from the vendored OpenAPI spec.

    The registry is built lazily and cached. It resolves $ref pointers inside
    ElementDTO and FormSettingsDTO, including self-referential schemas like
    ElementDTO.subElements.

    Returns:
        A referencing Registry for jsonschema validation.
    """
    spec = load_spec()

    # Deep copy the spec so we can sanitize it without mutating the cached version
    spec_copy = copy.deepcopy(spec)

    # Remove unsupported regex patterns from all schemas
    schemas = spec_copy.get("components", {}).get("schemas", {})
    for schema in schemas.values():
        _sanitize_schema_for_python_re(schema)

    # Use a base URI for the spec
    base_uri = "https://nettskjema.no/openapi.json"

    # Create a resource from the full spec
    resource = Resource.from_contents(spec_copy, default_specification=DRAFT202012)

    # Build registry with the full spec anchored at base_uri
    registry: Registry[Any] = Registry().with_resource(uri=base_uri, resource=resource)
    return registry


def validate_body(
    schema_name: str,
    body: object,
    *,
    partial: bool = False,
    as_array: bool = False,
) -> None:
    """
    Validate a request body against a vendored OpenAPI schema.

    When partial=True, the top-level required constraint is removed so that
    PATCH endpoints can accept bodies with only a subset of fields. Nested
    objects are not affected: if a nested object appears in a partial body, it
    is validated as a complete object. This matches the Nettskjema API's own
    behavior — partial updates target specific top-level fields, and any nested
    object that is supplied is replaced whole.

    Args:
        schema_name: The schema name in components/schemas (e.g., "FormSettingsDTO").
        body: The request body to validate.
        partial: If True, remove the top-level required constraint.
        as_array: If True, wrap the schema in {"type": "array", "items": <schema>}.

    Raises:
        ValueError: If schema_name does not exist in the spec.
        BadRequestError: If validation fails.
    """
    spec = load_spec()
    schemas = spec.get("components", {}).get("schemas", {})

    if schema_name not in schemas:
        raise ValueError(
            f"Schema '{schema_name}' not found in OpenAPI spec. "
            f"Available schemas: {', '.join(sorted(schemas.keys()))}"
        )

    # Build the schema to validate against
    # Use a $ref to the schema in the registry so nested $refs resolve correctly
    schema: dict[str, Any] = {
        "$ref": f"https://nettskjema.no/openapi.json#/components/schemas/{schema_name}"
    }

    if partial:
        # For partial validation, we need to modify the schema to remove required.
        # We can't use a $ref here, so we copy the schema and modify it.
        schema_def = copy.deepcopy(schemas[schema_name])
        _sanitize_schema_for_python_re(schema_def)
        if "required" in schema_def:
            del schema_def["required"]
        schema = schema_def

    if as_array:
        # Wrap in array schema
        if partial:
            # We already have the unwrapped schema
            schema = {"type": "array", "items": schema}
        else:
            # Use a ref for the items
            schema = {
                "type": "array",
                "items": {
                    "$ref": f"https://nettskjema.no/openapi.json#/components/schemas/{schema_name}"
                },
            }

    # Build the registry and validate
    registry = _build_registry()
    validator = jsonschema.Draft202012Validator(schema, registry=registry)

    # Collect all validation errors, not just the first
    errors = list(validator.iter_errors(body))

    if not errors:
        return

    # Map each JSON pointer to its error messages, sorted deterministically
    field_errors: dict[str, list[str]] = {}
    for error in sorted(errors, key=lambda e: e.json_path):
        # The JSON path is the field location (e.g., "/respondentGroup" or "/0/elementType")
        path = error.json_path or "/"

        # Build a clear error message depending on the validation failure
        if error.validator == "enum":
            allowed = ", ".join(repr(v) for v in error.validator_value)
            message = f"must be one of: {allowed}"
        elif error.validator == "type":
            expected = error.validator_value
            message = f"must be of type {expected}"
        elif error.validator == "required":
            missing = error.validator_value
            message = f"missing required field(s): {', '.join(missing)}"
        elif error.validator == "additionalProperties":
            message = f"unknown field: {error.message}"
        else:
            message = error.message

        field_errors.setdefault(path, []).append(message)

    raise BadRequestError(
        "Validation failed",
        field_errors=field_errors,
    )
