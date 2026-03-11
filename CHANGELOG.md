# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-11

### Added
- Initial release of Nettskjema MCP server
- OAuth 2.1 client credentials authentication flow
- Automatic token caching and refresh (24-hour validity)
- 24 MCP tools for Nettskjema API:
  - Form management (create, list, update, delete, get info)
  - Submission management (submit, retrieve, list, delete)
  - Invitation management (create, list, delete, send reminders)
  - Data export (CSV, Excel, SPSS syntax)
  - User information and auth status checking
- FastMCP-based server implementation
- Type hints and py.typed marker
- Comprehensive documentation (README, TESTING, CLAUDE)
- Example usage script
- Automated setup script
- MIT License

### Security
- Secure OAuth credential handling via environment variables
- Token caching with automatic refresh
- No hardcoded secrets

[0.1.0]: https://github.com/yourusername/nettskjema-mcp/releases/tag/v0.1.0
