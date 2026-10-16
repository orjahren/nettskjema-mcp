"""Import smoke tests to catch import cycles and basic breakage."""


def test_all_modules_import_without_error() -> None:
    """Verify all nettskjema_mcp modules can be imported."""
    # Import all modules that should exist
    import nettskjema_mcp.config  # noqa: F401
    import nettskjema_mcp.errors  # noqa: F401
