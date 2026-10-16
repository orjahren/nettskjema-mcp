## # Workflows

This document covers common workflows and patterns when using the Nettskjema MCP server.

## Form Creation

### Required Fields

When creating a form with `create_form`, only two fields are required:
- `title`: The form title
- `language`: The form language (`no`, `en`, `se`, or `nn`)

All other settings are optional and can be configured later with `update_form_settings`.

### Granting Access

Before you can access a form via the API, you must grant permissions:

1. Your API client username is `<clientId>@apiclient`
2. For each form, add this username to the form permissions in the Nettskjema web UI:
   - Open the form in Nettskjema
   - Go to **Settings → Permissions → Editing permissions**
   - Add your client username

Without this permission, all API calls for that form will fail with 403 Forbidden.

## Form Elements

### Read-Modify-Write Cycle

The element tools use a read-modify-write pattern:

1. **Read**: Call `get_form_elements` to retrieve the current element list
2. **Modify**: Transform the elements in your code:
   - Add new elements
   - Update existing elements by ID
   - Remove elements by omitting them from the list
   - Reorder by changing the list order
3. **Write**: Call `replace_form_elements` with the complete modified list

**Important**: `replace_form_elements` uses **keep-list semantics**. Elements omitted from the list are deleted. Always send the complete element list you want the form to have, not just the changes.

### Individual Element Updates

For small changes to a single element, use `update_form_element` instead of the full read-modify-write cycle. This updates one element by ID without affecting others.

## Submissions

### 207 Multi-Status Responses

Several write operations return HTTP 207 Multi-Status when operating on multiple items:

- `delete_submissions`: Deleting specific submissions by ID
- `delete_forms`: Deleting multiple forms

A 207 response means:
- The overall request succeeded
- Individual items may have succeeded or failed
- Check the response body for per-item status
- The tool returns a formatted summary of successes and failures

## Invitations

### Invitation Management Gap

**The v1 invitation API (`/form/{formId}/invitations`) is not supported.** The v2 invitation API is private and not available through this MCP server.

To work with invitations:

1. **Configure the form** for invitations via MCP:
   - Use `update_form_settings` to set `respondentGroup: "INVITED"`
   - Configure other invitation-related settings as needed

2. **Create invitations** in the frontend:
   - Go to `https://nettskjema.no/user/form/{formId}/collect-responses/invited/create`
   - Create individual or batch invitations through the web UI

3. **Manage invitations** in the frontend:
   - View and manage invitations at `https://nettskjema.no/user/form/{formId}/collect-responses/invited/overview`

4. **Send reminders** via MCP:
   - Use `remind_all_pending_invitations` to send reminders for all pending invitations
   - This reaches both v1 and v2 invitations

5. **Collect responses** via MCP:
   - Use `get_submission_metadata` to see submissions from invited respondents
   - Use `get_form_answers` to get the answers

### Why This Gap Exists

The v2 invitation API is marked as private in the OpenAPI spec (paths start with `/private/`). This MCP server only implements the public API surface. The frontend has access to the private endpoints and handles invitation creation and management through its own dedicated interface.

## Data Export

### Export Formats

Three export formats are available:

- **CSV**: `export_form_csv` - Semicolon-delimited text file
- **Excel**: `export_form_excel` - Binary Excel file (`.xlsx`)
- **SPSS**: `get_spss_syntax` - SPSS syntax file for data analysis

### Answer Data

For programmatic access to answers, use `get_form_answers` which returns structured JSON data. This is more suitable for API integration than the export files, which are designed for human analysis.

## Attachments

### Uploading Attachments

Use `upload_submission_attachment` to attach files to a submission. The file must be base64-encoded in the request body.

### Transcription

For audio/video attachments, Nettskjema can provide transcriptions:

- Use `get_attachment_transcription` to retrieve a transcription in JSON, TXT, or VTT format
- Use `retranscribe_attachment` to request a new transcription

### Downloads

- Use `get_answer_attachment` to download an attachment by its ID
- Use `get_submission_pdf` to get a PDF rendering of a submission

## Images

Images (for use in form elements, etc.) are managed separately:

- `upload_image`: Upload an image and get an image ID
- `get_image`: Retrieve an image by ID

These are distinct from answer attachments and are used for form design rather than submission data.

## Error Handling

### ErrorMessage in Success Responses

Some operations return an `ErrorMessage` schema even on HTTP 200. The most notable is:

- `replace_form_elements`: Returns HTTP 200 with an error body if validation fails

The client automatically checks these responses and raises `UpstreamError` if the body indicates failure. You will not receive a success response with hidden errors.

### Validation Before Write

Use `get_form_settings_validation` to check for validation errors before attempting to update settings. This returns a list of validation problems without attempting to save.
