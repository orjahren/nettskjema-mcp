"""Tests for the submission write tools: delivering a response, and deleting responses."""

import inspect
import json

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from nettskjema_mcp.tools.submissions import (
    delete_all_submissions,
    delete_submissions,
    submit_form,
    submit_form_for_invitation,
)
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

# The spec declares the 200 of both deliver operations as an untyped object map
# ({"type": "object", "additionalProperties": {}}), so no property is part of the
# contract. The key below is illustrative: the tool passes the body through
# unchanged, and the fixture validator accepts any object here.
DELIVERED_SUBMISSION: dict[str, object] = {"submissionId": 98765}


async def test_submit_form_sends_deliver_submission_shape(respx_mock: respx.MockRouter) -> None:
    """submit_form() sends DeliverSubmissionDTO: {answers: [...], metadata: {...}}."""
    url = f"{TEST_BASE_URL}/form/123/submission"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=DELIVERED_SUBMISSION))

    await submit_form(
        123,
        answers=[{"questionId": 11, "type": "TEXT", "text": "Hello"}],
        metadata={"elapsedTime": 42},
    )

    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content.decode("utf-8"))

    # Not a flat answer map: the answers live under "answers".
    assert set(body) == {"answers", "metadata"}
    assert body["answers"] == [{"questionId": 11, "type": "TEXT", "text": "Hello"}]
    assert body["metadata"] == {"elapsedTime": 42}


async def test_submit_form_omits_metadata_when_none(respx_mock: respx.MockRouter) -> None:
    """submit_form() leaves metadata out entirely rather than sending null."""
    url = f"{TEST_BASE_URL}/form/123/submission"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=DELIVERED_SUBMISSION))

    await submit_form(123, answers=[{"type": "TEXT", "text": "Hello"}])

    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content.decode("utf-8"))
    assert set(body) == {"answers"}


async def test_submit_form_for_invitation_uses_the_invitation_path(
    respx_mock: respx.MockRouter,
) -> None:
    """submit_form_for_invitation() posts to /form/invitation/{id}/submission."""
    url = f"{TEST_BASE_URL}/form/invitation/55/submission"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=DELIVERED_SUBMISSION))

    await submit_form_for_invitation(55, answers=[{"type": "TEXT", "text": "Hi"}])

    assert route.call_count == 1
    request = route.calls.last.request
    assert request.url.path.endswith("/form/invitation/55/submission")
    assert json.loads(request.content.decode("utf-8")) == {
        "answers": [{"type": "TEXT", "text": "Hi"}]
    }


async def test_submit_form_rejects_an_invalid_answer_type_locally(
    respx_mock: respx.MockRouter,
) -> None:
    """An answer type outside the ClientAnswerDTO enum fails before the request."""
    url = f"{TEST_BASE_URL}/form/123/submission"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=DELIVERED_SUBMISSION))

    with pytest.raises(ToolError) as caught:
        await submit_form(123, answers=[{"type": "NOT_A_TYPE"}])

    assert "NOT_A_TYPE" in str(caught.value) or "one of" in str(caught.value)
    assert route.call_count == 0


async def test_submit_form_passes_an_undeclared_answer_field_through(
    respx_mock: respx.MockRouter,
) -> None:
    """A field newer than the vendored snapshot reaches the API instead of being rejected."""
    url = f"{TEST_BASE_URL}/form/123/submission"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200, json=DELIVERED_SUBMISSION))

    await submit_form(123, answers=[{"type": "TEXT", "text": "Hi", "subElementId": 7}])

    assert route.call_count == 1
    body = json.loads(route.calls.last.request.content.decode("utf-8"))
    assert body["answers"][0]["subElementId"] == 7


async def test_delete_submissions_sends_a_bare_array(respx_mock: respx.MockRouter) -> None:
    """delete_submissions() sends [1,2,3], not {"submissionIds": [1,2,3]}."""
    url = f"{TEST_BASE_URL}/form/123/submission"
    route = respx_mock.delete(url).mock(return_value=httpx.Response(200))

    await delete_submissions(123, [1, 2, 3])

    assert route.call_count == 1
    request = route.calls.last.request

    # Raw bytes: wrapping the bare array in an object is the recurring defect.
    assert request.content == b"[1,2,3]"
    # The singular path, which deletes only the listed submissions.
    assert request.url.path.endswith("/form/123/submission")


