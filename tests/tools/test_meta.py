"""Tests for the meta tools and for the server conventions they establish."""

import ast
import inspect
import json
import logging
import sys
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import nettskjema_mcp
from nettskjema_mcp import server as server_module
from nettskjema_mcp.client import dump
from nettskjema_mcp.config import reset_settings
from nettskjema_mcp.routes import (
    ERROR_BODY_EXEMPT,
    ERROR_BODY_ROUTES,
    LOCAL_TOOLS,
    REGISTRY,
    Route,
    load_spec,
)
from nettskjema_mcp.server import _log_level, bridge_errors, main, mcp, tool
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


def _writes_to_stdout(func: ast.expr) -> bool:
    """
    Report whether a call target writes to stdout.

    Covers the plain ``print(...)`` anyone leaves behind while debugging, the
    attribute forms that dodge a bare-name check (``builtins.print``), and
    direct writes such as ``sys.stdout.write`` — the one a tool streaming a
    large export might reach for.
    """
    target = ast.unparse(func)
    return target == "print" or target.endswith(".print") or "stdout" in target


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
            if isinstance(node, ast.Call) and _writes_to_stdout(node.func):
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
                "errors": {"username": ["is unknown"]},
            },
        )
    )

    with pytest.raises(ToolError) as caught:
        await get_user_info()

    message = str(caught.value)
    assert "No such user" in message
    assert "username" in message
    assert "is unknown" in message


@pytest.mark.parametrize("mask_error_details", [False, True])
async def test_a_typed_error_keeps_its_detail_through_the_server(
    respx_mock: respx.MockRouter, mask_error_details: bool
) -> None:
    """
    The detail survives FastMCP's own error handling, masked or not.

    Both halves of this matter. With masking on, FastMCP replaces an unhandled
    exception with a bare "Error calling tool", which is the whole argument for
    wrapping the body instead of using middleware. With masking off it keeps
    the text but prefixes it — so the assertion is on the exact message, not on
    a substring: the prefix is what tells us the bridge did not fire.
    """
    respx_mock.get(ME_URL).mock(
        return_value=httpx.Response(
            400,
            json={
                "message": "Validation failed",
                "errors": {
                    "title": ["must not be blank"],
                    "elements[2].questionText": ["is too long"],
                },
            },
        )
    )
    # A server of its own, because masking is fixed at construction. It serves
    # the same bridged function the shared server registered.
    server: FastMCP = FastMCP("masking-probe", mask_error_details=mask_error_details)
    server.tool(get_user_info, annotations={"readOnlyHint": True})

    with pytest.raises(ToolError) as caught:
        await server.call_tool("get_user_info", {})

    assert str(caught.value) == (
        "Validation failed\ntitle → must not be blank\nelements[2].questionText → is too long"
    )


async def test_every_registered_tool_goes_through_the_error_bridge() -> None:
    """
    No tool may be registered with a bare @mcp.tool.

    The bridge is what turns a typed error into a ToolError the model can read;
    a tool that skipped it would report "Error calling tool" and lose the
    per-field detail. This is the contract tasks 7-15 inherit.
    """
    tools = await mcp.list_tools()

    assert tools
    for registered in tools:
        fn = getattr(registered, "fn", None)
        assert fn is not None, f"{registered.name} is not a function tool"
        assert getattr(fn, "__nettskjema_bridged__", False), (
            f"{registered.name} was registered without the error bridge; "
            "use @tool() from nettskjema_mcp.server, not @mcp.tool"
        )


async def test_every_registered_tool_declares_its_routes() -> None:
    """
    A tool must say which routes it calls, or say that it calls none.

    REGISTRY is what test_contract.py validates against the vendored OpenAPI
    spec, so a tool that never lands there ships an unchecked route — which is
    exactly how the version being replaced ended up with five tools calling
    endpoints that do not exist.
    """
    tools = await mcp.list_tools()

    assert tools
    for registered in tools:
        assert registered.name in REGISTRY or registered.name in LOCAL_TOOLS, (
            f"{registered.name} declares no routes; add @endpoint(ROUTE) below @tool(), "
            "or add the name to routes.LOCAL_TOOLS if it makes no request"
        )


