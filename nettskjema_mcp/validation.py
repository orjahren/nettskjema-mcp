"""Payload validation against vendored OpenAPI schemas."""

import copy
import difflib
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
    schema_name: str, partial: bool, as_array: bool, strict: bool
) -> tuple[dict[str, Any], Registry[Any]]:
    """
    Get a schema and registry for validation.

    Schemas are cached per (schema_name, partial, as_array, strict) to avoid
    rebuilding them on every validation call. The returned schema dict is
    immutable (read-only) and must not be modified by callers.

    When strict=True, additionalProperties: false is injected at the top level so
    unknown keys are rejected. This catches typos and flags fields that are newer
    than the vendored spec snapshot. Top level only: nested $ref'd schemas are not
    modified, where the constraint is far likelier to be wrong. When strict=False
    the schema is used as the spec writes it, which is what a payload that may be
    round-tripped from the API needs — see validate_body.

    When partial=True, the top-level required constraint is also removed so that
    PATCH endpoints can accept bodies with only a subset of fields.

    Args:
        schema_name: The schema name in components/schemas.
        partial: If True, remove the top-level required constraint.
        as_array: If True, wrap the schema in an array.
        strict: If True, reject keys the schema does not declare.

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

    modified_schema = copy.deepcopy(schemas[schema_name])

    if strict:
        # Reject unknown keys at the top level
        modified_schema["additionalProperties"] = False

    if partial:
        # For partial validation, also remove the required constraint
        if "required" in modified_schema:
            del modified_schema["required"]

    # Create a temporary document with the modified schema. The suffix names
    # every variant distinctly, so two variants of one schema cannot collide on
    # the registry URI.
    suffix = f"_{'Partial' if partial else 'Full'}{'Strict' if strict else 'Open'}"
    temp_doc = {
        "components": {"schemas": {f"{schema_name}{suffix}": modified_schema}},
        # Include all other schemas so nested $refs resolve
        **spec,
    }
    temp_doc["components"]["schemas"] = {
        **spec.get("components", {}).get("schemas", {}),
        f"{schema_name}{suffix}": modified_schema,
    }

    # Register the temporary document
    temp_uri = f"https://nettskjema.no/{schema_name.lower()}{suffix.lower()}.json"
    temp_resource = Resource.from_contents(temp_doc, default_specification=DRAFT202012)
    registry = registry.with_resource(uri=temp_uri, resource=temp_resource)

    # Reference the modified schema in the temporary document
    ref = f"{temp_uri}#/components/schemas/{schema_name}{suffix}"
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
    strict: bool = True,
) -> None:
    """
    Validate a request body against a vendored OpenAPI schema.

    By default unknown keys are rejected locally to catch typos and flag fields
    that are newer than the vendored spec snapshot. The error message names close
    matches among the schema's real property names, turning a typo into an
    instant fix and a stale snapshot into a legible complaint instead of a dead
    end.

    Pass strict=False for a payload the caller may have read back from the API.
    Rejecting a key the API itself produced is worse than not checking at all:
    the caller cannot remove a field it never wrote, so the only way past the
    validator would be to drop data the server sent — which a whole-list write
    would then delete. Element payloads are the case this exists for; flat
    settings objects, which the caller always composes itself, stay strict.
    Everything else in the schema — types, enums, required fields, lengths — is
    checked either way.

    When partial=True, the top-level required constraint is removed so that
    PATCH endpoints can accept bodies with only a subset of fields. Nested
    objects are not affected: if a nested object appears in a partial body, it
    is validated as a complete object. This matches the Nettskjema API's own
    behavior — partial updates target specific top-level fields, and any nested
    object that is supplied is replaced whole.

    The prepared schema is cached per (schema_name, partial, as_array, strict)
    to avoid rebuilding it on every call. The cache is read-only and immutable.

    Args:
        schema_name: The schema name in components/schemas (e.g., "FormSettingsDTO").
        body: The request body to validate.
        partial: If True, remove the top-level required constraint.
        as_array: If True, wrap the schema in {"type": "array", "items": <schema>}.
        strict: If False, accept keys the vendored schema does not declare.

    Raises:
        ValueError: If schema_name does not exist in the spec.
        BadRequestError: If validation fails.
    """
    schema, registry = _get_schema_and_registry(schema_name, partial, as_array, strict)
    validator = jsonschema.Draft202012Validator(schema, registry=registry)

    # Collect all validation errors, not just the first
    errors = list(validator.iter_errors(body))

    if not errors:
        return

    # Get the base schema's properties for close-match suggestions
    spec = load_spec()
    base_schema = spec.get("components", {}).get("schemas", {}).get(schema_name, {})
    properties = list(base_schema.get("properties", {}).keys())

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
            # Extract the unknown field name from the error message
            # The message is typically "Additional properties are not allowed ('fieldName' was unexpected)"
            unknown_field = None
            if "'" in error.message:
                parts = error.message.split("'")
                if len(parts) >= 2:
                    unknown_field = parts[1]

            # Name the offending key. The JSON path only locates the object that
            # contained it — on an array that is just "$[0]" — so without this a
            # novel field name never appears anywhere in the error, and only a
            # near-miss typo is legible through the suggestions below.
            named = f"{unknown_field!r} is " if unknown_field else ""
            message = f"{named}not in the vendored {schema_name} schema snapshot"
            if unknown_field and properties:
                # Suggest close matches
                matches = difflib.get_close_matches(unknown_field, properties, n=3, cutoff=0.6)
                if matches:
                    suggestions = ", ".join(repr(m) for m in matches)
                    message += f"; did you mean {suggestions}?"
        elif error.validator in ("pattern", "maxLength", "minLength"):
            # These validators embed the failing instance in their default message.
            # Build the message from the keyword and path only, to avoid leaking
            # credential values when a token field later gains such a constraint.
            message = f"failed the {error.validator} constraint"
        else:
            message = error.message

        field_errors.setdefault(path, []).append(message)

    raise BadRequestError(
        "Validation failed",
        field_errors=field_errors,
    )
