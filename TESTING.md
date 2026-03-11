# Testing Guide

This guide explains how to test the Nettskjema MCP server.

## Prerequisites

1. **API Client Credentials**:
   - Create an API client at https://authorization.nettskjema.no/
   - Register a new client and save your `clientId` and `clientSecret`
   - **Important**: The clientSecret is shown only once!

2. **Environment Setup**: Add your credentials to the `.env` file:
   ```env
   NETTSKJEMA_CLIENT_ID=your_client_id_here
   NETTSKJEMA_CLIENT_SECRET=your_client_secret_here
   ```

3. **Form Access**: Add your API client to form permissions:
   - Your client username: `<clientId>@apiclient`
   - Add to form: Settings → Permissions → Editing permissions

## Running Tests

### Test Individual Tools

Use the provided `example_usage.py` script:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the example
python example_usage.py
```

### Test with MCP Inspector

The MCP Inspector is a tool for debugging MCP servers:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Run the inspector
mcp-inspector python server.py
```

This will open a web interface where you can:
- See all available tools
- Call tools with test parameters
- View responses
- Debug errors

### Manual Testing

You can also test individual functions by importing them:

```python
import asyncio
import os
from server import list_my_forms, get_form_info

# Set environment variables if not in .env
os.environ['NETTSKJEMA_CLIENT_ID'] = 'your_client_id'
os.environ['NETTSKJEMA_CLIENT_SECRET'] = 'your_client_secret'

async def test():
    # Test listing forms
    forms = await list_my_forms()
    print(forms)

    # Test getting specific form info
    # form_info = await get_form_info(form_id=12345)
    # print(form_info)

asyncio.run(test())
```

## Common Test Scenarios

### 1. List Your Forms
```python
result = await list_my_forms()
```

### 2. Get Form Information
```python
result = await get_form_info(form_id=YOUR_FORM_ID)
```

### 3. Get Form Elements
```python
result = await get_form_elements(form_id=YOUR_FORM_ID)
```

### 4. Export Form Data
```python
result = await export_form_csv(form_id=YOUR_FORM_ID)
```

### 5. Create Invitation
```python
result = await create_invitation(
    form_id=YOUR_FORM_ID,
    email="test@example.com"
)
```

## Error Handling

The server includes error handling for common issues:

- **Missing API Token**: Clear error message about setting `NETTSKJEMA_API_TOKEN`
- **HTTP Errors**: Formatted error messages with status codes
- **Invalid Parameters**: Type checking and validation

## Debugging

If you encounter issues:

1. **Check OAuth Credentials**:
   - Ensure `NETTSKJEMA_CLIENT_ID` and `NETTSKJEMA_CLIENT_SECRET` are set correctly
   - Verify your clientSecret hasn't expired (valid for 365 days)
   - Check credentials at https://authorization.nettskjema.no/

2. **Check Form Access**:
   - Your client username is: `<clientId>@apiclient`
   - Verify this username is added to the form's editing permissions
   - Go to: Settings → Permissions → Editing permissions

3. **Check Token Issues**:
   - OAuth tokens are cached for 24 hours and auto-refresh
   - If you get 401 errors, the token cache may be stale
   - Restart the server to force a new token fetch

4. **Check API Status**: Visit https://nettskjema.no to ensure the service is running

5. **Enable Debug Logging**: Add logging to the server for more details:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Integration Testing with MCP Clients

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nettskjema": {
      "command": "python",
      "args": ["/path/to/nettskjema-mcp/server.py"],
      "env": {
        "NETTSKJEMA_CLIENT_ID": "your_client_id_here",
        "NETTSKJEMA_CLIENT_SECRET": "your_client_secret_here"
      }
    }
  }
}
```

Then restart Claude Desktop and try commands like:
- "List my Nettskjema forms"
- "Get information about form 12345"
- "Export form data as CSV"

## Performance Testing

For testing with large datasets:

```python
import time

async def performance_test():
    start = time.time()
    result = await get_form_answers(form_id=YOUR_FORM_ID)
    end = time.time()
    print(f"Time taken: {end - start:.2f} seconds")

asyncio.run(performance_test())
```

## Security Testing

- **Never commit** your `clientSecret` to version control - treat it like a password
- **Use environment variables** for sensitive credentials
- **Token Management**:
  - OAuth tokens are automatically cached and refreshed
  - Tokens expire after 24 hours
  - The server handles token refresh transparently
- **Verify HTTPS**: All API requests use HTTPS
- **Client Credentials Security**:
  - clientSecret expires after 365 days
  - Store it securely (password manager, secret vault, etc.)
  - It's shown only once when created
