"""Tests for the element tools.

The write endpoint replaces a form's whole element list, so these tests check the
exact bytes on the wire and that no write is issued on the paths where a write
would silently destroy content.
"""

import json

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from nettskjema_mcp.tools.elements import (
    get_form_elements,
    replace_form_elements,
    update_form_element,
)
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

ELEMENTS_URL = f"{TEST_BASE_URL}/form/123/elements"

# Three elements in the shape the API returns them, using only ElementDTO fields
# from the vendored spec.
THREE_ELEMENTS: list[dict[str, object]] = [
    {"elementId": 11, "elementType": "HEADING", "text": "Part one", "sequence": 1},
    {
        "elementId": 22,
        "elementType": "RADIO",
        "text": "old",
        "sequence": 2,
        "isMandatory": True,
        "answerOptions": [
            {"answerOptionId": 1, "text": "Yes", "sequence": 1},
            {"answerOptionId": 2, "text": "No", "sequence": 2},
        ],
    },
    {"elementId": 33, "elementType": "PAGE_BREAK", "sequence": 3},
]

# The spec declares this endpoint's 200 as ErrorMessage, so a rejected write
# arrives with a clean status and the refusal only in the body. "empty" is the
# Spring MultiValueMap artefact the extractor must drop.
REJECTION_BODY: dict[str, object] = {
    "message": "Validation failed",
    "errors": {"elements[0].text": ["must not be blank"], "empty": False},
    "confirmForceCleanupErrors": {},
}


def _body(route: respx.Route) -> object:
    """Decode the JSON body of a route's last request."""
    return json.loads(route.calls.last.request.content.decode("utf-8"))


async def test_get_form_elements_does_not_send_the_answer_parameter(
    respx_mock: respx.MockRouter,
) -> None:
    """
    get_form_elements() sends no query parameters at all.

    The vendored spec declares exactly one parameter on this operation, formId,
    in the path — no query parameter of any name, including "answer". The client
    can attach one, so this pins that the tool does not: a parameter nobody asked
    for could select a different view of the same path and answer a different
    question than the caller put.
    """
    route = respx_mock.get(ELEMENTS_URL).mock(return_value=httpx.Response(200, json=THREE_ELEMENTS))

    await get_form_elements(123)

    assert route.call_count == 1
    request = route.calls.last.request
    assert "answer" not in str(request.url)
    assert request.url.query == b""


async def test_replace_form_elements_sends_a_bare_array(respx_mock: respx.MockRouter) -> None:
    """replace_form_elements() sends a bare JSON array, not {"elements": [...]}."""
    route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    await replace_form_elements(123, [{"elementType": "TEXT", "text": "Hello"}])

    assert route.call_count == 1
    # Assert the raw bytes: the wrapping defect is invisible to a parsed comparison
    # of the inner list.
    assert route.calls.last.request.content == b'[{"elementType":"TEXT","text":"Hello"}]'


async def test_replace_form_elements_raises_when_a_200_reports_field_errors(
    respx_mock: respx.MockRouter,
) -> None:
    """
    A 200 whose ErrorMessage body carries field errors must not read as success.

    The spec declares this endpoint's 200 as ErrorMessage, so the status says the
    request was understood and only the body says whether it was applied. Handing
    that body back as an ordinary result reports a write that did not happen.
    """
    respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json=REJECTION_BODY))

    with pytest.raises(ToolError) as caught:
        await replace_form_elements(123, [{"elementType": "TEXT", "text": ""}])

    message = str(caught.value)
    assert "Validation failed" in message
    assert "elements[0].text" in message
    assert "must not be blank" in message
    # The MultiValueMap artefact is not reported as a failing field.
    assert "empty" not in message


async def test_update_form_element_raises_when_a_200_reports_field_errors(
    respx_mock: respx.MockRouter,
) -> None:
    """update_form_element() inherits the body check from the same PUT route."""
    respx_mock.get(ELEMENTS_URL).mock(return_value=httpx.Response(200, json=THREE_ELEMENTS))
    respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json=REJECTION_BODY))

    with pytest.raises(ToolError) as caught:
        await update_form_element(123, 22, {"text": ""})

    assert "elements[0].text" in str(caught.value)


async def test_replace_form_elements_accepts_a_200_with_no_field_errors(
    respx_mock: respx.MockRouter,
) -> None:
    """
    An absent or empty errors object on this route is a genuine success.

    The predicate is "carries a real field error", not "has an errors key": an
    ErrorMessage body saying nothing went wrong must still come back as a result.
    """
    respx_mock.put(ELEMENTS_URL).mock(
        return_value=httpx.Response(
            200, json={"message": "OK", "errors": {"empty": True}, "confirmForceCleanupErrors": {}}
        )
    )

    result = await replace_form_elements(123, [{"elementType": "TEXT", "text": "Hello"}])

    assert json.loads(result)["message"] == "OK"