async def test_delete_submissions_rejects_an_empty_list(respx_mock: respx.MockRouter) -> None:
    """An empty id list is refused rather than sent: its server-side meaning is unspecified."""
    url = f"{TEST_BASE_URL}/form/123/submission"
    route = respx_mock.delete(url).mock(return_value=httpx.Response(200))

    with pytest.raises(ToolError) as caught:
        await delete_submissions(123, [])

    assert "submission_ids" in str(caught.value)
    assert route.call_count == 0


async def test_delete_all_submissions_hits_the_plural_path(respx_mock: respx.MockRouter) -> None:
    """delete_all_submissions() hits /submissions, not the singular /submission."""
    singular = respx_mock.delete(f"{TEST_BASE_URL}/form/123/submission").mock(
        return_value=httpx.Response(200)
    )
    plural = respx_mock.delete(f"{TEST_BASE_URL}/form/123/submissions").mock(
        return_value=httpx.Response(200)
    )

    await delete_all_submissions(123)

    assert plural.call_count == 1
    assert singular.call_count == 0
    assert plural.calls.last.request.url.path.endswith("/form/123/submissions")


async def test_delete_all_submissions_sends_no_body(respx_mock: respx.MockRouter) -> None:
    """
    No id list is sent, because none would scope the deletion.

    The spec marks the request body optional on an operation whose summary is
    "Delete all submissions", so sending ids could only mislead a reader of the
    call into thinking the blast radius was limited.

    The headers are pinned alongside the bytes: the whole safety argument for
    this tool is that a bodiless DELETE is acceptable here, and a request
    announcing a JSON body it does not have is not that. A later change to the
    client that always set Content-Type would otherwise pass unnoticed.
    """
    route = respx_mock.delete(f"{TEST_BASE_URL}/form/123/submissions").mock(
        return_value=httpx.Response(200)
    )

    await delete_all_submissions(123)

    assert route.call_count == 1
    request = route.calls.last.request
    assert request.content == b""
    assert "content-type" not in request.headers
    assert "content-length" not in request.headers


async def test_delete_all_submissions_takes_no_id_parameter() -> None:
    """
    The tool must not offer a parameter that looks like it limits the deletion.

    A model passing three ids and losing every response is the failure this
    signature exists to make impossible, so it is asserted rather than left to
    a reviewer.
    """
    assert list(inspect.signature(delete_all_submissions).parameters) == ["form_id"]


async def test_delete_tools_report_an_empty_body_as_success(respx_mock: respx.MockRouter) -> None:
    """Both deletes answer 200 with no content; that is rendered as a success marker."""
    respx_mock.delete(f"{TEST_BASE_URL}/form/123/submission").mock(return_value=httpx.Response(200))
    respx_mock.delete(f"{TEST_BASE_URL}/form/123/submissions").mock(
        return_value=httpx.Response(200)
    )

    assert json.loads(await delete_submissions(123, [1])) == {
        "status": "success",
        "httpStatus": 200,
    }
    assert json.loads(await delete_all_submissions(123)) == {
        "status": "success",
        "httpStatus": 200,
    }


async def test_submit_form_surfaces_a_rejection(respx_mock: respx.MockRouter) -> None:
    """A 400 from the deliver endpoint reaches the model with its field errors."""
    url = f"{TEST_BASE_URL}/form/123/submission"
    respx_mock.post(url).mock(
        return_value=httpx.Response(
            400,
            json={
                "message": "Submission rejected",
                "errors": {"answers": ["question 11 is mandatory"]},
            },
        )
    )

    with pytest.raises(ToolError) as caught:
        await submit_form(123, answers=[{"type": "TEXT", "text": ""}])

    message = str(caught.value)
    assert "answers" in message
    assert "mandatory" in message
