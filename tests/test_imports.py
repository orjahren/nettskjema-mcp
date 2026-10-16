"""Import smoke tests to catch import cycles and basic breakage."""

import importlib
import pkgutil

import pytest

import nettskjema_mcp


def _discover_modules() -> list[str]:
    """Discover all importable modules under nettskjema_mcp."""
    modules = []
    for module_info in pkgutil.walk_packages(nettskjema_mcp.__path__, prefix="nettskjema_mcp."):
        modules.append(module_info.name)
    return modules


@pytest.mark.parametrize("module_name", _discover_modules())
def test_module_imports_without_error(module_name: str) -> None:
    """Verify each nettskjema_mcp module can be imported."""
    importlib.import_module(module_name)
