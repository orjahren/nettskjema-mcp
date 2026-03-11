"""
Example usage of the Nettskjema MCP server tools.

This file demonstrates how to use the various tools provided by the MCP server.
Note: In practice, these tools are called through an MCP client, not directly.
"""

import asyncio
import traceback
from nettskjema_mcp import get_user_info, list_my_forms, check_auth_status


async def main():
    """Example usage of Nettskjema MCP tools."""

    print("=" * 60)
    print("Nettskjema MCP Server - Example Usage")
    print("=" * 60)

    # Check authentication status first
    print("\n0. Checking authentication status...")
    try:
        auth_status = await check_auth_status()
        print(f"Auth status: {auth_status}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR in check_auth_status:")
        print(f"  Exception type: {type(e).__name__}")
        print(f"  Exception message: {e}")
        print(f"  Full traceback:")
        traceback.print_exc()

    # Get user information
    print("\n1. Getting user information...")
    try:
        user_info = await get_user_info()
        print(f"✓ User info retrieved successfully:")
        print(f"{user_info}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR in get_user_info:")
        print(f"  Exception type: {type(e).__name__}")
        print(f"  Exception message: {e}")
        print(f"  Full traceback:")
        traceback.print_exc()

    # List all forms
    print("\n2. Listing your forms...")
    try:
        forms = await list_my_forms()
        print(f"✓ Forms retrieved successfully:")
        print(f"{forms}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR in list_my_forms:")
        print(f"  Exception type: {type(e).__name__}")
        print(f"  Exception message: {e}")
        print(f"  Full traceback:")
        traceback.print_exc()

    # Example: Get specific form info (replace with actual form_id)
    # print("\n3. Getting form information...")
    # try:
    #     form_info = await get_form_info(form_id=12345)
    #     print(f"Form info: {form_info}")
    # except Exception as e:
    #     print(f"Error: {e}")

    print("\n" + "=" * 60)
    print("Example completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
