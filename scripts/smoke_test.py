#!/usr/bin/env python3
"""Smoke test script for the Nettskjema MCP server.

Exercises one read-only tool from each module against a live Nettskjema instance
to verify basic connectivity and authentication. Does not create or modify any data.

Usage:
    python scripts/smoke_test.py

Requires NETTSKJEMA_CLIENT_ID and NETTSKJEMA_CLIENT_SECRET to be set.
"""

import asyncio
import sys
from typing import Any

from nettskjema_mcp.tools.auth import check_auth_status
from nettskjema_mcp.tools.forms_read import get_user_info, list_my_forms

from nettskjema_mcp.config import get_settings


async def run_smoke_test() -> None:
    """Run smoke tests on read-only tools."""
    print("Nettskjema MCP Smoke Test")
    print("=" * 50)

    # Check configuration
    settings = get_settings()
    print(f"Base URL: {settings.base_url}")
    print(f"Client ID: {settings.client_id}")
    print()

    if not settings.client_id or not settings.client_secret:
        print("ERROR: NETTSKJEMA_CLIENT_ID and NETTSKJEMA_CLIENT_SECRET must be set")
        sys.exit(1)

    tests: list[tuple[str, Any]] = [
        ("Auth Status", check_auth_status),
        ("User Info", get_user_info),
        ("List Forms", list_my_forms),
    ]

    passed = 0
    failed = 0

    for name, tool in tests:
        try:
            print(f"Testing {name}...", end=" ")
            result = await tool()
            print("✓ PASS")
            print(f"  {result[:100]}...")  # Show first 100 chars
            print()
            passed += 1
        except Exception as e:
            print("✗ FAIL")
            print(f"  Error: {e}")
            print()
            failed += 1

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
