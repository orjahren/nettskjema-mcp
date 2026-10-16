"""Route registry and OpenAPI spec loader for Nettskjema MCP tools."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

try:
    from importlib.resources import files
except ImportError:
    # Python 3.11 fallback
    from importlib.resources import files  # type: ignore[attr-defined]


F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class Route:
    """An HTTP route defined in the OpenAPI spec."""

    method: str  # upper-case
    path: str  # spec-style, e.g. "/form/{formId}/info"


# Global registry mapping tool names to their routes
REGISTRY: dict[str, tuple[Route, ...]] = {}

# Tools that have no associated route (local operations only)
LOCAL_TOOLS: frozenset[str] = frozenset({"check_auth_status"})

# Out-of-scope routes with reasons for exclusion
OUT_OF_SCOPE: dict[tuple[str, str], str] = {
    ("GET", "/form/{formId}/invitations"): (
        "v1 invitation management; v2 is the supported surface and is private"
    ),
    ("POST", "/form/{formId}/invitations"): (
        "v1 invitation management; v2 is the supported surface and is private"
    ),
    ("DELETE", "/form/{formId}/invitations"): (
        "v1 invitation management; v2 is the supported surface and is private"
    ),
    ("DELETE", "/form/{formId}/invitation"): (
        "v1 invitation management; v2 is the supported surface and is private"
    ),
}


def endpoint(*routes: Route) -> Callable[[F], F]:
    """
    Register routes for a tool function.

    Must be applied below @mcp.tool so it sees the undecorated function name.
    Duplicate registration of the same tool name raises ValueError.

    Args:
        *routes: One or more Route instances for this tool

    Returns:
        The function unchanged

    Raises:
        ValueError: If the function name is already registered
    """

    def decorator(fn: F) -> F:
        if fn.__name__ in REGISTRY:
            raise ValueError(f"Duplicate tool registration: {fn.__name__}")
        REGISTRY[fn.__name__] = routes
        return fn

    return decorator


@lru_cache(maxsize=1)
def load_spec() -> dict[str, Any]:
    """
    Load the vendored OpenAPI spec.

    The spec is cached after first load and the same dict instance is returned
    on every call. The returned mapping is a shared, cached, **read-only** view:
    callers must not mutate it or anything reachable from it. If mutation is
    needed, copy first.

    Returns:
        The OpenAPI spec as a dictionary (shared, read-only)
    """
    spec_file = files("nettskjema_mcp.spec").joinpath("openapi.json")
    with spec_file.open("r", encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]
