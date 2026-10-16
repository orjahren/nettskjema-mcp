"""Test that all response fixtures match the vendored OpenAPI spec."""

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


def test_list_my_forms_fixture() -> None:
    """Validate the list_my_forms fixture."""
    validate_response_fixture("GET", "/form/me", FORMS)


def test_lookup_form_by_title_fixture() -> None:
    """Validate the lookup_form_by_title fixture."""
    validate_response_fixture("GET", "/form/titleshort/{titleShort}", FORM_METADATA)


def test_get_form_info_fixture() -> None:
    """Validate the get_form_info fixture."""
    validate_response_fixture("GET", "/form/{formId}/info", FORM_INFO)


def test_get_form_settings_fixture() -> None:
    """Validate the get_form_settings fixture."""
    validate_response_fixture("GET", "/form/{formId}/settings", FORM_SETTINGS)


def test_get_form_settings_validation_fixture() -> None:
    """Validate the get_form_settings_validation fixture."""
    validate_response_fixture("GET", "/form/{formId}/settings/validation", FORM_VALIDATION)


def test_get_form_definition_fixture() -> None:
    """Validate the get_form_definition fixture."""
    validate_response_fixture("GET", "/form/{formId}/definition", FORM_DEFINITION)


def test_list_forms_collecting_personal_data_fixture() -> None:
    """Validate the list_forms_collecting_personal_data fixture."""
    validate_response_fixture("GET", "/personal-data/collects-personal-data", PERSONAL_DATA_FORMS)


def test_get_submission_fixture() -> None:
    """Validate the get_submission fixture."""
    validate_response_fixture("GET", "/form/submission/{submissionId}", SUBMISSION)


def test_list_my_submissions_fixture() -> None:
    """Validate the list_my_submissions fixture."""
    validate_response_fixture("GET", "/form/submission/me", MY_SUBMISSIONS)
