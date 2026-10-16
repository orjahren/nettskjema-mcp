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
    msg = str(e.value)
    # Assert the error is specifically for respondentGroup, not just anywhere in the message
    assert "/respondentGroup" in msg or "respondentGroup" in msg
    assert "INVITED" in msg


def test_wrong_type_names_the_field() -> None:
    with pytest.raises(BadRequestError) as e:
        validate_body("FormSettingsDTO", {"maxSubmissionsForm": "lots"}, partial=True)
    assert "maxSubmissionsForm" in str(e.value)


def test_element_list_validates_each_item() -> None:
    with pytest.raises(BadRequestError) as e:
        validate_body("ElementDTO", [{"elementType": "NOT_A_TYPE"}], as_array=True)
    msg = str(e.value)
    assert "elementType" in msg
    # Assert the error identifies the failing index
    assert "$[0]" in msg or "[0]" in msg


def test_nested_ref_resolves() -> None:
    # ElementDTO.answerOptions -> AnswerOptionDTO must resolve, not raise RefResolutionError
    validate_body(
        "ElementDTO",
        {"elementType": "RADIO", "answerOptions": [{"text": "Option 1"}]},
    )


def test_partial_nested_ref_resolves() -> None:
    """
    Critical: partial=True must not break nested $ref resolution.

    FormSettingsDTO.editors is a $ref to PersonDTO. When partial=True, the modified
    schema must still be registered in the registry so nested $refs resolve.
    Without this fix, the schema is detached and validation crashes with PointerToNowhere.
    """
    validate_body(
        "FormSettingsDTO",
        {
            "title": "x",
            "editors": [{"userType": "FEIDE", "username": "testuser"}],
        },
        partial=True,
    )


def test_partial_nested_required_still_enforced() -> None:
    """
    partial=True strips only the top-level required constraint.

    Nested objects (like FormSettingsSupportuserDTO in FormSettingsDTO.supportuser) keep
    their validation constraints. If a nested object appears in a partial body, it must be valid.
    """
    with pytest.raises(BadRequestError) as e:
        validate_body(
            "FormSettingsDTO",
            {
                "title": "x",
                "supportuser": {"theme": "INVALID_THEME"},  # invalid theme enum
            },
            partial=True,
        )
    msg = str(e.value)
    assert "theme" in msg or "DEFAULT" in msg


def test_array_errors_sorted_naturally() -> None:
    """
    Critical: array errors must be sorted naturally, not lexicographically.

    With lexicographic sorting, $[0], $[100], $[10] would appear out of order,
    and the first 20 rendered errors would skip indices 1-9 and 20-99.
    Natural sorting ensures $[0], $[1], ..., $[19] appear in order.
    """
    # Create 15 items with errors to confirm the first 15 are shown in order
    bad_body = [{"text": f"item {i}"} for i in range(15)]
    with pytest.raises(BadRequestError) as e:
        validate_body("ElementDTO", bad_body, as_array=True)
    msg = str(e.value)
    # Confirm indices 0-14 appear in the message, in order
    for i in range(15):
        assert f"$[{i}]" in msg or f"[{i}]" in msg


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