async def test_read_only_tools_are_exactly_the_get_only_tools() -> None:
    """
    readOnlyHint must agree with the tool's HTTP methods, in both directions.

    Clients auto-approve a call annotated read-only without asking the user, so
    the hint on a tool that writes is a safety defect, not a documentation one.
    The converse is asserted too: a tool that only reads and forgets the hint
    makes clients prompt for permission it did not need, which trains people to
    click through the prompts that matter. Tools in LOCAL_TOOLS issue no
    request at all and are exempt from both directions.

    Tools that write to the local filesystem invert the gets-only side rather
    than escaping it: they read from the API but can overwrite an arbitrary
    local file the model names, so they are not read-only in the MCP sense and
    the hint must be absent. Merely exempting them let the annotation come back
    unnoticed — re-adding readOnlyHint to export_form_csv left the suite green.
    """
    # Tools that must NOT carry readOnlyHint despite issuing only GETs, because
    # they write to local files and can overwrite user data.
    FILE_WRITERS = {
        "get_submission_pdf",  # writes PDF to output_path, overwrites existing files
        "export_form_excel",  # writes Excel to output_path, overwrites existing files
        "export_form_csv",  # writes CSV to output_path when given, overwrites existing files
        "get_answer_attachment",  # writes attachment to output_path, overwrites existing files
    }

    for registered in await mcp.list_tools():
        routes = REGISTRY.get(registered.name)
        if registered.name in LOCAL_TOOLS or routes is None:
            # An undeclared tool is reported by the route test, not twice here.
            continue
        annotations = registered.annotations
        read_only = annotations is not None and annotations.readOnlyHint is True
        gets_only = all(route.method == "GET" for route in routes)

        if registered.name in FILE_WRITERS:
            assert not read_only, (
                f"{registered.name} takes an output_path and overwrites whatever file "
                "the model names, but is annotated readOnlyHint; clients auto-approve "
                "read-only calls without asking, so drop the annotation. If it no "
                "longer writes a caller-named file, take it out of FILE_WRITERS"
            )
            continue

        if read_only:
            assert gets_only, (
                f"{registered.name} is annotated readOnlyHint but calls "
                f"{sorted({route.method for route in routes})}; clients auto-approve "
                "read-only tools, so drop the annotation if the tool changes anything. "
                "If it genuinely only reads and the API simply requires a non-GET verb, "
                "exempt it here deliberately rather than dropping the hint"
            )
        else:
            assert not gets_only, (
                f"{registered.name} only issues GETs but is not annotated readOnlyHint; "
                'add annotations={"readOnlyHint": True}'
            )


async def test_delete_and_put_tools_carry_destructive_hint() -> None:
    """
    Every tool with a DELETE or PUT route must carry destructiveHint.

    Clients may warn or require extra confirmation for destructive operations,
    so missing the hint on such a tool trains users to ignore warnings. PUT is
    counted because every PUT in this API is replace semantics — PUT
    /form/{formId}/elements overwrites a form's whole element list — and that is
    exactly the kind of call a client must not wave through.

    One-directional: a tool with neither verb may still carry the hint. If a
    later task adds a PUT that genuinely is not destructive, exempt it here
    deliberately rather than discovering the rule by deleting the annotation.
    """
    for registered in await mcp.list_tools():
        routes = REGISTRY.get(registered.name)
        if registered.name in LOCAL_TOOLS or routes is None:
            continue

        annotations = registered.annotations
        destructive = annotations is not None and annotations.destructiveHint is True
        replacing = sorted({r.method for r in routes if r.method in {"DELETE", "PUT"}})

        if replacing:
            assert destructive, (
                f"{registered.name} issues {', '.join(replacing)} but is not annotated "
                'destructiveHint; add annotations={"destructiveHint": True}. If this '
                "particular PUT genuinely replaces nothing the caller would miss, exempt "
                "it in this test by name and say why"
            )


def _error_message_success_routes() -> set[Route]:
    """
    Find every route the spec declares with an ErrorMessage-shaped plain 2xx.

    207 is excluded: the client already raises PartialSuccessError on it from the
    status alone, so the body check has nothing left to catch there. What is left
    are the routes where the status is clean and only the body says whether the
    change was applied.
    """
    spec = load_spec()
    found: set[Route] = set()
    for path, operations in spec["paths"].items():  # type: ignore[union-attr]
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for code, response in operation.get("responses", {}).items():
                if not code.startswith("2") or code == "207":
                    continue
                for media in response.get("content", {}).values():
                    ref = media.get("schema", {}).get("$ref", "")
                    if ref.endswith("/ErrorMessage"):
                        found.add(Route(method.upper(), path))
    return found


