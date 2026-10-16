"""Unit tests for the e2e production guard.

The guard function is tested here, outside tests/e2e/, because an autouse
session fixture in tests/e2e/conftest.py fires during collection of anything
under that directory — including its own guard test. The default suite pins
base_url to example.invalid, so a fixture-based guard test would pytest.exit
the entire default run. Testing the function directly keeps the default suite
runnable.
"""

import pytest

from tests.e2e.conftest import assert_host_is_safe


def test_guard_aborts_on_a_production_host() -> None:
    """The guard must abort on production to prevent accidental data loss."""
    with pytest.raises(pytest.exit.Exception) as exc_info:
        assert_host_is_safe("https://nettskjema.no/api/v3")

    assert "nettskjema.no" in str(exc_info.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://nettskjema-test.uio.no/api/v3",
        "http://localhost:8008/api/v3",
    ],
)
def test_guard_allows_the_test_hosts(url: str) -> None:
    """The guard must allow test and localhost."""
    assert_host_is_safe(url)  # no exception means success
