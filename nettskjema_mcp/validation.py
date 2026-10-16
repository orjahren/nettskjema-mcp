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


def _natural_sort_key(json_path: str) -> list[int | str]:
    """
    Convert a JSON path to a natural sort key.

    Array indices like $[0], $[1], $[10] are sorted numerically, not lexicographically.
    This ensures errors appear in index order: $[0], $[1], ..., $[10], not $[0], $[1], $[10], $[100], ...

    Args:
        json_path: A JSON path string like "$[0].elementType" or "/respondentGroup"

    Returns:
        A list of comparable segments where numeric segments are ints, others are strings.
    """
    segments: list[int | str] = []
    # Split on common delimiters: /, [, ], .
    for part in re.split(r"[/\[\].]", json_path):
        if not part:
            continue
        # Try to parse as int
        try:
            segments.append(int(part))
        except ValueError:
            segments.append(part)
    return segments


@lru_cache(maxsize=1)
def _build_base_registry() -> tuple[Registry[Any], dict[str, Any]]:
    """
    Build a referencing registry from the vendored OpenAPI spec.

    The registry is built lazily and cached. It resolves $ref pointers inside
    ElementDTO and FormSettingsDTO, including self-referential schemas like
    ElementDTO.subElements.

    Returns:
        A tuple of (registry, sanitized_spec) for jsonschema validation.
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
    return registry, spec_copy


@lru_cache(maxsize=128)
def _get_schema_and_registry(
    schema_name: str, partial: bool, as_array: bool
) -> tuple[dict[str, Any], Registry[Any]]:
    """
    Get a schema and registry for validation.

    Schemas are cached per (schema_name, partial, as_array) to avoid rebuilding
    them on every validation call. The returned schema dict is immutable (read-only)
    and must not be modified by callers.

    When partial=True, a modified schema with the top-level 'required' field removed
    is created and registered in a temporary document in the registry, so nested
    $refs still resolve correctly.

    Args:
        schema_name: The schema name in components/schemas.
        partial: If True, remove the top-level required constraint.
        as_array: If True, wrap the schema in an array.

    Returns:
        A tuple of (schema_dict, registry) ready for validation.

    Raises:
        ValueError: If schema_name does not exist in the spec.
    """
    registry, spec = _build_base_registry()
    schemas = spec.get("components", {}).get("schemas", {})

    if schema_name not in schemas:
        raise ValueError(
            f"Schema '{schema_name}' not found in OpenAPI spec. "
            f"Available schemas: {', '.join(sorted(schemas.keys()))}"
        )

    base_uri = "https://nettskjema.no/openapi.json"

    if partial:
        # For partial validation, create a modified schema without 'required'.
        # Wrap it in a temporary OpenAPI-like document and register it so
        # nested $refs resolve correctly.
        partial_schema = copy.deepcopy(schemas[schema_name])
        if "required" in partial_schema:
            del partial_schema["required"]

        # Create a temporary document with the partial schema
        temp_doc = {
            "components": {"schemas": {f"{schema_name}_Partial": partial_schema}},
            # Include all other schemas so nested $refs resolve
            **spec,
        }
        temp_doc["components"]["schemas"] = {
            **spec.get("components", {}).get("schemas", {}),
            f"{schema_name}_Partial": partial_schema,
        }

        # Register the temporary document
        temp_uri = f"https://nettskjema.no/partial-{schema_name}.json"
        temp_resource = Resource.from_contents(temp_doc, default_specification=DRAFT202012)
        registry = registry.with_resource(uri=temp_uri, resource=temp_resource)

        # Reference the partial schema in the temporary document
        ref = f"{temp_uri}#/components/schemas/{schema_name}_Partial"
        if as_array:
            schema = {"type": "array", "items": {"$ref": ref}}
        else:
            schema = {"$ref": ref}
    else:
        # Use a $ref to the schema in the base registry
        ref = f"{base_uri}#/components/schemas/{schema_name}"
        if as_array:
            schema = {"type": "array", "items": {"$ref": ref}}
        else:
            schema = {"$ref": ref}

    return schema, registry


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

    The prepared schema is cached per (schema_name, partial, as_array) to avoid
    rebuilding it on every call. The cache is read-only and immutable.

    Args:
        schema_name: The schema name in components/schemas (e.g., "FormSettingsDTO").
        body: The request body to validate.
        partial: If True, remove the top-level required constraint.
        as_array: If True, wrap the schema in {"type": "array", "items": <schema>}.

    Raises:
        ValueError: If schema_name does not exist in the spec.
        BadRequestError: If validation fails.
    """
    schema, registry = _get_schema_and_registry(schema_name, partial, as_array)
    validator = jsonschema.Draft202012Validator(schema, registry=registry)

    # Collect all validation errors, not just the first
    errors = list(validator.iter_errors(body))

    if not errors:
        return

    # Map each JSON pointer to its error messages, sorted naturally (numeric indices as ints)
    field_errors: dict[str, list[str]] = {}
    for error in sorted(errors, key=lambda e: _natural_sort_key(e.json_path)):
        # The JSON path is the field location (e.g., "/respondentGroup" or "$[0].elementType")
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
