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
- Authentication: Bearer token via `NETTSKJEMA_API_TOKEN` environment variable
- All endpoints require authentication
- Use httpx for async HTTP requests

### Adding New Tools
When adding new tools:
1. Use the `@mcp.tool()` decorator
2. Add clear docstring with Args description
3. Use the `api_request()` helper function
4. Handle errors appropriately
5. Return string representations of results

### Testing
- Ensure NETTSKJEMA_API_TOKEN is set before testing
- Use `example_usage.py` to test individual tools
- Test with real Nettskjema forms when possible

### Dependencies
- fastmcp: MCP server framework
- httpx: Async HTTP client
- Standard library: os, typing
