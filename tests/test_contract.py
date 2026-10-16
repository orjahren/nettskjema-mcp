"""Contract tests between our tool declarations and the OpenAPI spec."""

import json
import re
from collections.abc import Awaitable, Callable

import httpx
import jsonschema
import pytest
import respx

from nettskjema_mcp.enums import (
    AnswerType,
    DateFormat,
    DeliveryDestination,
    EditorsSubmissionEmailType,
    ElementType,
    FormType,
    LinearScaleType,
    NationalIdNumberType,
    RespondentGroup,
    ScoreResultDisplayType,
)
from nettskjema_mcp.routes import LOCAL_TOOLS, OUT_OF_SCOPE, REGISTRY, Route, endpoint, load_spec
from nettskjema_mcp.tools.admin import activate_educloud, activate_tsd, upload_image
from nettskjema_mcp.tools.attachments import retranscribe_attachment
from nettskjema_mcp.tools.elements import replace_form_elements, update_form_element
from nettskjema_mcp.tools.exports import upload_codebook
from nettskjema_mcp.tools.forms import create_form, delete_forms, update_form_settings
from nettskjema_mcp.tools.submissions import (
    delete_submissions,
    submit_form,
    submit_form_for_invitation,
)


def _spec_enum(spec: dict[str, object], schema: str, prop: str) -> list[str]:
    """Extract enum values from a schema property, following items.enum for arrays."""
    schemas = spec.get("components", {}).get("schemas", {})  # type: ignore[union-attr]
    schema_obj = schemas.get(schema, {})  # type: ignore[union-attr]
    properties = schema_obj.get("properties", {})  # type: ignore[union-attr]
    prop_obj = properties.get(prop, {})  # type: ignore[union-attr]

    # Follow items.enum for arrays
    if "items" in prop_obj:
        return prop_obj["items"].get("enum", [])  # type: ignore[union-attr]

    return prop_obj.get("enum", [])  # type: ignore[union-attr]


ENUM_LOCATIONS = [
    (ElementType, "ElementDTO", "elementType"),
    (FormType, "FormSettingsDTO", "formType"),
    (RespondentGroup, "FormSettingsDTO", "respondentGroup"),
    (DeliveryDestination, "FormSettingsDTO", "deliveryDestination"),
    (AnswerType, "ClientAnswerDTO", "type"),
    (DateFormat, "ElementDTO", "dateFormat"),
    (LinearScaleType, "ElementDTO", "linearScaleType"),
    (NationalIdNumberType, "ElementDTO", "nationalIdNumberType"),
    (ScoreResultDisplayType, "FormSettingsDTO", "scoreResultDisplayType"),
    (EditorsSubmissionEmailType, "FormSettingsDTO", "editorsSubmissionEmailType"),
]


def test_every_registered_route_exists_in_the_spec() -> None:
    """Verify all registered routes exist in the vendored OpenAPI spec."""
    spec = load_spec()
    for tool, routes in REGISTRY.items():
        for r in routes:
            assert r.path in spec["paths"], f"{tool}: unknown path {r.path}"  # type: ignore[operator]
            assert r.method.lower() in spec["paths"][r.path], f"{tool}: {r}"  # type: ignore[index]


def test_out_of_scope_holds_exactly_the_four_v1_invitation_operations() -> None:
    """Verify OUT_OF_SCOPE contains exactly the four v1 invitation endpoints."""
    assert set(OUT_OF_SCOPE) == {
        ("GET", "/form/{formId}/invitations"),
        ("POST", "/form/{formId}/invitations"),
        ("DELETE", "/form/{formId}/invitations"),
        ("DELETE", "/form/{formId}/invitation"),
    }
    assert all(reason for reason in OUT_OF_SCOPE.values())


def test_spec_snapshot_is_the_production_surface() -> None:
    """Verify the vendored spec has the expected number of paths and operations."""
    spec = load_spec()
    assert len(spec["paths"]) == 36  # type: ignore[arg-type]
    assert (
        sum(
            1
            for p in spec["paths"].values()  # type: ignore[union-attr]
            for m in p  # type: ignore[union-attr]
            if m in {"get", "post", "put", "patch", "delete"}
        )
        == 42
    )


@pytest.mark.parametrize("enum_cls,schema,prop", ENUM_LOCATIONS)
def test_enum_members_match_the_spec(enum_cls: type, schema: str, prop: str) -> None:
    """Verify enum members match the spec definition."""
    declared = _spec_enum(load_spec(), schema, prop)
    assert [e.value for e in enum_cls] == declared  # type: ignore[attr-defined]


