"""Validate every response fixture against the vendored OpenAPI spec.

Two tests, and the second is the one that gives the first its teeth:

* ``test_all_response_fixtures_validate`` checks each registered fixture
  against the schema the spec declares for its route.
* ``test_every_discovered_fixture_is_registered`` walks the tool test modules,
  finds the module-level response fixtures by inspection, and fails if one of
  them is missing from ``ALL_FIXTURES``.

The second test replaces an earlier count guard that compared a hand-written
number against ``len(ALL_FIXTURES)``. Both sides of that comparison came from
the same hand-maintained list, so it answered "is the list as long as I said"
rather than "is every fixture registered", and an unregistered fixture passed
straight through it. Discovery asks the real question.
"""

import importlib
import pkgutil
from types import ModuleType
from typing import Any

import pytest

import tests.tools
from tests.conftest import validate_response_fixture

# Import all fixtures from test modules
from tests.tools.test_attachments import UPLOAD_SUCCESS_RESPONSE
from tests.tools.test_elements import REJECTION_BODY, THREE_ELEMENTS
from tests.tools.test_forms_read import (
    FORM_DEFINITION,
    FORM_INFO,
    FORM_METADATA,
    FORM_SETTINGS,
    FORM_VALIDATION,
    FORMS,
    PERSONAL_DATA_FORMS,
)
from tests.tools.test_meta import USER
from tests.tools.test_submissions_read import MY_SUBMISSIONS, SUBMISSION
from tests.tools.test_submissions_write import DELIVERED_SUBMISSION

# Registry of all response fixtures with their routes
# Format: (method, path, fixture, fixture_name)
ALL_FIXTURES: list[tuple[str, str, Any, str]] = [
    ("GET", "/me", USER, "USER"),
    ("GET", "/form/me", FORMS, "FORMS"),
    ("GET", "/form/titleshort/{titleShort}", FORM_METADATA, "FORM_METADATA"),
    ("GET", "/form/{formId}/info", FORM_INFO, "FORM_INFO"),
    ("GET", "/form/{formId}/settings", FORM_SETTINGS, "FORM_SETTINGS"),
    ("GET", "/form/{formId}/settings/validation", FORM_VALIDATION, "FORM_VALIDATION"),
    ("GET", "/form/{formId}/definition", FORM_DEFINITION, "FORM_DEFINITION"),
    ("GET", "/personal-data/collects-personal-data", PERSONAL_DATA_FORMS, "PERSONAL_DATA_FORMS"),
    ("GET", "/form/{formId}/elements", THREE_ELEMENTS, "THREE_ELEMENTS"),
    ("PUT", "/form/{formId}/elements", REJECTION_BODY, "REJECTION_BODY"),
    ("GET", "/form/submission/{submissionId}", SUBMISSION, "SUBMISSION"),
    ("GET", "/form/submission/me", MY_SUBMISSIONS, "MY_SUBMISSIONS"),
    ("POST", "/form/{formId}/submission", DELIVERED_SUBMISSION, "DELIVERED_SUBMISSION"),
    (
        "POST",
        "/form/invitation/{invitationId}/submission",
        DELIVERED_SUBMISSION,
        "DELIVERED_SUBMISSION",
    ),
    (
        "PUT",
        "/form/submission/{submissionId}/attachment",
        UPLOAD_SUCCESS_RESPONSE,
        "UPLOAD_SUCCESS_RESPONSE",
    ),
]

# Module-level JSON constants that are not response fixtures, with the reason.
# Keyed by (module name without package, constant name). Add to this rather than
# registering something in ALL_FIXTURES that no endpoint ever returns: a bogus
# registration would be validated against a schema it has nothing to do with.
DISCOVERY_EXEMPT: dict[tuple[str, str], str] = {
    # (module, constant) -> reason
    (
        "test_attachments",
        "TRANSCRIBED_JSON_RESPONSE",
    ): "Real response body, but the route's 200 declares no content, so there is nothing to validate against",
}


def _is_json_data(value: object) -> bool:
    """
    Report whether a value is plain JSON data: the shape a response fixture has.

    Containers are walked to the leaves, so a list of pytest marks or a list of
    tuples — ALL_FIXTURES itself, for one — is not mistaken for a fixture.

    Args:
        value: Any module-level constant.

    Returns:
        True if the value consists only of dicts, lists and JSON scalars.
    """
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_data(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_is_json_data(item) for item in value)
    return isinstance(value, (str, int, float, bool)) or value is None


def _looks_like_a_fixture(value: object) -> bool:
    """
    Report whether a constant has the shape of a mocked response body.

    A non-empty JSON object or array. Bare scalars are excluded because the
    test modules are full of them — TEST_BASE_URL and the per-module URL
    constants are strings, and no endpoint in this API answers with a bare JSON
    scalar. Empty containers are excluded too: there is no field in one for the
    schema check to catch, and the empty DISCOVERY_EXEMPT registry below would
    otherwise report itself.

    Args:
        value: Any module-level constant.

    Returns:
        True if the value is a non-empty JSON object or array.
    """
    return isinstance(value, (dict, list)) and bool(value) and _is_json_data(value)


