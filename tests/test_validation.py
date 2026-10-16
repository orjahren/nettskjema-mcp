"""Tests for payload validation against vendored OpenAPI schemas."""

import pytest

from nettskjema_mcp.errors import BadRequestError
from nettskjema_mcp.validation import validate_body


def test_valid_form_settings_passes() -> None:
    validate_body(
        "FormSettingsDTO",
        {
            "title": "t",
            "formType": "DEFAULT",
            "languageCode": "en",
            "respondentGroup": "ALL",
            "collectsPersonalData": False,
            "sensitivePersonalDataCollected": False,
        },
    )


def test_partial_patch_skips_required_fields() -> None:
    # the published schema marks six fields required, but PATCH takes partial bodies;
    # without partial=True this call would be rejected
    validate_body("FormSettingsDTO", {"title": "only the title"}, partial=True)


def test_full_body_still_enforces_required_fields() -> None:
    with pytest.raises(BadRequestError):
        validate_body("FormSettingsDTO", {"title": "no other fields"})


def test_bad_enum_value_names_the_field_and_the_allowed_values() -> None:
    with pytest.raises(BadRequestError) as e:
        validate_body("FormSettingsDTO", {"respondentGroup": "EVERYONE"}, partial=True)
    assert "respondentGroup" in str(e.value) and "INVITED" in str(e.value)


def test_wrong_type_names_the_field() -> None:
    with pytest.raises(BadRequestError) as e:
        validate_body("FormSettingsDTO", {"maxSubmissionsForm": "lots"}, partial=True)
    assert "maxSubmissionsForm" in str(e.value)


def test_element_list_validates_each_item() -> None:
    with pytest.raises(BadRequestError) as e:
        validate_body("ElementDTO", [{"elementType": "NOT_A_TYPE"}], as_array=True)
    assert "elementType" in str(e.value)


def test_nested_ref_resolves() -> None:
    # ElementDTO.answerOptions -> AnswerOptionDTO must resolve, not raise RefResolutionError
    validate_body(
        "ElementDTO",
        {"elementType": "RADIO", "answerOptions": [{"text": "Option 1"}]},
    )


def test_pathological_body_stays_bounded() -> None:
    """A body with many errors must not produce a message that exceeds the error cap."""
    # Create an array with many items that have validation errors
    # Each item is missing the required 'elementType' field
    bad_body = [{"text": f"item {i}"} for i in range(200)]
    with pytest.raises(BadRequestError) as e:
        validate_body("ElementDTO", bad_body, as_array=True)
    # MAX_RENDERED_ERROR_LENGTH is 10,000 from test_errors.py
    assert len(str(e.value)) < 10_000


def test_unknown_schema_name_raises_clear_error() -> None:
    """Unknown schema names are programming errors, not user input."""
    with pytest.raises(ValueError) as e:
        validate_body("NoSuchSchemaDTO", {})
    assert "NoSuchSchemaDTO" in str(e.value)
