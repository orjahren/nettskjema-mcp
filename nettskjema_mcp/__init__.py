"""
Nettskjema MCP Server
A Model Context Protocol server for interacting with the Nettskjema API.
"""

import os
import json
from typing import Optional, Any
from datetime import datetime, timedelta
import httpx
from fastmcp import FastMCP

__version__ = "0.1.0"
__all__ = [
    "mcp",
    "get_user_info",
    "check_auth_status",
    "list_my_forms",
    "get_form_info",
    "get_form_settings",
    "get_form_elements",
    "get_submission",
    "get_submission_metadata",
    "list_my_submissions",
    "get_form_answers",
    "export_form_csv",
    "get_invitations",
    "create_invitation",
    "delete_submissions",
    "lookup_form_by_title",
    "update_form_settings",
    "send_reminder",
    "create_form",
    "delete_forms",
    "get_form_definition",
    "submit_form",
    "delete_invitations",
    "export_form_excel",
    "get_spss_syntax",
]

# Initialize FastMCP server
mcp = FastMCP("nettskjema")

# Base URLs
BASE_URL = "https://nettskjema.no/api/v3"
AUTH_URL = "https://authorization.nettskjema.no/oauth2/token"

# Token cache
_token_cache: Optional[dict[str, Any]] = None


async def get_oauth_token() -> str:
    """
    Get OAuth 2.1 access token using client credentials flow.
    Tokens are cached and reused for their 24-hour lifetime.
    """
    global _token_cache

    # Check if we have a valid cached token
    if _token_cache and datetime.now() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    # Get credentials from environment
    client_id = os.getenv("NETTSKJEMA_CLIENT_ID")
    client_secret = os.getenv("NETTSKJEMA_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError(
            "NETTSKJEMA_CLIENT_ID and NETTSKJEMA_CLIENT_SECRET environment variables must be set. "
            "Get your credentials from https://authorization.nettskjema.no/"
        )

    # Request new token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            AUTH_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            timeout=30.0,
        )
        response.raise_for_status()
        token_data = response.json()

    # Cache token (expires in 24h, we'll refresh after 23h to be safe)
    expires_in = token_data.get("expires_in", 86400)  # Default 24h
    _token_cache = {
        "access_token": token_data["access_token"],
        "expires_at": datetime.now() + timedelta(seconds=expires_in - 3600),  # 1h buffer
    }

    return _token_cache["access_token"]


async def get_auth_headers() -> dict[str, str]:
    """Get authorization headers with OAuth bearer token."""
    token = await get_oauth_token()
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


async def api_request(
    method: str,
    endpoint: str,
    params: Optional[dict[str, Any]] = None,
    json_data: Optional[dict[str, Any]] = None,
) -> Any:
    """Make an authenticated request to the Nettskjema API."""
    headers = await get_auth_headers()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=method,
                url=f"{BASE_URL}{endpoint}",
                headers=headers,
                params=params,
                json=json_data,
                timeout=30.0,
            )
            response.raise_for_status()

            # Handle different response types
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return response.text
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            raise Exception(error_msg) from e
        except Exception as e:
            raise Exception(f"API request failed: {str(e)}") from e


def format_response(data: Any) -> str:
    """Format response data as readable JSON string."""
    if isinstance(data, (dict, list)):
        return json.dumps(data, indent=2, ensure_ascii=False)
    return str(data)


@mcp.tool()
async def get_user_info() -> str:
    """Get information about the authenticated user."""
    result = await api_request("GET", "/me")
    return format_response(result)


@mcp.tool()
async def check_auth_status() -> str:
    """
    Check OAuth authentication status and token information.
    Useful for debugging authentication issues.
    """
    client_id = os.getenv("NETTSKJEMA_CLIENT_ID")
    client_secret = os.getenv("NETTSKJEMA_CLIENT_SECRET")

    status = {
        "client_id_set": bool(client_id),
        "client_secret_set": bool(client_secret),
        "client_username": f"{client_id}@apiclient" if client_id else None,
        "token_cached": _token_cache is not None,
    }

    if _token_cache:
        status["token_expires_at"] = _token_cache["expires_at"].isoformat()
        status["token_valid"] = datetime.now() < _token_cache["expires_at"]

    return format_response(status)


