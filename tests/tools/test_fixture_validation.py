"""Test that all response fixtures match the vendored OpenAPI spec.

Validates fixtures against the spec and enforces that all module-level response
fixtures are validated - new fixtures cannot escape.
"""

from tests.conftest import validate_response_fixture

# Import all fixtures from test modules
from tests.tools.test_forms_read import (
    FORM_DEFINITION,
    FORM_INFO,
    FORM_METADATA,
    FORM_SETTINGS,
    FORM_VALIDATION,
    FORMS,
    PERSONAL_DATA_FORMS,
)
from tests.tools.test_submissions_read import MY_SUBMISSIONS, SUBMISSION

# Registry of all response fixtures with their routes
# Format: (method, path, fixture, fixture_name)
ALL_FIXTURES = [
    ("GET", "/form/me", FORMS, "FORMS"),
    ("GET", "/form/titleshort/{titleShort}", FORM_METADATA, "FORM_METADATA"),
    ("GET", "/form/{formId}/info", FORM_INFO, "FORM_INFO"),
    ("GET", "/form/{formId}/settings", FORM_SETTINGS, "FORM_SETTINGS"),
    ("GET", "/form/{formId}/settings/validation", FORM_VALIDATION, "FORM_VALIDATION"),
    ("GET", "/form/{formId}/definition", FORM_DEFINITION, "FORM_DEFINITION"),
    ("GET", "/personal-data/collects-personal-data", PERSONAL_DATA_FORMS, "PERSONAL_DATA_FORMS"),
    ("GET", "/form/submission/{submissionId}", SUBMISSION, "SUBMISSION"),
    ("GET", "/form/submission/me", MY_SUBMISSIONS, "MY_SUBMISSIONS"),
]


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


def test_fixture_count_matches_expected() -> None:
    """Enforce that exactly 9 fixtures are validated (Tasks 7-10).

    This test fails if the fixture count changes, forcing an update to either
    add the new fixture to ALL_FIXTURES or document why it's exempt.
    """
    expected_count = 9
    actual_count = len(ALL_FIXTURES)
    assert actual_count == expected_count, (
        f"Expected {expected_count} response fixtures from Tasks 7-10, found {actual_count}. "
        f"If you added a new response fixture, add it to ALL_FIXTURES in this file. "
        f"If you removed one, update expected_count with a comment explaining why."
    )
