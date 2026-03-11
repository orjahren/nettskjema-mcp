# Nettskjema MCP Server

Model Context Protocol (MCP) server for the Nettskjema API. This server provides tools to interact with Nettskjema forms, submissions, invitations, and more through the MCP protocol.

## Features

- **Form Management**: List, retrieve, and update forms
- **Submissions**: Access and manage form submissions
- **Invitations**: Create and manage form invitations
- **Data Export**: Export form responses as CSV
- **User Information**: Get authenticated user details

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

1. Create a `.env` file from the example:
```bash
cp .env.example .env
```

2. Get your Nettskjema API token from: https://nettskjema.no/user/token

3. Add your token to the `.env` file:
```
NETTSKJEMA_API_TOKEN=your_actual_token_here
```

## Usage

### Running the Server

You can run the server directly:
```bash
python server.py
```

Or using the installed command:
```bash
nettskjema-mcp
```

### MCP Client Configuration

Add this to your MCP client configuration (e.g., Claude Desktop config):

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

Or if installed via pip:
```json
{
  "mcpServers": {
    "nettskjema": {
      "command": "nettskjema-mcp",
      "env": {
        "NETTSKJEMA_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

## Available Tools

### User & Forms
- `get_user_info` - Get authenticated user information
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

Full Nettskjema API documentation: https://nettskjema.no/api/v3/v3/api-docs

## License

MIT