async def test_replace_form_elements_validates_each_element(
    respx_mock: respx.MockRouter,
) -> None:
    """An invalid elementType is rejected locally and no request is sent."""
    route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError) as caught:
        await replace_form_elements(
            123,
            [{"elementType": "TEXT", "text": "fine"}, {"elementType": "NOPE"}],
        )

    message = str(caught.value)
    assert "elementType" in message
    # The offending element is named by index, not just "something is wrong".
    assert "1" in message
    assert route.call_count == 0


async def test_replace_form_elements_accepts_several_element_types(
    respx_mock: respx.MockRouter,
) -> None:
    """
    Real elements of different types pass local validation.

    ElementDTO is one flat schema covering every element type, so the unknown-key
    rejection applies to the union of all their fields. A validator that refused a
    legitimate MATRIX_RADIO or LINEAR_SCALE would be worse than no validator: the
    caller could not get past it.
    """
    route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    elements: list[dict[str, object]] = [
        {"elementType": "HEADING", "text": "Section", "sequence": 1},
        {"elementType": "QUESTION", "text": "Name?", "maxNumberOfCharacters": 100},
        {
            "elementType": "RADIO",
            "text": "Pick one",
            "isHorizontal": True,
            "answerOptions": [{"text": "Yes", "sequence": 1}],
        },
        {
            "elementType": "MATRIX_RADIO",
            "text": "Rate these",
            "subElements": [{"text": "Speed", "sequence": 1}],
            "answerOptions": [{"text": "Good", "sequence": 1}],
        },
        {
            "elementType": "LINEAR_SCALE",
            "minimumValue": 1,
            "maximumValue": 5,
            "linearScaleType": "START_END",
            "isRangeMarksShown": True,
        },
        {
            "elementType": "IMAGE",
            "imageUrl": "https://example.org/a.png",
            "imageAlignment": "CENTER",
            "imageSize": "MEDIUM",
            "altText": "An image",
        },
        {"elementType": "DATE", "dateFormat": "DATE_TIME", "text": "When?"},
        {
            "elementType": "NATIONAL_ID_NUMBER",
            "nationalIdNumberType": "NORWEGIAN_ID_NUMBER",
            "nationalIdNumberOfDigits": 11,
            "repeatedNationalIdRequired": True,
        },
    ]

    await replace_form_elements(123, elements)

    assert route.call_count == 1
    assert _body(route) == elements


async def test_replace_form_elements_accepts_an_unknown_key(
    respx_mock: respx.MockRouter,
) -> None:
    """
    A key the vendored snapshot does not declare is forwarded, not rejected.

    The documented way to use this tool is to read the elements, edit them and
    write them back. If the live API has gained a field since the snapshot was
    committed, rejecting it here would leave the caller nothing to do but delete
    data the server sent — which this whole-list write then makes permanent. The
    API has the final say on field names; the local check is for types, enums
    and required fields.
    """
    route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    element: dict[str, object] = {
        "elementId": 1,
        "elementType": "TEXT",
        "text": "Hello",
        "fieldFromTheFuture": 1,
    }
    await replace_form_elements(123, [element])

    assert route.call_count == 1
    assert _body(route) == [element]


async def test_update_form_element_reads_patches_and_puts_the_whole_list(
    respx_mock: respx.MockRouter,
) -> None:
    """update_form_element() PUTs every element back, with only the target changed."""
    get_route = respx_mock.get(ELEMENTS_URL).mock(
        return_value=httpx.Response(200, json=THREE_ELEMENTS)
    )
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    await update_form_element(123, 22, {"text": "new"})

    assert get_route.call_count == 1
    assert put_route.call_count == 1

    # Byte-for-byte: structural equality would miss a key added to the patched
    # element, or its keys coming back in a different order.
    expected = [dict(e) for e in THREE_ELEMENTS]
    expected[1]["text"] = "new"
    assert put_route.calls.last.request.content == json.dumps(
        expected, separators=(",", ":")
    ).encode("utf-8")

    sent = _body(put_route)
    assert isinstance(sent, list)
    assert len(sent) == 3
    # Order is preserved and the untouched elements are sent back unchanged.
    assert sent[0] == THREE_ELEMENTS[0]
    assert sent[2] == THREE_ELEMENTS[2]
    # Only the target's text changed; its other fields survive.
    assert sent[1]["text"] == "new"
    assert sent[1]["elementId"] == 22
    assert sent[1]["isMandatory"] is True
    assert sent[1]["answerOptions"] == THREE_ELEMENTS[1]["answerOptions"]


