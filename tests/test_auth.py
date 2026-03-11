"""Tests for OAuth authentication."""

import os
import pytest
from nettskjema_mcp import check_auth_status


@pytest.mark.asyncio
async def test_check_auth_status_no_credentials():
    """Test auth status check without credentials."""
    # Clear environment variables
    os.environ.pop("NETTSKJEMA_CLIENT_ID", None)
    os.environ.pop("NETTSKJEMA_CLIENT_SECRET", None)

    result = await check_auth_status()
    assert "client_id_set" in result
    assert "client_secret_set" in result


# Add more tests here as needed
# Note: Full integration tests require actual API credentials
