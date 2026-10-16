"""Tests for configuration module."""

import pytest
from nettskjema_mcp.config import get_settings, reset_settings


def test_defaults_are_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that defaults point to production endpoints."""
    for k in (
        "NETTSKJEMA_BASE_URL",
        "NETTSKJEMA_AUTH_URL",
        "NETTSKJEMA_TIMEOUT",
        "NETTSKJEMA_MAX_ANSWER_ROWS",
        "NETTSKJEMA_LOG_LEVEL",
    ):
        monkeypatch.delenv(k, raising=False)
    reset_settings()
    s = get_settings()
    assert s.base_url == "https://nettskjema.no/api/v3"
    assert s.auth_url == "https://authorization.nettskjema.no/oauth2/token"
    assert s.timeout == 30.0
    assert s.max_answer_rows == 1000
    assert s.log_level == "INFO"


def test_environment_overrides_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables should override defaults."""
    monkeypatch.setenv("NETTSKJEMA_BASE_URL", "https://nettskjema-test.uio.no/api/v3")
    reset_settings()
    assert get_settings().base_url == "https://nettskjema-test.uio.no/api/v3"


def test_settings_not_read_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings must be read lazily, not at import time."""
    # setenv after the module is already imported must still take effect
    monkeypatch.setenv("NETTSKJEMA_TIMEOUT", "5")
    reset_settings()
    assert get_settings().timeout == 5.0


def test_credentials_default_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client credentials should default to None when not set."""
    monkeypatch.delenv("NETTSKJEMA_CLIENT_ID", raising=False)
    monkeypatch.delenv("NETTSKJEMA_CLIENT_SECRET", raising=False)
    reset_settings()
    s = get_settings()
    assert s.client_id is None
    assert s.client_secret is None
