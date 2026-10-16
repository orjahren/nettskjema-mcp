# Tests

This directory contains tests for the Nettskjema MCP package.

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=nettskjema_mcp --cov-report=html

# Run specific test file
pytest tests/test_auth.py

# Run with verbose output
pytest -v
```

## Test Structure

- `test_auth.py` - OAuth authentication tests
- More test files to be added as features are developed

## Writing Tests

Tests should:
- Use pytest and pytest-asyncio
- Cover both success and error cases
- Mock external API calls where appropriate
- Include docstrings explaining what is being tested

Example:
```python
import pytest


@pytest.mark.asyncio
async def test_my_feature():
    """Test that my feature works correctly."""
    # Test implementation
    pass
```

## Note on Integration Tests

Full integration tests require actual Nettskjema API credentials. For CI/CD:
- Use mocked responses for most tests
- Run integration tests only in secure environments with credentials
- Never commit credentials to the repository
