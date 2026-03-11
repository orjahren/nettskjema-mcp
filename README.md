# Nettskjema MCP Server

Model Context Protocol (MCP) server for the Nettskjema API. This server provides tools to interact with Nettskjema forms, submissions, invitations, and more through the MCP protocol.

## Features

- **OAuth 2.1 Authentication**: Secure client credentials flow with 24-hour token caching
- **Form Management**: List, retrieve, and update forms
- **Submissions**: Access and manage form submissions
- **Invitations**: Create and manage form invitations
- **Data Export**: Export form responses as CSV, Excel, and SPSS
- **User Information**: Get authenticated user details
- **Automatic Token Management**: Tokens are cached and automatically refreshed

## Installation

1. Clone this repository:

```bash
git clone <repository-url>
cd nettskjema-mcp
```

2. Install dependencies using pip:

```bash
pip install -e .
```

Or using uv:

```bash
uv pip install -e .
```

## Configuration

### 1. Create API Client Credentials

1. Log into https://authorization.nettskjema.no/
2. Click **"Register client"**
3. Provide a client name and email
4. **Save the clientSecret immediately** - it's shown only once!
5. Note your `clientId` and `clientSecret`

### 2. Configure Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Add your credentials to the `.env` file:

```env
NETTSKJEMA_CLIENT_ID=your_client_id_here
NETTSKJEMA_CLIENT_SECRET=your_client_secret_here
```

**Security Note:** Never commit or hardcode your `clientSecret` in code. It's like a password and valid for 365 days. Store it in environment variables or a secure vault.

**Token Management:** OAuth access tokens are valid for 24 hours and are automatically cached and reused by the server. You don't need to manage token refresh manually.

### 3. Grant Form Access

Your API client username is: `<clientId>@apiclient`

For each form you want to access, add this username to the form permissions:
- Open the form in Nettskjema
- Go to: **Settings → Permissions → Editing permissions**
- Add your client username

## Usage

### Running the Server

After installation, you can run the server using the installed command:

```bash
nettskjema-mcp
```

Or run as a Python module:

```bash
python -m nettskjema_mcp
```

For development (without installation):

```bash
python -m nettskjema_mcp
```

### MCP Client Configuration

Add this to your MCP client configuration (e.g., Claude Desktop config):

**Option 1: Using installed command (recommended)**
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

**Option 2: Using Python module (for development)**
```json
{
  "mcpServers": {
    "nettskjema": {
      "command": "python",
      "args": ["-m", "nettskjema_mcp"],
      "cwd": "/path/to/nettskjema-mcp",
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

- `check_auth_status` - Check OAuth authentication status and token info (debugging)
- `get_user_info` - Get authenticated user information

### Forms

- `list_my_forms` - List all your forms
- `create_form` - Create a new form
- `delete_forms` - Delete forms with trash retention
- `get_form_info` - Get metadata for a specific form
- `get_form_settings` - Get form configuration
- `get_form_elements` - Get all questions/elements in a form
- `get_form_definition` - Get complete form definition
- `update_form_settings` - Update form settings
- `lookup_form_by_title` - Find form ID by short title

### Submissions

- `submit_form` - Submit a response to a form
- `get_submission` - Get a single submission with answers
- `get_submission_metadata` - Get metadata for all submissions
- `list_my_submissions` - List your submissions
- `get_form_answers` - Get all answers for a form
- `delete_submissions` - Delete specific submissions

### Data Export

- `export_form_csv` - Export responses as CSV
- `export_form_excel` - Export responses as Excel
- `get_spss_syntax` - Generate SPSS syntax file

### Invitations

- `get_invitations` - List all form invitations
- `create_invitation` - Create new invitation with optional SMS
- `delete_invitations` - Delete specific invitations
- `send_reminder` - Send reminder notifications

## Quick Start

After installation and configuration, you can use the MCP server with any MCP-compatible client. Here are some example use cases:

### List Your Forms

```
Use the list_my_forms tool to see all forms you have access to.
```

### Get Form Details

```
Use get_form_info with a form_id to see the form's metadata.
Use get_form_elements to see all questions in the form.
```

### Export Data

```
Use export_form_csv or export_form_excel to download form responses.
Use get_form_answers to get raw answer data.
```

### Manage Invitations

```
Use create_invitation to invite someone to fill out a form.
Use send_reminder to remind people who haven't responded yet.
```

## API Documentation

Full Nettskjema API documentation: https://nettskjema.no/apidoc

## License

MIT