@mcp.tool()
async def list_my_forms() -> str:
    """List all forms owned by the authenticated user."""
    result = await api_request("GET", "/form/me")
    return format_response(result)


@mcp.tool()
async def get_form_info(form_id: int) -> str:
    """
    Get metadata and status information for a specific form.

    Args:
        form_id: The ID of the form to retrieve
    """
    result = await api_request("GET", f"/form/{form_id}/info")
    return format_response(result)


@mcp.tool()
async def get_form_settings(form_id: int) -> str:
    """
    Get configuration settings for a specific form.

    Args:
        form_id: The ID of the form
    """
    result = await api_request("GET", f"/form/{form_id}/settings")
    return format_response(result)


@mcp.tool()
async def get_form_elements(form_id: int) -> str:
    """
    Get all elements (questions) in a form.

    Args:
        form_id: The ID of the form
    """
    result = await api_request("GET", f"/form/{form_id}/elements")
    return format_response(result)


@mcp.tool()
async def get_submission(submission_id: int) -> str:
    """
    Retrieve a single submission with all its answers.

    Args:
        submission_id: The ID of the submission to retrieve
    """
    result = await api_request("GET", f"/form/submission/{submission_id}")
    return format_response(result)


@mcp.tool()
async def get_submission_metadata(form_id: int) -> str:
    """
    Get metadata for all submissions of a form.

    Args:
        form_id: The ID of the form
    """
    result = await api_request("GET", f"/form/{form_id}/submission-metadata")
    return format_response(result)


@mcp.tool()
async def list_my_submissions() -> str:
    """List all submissions made by the authenticated user."""
    result = await api_request("GET", "/form/submission/me")
    return format_response(result)


@mcp.tool()
async def get_form_answers(form_id: int, element_id: Optional[int] = None) -> str:
    """
    Get all answers for a form, optionally filtered by element.

    Args:
        form_id: The ID of the form
        element_id: Optional element ID to filter answers for a specific question
    """
    params = {"elementId": element_id} if element_id else None
    result = await api_request("GET", f"/form/{form_id}/answers", params=params)
    return format_response(result)


@mcp.tool()
async def export_form_csv(form_id: int) -> str:
    """
    Export form responses as CSV.

    Args:
        form_id: The ID of the form to export
    """
    result = await api_request("GET", f"/form/{form_id}/csv-report")
    return result


@mcp.tool()
async def get_invitations(form_id: int) -> str:
    """
    List all invitations for a form.

    Args:
        form_id: The ID of the form
    """
    result = await api_request("GET", f"/form/{form_id}/invitations")
    return format_response(result)


@mcp.tool()
async def create_invitation(
    form_id: int,
    email: str,
    send_sms: bool = False,
    phone_number: Optional[str] = None,
) -> str:
    """
    Create a new invitation for a form.

    Args:
        form_id: The ID of the form
        email: Email address to send invitation to
        send_sms: Whether to also send SMS notification
        phone_number: Phone number for SMS (required if send_sms is True)
    """
    invitation_data = {
        "email": email,
    }

    if send_sms:
        if not phone_number:
            raise ValueError("phone_number is required when send_sms is True")
        invitation_data["sendSms"] = True
        invitation_data["phoneNumber"] = phone_number

    result = await api_request(
        "POST",
        f"/form/{form_id}/invitations",
        json_data=[invitation_data]
    )
    return format_response(result)