def _tool_test_modules() -> list[ModuleType]:
    """
    Import every ``test_*`` module under ``tests.tools``.

    Returns:
        The imported modules, including this one.
    """
    modules = []
    for info in pkgutil.iter_modules(tests.tools.__path__):
        if info.name.startswith("test_"):
            modules.append(importlib.import_module(f"{tests.tools.__name__}.{info.name}"))
    return modules


def _discovered_fixtures() -> dict[tuple[str, str], object]:
    """
    Find the module-level response fixtures in the tool test modules.

    The criterion is deliberately mechanical: an UPPER_CASE module-level
    constant whose value is a non-empty JSON object or array. Every fixture
    written so far looks like that, because that is what gets handed to
    ``httpx.Response(200, json=...)``.

    What this cannot see, and what therefore still relies on review:

    * a fixture built inside a function or a pytest fixture, or inlined in the
      single test that uses it — there is no module-level name to find;
    * a fixture held in a lower-case name, or assembled at import time into
      something other than plain JSON data;
    * an empty object or array used as a fixture — nothing in it could fail a
      schema check anyway;
    * whether a discovered constant is a *response* body rather than a request
      body. THREE_ELEMENTS is both, and is registered against the GET that
      returns it; a request-only payload would be a false positive here and
      belongs in DISCOVERY_EXEMPT with its reason.
    * a fixture in a test module outside ``tests/tools/``.

    A constant imported into another test module is reported under both, which
    is harmless: both names resolve to the same object, and registration is
    matched by identity.

    Returns:
        A mapping of (module name, constant name) to the constant's value.
    """
    found: dict[tuple[str, str], object] = {}
    for module in _tool_test_modules():
        short = module.__name__.rsplit(".", 1)[-1]
        for name, value in vars(module).items():
            if not name.isupper() or name.startswith("_"):
                continue
            if (short, name) in DISCOVERY_EXEMPT:
                continue
            if _looks_like_a_fixture(value):
                found[(short, name)] = value
    return found


def test_all_response_fixtures_validate() -> None:
    """Validate all response fixtures in a single test.

    This runs validation on every fixture in ALL_FIXTURES. If any fixture does
    not match its schema, the test fails with details about all failures.
    """
    failures: list[str] = []

    for method, path, fixture, name in ALL_FIXTURES:
        try:
            validate_response_fixture(method, path, fixture)
        except AssertionError as e:
            failures.append(f"{name} ({method} {path}): {e}")

    if failures:
        raise AssertionError(
            f"\n{len(failures)} fixture(s) failed validation:\n\n" + "\n\n".join(failures)
        )


def test_every_discovered_fixture_is_registered() -> None:
    """
    A response fixture nobody registered must fail the suite, not slip through.

    Registration is matched by object identity, not by value: two fixtures that
    happen to be equal are still two fixtures, and a registry entry that points
    at a different object than the one the tests actually mock would be worth
    nothing.
    """
    registered = {id(fixture) for _, _, fixture, _ in ALL_FIXTURES}
    unregistered = [
        f"{module}.{name}"
        for (module, name), value in sorted(_discovered_fixtures().items())
        if id(value) not in registered
    ]

    assert not unregistered, (
        "These module-level JSON constants are not in ALL_FIXTURES, so nothing checks them "
        f"against the vendored spec: {', '.join(unregistered)}. Add each one with the route "
        "that returns it, or — if it is not a response body — add it to DISCOVERY_EXEMPT "
        "with the reason."
    )


def test_registered_fixtures_name_constants_that_exist() -> None:
    """
    The label in each registry entry must be a real constant holding that object.

    Without this the fourth column is free text, and a renamed fixture would
    leave the registry describing something that no longer exists.
    """
    discovered = _discovered_fixtures()
    for _, _, fixture, name in ALL_FIXTURES:
        matches = [key for key, value in discovered.items() if key[1] == name]
        assert matches, f"ALL_FIXTURES names {name}, which no tool test module defines"
        assert any(discovered[key] is fixture for key in matches), (
            f"ALL_FIXTURES entry {name} holds a different object than the constant of that "
            "name; the registry and the fixture have drifted apart"
        )


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/form/{formId}/not-a-route"),
        ("PATCH", "/form/{formId}/elements"),
        ("DELETE", "/form/{formId}/submissions"),
    ],
)
def test_a_fixture_on_an_unresolvable_route_fails(method: str, path: str) -> None:
    """
    An unknown path, an unknown method, or a 200 with no schema must fail loudly.

    Skipping instead would make the validator silently stop checking the moment
    a route is renamed in the spec — the failure mode the whole fixture
    machinery exists to prevent. The third case is the DELETE added in Task 11,
    whose 200 declares no content at all: registering a body for it is a
    mistake about the endpoint and is reported as one.
    """
    with pytest.raises(AssertionError):
        validate_response_fixture(method, path, {})
