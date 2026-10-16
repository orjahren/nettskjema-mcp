# Project Instructions for Claude

## Project Overview

This is an MCP (Model Context Protocol) server for the Nettskjema API v3, built using FastMCP. It provides programmatic access to Nettskjema forms, submissions, and data export through a type-safe, validated interface.

## Architecture

### Module Structure

```
nettskjema_mcp/
├── __init__.py          # Package entry point (do not add tools here)
├── server.py            # MCP server and error bridge
├── config.py            # Settings from environment
├── client.py            # HTTP client with OAuth 2.1
├── routes.py            # Route registry and OpenAPI spec loader
├── spec/                # Vendored OpenAPI spec
│   └── openapi.json
└── tools/               # Tool implementations (add new tools here)
    ├── auth.py          # Authentication status
    ├── forms_read.py    # Read-only form operations
    ├── forms_write.py   # Form creation and modification
    ├── elements.py      # Form element operations
    ├── submissions_read.py
    ├── submissions_write.py
    ├── exports.py       # CSV, Excel, SPSS
    ├── answers.py       # Answer and attachment access
    ├── attachments.py   # Upload and transcription
    └── admin.py         # Delete forms, reminders
```

### Key Concepts

**Route Registry**: Every tool that calls an API endpoint is decorated with `@endpoint(Route(...))` to register its route. The registry (`REGISTRY` in `routes.py`) maps tool names to their routes and is used for documentation and testing.

**Error Bridge**: The `@tool` decorator from `server.py` wraps every tool function with error handling that translates upstream API errors into MCP-compatible error responses.

**Fixture Validation**: Test fixtures for response bodies are validated against the vendored OpenAPI spec to catch schema drift early.

**Out-of-Scope Routes**: Some API endpoints are deliberately not implemented. These are documented in `OUT_OF_SCOPE` in `routes.py` with reasons.

## Development Guidelines

### Adding a New Tool

1. Choose the correct module in `tools/` based on the operation type
2. Import the necessary components:
   ```python
   from nettskjema_mcp.routes import Route, endpoint
   from nettskjema_mcp.server import tool
   from nettskjema_mcp.client import get_client
   ```
3. Define the tool with both decorators:
   ```python
   @tool
   @endpoint(Route("GET", "/form/{formId}/example"))
   async def my_tool(form_id: int) -> str:
       """Docstring describing the tool."""
       client = get_client()
       response = await client.get(f"/form/{form_id}/example")
       return str(response.json())
   ```
4. The `@endpoint` decorator registers the route (use the OpenAPI path with placeholders)
5. The `@tool` decorator registers with FastMCP and wraps error handling
6. Return a string (MCP tools return strings to the model)

### Tool Docstrings

Tool docstrings must be grounded in the response schema from the vendored OpenAPI spec. Do not promise fields the API does not return. If a field's presence is uncertain, either:
- Check the spec and state it definitively, or
- Say "if present" in the docstring

Docstrings are the skill's interface documentation, so they must be accurate.

### Type Hints

- Every function parameter and return value must have a type hint
- Use `int`, `str`, `bool`, `list[int]`, etc. from the standard library
- Use `dict[str, Any]` when the structure is unknown
- Never use `Any` without a comment explaining why

### Authentication

Authentication is automatic:
- Configure via `NETTSKJEMA_CLIENT_ID` and `NETTSKJEMA_CLIENT_SECRET`
- Tokens are fetched on first request and cached for 24 hours
- Tokens are automatically refreshed when expired
- Use `get_client()` to get an authenticated httpx client

The base URL defaults to production (`https://nettskjema.no/api/v3`) but can be overridden with `NETTSKJEMA_BASE_URL`.

### Error Handling

**Do not catch exceptions in tool code.** The error bridge handles all errors:
- `httpx.HTTPStatusError` → `UpstreamError` with status and body
- `ValidationError` → `InvalidInput`
- Unknown errors → generic MCP error

If you need to check a response body for errors (e.g., HTTP 200 with an error schema), raise `UpstreamError` explicitly:
```python
if "error" in data:
    raise UpstreamError(f"API error: {data['error']}", status=200)
```

### Testing

**Test organization**: Tests are organized by module:
- `tests/tools/test_<module>.py` - Tool tests matching `nettskjema_mcp/tools/<module>.py`
- `tests/test_<feature>.py` - Non-tool tests (auth, config, client, etc.)

**Fixture validation**: All response fixtures must be validated against the OpenAPI spec:
```python
from tests.conftest import validate_response_fixture

EXAMPLE_RESPONSE = {"key": "value"}
validate_response_fixture("GET", "/form/{formId}/example", EXAMPLE_RESPONSE)
```

**Test pattern**:
```python
import pytest
from tests.conftest import validate_response_fixture

FIXTURE = {"id": 123}
validate_response_fixture("GET", "/endpoint", FIXTURE)


@pytest.mark.asyncio
async def test_my_tool(respx_mock, token_route):
    respx_mock.get("https://nettskjema.invalid/api/v3/endpoint").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await my_tool()
    assert "123" in result
```

### Commit Messages

Use conventional commit prefixes:
- `feat:` - New tool or feature
- `fix:` - Bug fix
- `refactor:` - Code restructuring without behavior change
- `test:` - Add or update tests
- `docs:` - Documentation only
- `chore:` - Dependencies, config, build

English, imperative mood, signed commits required.

### Code Quality

Before committing:
```bash
uv run ruff check .          # Lint
uv run ruff format .         # Format
uv run mypy nettskjema_mcp   # Type check
uv run pytest                # Test
```

All must pass.

## API Specifics

### Invitation Gap

The v2 invitation API is private (paths start with `/private/`) and not implemented. The MCP server supports:
- Configuring forms for invitations (`update_form_settings`)
- Sending reminders (`remind_all_pending_invitations`)
- Retrieving invitation responses

Invitation creation must be done through the frontend at `https://nettskjema.no/user/form/{formId}/collect-responses/invited/create`.

### Element Keep-List Semantics

`replace_form_elements` uses **keep-list semantics**: elements not in the submitted list are deleted. Always send the complete desired element list.

### 207 Multi-Status

Some endpoints return HTTP 207 when operating on multiple items:
- `delete_submissions`
- `delete_forms`

These are not errors. The response body contains per-item status.

### ErrorMessage in 2xx

`PUT /form/{formId}/elements` returns HTTP 200 with an `ErrorMessage` schema if validation fails. The client checks the body and raises `UpstreamError` on error bodies, so tools receive only actual successes.

## Security

- Never log or print access tokens, client secrets, or request/response bodies
- Answers may contain sensitive personal data
- This repo is GPL-3.0-or-later and intended for publication: no UiO-internal paths or class names
- E2E tests have a production guard that aborts if pointed at `nettskjema.no`

## Resources

- OpenAPI spec: `nettskjema_mcp/spec/openapi.json`
- API docs: https://nettskjema.no/api/v3/v3/api-docs
- Tool coverage: `docs/api-coverage.md`
- Workflows: `docs/workflows.md`
