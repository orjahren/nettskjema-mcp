# Nettskjema MCP Server

Model Context Protocol (MCP) server for the Nettskjema API v3. Provides tools to interact with Nettskjema forms, submissions, and data export through the MCP protocol.

## Features

- **OAuth 2.1 Authentication**: Secure client credentials flow with automatic token caching and refresh
- **Form Management**: Create, list, retrieve, update, and delete forms
- **Form Elements**: Get, update, and replace form elements (questions)
- **Submissions**: Submit, retrieve, and manage form responses
- **Data Export**: Export form responses as CSV, Excel, and SPSS
- **Attachments**: Upload and retrieve submission attachments with transcription support
- **Invitations**: Send reminders to pending invitations (creation handled in frontend)
- **User Information**: Get authenticated user details
- **Type-Safe**: Full type hints and validated against the OpenAPI spec

## Installation

Clone this repository and install with pip or uv:

```bash
git clone <repository-url>
cd nettskjema-mcp
pip install -e .
```

Or with uv:

```bash
uv pip install -e .
```

## Configuration

### 1. Create API Client Credentials

1. Log into https://authorization.nettskjema.no/
2. Click **"Register client"**
3. Provide a client name and email
4. **Save the clientSecret immediately** - it's shown only once
5. Note your `clientId` and `clientSecret`

### 2. Configure Environment Variables

Create a `.env` file:

```bash
cp .env.example .env
```

Add your credentials:

```env
NETTSKJEMA_CLIENT_ID=your_client_id_here
NETTSKJEMA_CLIENT_SECRET=your_client_secret_here
```

**Security**: Never commit your `clientSecret`. Store it in environment variables or a secure vault.

**Token Management**: OAuth access tokens are valid for 24 hours and are automatically cached and refreshed.

### 3. Grant Form Access

Your API client username is: `<clientId>@apiclient`

For each form you want to access:
- Open the form in Nettskjema
- Go to: **Settings → Permissions → Editing permissions**
- Add your client username

## Usage

### Running the Server

After installation:

```bash
nettskjema-mcp
```

Or as a Python module:

```bash
python -m nettskjema_mcp
```

### MCP Client Configuration

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "nettskjema": {
      "command": "nettskjema-mcp",
      "env": {
        "NETTSKJEMA_CLIENT_ID": "your_client_id_here",
        "NETTSKJEMA_CLIENT_SECRET": "your_client_secret_here"
      }
    }
  }
}
```

## Available Tools

### Authentication & User

| Tool | Description |
|------|-------------|
| `check_auth_status` | Check OAuth authentication status and token info |
| `get_user_info` | Get authenticated user information |

### Forms

| Tool | Description |
|------|-------------|
| `list_my_forms` | List all your forms |
| `create_form` | Create a new form (requires title and language) |
| `delete_forms` | Delete forms by ID (with trash retention) |
| `get_form_info` | Get metadata for a form |
| `get_form_definition` | Get complete form definition |
| `get_form_settings` | Get form configuration |
| `get_form_settings_validation` | Validate form settings without saving |
| `update_form_settings` | Update form configuration |
| `lookup_form_by_title` | Find form ID by short title |
| `activate_educloud` | Activate EduCloud integration |
| `activate_tsd` | Activate TSD (Tjenester for Sensitive Data) |
| `list_forms_collecting_personal_data` | List forms that collect personal data |

### Form Elements

| Tool | Description |
|------|-------------|
| `get_form_elements` | Get all elements in a form |
| `update_form_element` | Update a single element by ID |
| `replace_form_elements` | Replace entire element list (keep-list semantics) |

**Note**: Element tools use read-modify-write. See [docs/workflows.md](docs/workflows.md) for details.

### Submissions

| Tool | Description |
|------|-------------|
| `submit_form` | Submit a response to a form |
| `submit_form_for_invitation` | Submit response using an invitation ID |
| `get_submission` | Get a submission with answers |
| `get_submission_metadata` | Get metadata for all submissions |
| `get_postponed_submission_metadata` | Get metadata for postponed submissions |
| `get_submission_pdf` | Get PDF rendering of a submission |
| `list_my_submissions` | List your submissions |
| `delete_submissions` | Delete specific submissions by ID |
| `delete_all_submissions` | Delete all submissions from a form |

### Answers & Attachments

| Tool | Description |
|------|-------------|
| `get_form_answers` | Get all answers for a form |
| `get_answer_attachment` | Download an attachment by ID |
| `upload_submission_attachment` | Upload file attachment to a submission |
| `get_attachment_transcription` | Get transcription of audio/video attachment |
| `retranscribe_attachment` | Request new transcription of attachment |

### Data Export

| Tool | Description |
|------|-------------|
| `export_form_csv` | Export responses as CSV (semicolon delimiter) |
| `export_form_excel` | Export responses as Excel file |
| `get_spss_syntax` | Generate SPSS syntax file |

### Codebooks & Images

| Tool | Description |
|------|-------------|
| `upload_codebook` | Upload a codebook for a form |
| `upload_image` | Upload an image to Vortex |
| `get_image` | Retrieve an image by ID |

### Invitations

| Tool | Description |
|------|-------------|
| `remind_all_pending_invitations` | Send reminders to all pending invitations |

**Invitation Creation Not Supported**: The v2 invitation API is private and not available through this MCP server. To create invitations, use the frontend at `https://nettskjema.no/user/form/{formId}/collect-responses/invited/create`. Configure the form for invitations via MCP using `update_form_settings` with `respondentGroup: "INVITED"`, then create invitations in the web UI. See [docs/workflows.md](docs/workflows.md#invitations) for the complete workflow.

## Documentation

- [API Coverage](docs/api-coverage.md) - Complete mapping of API routes to tools
- [Workflows](docs/workflows.md) - Common patterns and workflows
- [Contributing](CONTRIBUTING.md) - Development guidelines

## Testing

Run the test suite:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=nettskjema_mcp --cov-report=html
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and testing guidelines.

## API Documentation

Full Nettskjema API documentation: https://nettskjema.no/api/v3/v3/api-docs

## License

Copyright (C) 2026 Oliver Ruste Jahren

This program is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this
program. If not, see <https://www.gnu.org/licenses/>.
