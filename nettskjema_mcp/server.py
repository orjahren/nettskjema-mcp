"""The FastMCP server: the shared instance, the error bridge, and the entry point.

Tool modules do not create servers of their own. They import :func:`tool` from
here, and this module imports them at the bottom for their registration side
effects. Adding a tool module is therefore one line there and nothing else.
"""

import functools
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

from dotenv import load_dotenv
from fastmcp import FastMCP

from nettskjema_mcp.config import get_settings
from nettskjema_mcp.errors import NettskjemaError, to_tool_error

logger = logging.getLogger(__name__)

mcp: FastMCP = FastMCP("nettskjema")

# Every tool is an async function answering with a string: a tool result is
# text, and the client renders whatever we hand back.
ToolFunction = TypeVar("ToolFunction", bound=Callable[..., Awaitable[str]])

# Marks a function as having been wrapped by bridge_errors. A contract test
# asserts it on every registered tool, so a tool registered with a bare
# @mcp.tool — which would lose the bridge — fails the suite instead of quietly
# reporting unhelpful errors at runtime.
BRIDGED_ATTRIBUTE = "__nettskjema_bridged__"

DEFAULT_LOG_LEVEL = logging.INFO


def bridge_errors(fn: ToolFunction) -> ToolFunction:
    """
    Wrap a tool so its typed errors reach the model as MCP tool errors.

    Tool bodies raise the typed errors from :mod:`nettskjema_mcp.errors` and
    never catch them; the translation happens here, once, for every tool.

    FastMCP re-raises a ToolError untouched but rewrites any other exception
    into ``Error calling tool '<name>': ...`` — or, with ``mask_error_details``
    enabled, into ``Error calling tool '<name>'`` with no detail at all. Both
    would throw away the per-field validation detail the error hierarchy goes
    to the trouble of rendering, so the conversion happens before FastMCP sees
    the failure rather than after.

    Args:
        fn: The undecorated tool coroutine function.

    Returns:
        A wrapper with the same signature, name and docstring.
    """

    @functools.wraps(fn)
    async def bridged(*args: object, **kwargs: object) -> str:
        try:
            return await fn(*args, **kwargs)
        except NettskjemaError as exc:
            raise to_tool_error(exc) from exc

    setattr(bridged, BRIDGED_ATTRIBUTE, True)
    # functools.wraps keeps the signature FastMCP reads, but the wrapper's own
    # (*args, **kwargs) type cannot express that, so the cast restores it.
    return cast(ToolFunction, bridged)


def tool(*, annotations: dict[str, bool] | None = None) -> Callable[[ToolFunction], ToolFunction]:
    """
    Register a tool with the shared server, through the error bridge.

    Use this instead of ``@mcp.tool``: it is the single point where typed
    errors are translated. The decorated name stays a plain coroutine function,
    so a tool can be called — and tested — directly.

    Args:
        annotations: MCP tool annotations. Pass ``{"readOnlyHint": True}`` for
            a tool that only reads.

    Returns:
        A decorator registering the function and returning the bridged wrapper.
    """

    def decorator(fn: ToolFunction) -> ToolFunction:
        bridged = bridge_errors(fn)
        mcp.tool(bridged, annotations=annotations)
        return bridged

    return decorator


def _log_level(name: str) -> int:
    """
    Resolve a configured level name, falling back to INFO.

    Args:
        name: The level name from the environment, in any case.

    Returns:
        The matching logging level, or INFO if the name is not a level.
    """
    return logging.getLevelNamesMapping().get(name.strip().upper(), DEFAULT_LOG_LEVEL)


def main() -> None:
    """
    Run the MCP server over stdio.

    Loads the .env file first, so that configuration read afterwards sees it,
    and sends every log record to stderr: stdout is the JSON-RPC channel and
    anything written there corrupts the protocol.
    """
    load_dotenv()
    settings = get_settings()
    logging.basicConfig(
        level=_log_level(settings.log_level),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.debug("Starting the Nettskjema MCP server against %s", settings.base_url)
    mcp.run()


# Tool modules are imported for their registration side effects, after `mcp`
# and `tool` exist above. This block is the integration point: a new tool
# module is one line here and nothing else.
from nettskjema_mcp.tools import meta  # noqa: E402, F401

__all__ = ["bridge_errors", "main", "mcp", "tool"]