def test_endpoint_duplicate_registration_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that registering the same tool name twice raises ValueError."""
    # Use a fresh registry to avoid polluting the global one
    test_registry: dict[str, tuple[Route, ...]] = {}
    monkeypatch.setattr("nettskjema_mcp.routes.REGISTRY", test_registry)

    # First registration succeeds
    @endpoint(Route("GET", "/test"))
    def my_tool() -> None:
        pass

    assert "my_tool" in test_registry

    # Second registration with the same name fails
    with pytest.raises(ValueError, match="my_tool"):

        @endpoint(Route("POST", "/other"))
        def my_tool() -> None:  # noqa: F811
            pass


def test_load_spec_returns_cached_identity() -> None:
    """Verify load_spec() returns the same cached object (read-only contract)."""
    # The spec is cached and shared — callers must not mutate it.
    # See load_spec() docstring for the read-only contract.
    assert load_spec() is load_spec()


def test_every_in_scope_operation_has_a_tool() -> None:
    """Verify every in-scope operation is covered by a tool."""
    spec = load_spec()
    covered = {(r.method, r.path) for routes in REGISTRY.values() for r in routes}
    declared = {
        (m.upper(), p)
        for p, item in spec["paths"].items()  # type: ignore[union-attr]
        for m in item  # type: ignore[union-attr]
        if m in {"get", "post", "put", "patch", "delete"}
    }
    assert declared - covered - set(OUT_OF_SCOPE) == set()


def test_the_surface_is_the_expected_size() -> None:
    """
    Verify the surface has exactly 38 tools: 37 routed + check_auth_status.

    get_attachment_transcription covers three operations with one tool, and
    update_form_element reuses two element routes rather than adding any.
    Operation coverage is 38 and is checked by
    test_every_in_scope_operation_has_a_tool above.
    """
    assert len(REGISTRY) + len(LOCAL_TOOLS) == 38, (
        f"Tool surface changed: {len(REGISTRY)} routed + {len(LOCAL_TOOLS)} local = "
        f"{len(REGISTRY) + len(LOCAL_TOOLS)}. If this is deliberate, confirm the new operation "
        "is in the spec and update this count and the docstring's derivation. If not, a tool was "
        "added or lost by accident."
    )


def test_out_of_scope_operations_have_no_tool() -> None:
    """Verify out-of-scope operations are not covered by any tool."""
    covered = {(r.method, r.path) for routes in REGISTRY.values() for r in routes}
    assert covered.isdisjoint(OUT_OF_SCOPE)


def test_no_tool_targets_a_private_path() -> None:
    """Verify no tool declares a route starting with /private."""
    assert not [r for routes in REGISTRY.values() for r in routes if r.path.startswith("/private")]


def _resolve_schema_refs(
    schema: dict[str, object], spec: dict[str, object], seen: set[str] | None = None
) -> dict[str, object]:
    """
    Recursively resolve $ref pointers in a schema.

    Args:
        schema: The schema to resolve.
        spec: The full OpenAPI spec containing components.
        seen: Set of schema names already being resolved (cycle guard).

    Returns:
        The resolved schema with all $refs replaced by their definitions.

    Raises:
        ValueError: If a circular reference is detected.
    """
    if seen is None:
        seen = set()

    if "$ref" in schema:
        ref = schema["$ref"]
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            schema_name = ref.split("/")[-1]
            if schema_name in seen:
                raise ValueError(
                    f"Circular reference detected: {schema_name} is part of a reference cycle"
                )
            components = spec.get("components", {})
            if isinstance(components, dict):
                schemas = components.get("schemas", {})
                if isinstance(schemas, dict):
                    resolved = schemas.get(schema_name)
                    if isinstance(resolved, dict):
                        return _resolve_schema_refs(dict(resolved), spec, seen | {schema_name})
        return schema

    # Recursively resolve refs in nested schemas
    result = dict(schema)
    for key, value in schema.items():
        if isinstance(value, dict):
            result[key] = _resolve_schema_refs(value, spec, seen)
        elif isinstance(value, list):
            result[key] = [
                _resolve_schema_refs(item, spec, seen) if isinstance(item, dict) else item
                for item in value
            ]
    return result


def _remove_unsupported_constraints(
    schema: dict[str, object], is_partial: bool = False
) -> dict[str, object]:
    """
    Recursively remove constraints Python's re module cannot handle.

    Some patterns in the OpenAPI spec use PCRE syntax (\\p{L} for Unicode
    categories) that Python's re module does not support. This removes only those
    patterns that fail re.compile, preserving the rest.

    Note: This matches on key name anywhere in the tree, so a schema with a
    property literally named "pattern" or "required" would lose it. No schema in
    the current snapshot has one.

    Args:
        schema: The schema to clean.
        is_partial: If True, remove the top-level `required` constraint only.

    Returns:
        The schema with unsupported `pattern` constraints removed, and optionally
        the top-level `required` removed for PATCH.
    """
    result = {}
    for key, value in schema.items():
        if key == "pattern" and isinstance(value, str):
            # Skip only patterns that Python's re module cannot compile
            try:
                re.compile(value)
                result[key] = value  # Pattern compiles; keep it
            except re.error:
                continue  # Pattern fails; strip it
        elif key == "required" and is_partial:
            # Skip required constraints for partial updates (PATCH), top-level only
            continue
        elif isinstance(value, dict):
            # Don't propagate is_partial to nested objects
            result[key] = _remove_unsupported_constraints(value, False)
        elif isinstance(value, list):
            result[key] = [
                _remove_unsupported_constraints(item, False) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def _request_schema(spec: dict[str, object], route: Route) -> dict[str, object] | None:
    """
    Extract the request body schema for a route, or None if it has none.

    Args:
        spec: The vendored OpenAPI spec.
        route: The route to look up.

    Returns:
        The request body schema dict with $refs resolved and unsupported
        constraints removed, or None if the operation declares no requestBody.
    """
    paths = spec.get("paths", {})  # type: ignore[union-attr]
    if not isinstance(paths, dict):
        return None
    operation = paths.get(route.path, {}).get(route.method.lower(), {})  # type: ignore[union-attr]
    if not isinstance(operation, dict):
        return None
    request_body = operation.get("requestBody", {})
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content", {})
    if not isinstance(content, dict):
        return None
    json_content = content.get("application/json", {})
    if not isinstance(json_content, dict):
        return None
    schema = json_content.get("schema")
    if not isinstance(schema, dict):
        return None
    resolved = _resolve_schema_refs(dict(schema), spec)
    # PATCH operations send partial updates, so remove required constraints
    is_partial = route.method == "PATCH"
    return _remove_unsupported_constraints(resolved, is_partial)


# Routes that declare a request body but are deliberately excluded from
# schema validation tests, with reasons.
BODY_VALIDATION_EXEMPT: dict[tuple[str, str], str] = {
    ("DELETE", "/form/{formId}/submissions"): (
        "delete_all_submissions declares an optional request body but the tool "
        "sends none. An argument that looks like it narrows a deletion but may not "
        "is the worst affordance this API offers, so the tool exposes no id parameter."
    ),
}

# WRITE_TOOL_CASES: one (callable, kwargs, Route) row per tool that sends a
# JSON request body. 13 rows covering create_form, delete_forms,
# update_form_settings, replace_form_elements, update_form_element, submit_form,
# submit_form_for_invitation, delete_submissions, upload_codebook,
# retranscribe_attachment, activate_tsd, activate_educloud, upload_image.
# delete_all_submissions is deliberately absent (see BODY_VALIDATION_EXEMPT).
# upload_submission_attachment is excluded because PUT
# /form/submission/{submissionId}/attachment declares no requestBody key in the
# spec at all — it is all query parameters despite uploading a file. The
# attachment upload's body can never be checked by this test, no matter what the
# tool sends, because the spec declares nothing to check it against.
WRITE_TOOL_CASES = [
    (
        create_form,
        {
            "title": "Test Form",
            "language_code": "en",
            "form_type": FormType.DEFAULT,
            "respondent_group": RespondentGroup.FEIDE,
            "collects_personal_data": False,
            "sensitive_personal_data_collected": False,
        },
        Route("POST", "/form"),
    ),
    (
        delete_forms,
        {"form_ids": [1, 2]},
        Route("DELETE", "/form"),
    ),
    (
        update_form_settings,
        {"form_id": 1, "settings": {"title": "Updated"}},
        Route("PATCH", "/form/{formId}/settings"),
    ),
    (
        replace_form_elements,
        {
            "form_id": 1,
            "elements": [{"elementType": "TEXT", "questionText": "Q1"}],
        },
        Route("PUT", "/form/{formId}/elements"),
    ),
    (
        update_form_element,
        {
            "form_id": 1,
            "element_id": 1,
            "changes": {"questionText": "Updated Q1"},
        },
        Route("PUT", "/form/{formId}/elements"),
    ),
    (
        submit_form,
        {
            "form_id": 1,
            "answers": [{"type": "TEXT", "questionId": 1, "text": "Answer"}],
        },
        Route("POST", "/form/{formId}/submission"),
    ),
    (
        submit_form_for_invitation,
        {
            "invitation_id": 1,
            "answers": [{"type": "TEXT", "questionId": 1, "text": "Answer"}],
        },
        Route("POST", "/form/invitation/{invitationId}/submission"),
    ),
    (
        delete_submissions,
        {"form_id": 1, "submission_ids": [1, 2]},
        Route("DELETE", "/form/{formId}/submission"),
    ),
    (
        upload_codebook,
        {
            "form_id": 1,
            "element_ids_and_external_element_ids_map": {},
            "sub_element_ids_and_external_element_ids_map": {},
            "answer_option_ids_and_external_answer_option_ids_map": {},
        },
        Route("PUT", "/form/{formId}/codebook"),
    ),
    (
        retranscribe_attachment,
        {
            "answer_attachment_id": 1,
            "model": "model_auto",
        },
        Route("POST", "/submission/attachment/{answerAttachmentId}/retranscribe"),
    ),
    (
        activate_tsd,
        {"form_id": 1, "project_name": "test-project", "token": "test-token"},
        Route("POST", "/form/{formId}/activate/tsd"),
    ),
    (
        activate_educloud,
        {"form_id": 1, "project_name": "test-project", "token": "test-token"},
        Route("POST", "/form/{formId}/activate/educloud"),
    ),
    (
        upload_image,
        {"file_path": __file__},
        Route("POST", "/image"),
    ),
]


@pytest.mark.parametrize("tool,kwargs,route", WRITE_TOOL_CASES)
@pytest.mark.respx(assert_all_called=False)
@pytest.mark.usefixtures("token_route")
async def test_outgoing_body_validates_against_its_declared_schema(
    tool: Callable[..., Awaitable[str]],
    kwargs: dict[str, object],
    route: Route,
    respx_mock: respx.MockRouter,
) -> None:
    """Verify outgoing request bodies validate against their declared schemas."""
    # Mock the GET request for update_form_element, which reads before writing
    if tool.__name__ == "update_form_element":
        respx_mock.route(method="GET").mock(
            return_value=httpx.Response(
                200, json=[{"elementId": 1, "elementType": "TEXT", "questionText": "Q1"}]
            )
        )

    captured = respx_mock.route(method=route.method).mock(return_value=httpx.Response(200, json={}))
    await tool(**kwargs)

    # For update_form_element, find the PUT request (not the GET)
    if tool.__name__ == "update_form_element":
        put_call = next(call for call in captured.calls if call.request.method == "PUT")
        body = json.loads(put_call.request.content)
        actual_request = put_call.request
    else:
        body = json.loads(captured.calls.last.request.content)
        actual_request = captured.calls.last.request

    # Verify the request went to the declared path, not a different route
    # Substitute path params from kwargs into the route's path template
    resolved_path = route.path
    for param_name, param_value in kwargs.items():
        # Convert snake_case param names to camelCase for path substitution
        camel_name = "".join(
            word.capitalize() if i > 0 else word for i, word in enumerate(param_name.split("_"))
        )
        resolved_path = resolved_path.replace(f"{{{camel_name}}}", str(param_value))
    assert actual_request.url.path.endswith(resolved_path), (
        f"{tool.__name__} declared {route.method} {route.path} but called "
        f"{actual_request.method} {actual_request.url.path}"
    )

    schema = _request_schema(load_spec(), route)
    assert schema is not None, f"{route.method} {route.path} declares no request body in the spec"
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(body)


def test_body_validation_exempt_holds_exactly_one_entry() -> None:
    """
    Pin BODY_VALIDATION_EXEMPT to its single entry with a non-empty reason.

    This dict is an escape hatch from the coverage requirement and is
    subtracted in test_every_route_with_a_request_body_has_a_case. Growing it
    must be a deliberate, reviewed act, not the quiet way to make a red test
    green. Mirrored from test_out_of_scope_holds_exactly_the_four_v1_invitation_operations.
    """
    assert set(BODY_VALIDATION_EXEMPT) == {
        ("DELETE", "/form/{formId}/submissions"),
    }
    assert all(reason for reason in BODY_VALIDATION_EXEMPT.values())


def test_write_tool_cases_has_exactly_thirteen_rows() -> None:
    """
    Pin WRITE_TOOL_CASES to 13 rows.

    Deleting a row without adding it to BODY_VALIDATION_EXEMPT should fail the
    coverage test, but pinning the count closes the other half: a deleted row
    would otherwise vanish without any count changing.
    """
    assert len(WRITE_TOOL_CASES) == 13, (
        f"WRITE_TOOL_CASES has {len(WRITE_TOOL_CASES)} rows; expected 13. If a tool was added, "
        "update this count and confirm the new route is in the spec. If a tool was removed, "
        "ensure it was removed from REGISTRY and not just added to BODY_VALIDATION_EXEMPT."
    )


def test_every_route_with_a_request_body_has_a_case() -> None:
    """Verify WRITE_TOOL_CASES covers every route that declares a JSON request body."""
    declared = {
        (r.method, r.path)
        for routes in REGISTRY.values()
        for r in routes
        if _request_schema(load_spec(), r) is not None
    }
    # Exclude routes that are deliberately not tested (see BODY_VALIDATION_EXEMPT)
    declared -= set(BODY_VALIDATION_EXEMPT)
    assert declared == {(r.method, r.path) for _, _, r in WRITE_TOOL_CASES}
