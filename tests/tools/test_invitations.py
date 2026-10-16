"""Tests for invitation tools."""

import inspect
import json

import httpx
import pytest
import respx

from nettskjema_mcp.server import mcp
from nettskjema_mcp.tools.invitations import remind_all_pending_invitations
from tests.conftest import TEST_BASE_URL

pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]


async def test_remind_sends_no_body(respx_mock: respx.MockRouter) -> None:
    """remind_all_pending_invitations() POSTs with no request body."""
    url = f"{TEST_BASE_URL}/form/1/remind"
    route = respx_mock.post(url).mock(return_value=httpx.Response(200))

    await remind_all_pending_invitations(form_id=1)

    assert route.call_count == 1
    # Verify no body was sent (content is empty or None)
    request = route.calls.last.request
    assert not request.content or request.content == b""


async def test_remind_takes_only_a_form_id() -> None:
    """remind_all_pending_invitations() accepts only form_id as a parameter."""
    sig = inspect.signature(remind_all_pending_invitations)
    assert list(sig.parameters) == ["form_id"]


def test_docstring_states_the_scope_and_the_frontend_handoff() -> None:
    """Docstring documents all-or-nothing scope and frontend URLs for full management."""
    doc = remind_all_pending_invitations.__doc__
    assert doc is not None
    assert "every" in doc.lower()
    assert "collect-responses/invited" in doc


async def test_remind_returns_the_success_marker(respx_mock: respx.MockRouter) -> None:
    """
    The returned marker is the only observable output, so it is pinned here.

    The spec declares a 200 with no content, so there is nothing to report but
    the marker the client synthesises. The docstring quotes it exactly; without
    this test the docstring could promise any shape at all and stay green.
    """
    respx_mock.post(f"{TEST_BASE_URL}/form/7/remind").mock(return_value=httpx.Response(200))

    result = await remind_all_pending_invitations(form_id=7)

    assert json.loads(result) == {"status": "success", "httpStatus": 200}
    assert '{"status": "success", "httpStatus": 200}' in (
        remind_all_pending_invitations.__doc__ or ""
    )


async def test_remind_is_annotated_destructive() -> None:
    """
    The annotation is the only thing standing between a model and five thousand
    emails.

    MCP clients use it to decide whether to ask before calling. The endpoint
    reminds every pending invitee on the form and nothing undoes a sent email,
    so the hint is load-bearing rather than decorative.
    """
    tools = {registered.name: registered for registered in await mcp.list_tools()}

    annotations = tools["remind_all_pending_invitations"].annotations
    assert annotations is not None
    assert annotations.destructiveHint is True
