# Contributing to Nettskjema MCP

Thank you for considering contributing to the Nettskjema MCP server!

## Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd nettskjema-mcp
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install in development mode**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your Nettskjema API credentials
   ```

## Code Quality

We use several tools to maintain code quality:

### Linting and Formatting
```bash
# Run ruff linter
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

### Type Checking
```bash
# Run mypy
mypy nettskjema_mcp
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=nettskjema_mcp --cov-report=html

# Run specific test file
pytest tests/test_auth.py
```

## Adding New Features

### Adding a New MCP Tool

1. **Add the tool function** in `nettskjema_mcp/__init__.py`:
   ```python
   @mcp.tool()
   async def my_new_tool(param: str) -> str:
       """
       Tool description here.

       Args:
           param: Parameter description
       """
       result = await api_request("GET", f"/endpoint/{param}")
       return format_response(result)
   ```

2. **Export it** in `__all__`:
   ```python
   __all__ = [
       # ... existing tools ...
       "my_new_tool",
   ]
   ```

3. **Document it** in `README.md` under "Available Tools"

4. **Add tests** in `tests/test_*.py`

### Updating Documentation

- Update `README.md` for user-facing changes
- Update `TESTING.md` for testing procedures
- Update `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/)
- Update `CLAUDE.md` for development guidelines

## Pull Request Process

1. **Create a branch** for your feature:
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make your changes** following the code quality guidelines

3. **Test your changes**:
   ```bash
   pytest
   ruff check .
   mypy nettskjema_mcp
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add: description of your changes"
   ```

5. **Push and create a PR**:
   ```bash
   git push origin feature/my-new-feature
   ```

## Commit Message Guidelines

Follow conventional commits:

- `Add: new feature or capability`
- `Fix: bug fix`
- `Update: modify existing functionality`
- `Docs: documentation changes`
- `Test: add or modify tests`
- `Refactor: code refactoring`
- `Chore: maintenance tasks`

## Questions?

Feel free to open an issue for:
- Bug reports
- Feature requests
- Questions about the code
- Suggestions for improvements

Thank you for contributing! 🎉