async def test_update_form_element_raises_when_the_id_is_absent(
    respx_mock: respx.MockRouter,
) -> None:
    """
    An element id that is not in the form fails, and nothing is written.

    PUTting the unchanged list would report success while changing nothing, and
    the caller's next step assumes the edit landed.
    """
    get_route = respx_mock.get(ELEMENTS_URL).mock(
        return_value=httpx.Response(200, json=THREE_ELEMENTS)
    )
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError) as caught:
        await update_form_element(123, 4242, {"text": "new"})

    message = str(caught.value)
    assert "4242" in message
    # The ids that do exist are named, so the caller can correct itself.
    assert "22" in message
    assert get_route.call_count == 1
    assert put_route.call_count == 0


async def test_update_form_element_replaces_nested_lists_whole(
    respx_mock: respx.MockRouter,
) -> None:
    """changes merges shallowly: answerOptions is replaced, not merged element-wise."""
    respx_mock.get(ELEMENTS_URL).mock(return_value=httpx.Response(200, json=THREE_ELEMENTS))
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    await update_form_element(
        123, 22, {"answerOptions": [{"answerOptionId": 1, "text": "Maybe", "sequence": 1}]}
    )

    sent = _body(put_route)
    assert isinstance(sent, list)
    assert sent[1]["answerOptions"] == [{"answerOptionId": 1, "text": "Maybe", "sequence": 1}]


async def test_update_form_element_validates_changes_before_reading(
    respx_mock: respx.MockRouter,
) -> None:
    """A bad value in changes fails before either request is issued."""
    get_route = respx_mock.get(ELEMENTS_URL).mock(
        return_value=httpx.Response(200, json=THREE_ELEMENTS)
    )
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError) as caught:
        await update_form_element(123, 22, {"elementType": "NOPE"})

    assert "elementType" in str(caught.value)
    assert get_route.call_count == 0
    assert put_route.call_count == 0


async def test_update_form_element_does_not_validate_the_servers_own_elements(
    respx_mock: respx.MockRouter,
) -> None:
    """
    A field newer than the vendored snapshot does not block a read-modify-write.

    The elements come back from the API, not from the caller, so revalidating them
    would turn any drift between the live API and the snapshot into a dead end:
    the caller could neither remove the unknown field nor get past the validator.
    """
    drifted = [{"elementId": 22, "elementType": "TEXT", "text": "old", "fieldFromTheFuture": 1}]
    respx_mock.get(ELEMENTS_URL).mock(return_value=httpx.Response(200, json=drifted))
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    await update_form_element(123, 22, {"text": "new"})

    assert put_route.call_count == 1
    sent = _body(put_route)
    assert isinstance(sent, list)
    assert sent[0]["fieldFromTheFuture"] == 1
    assert sent[0]["text"] == "new"


async def test_update_form_element_rejects_empty_changes(respx_mock: respx.MockRouter) -> None:
    """
    An empty changes dict fails instead of rewriting the list for no reason.

    The PUT would be a no-op in content, but it still overwrites whatever someone
    else wrote between the read and the write — the hazard this tool's own
    docstring warns about, incurred for no benefit at all.
    """
    get_route = respx_mock.get(ELEMENTS_URL).mock(
        return_value=httpx.Response(200, json=THREE_ELEMENTS)
    )
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError) as caught:
        await update_form_element(123, 22, {})

    assert "empty" in str(caught.value)
    assert get_route.call_count == 0
    assert put_route.call_count == 0


async def test_update_form_element_rejects_element_id_in_changes(
    respx_mock: respx.MockRouter,
) -> None:
    """
    changes may not carry elementId: it would replace the element, not retarget.

    ElementDTO declares elementId, so the schema accepts it. Applied, it gives the
    matched element a different id, which asks the API to swap it for another
    element rather than update the one the caller named.
    """
    get_route = respx_mock.get(ELEMENTS_URL).mock(
        return_value=httpx.Response(200, json=THREE_ELEMENTS)
    )
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError) as caught:
        await update_form_element(123, 22, {"elementId": 99, "text": "new"})

    assert "elementId" in str(caught.value)
    assert get_route.call_count == 0
    assert put_route.call_count == 0


async def test_update_form_element_rejects_a_non_list_response(
    respx_mock: respx.MockRouter,
) -> None:
    """A GET that does not answer with a list of elements fails instead of guessing."""
    respx_mock.get(ELEMENTS_URL).mock(
        return_value=httpx.Response(200, json={"elements": THREE_ELEMENTS})
    )
    put_route = respx_mock.put(ELEMENTS_URL).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(ToolError):
        await update_form_element(123, 22, {"text": "new"})

    assert put_route.call_count == 0
