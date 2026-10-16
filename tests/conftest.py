"""Shared fixtures for the whole test suite."""

from collections.abc import Iterator

import pytest

from nettskjema_mcp.client import reset_client
from nettskjema_mcp.config import reset_settings

# The .invalid TLD is reserved and never resolves, so a request that escapes its
# mock fails loudly instead of quietly reaching the real Nettskjema API.
TEST_BASE_URL = "https://nettskjema.invalid/api/v3"
TEST_AUTH_URL = "https://authorization.nettskjema.invalid/oauth2/token"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point every test at unroutable hosts and reset the module-level caches."""
    monkeypatch.setenv("NETTSKJEMA_BASE_URL", TEST_BASE_URL)
    monkeypatch.setenv("NETTSKJEMA_AUTH_URL", TEST_AUTH_URL)
    monkeypatch.setenv("NETTSKJEMA_CLIENT_ID", "test-client")
    monkeypatch.setenv("NETTSKJEMA_CLIENT_SECRET", "test-secret")
    reset_settings()
    reset_client()
    yield
    reset_settings()
    reset_client()
