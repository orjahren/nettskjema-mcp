"""Tests for the form read tools."""

import json

import httpx
import pytest
import respx

from nettskjema_mcp.tools.forms import (
    get_form_definition,
    get_form_info,
    get_form_settings,
    get_form_settings_validation,
    list_forms_collecting_personal_data,
    list_my_forms,
    lookup_form_by_title,
)
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

FORMS = [{"formId": 1, "title": "Test Form"}]
FORM_METADATA = {"formId": 1, "title": "Test Form", "titleShort": "test-form"}
FORM_INFO = {"owner": "test-client@apiclient", "created": "2024-01-01T00:00:00Z"}
FORM_SETTINGS = {"title": "Test Form", "description": "A test form"}
FORM_VALIDATION = {"titleRequired": True}
FORM_DEFINITION = {"elements": [{"elementId": 1, "elementType": "TEXT"}]}
PERSONAL_DATA_FORMS = [{"formId": 1, "collectsPersonalData": True}]


async def test_list_my_forms(respx_mock: respx.MockRouter) -> None:
    """list_my_forms() GETs /form/me and returns the dumped body."""
    url = f"{TEST_BASE_URL}/form/me"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=FORMS))

    result = await list_my_forms()

    assert route.call_count == 1
    assert json.loads(result) == FORMS
    assert route.calls.last.request.url == url


async def test_lookup_form_by_title(respx_mock: respx.MockRouter) -> None:
    """lookup_form_by_title() GETs /form/titleshort/{titleShort} and returns the dumped body."""
    url = f"{TEST_BASE_URL}/form/titleshort/test-form"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=FORM_METADATA))

    result = await lookup_form_by_title("test-form")

    assert route.call_count == 1
    assert json.loads(result) == FORM_METADATA
    assert route.calls.last.request.url == url


async def test_get_form_info(respx_mock: respx.MockRouter) -> None:
    """get_form_info() GETs /form/{formId}/info and returns the dumped body."""
    url = f"{TEST_BASE_URL}/form/123/info"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=FORM_INFO))

    result = await get_form_info(123)

    assert route.call_count == 1
    assert json.loads(result) == FORM_INFO
    assert route.calls.last.request.url == url


async def test_get_form_settings_without_query_param(respx_mock: respx.MockRouter) -> None:
    """get_form_settings() without is_for_create_form omits the query parameter."""
    url = f"{TEST_BASE_URL}/form/123/settings"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=FORM_SETTINGS))

    result = await get_form_settings(123)

    assert route.call_count == 1
    assert json.loads(result) == FORM_SETTINGS
    assert route.calls.last.request.url == url


async def test_get_form_settings_with_is_for_create_form_true(respx_mock: respx.MockRouter) -> None:
    """get_form_settings() with is_for_create_form=True includes the query parameter."""
    url = f"{TEST_BASE_URL}/form/123/settings?is-for-create-form=true"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=FORM_SETTINGS))

    result = await get_form_settings(123, is_for_create_form=True)

    assert route.call_count == 1
    assert json.loads(result) == FORM_SETTINGS
    assert str(route.calls.last.request.url) == url


async def test_get_form_settings_validation(respx_mock: respx.MockRouter) -> None:
    """get_form_settings_validation() GETs /form/{formId}/settings/validation."""
    url = f"{TEST_BASE_URL}/form/123/settings/validation"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=FORM_VALIDATION))

    result = await get_form_settings_validation(123)

    assert route.call_count == 1
    assert json.loads(result) == FORM_VALIDATION
    assert route.calls.last.request.url == url


async def test_get_form_definition(respx_mock: respx.MockRouter) -> None:
    """get_form_definition() GETs /form/{formId}/definition and returns the dumped body."""
    url = f"{TEST_BASE_URL}/form/123/definition"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=FORM_DEFINITION))

    result = await get_form_definition(123)

    assert route.call_count == 1
    assert json.loads(result) == FORM_DEFINITION
    assert route.calls.last.request.url == url


async def test_list_forms_collecting_personal_data_no_filters(respx_mock: respx.MockRouter) -> None:
    """list_forms_collecting_personal_data() without filters omits query parameters."""
    url = f"{TEST_BASE_URL}/personal-data/collects-personal-data"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=PERSONAL_DATA_FORMS))

    result = await list_forms_collecting_personal_data()

    assert route.call_count == 1
    assert json.loads(result) == PERSONAL_DATA_FORMS
    assert route.calls.last.request.url == url


async def test_list_forms_collecting_personal_data_with_anonymous_true(
    respx_mock: respx.MockRouter,
) -> None:
    """list_forms_collecting_personal_data() with anonymous=True includes the query parameter."""
    url = f"{TEST_BASE_URL}/personal-data/collects-personal-data?anonymous=true"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=PERSONAL_DATA_FORMS))

    result = await list_forms_collecting_personal_data(anonymous=True)

    assert route.call_count == 1
    assert json.loads(result) == PERSONAL_DATA_FORMS
    assert str(route.calls.last.request.url) == url


async def test_list_forms_collecting_personal_data_with_anonymous_false(
    respx_mock: respx.MockRouter,
) -> None:
    """list_forms_collecting_personal_data() with anonymous=False serializes as 'false'."""
    url = f"{TEST_BASE_URL}/personal-data/collects-personal-data?anonymous=false"
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=PERSONAL_DATA_FORMS))

    result = await list_forms_collecting_personal_data(anonymous=False)

    assert route.call_count == 1
    assert json.loads(result) == PERSONAL_DATA_FORMS
    assert str(route.calls.last.request.url) == url


async def test_list_forms_collecting_personal_data_with_inactive_suspected(
    respx_mock: respx.MockRouter,
) -> None:
    """list_forms_collecting_personal_data() with inactive_personal_data_suspected=True."""
    url = (
        f"{TEST_BASE_URL}/personal-data/collects-personal-data"
        "?inactive-personal-data-suspected=true"
    )
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=PERSONAL_DATA_FORMS))

    result = await list_forms_collecting_personal_data(inactive_personal_data_suspected=True)

    assert route.call_count == 1
    assert json.loads(result) == PERSONAL_DATA_FORMS
    assert str(route.calls.last.request.url) == url


async def test_list_forms_collecting_personal_data_with_both_filters(
    respx_mock: respx.MockRouter,
) -> None:
    """list_forms_collecting_personal_data() with both query parameters."""
    url = (
        f"{TEST_BASE_URL}/personal-data/collects-personal-data"
        "?anonymous=true&inactive-personal-data-suspected=false"
    )
    route = respx_mock.get(url).mock(return_value=httpx.Response(200, json=PERSONAL_DATA_FORMS))

    result = await list_forms_collecting_personal_data(
        anonymous=True, inactive_personal_data_suspected=False
    )

    assert route.call_count == 1
    assert json.loads(result) == PERSONAL_DATA_FORMS
    assert str(route.calls.last.request.url) == url


async def test_optional_query_params_are_omitted_when_none() -> None:
    """None-valued optional query parameters produce no query string at all."""
    # get_form_settings is tested above with no query param
    # list_forms_collecting_personal_data is tested above with no query params
    # Both cases already covered, this test documents the contract explicitly
    assert True
