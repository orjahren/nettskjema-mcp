# Testing Guide

This guide explains how to test the Nettskjema MCP server.

## Prerequisites

1. **API Token**: Get your Nettskjema API token from https://nettskjema.no/user/token
2. **Environment Setup**: Add the token to your `.env` file:
   ```
   NETTSKJEMA_API_TOKEN=your_actual_token_here
   ```

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

# Set environment variable if not in .env
os.environ['NETTSKJEMA_API_TOKEN'] = 'your_token_here'

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

1. **Check API Token**: Ensure it's valid and not expired
2. **Check Form Access**: Verify you have permission to access the forms
3. **Check API Status**: Visit https://nettskjema.no to ensure the service is running
4. **Enable Debug Logging**: Add logging to the server for more details:

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
        "NETTSKJEMA_API_TOKEN": "your_token_here"
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

- **Never commit** your API token to version control
- **Use environment variables** for sensitive data
- **Test token rotation**: Ensure the server handles token updates gracefully
- **Verify HTTPS**: All API requests use HTTPS
