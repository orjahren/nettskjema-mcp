"""Tests for the meta tools and for the server conventions they establish."""

import ast
import inspect
import json
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import nettskjema_mcp
from nettskjema_mcp.client import dump
from nettskjema_mcp.config import reset_settings
from nettskjema_mcp.routes import LOCAL_TOOLS, REGISTRY
from nettskjema_mcp.server import bridge_errors, mcp
from nettskjema_mcp.tools.meta import check_auth_status, get_user_info
from tests.conftest import TEST_BASE_URL

# Several tests deliberately expect no request at all, so routes are asserted
# on explicitly rather than by respx's all-called check.
pytestmark = [
    pytest.mark.respx(assert_all_called=False),
    pytest.mark.usefixtures("token_route"),
]

ME_URL = f"{TEST_BASE_URL}/me"

USER = {"username": "test-client@apiclient", "isSuperUser": False}


async def test_get_user_info_calls_me(respx_mock: respx.MockRouter) -> None:
    """get_user_info() GETs /me and returns the dumped body."""
    route = respx_mock.get(ME_URL).mock(return_value=httpx.Response(200, json=USER))

    result = await get_user_info()

    assert route.call_count == 1
    assert json.loads(result) == USER


async def test_check_auth_status_reports_missing_credentials(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check_auth_status() names both credential variables without calling the API."""
    monkeypatch.delenv("NETTSKJEMA_CLIENT_ID", raising=False)
    monkeypatch.delenv("NETTSKJEMA_CLIENT_SECRET", raising=False)
    reset_settings()
    route = respx_mock.get(ME_URL).mock(return_value=httpx.Response(200, json=USER))

    result = await check_auth_status()

    assert route.call_count == 0
    assert "NETTSKJEMA_CLIENT_ID" in result
    assert "NETTSKJEMA_CLIENT_SECRET" in result
    status = json.loads(result)
    assert status["clientIdSet"] is False
    assert status["clientSecretSet"] is False
    assert status["ready"] is False


async def test_check_auth_status_never_reveals_the_client_secret() -> None:
    """The secret is reported as set or unset, never quoted."""
    result = await check_auth_status()

    assert "test-secret" not in result
    status = json.loads(result)
    assert status["clientSecretSet"] is True
    assert status["ready"] is True


async def test_check_auth_status_is_registered_as_a_local_tool() -> None:
    """The diagnostic has no route, so the coverage contract must exempt it."""
    assert "check_auth_status" in LOCAL_TOOLS
    assert "check_auth_status" not in REGISTRY


def test_no_print_calls_in_the_package() -> None:
    """
    Nothing under nettskjema_mcp/ may print.

    Under the MCP stdio transport stdout carries JSON-RPC, so a stray print
    corrupts the protocol. Logging goes to stderr instead.
    """
    package_root = Path(nettskjema_mcp.__file__).parent
    offenders = []
    for path in sorted(package_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                offenders.append(f"{path.relative_to(package_root)}:{node.lineno}")

    assert offenders == []


def test_server_imports_every_tool_module() -> None:
    """Importing the server is enough to register every tool."""
    import nettskjema_mcp.server  # noqa: F401

    assert {"get_user_info", "check_auth_status"} <= set(REGISTRY) | LOCAL_TOOLS


async def test_both_meta_tools_are_registered_with_the_server() -> None:
    """The tools reach the MCP surface, read-only, with their docstrings."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert {"get_user_info", "check_auth_status"} <= set(tools)
    for name in ("get_user_info", "check_auth_status"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.readOnlyHint is True  # type: ignore[union-attr]
        assert tools[name].description


async def test_a_typed_error_surfaces_as_a_tool_error(respx_mock: respx.MockRouter) -> None:
    """A typed error becomes a ToolError that still carries the API's detail."""
    respx_mock.get(ME_URL).mock(
        return_value=httpx.Response(
            404,
            json={
                "message": "No such user",
                "errorKeysAndErrorMessages": {"username": ["is unknown"]},
            },
        )
    )

    with pytest.raises(ToolError) as caught:
        await get_user_info()

    message = str(caught.value)
    assert "No such user" in message
    assert "username" in message
    assert "is unknown" in message


async def test_a_typed_error_keeps_its_detail_through_the_server(
    respx_mock: respx.MockRouter,
) -> None:
    """The detail survives FastMCP's own error handling, masked or not."""
    respx_mock.get(ME_URL).mock(return_value=httpx.Response(404, json={"message": "No such user"}))

    with pytest.raises(ToolError) as caught:
        await mcp.call_tool("get_user_info", {})

    assert "No such user" in str(caught.value)


async def test_every_registered_tool_goes_through_the_error_bridge() -> None:
    """
    No tool may be registered with a bare @mcp.tool.

    The bridge is what turns a typed error into a ToolError the model can read;
    a tool that skipped it would report "Error calling tool" and lose the
    per-field detail. This is the contract tasks 7-15 inherit.
    """
    tools = await mcp.list_tools()

    assert tools
    for tool in tools:
        fn = getattr(tool, "fn", None)
        assert fn is not None, f"{tool.name} is not a function tool"
        assert getattr(fn, "__nettskjema_bridged__", False), (
            f"{tool.name} was registered without the error bridge; "
            "use @tool from nettskjema_mcp.server, not @mcp.tool"
        )


async def test_the_error_bridge_preserves_the_signature_fastmcp_reads() -> None:
    """Wrapping must not flatten a tool's parameters into *args/**kwargs."""

    async def example(form_id: int, title: str | None = None) -> str:
        return dump({"formId": form_id, "title": title})

    bridged = bridge_errors(example)
    assert inspect.signature(bridged) == inspect.signature(example)
    assert await bridged(1) == dump({"formId": 1, "title": None})

    probe: FastMCP = FastMCP("probe")
    probe.tool(bridged)
    registered = await probe.get_tool("example")
    assert registered is not None
    assert set(registered.parameters["properties"]) == {"form_id", "title"}
    assert registered.parameters["required"] == ["form_id"]
