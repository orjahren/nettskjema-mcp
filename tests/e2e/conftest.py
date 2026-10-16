"""Fixtures for end-to-end tests against a live Nettskjema test environment.

E2E tests run against https://nettskjema-test.uio.no/api/v3 with credentials
from NETTSKJEMA_E2E_CLIENT_ID and NETTSKJEMA_E2E_CLIENT_SECRET. The hosts are
pinned in code — not read from the environment — so a stray .env cannot point
the harness at production.

Tests are skipped at collection if credentials are unset, so with no credentials
the session fixture never fires and nothing exits. With credentials set, the
guard checks the configured host and aborts if it is not in ALLOWED_HOSTS.
"""

import os
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urlparse

import pytest

from nettskjema_mcp.client import reset_client
from nettskjema_mcp.config import get_settings, reset_settings

# Pinned test environment hosts (not configurable from environment)
E2E_BASE_URL = "https://nettskjema-test.uio.no/api/v3"
E2E_AUTH_URL = "https://nettskjema-authorization-test.uio.no/oauth2/token"

# Allowed hosts for e2e runs (production is explicitly excluded)
ALLOWED_HOSTS = {"nettskjema-test.uio.no", "localhost"}


def assert_host_is_safe(base_url: str) -> None:
    """
    Verify the base_url host is in ALLOWED_HOSTS.

    This is the guard function that the session fixture delegates to. It is
    tested in tests/test_e2e_guard.py (outside tests/e2e/) so the test does
    not trigger the autouse fixture that calls it.

    Args:
        base_url: The base URL to check

    Raises:
        pytest.exit.Exception: If the host is not in ALLOWED_HOSTS
    """
    host = urlparse(base_url).hostname
    if host not in ALLOWED_HOSTS:
        pytest.exit(f"e2e refused: base_url host {host!r} is not in {ALLOWED_HOSTS}")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Skip e2e tests at collection if credentials are unset.

    This runs before the session fixture fires, so with no credentials no e2e
    item runs, the session fixture never fires, and nothing exits.
    """
    client_id = os.getenv("NETTSKJEMA_E2E_CLIENT_ID")
    client_secret = os.getenv("NETTSKJEMA_E2E_CLIENT_SECRET")

    if not client_id or not client_secret:
        skip_marker = pytest.mark.skip(reason="E2E credentials unset")
        for item in items:
            if item.get_closest_marker("e2e") is not None:
                item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def e2e_settings() -> Iterator[None]:
    """
    Configure the environment for e2e tests and reset on teardown.

    Sets NETTSKJEMA_BASE_URL and NETTSKJEMA_AUTH_URL to the pinned test hosts,
    and NETTSKJEMA_CLIENT_ID and NETTSKJEMA_CLIENT_SECRET from the E2E
    credentials. Resets the settings and client caches before and after.

    This fixture must be requested by any e2e fixture that needs to read
    settings or create a client.
    """
    # Save original environment
    original_env = {
        "NETTSKJEMA_BASE_URL": os.environ.get("NETTSKJEMA_BASE_URL"),
        "NETTSKJEMA_AUTH_URL": os.environ.get("NETTSKJEMA_AUTH_URL"),
        "NETTSKJEMA_CLIENT_ID": os.environ.get("NETTSKJEMA_CLIENT_ID"),
        "NETTSKJEMA_CLIENT_SECRET": os.environ.get("NETTSKJEMA_CLIENT_SECRET"),
    }

    try:
        # Set e2e environment
        os.environ["NETTSKJEMA_BASE_URL"] = E2E_BASE_URL
        os.environ["NETTSKJEMA_AUTH_URL"] = E2E_AUTH_URL
        os.environ["NETTSKJEMA_CLIENT_ID"] = os.getenv("NETTSKJEMA_E2E_CLIENT_ID", "")
        os.environ["NETTSKJEMA_CLIENT_SECRET"] = os.getenv("NETTSKJEMA_E2E_CLIENT_SECRET", "")

        reset_settings()
        reset_client()

        yield
    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        reset_settings()
        reset_client()


@pytest.fixture(scope="session", autouse=True)
def _refuse_to_run_against_production(e2e_settings: None) -> None:
    """
    Guard against accidental e2e runs against production.

    This is an autouse session fixture, so it fires once before any e2e test
    runs. It requests e2e_settings (which configures the environment) and then
    checks the configured host. If the host is not in ALLOWED_HOSTS, it aborts
    the entire session.

    The guard is a hard session abort, not a skip: delete_all_submissions is in
    the tool surface, so one accidental run against production would be
    unrecoverable.
    """
    assert_host_is_safe(get_settings().base_url)


@pytest.fixture
async def temp_form(e2e_settings: None) -> AsyncIterator[int]:
    """
    Create a throwaway form and delete it on teardown.

    Each test owns a form that exists for seconds. The form is created with
    minimal settings and deleted in teardown regardless of test outcome.

    Yields:
        The form ID

    Raises:
        UpstreamError: If form creation or deletion fails
    """
    from nettskjema_mcp.tools.forms_write import create_form

    # Create a minimal form
    result = await create_form(
        title="E2E Test Form",
        language="no",
    )
    # Extract form ID from the result string
    form_id = int(result.split("Form created with ID: ")[1].split("\n")[0])

    try:
        yield form_id
    finally:
        # Delete the form in teardown
        from nettskjema_mcp.tools.admin import delete_forms

        try:
            await delete_forms(form_ids=[form_id])
        except Exception:
            # Swallow deletion failures to avoid masking test failures
            pass


@pytest.fixture
def e2e_email() -> str:
    """
    Get the e2e test email address.

    Returns:
        The email address from NETTSKJEMA_E2E_EMAIL

    Raises:
        pytest.skip.Exception: If NETTSKJEMA_E2E_EMAIL is unset
    """
    email = os.getenv("NETTSKJEMA_E2E_EMAIL")
    if not email:
        pytest.skip("NETTSKJEMA_E2E_EMAIL unset")
    return email