@mcp.tool()
async def delete_submissions(form_id: int, submission_ids: list[int]) -> str:
    """
    Delete specific submissions from a form.

    Args:
        form_id: The ID of the form
        submission_ids: List of submission IDs to delete
    """
    result = await api_request(
        "DELETE",
        f"/form/{form_id}/submission",
        json_data={"submissionIds": submission_ids}
    )
    return format_response(result)


@mcp.tool()
async def lookup_form_by_title(title_short: str) -> str:
    """
    Look up a form ID by its short title.

    Args:
        title_short: The short title of the form
    """
    result = await api_request("GET", f"/form/titleshort/{title_short}")
    return format_response(result)


@mcp.tool()
async def update_form_settings(form_id: int, settings: dict[str, Any]) -> str:
    """
    Update form settings.

    Args:
        form_id: The ID of the form
        settings: Dictionary of settings to update (e.g., {"title": "New Title"})
    """
    result = await api_request(
        "PATCH",
        f"/form/{form_id}/settings",
        json_data=settings
    )
    return format_response(result)


@mcp.tool()
async def send_reminder(form_id: int, invitation_ids: list[int]) -> str:
    """
    Send reminder notifications for specific invitations.

    Args:
        form_id: The ID of the form
        invitation_ids: List of invitation IDs to send reminders to
    """
    result = await api_request(
        "POST",
        f"/form/{form_id}/remind",
        json_data={"invitationIds": invitation_ids}
    )
    return format_response(result)


@mcp.tool()
async def create_form(title: str, language: str = "no-NB") -> str:
    """
    Create a new form.

    Args:
        title: Title of the new form
        language: Language code (default: "no-NB" for Norwegian Bokmål)
    """
    form_data = {
        "title": title,
        "language": language,
    }
    result = await api_request("POST", "/form", json_data=form_data)
    return format_response(result)


@mcp.tool()
async def delete_forms(form_ids: list[int], trash_retention_days: int = 30) -> str:
    """
    Delete forms by IDs with optional trash retention period.

    Args:
        form_ids: List of form IDs to delete
        trash_retention_days: Days to keep in trash (default: 30)
    """
    delete_data = {
        "formIds": form_ids,
        "trashRetentionDays": trash_retention_days,
    }
    result = await api_request("DELETE", "/form", json_data=delete_data)
    return format_response(result)


@mcp.tool()
async def get_form_definition(form_id: int) -> str:
    """
    Get complete form definition (required for high-security activation).

    Args:
        form_id: The ID of the form
    """
    result = await api_request("GET", f"/form/{form_id}/definition")
    return format_response(result)


@mcp.tool()
async def submit_form(form_id: int, answers: dict[str, Any]) -> str:
    """
    Submit a response to a form.

    Args:
        form_id: The ID of the form to submit to
        answers: Dictionary of answers where keys are element IDs
    """
    result = await api_request(
        "POST",
        f"/form/{form_id}/submission",
        json_data={"answers": answers}
    )
    return format_response(result)


@mcp.tool()
async def delete_invitations(form_id: int, invitation_ids: list[int]) -> str:
    """
    Delete specific invitations from a form.

    Args:
        form_id: The ID of the form
        invitation_ids: List of invitation IDs to delete
    """
    result = await api_request(
        "DELETE",
        f"/form/{form_id}/invitations",
        json_data={"invitationIds": invitation_ids}
    )
    return format_response(result)


@mcp.tool()
async def export_form_excel(form_id: int) -> str:
    """
    Export form responses as Excel file.

    Args:
        form_id: The ID of the form to export
    """
    result = await api_request("GET", f"/form/{form_id}/excel-report")
    return format_response(result)


@mcp.tool()
async def get_spss_syntax(form_id: int) -> str:
    """
    Generate SPSS syntax file for the form.

    Args:
        form_id: The ID of the form
    """
    result = await api_request("GET", f"/form/{form_id}/spss-syntax")
    return result  # Return as-is since it's syntax text


def main() -> None:
    """Main entry point for the CLI."""
    mcp.run()


if __name__ == "__main__":
    main()
