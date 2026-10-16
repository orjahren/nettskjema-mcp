"""Contract tests between our tool declarations and the OpenAPI spec."""

import pytest

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
from nettskjema_mcp.routes import REGISTRY, OUT_OF_SCOPE, Route, endpoint, load_spec


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
    assert sum(
        1
        for p in spec["paths"].values()  # type: ignore[union-attr]
        for m in p  # type: ignore[union-attr]
        if m in {"get", "post", "put", "patch", "delete"}
    ) == 42


@pytest.mark.parametrize("enum_cls,schema,prop", ENUM_LOCATIONS)
def test_enum_members_match_the_spec(
    enum_cls: type, schema: str, prop: str
) -> None:
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
