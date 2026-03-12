# Project Instructions for Claude

## Project Overview
This is a Model Context Protocol (MCP) server for the Nettskjema API, built using FastMCP.

## Development Guidelines

### Code Style
- Use type hints for all function parameters and return values
- Use async/await for all API calls
- Keep tool functions focused and single-purpose
- Document all tools with clear docstrings

### API Integration
- Base URL: `https://nettskjema.no/api/v3`
- Auth URL: `https://authorization.nettskjema.no/oauth2/token`
- Authentication: OAuth 2.1 client credentials flow
  - Requires `NETTSKJEMA_CLIENT_ID` and `NETTSKJEMA_CLIENT_SECRET`
  - Tokens are JWTs valid for 24 hours (86,400 seconds)
  - Tokens are cached in memory and auto-refreshed
- All endpoints require authentication
- Use httpx for async HTTP requests
- Client username format: `<clientId>@apiclient`

### Available Tools

The server provides tools for:
- **Form Management**: create_form, delete_forms, update_form_settings, etc.
- **Form Elements**: add_form_element, update_form_element, delete_form_element, reorder_form_elements, duplicate_form_element
- **Submissions**: get_submission, list_my_submissions, delete_submissions, etc.
- **Invitations**: create_invitation, get_invitations, delete_invitations, send_reminder
- **Data Export**: export_form_csv, export_form_excel, get_spss_syntax

### Adding New Tools
When adding new tools:
1. Use the `@mcp.tool()` decorator
2. Add clear docstring with Args description
3. Use the `api_request()` helper function
4. Handle errors appropriately
5. Return string representations of results
6. Add to __all__ export list

### Testing
- Ensure NETTSKJEMA_API_TOKEN is set before testing
- Use `example_usage.py` to test individual tools
- Test with real Nettskjema forms when possible

### Dependencies
- fastmcp: MCP server framework
- httpx: Async HTTP client
- Standard library: os, typing