def test_every_error_message_success_route_is_classified() -> None:
    """
    A route whose success body carries the outcome must be checked, or exempted.

    The spec declares a few operations with an ErrorMessage schema on a plain
    2xx: HTTP 200 means the request was understood, and the body says whether
    anything was applied. Returning such a body as an ordinary result reports a
    rejected write as a successful one — on PUT /form/{formId}/elements, which
    replaces a form's whole content, that is the worst reply the server can
    give.

    The check lives in the client, keyed on routes.ERROR_BODY_ROUTES, so a tool
    cannot forget it. This test keeps that set honest against the spec: a later
    task that registers another such route fails here until it either adds the
    route to ERROR_BODY_ROUTES or records in ERROR_BODY_EXEMPT why its body is
    an answer rather than a failure report.
    """
    declared = ERROR_BODY_ROUTES | set(ERROR_BODY_EXEMPT)
    from_spec = _error_message_success_routes()

    # Every registered route with such a response must be classified. Scoped to
    # the registry so an unimplemented route is a later task's problem, not a
    # failure now.
    registered = {route for routes in REGISTRY.values() for route in routes}
    for route in sorted(registered & from_spec, key=lambda r: (r.path, r.method)):
        assert route in declared, (
            f"{route.method} {route.path} declares an ErrorMessage schema on a plain 2xx, "
            "so its body decides whether the change was applied. Add it to "
            "routes.ERROR_BODY_ROUTES so the client raises on a rejection, or to "
            "routes.ERROR_BODY_EXEMPT with the reason its body is the answer"
        )

    # And nothing stale: every route we classify must really look like that in
    # the spec, or the classification is describing a surface that moved.
    for route in sorted(declared, key=lambda r: (r.path, r.method)):
        assert route in from_spec, (
            f"{route.method} {route.path} is classified in routes.py as answering with "
            "ErrorMessage on a plain 2xx, but the vendored spec no longer says so; "
            "remove the entry"
        )
    assert ERROR_BODY_ROUTES.isdisjoint(ERROR_BODY_EXEMPT)


def test_tool_must_be_called_with_parentheses() -> None:
    """A bare @tool is the likely first mistake, so it must say what to write."""
    with pytest.raises(TypeError) as caught:
        tool(get_user_info)

    assert "@tool()" in str(caught.value)


async def test_the_error_bridge_preserves_the_signature_fastmcp_reads() -> None:
    """Wrapping must not flatten a tool's parameters into *args/**kwargs."""

    async def example(form_id: int, title: str | None = None) -> str:
        return dump({"formId": form_id, "title": title})

    bridged = bridge_errors(example)
    assert inspect.signature(bridged) == inspect.signature(example)
    assert await bridged(1) == dump({"formId": 1, "title": None})

    probe: FastMCP = FastMCP("signature-probe")
    probe.tool(bridged)
    registered = await probe.get_tool("example")
    assert registered is not None
    assert set(registered.parameters["properties"]) == {"form_id", "title"}
    assert registered.parameters["required"] == ["form_id"]


@pytest.mark.parametrize(
    "configured,expected",
    [
        ("debug", logging.DEBUG),
        ("WARNING", logging.WARNING),
        (" info ", logging.INFO),
        ("nonsense", logging.INFO),
        ("", logging.INFO),
    ],
)
def test_log_level_resolves_the_configured_name(configured: str, expected: int) -> None:
    """An unknown level name must not crash the server on startup."""
    assert _log_level(configured) == expected


def test_main_configures_stderr_logging_before_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Logging goes to stderr, at the configured level, and the server then runs.

    stdout is the JSON-RPC channel: a log handler pointed at it would corrupt
    every session. basicConfig() is a no-op once the root logger has a handler,
    so the root logger is emptied first to see what main() actually installs.
    """
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    # Real dotenv loading would read whatever .env file sits above the worktree.
    loaded: list[str] = []
    monkeypatch.setattr(server_module, "load_dotenv", lambda: loaded.append("load_dotenv"))
    monkeypatch.setattr(mcp, "run", lambda: loaded.append("run"))
    monkeypatch.setenv("NETTSKJEMA_LOG_LEVEL", "DEBUG")
    reset_settings()

    main()

    assert loaded == ["load_dotenv", "run"], "the .env file must be read before the server starts"
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
