"""
Example usage of the Nettskjema MCP server tools.

This file demonstrates how to use the various tools provided by the MCP server.
Note: In practice, these tools are called through an MCP client, not directly.
"""

import asyncio
from nettskjema_mcp import get_user_info, list_my_forms


async def main():
    """Example usage of Nettskjema MCP tools."""

    print("=" * 60)
    print("Nettskjema MCP Server - Example Usage")
    print("=" * 60)

    # Get user information
    print("\n1. Getting user information...")
    try:
        user_info = await get_user_info()
        print(f"User info: {user_info}")
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}")

    # List all forms
    print("\n2. Listing your forms...")
    try:
        forms = await list_my_forms()
        print(f"Forms: {forms}")
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}")

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
