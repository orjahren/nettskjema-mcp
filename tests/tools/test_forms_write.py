"""Tests for the form write tools."""

import json

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from nettskjema_mcp.enums import FormType, RespondentGroup
from nettskjema_mcp.tools.forms import create_form, delete_forms, update_form_settings
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]


async def test_create_form_sends_form_settings_and_elements_shape(
    respx_mock: respx.MockRouter,
) -> None:
    """create_form() sends FormSettingsAndElementsDTO: {formSettings: {...}, elements: [...]}."""
    url = f"{TEST_BASE_URL}/form"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json={"formId": 123}))

    await create_form(
        title="Test Form",
        language_code="en",
        form_type=FormType.DEFAULT,
        respondent_group=RespondentGroup.FEIDE,
        collects_personal_data=True,
        sensitive_personal_data_collected=False,
    )

    assert route.call_count == 1
    request = route.calls.last.request
    body = json.loads(request.content.decode("utf-8"))

    # The body must be {formSettings: {...}, elements: []}
    assert set(body.keys()) == {"formSettings", "elements"}
    assert isinstance(body["formSettings"], dict)
    assert isinstance(body["elements"], list)

    # The six required settings must be in formSettings
    settings = body["formSettings"]
    assert settings["title"] == "Test Form"
    assert settings["languageCode"] == "en"
    assert settings["formType"] == "DEFAULT"
    assert settings["respondentGroup"] == "FEIDE"
    assert settings["collectsPersonalData"] is True
    assert settings["sensitivePersonalDataCollected"] is False


async def test_create_form_merges_extra_settings_without_overriding_required(
    respx_mock: respx.MockRouter,
) -> None:
    """create_form() merges extra_settings but required params take precedence."""
    url = f"{TEST_BASE_URL}/form"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json={"formId": 456}))

    await create_form(
        title="Named Title",
        language_code="no",
        form_type=FormType.SIGN_UP,
        respondent_group=RespondentGroup.ID_PORTEN_LEVEL_3,
        collects_personal_data=False,
        sensitive_personal_data_collected=False,
        extra_settings={
            "description": "A custom description",
            "title": "Ignored Title",  # This should be overridden
        },
    )

    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content.decode("utf-8"))
    settings = body["formSettings"]

    # Named parameters take precedence
    assert settings["title"] == "Named Title"
    assert settings["description"] == "A custom description"


async def test_create_form_includes_elements_when_provided(respx_mock: respx.MockRouter) -> None:
    """create_form() includes elements in the request when provided."""
    url = f"{TEST_BASE_URL}/form"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json={"formId": 789}))

    await create_form(
        title="Form with Elements",
        language_code="en",
        form_type=FormType.DEFAULT,
        respondent_group=RespondentGroup.FEIDE,
        collects_personal_data=False,
        sensitive_personal_data_collected=False,
        elements=[{"elementType": "TEXT", "questionText": "What is your name?"}],
    )

    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content.decode("utf-8"))
    assert len(body["elements"]) == 1
    assert body["elements"][0]["elementType"] == "TEXT"


async def test_delete_forms_sends_a_bare_array(respx_mock: respx.MockRouter) -> None:
    """delete_forms() sends a bare JSON array [1, 2], not {formIds: [1, 2]}."""
    url = f"{TEST_BASE_URL}/form"
    route = respx_mock.delete(url).mock(return_value=httpx.Response(200))

    await delete_forms([1, 2, 3])

    assert route.call_count == 1
    request = route.calls.last.request

    # Assert the raw bytes: [1,2,3], not {"formIds":[1,2,3]}
    assert request.content == b"[1,2,3]"


async def test_delete_forms_sends_no_trash_can_parameter(respx_mock: respx.MockRouter) -> None:
    """delete_forms() does not send days-in-trash-can in the query string."""
    url = f"{TEST_BASE_URL}/form"
    route = respx_mock.delete(url).mock(return_value=httpx.Response(200))

    await delete_forms([1, 2])

    assert route.call_count == 1
    request = route.calls.last.request

    # The URL must not contain days-in-trash-can
    assert "days-in-trash-can" not in str(request.url)


async def test_update_form_settings_sends_a_partial_body(respx_mock: respx.MockRouter) -> None:
    """update_form_settings() sends a partial body and is not rejected locally."""
    url = f"{TEST_BASE_URL}/form/123/settings"
    route = respx_mock.patch(url).mock(return_value=httpx.Response(204))

    await update_form_settings(123, {"title": "New Title"})

    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content.decode("utf-8"))
    assert body == {"title": "New Title"}


async def test_update_form_settings_rejects_invalid_type_locally(
    respx_mock: respx.MockRouter,
) -> None:
    """update_form_settings() rejects invalid field types before calling the API."""
    url = f"{TEST_BASE_URL}/form/123/settings"
    route = respx_mock.patch(url).mock(return_value=httpx.Response(204))

    with pytest.raises(ToolError) as caught:
        await update_form_settings(123, {"title": 123})  # title must be string

    assert "title" in str(caught.value) or "type" in str(caught.value)
    assert route.call_count == 0


async def test_update_form_settings_surfaces_a_207(respx_mock: respx.MockRouter) -> None:
    """update_form_settings() surfaces a 207 as a ToolError naming the failed settings."""
    url = f"{TEST_BASE_URL}/form/123/settings"
    respx_mock.patch(url).mock(
        return_value=httpx.Response(
            207,
            json={
                "message": "Some settings could not be updated",
                "errorKeysAndErrorMessages": {
                    "openFrom": ["must be before openTo"],
                    "title": ["is reserved"],
                },
            },
        )
    )

    with pytest.raises(ToolError) as caught:
        await update_form_settings(123, {"openFrom": "2024-12-01", "title": "Reserved Name"})

    message = str(caught.value)
    # Must not read as success
    assert "207" in message or "Partial" in message or "partial" in message
    # Must name the failed settings
    assert "openFrom" in message
    assert "title" in message


async def test_update_form_settings_passes_force_cleanup(respx_mock: respx.MockRouter) -> None:
    """update_form_settings() passes forceCleanup as a query parameter when True."""
    url = f"{TEST_BASE_URL}/form/123/settings?forceCleanup=true"
    route = respx_mock.patch(url).mock(return_value=httpx.Response(204))

    await update_form_settings(123, {"title": "Updated"}, force_cleanup=True)

    assert route.call_count == 1
    assert str(route.calls.last.request.url) == url
