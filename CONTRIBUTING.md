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

1. **Determine the module**: Tools are organized by category in `nettskjema_mcp/tools/`:
   - `forms_read.py` - Read-only form operations
   - `forms_write.py` - Form creation and modification
   - `elements.py` - Form element operations
   - `submissions_read.py` - Read submission data
   - `submissions_write.py` - Submit and delete
   - `exports.py` - CSV, Excel, SPSS
   - `answers.py` - Answer and attachment access
   - `attachments.py` - Attachment upload and transcription
   - `admin.py` - Delete forms, reminders
   - `auth.py` - Authentication status

2. **Add the tool function** in the appropriate module:
   ```python
   from nettskjema_mcp.routes import Route, endpoint
   from nettskjema_mcp.server import tool


   @tool
   @endpoint(Route("GET", "/form/{formId}/example"))
   async def my_new_tool(form_id: int) -> str:
       """
       Brief description of what this tool does.

       Args:
           form_id: Description of the parameter

       Returns:
           Description of what the tool returns
       """
       client = get_client()
       response = await client.get(f"/form/{form_id}/example")
       data = response.json()
       return f"Result: {data}"
   ```

3. **Register the route** using the `@endpoint` decorator with the OpenAPI path

4. **Add tests** in `tests/tools/test_<module>.py` with mocked responses

5. **Validate fixtures** against the OpenAPI spec using `validate_response_fixture`

6. **Run the test suite** to ensure everything passes

7. **Update documentation**:
   - `docs/api-coverage.md` (regenerate programmatically if needed)
   - `docs/workflows.md` if the tool introduces a new workflow
   - `README.md` if it's a major feature

### Updating Documentation

- Update `README.md` for user-facing changes
- Update `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/)
- Update `CLAUDE.md` for development guidelines
- Update `docs/api-coverage.md` and `docs/workflows.md` if adding new tools or workflows

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
