# API Coverage

This document maps every Nettskjema API v3 operation to its corresponding MCP tool.

## Tool-to-Route Mapping

### Authentication & User

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `check_auth_status` | LOCAL | — | Check OAuth authentication status |
| `get_user_info` | GET | /me |  |

### Forms - Read

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `list_my_forms` | GET | /form/me |  |
| `lookup_form_by_title` | GET | /form/titleshort/{titleShort} |  |
| `get_form_definition` | GET | /form/{formId}/definition |  |
| `get_form_info` | GET | /form/{formId}/info | Info about the form for answering |
| `get_form_settings` | GET | /form/{formId}/settings |  |
| `get_form_settings_validation` | GET | /form/{formId}/settings/validation |  |
| `list_forms_collecting_personal_data` | GET | /personal-data/collects-personal-data |  |

### Forms - Write

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `delete_forms` | DELETE | /form | Delete a list of forms by ids |
| `create_form` | POST | /form |  |
| `activate_educloud` | POST | /form/{formId}/activate/educloud |  |
| `activate_tsd` | POST | /form/{formId}/activate/tsd |  |
| `remind_all_pending_invitations` | POST | /form/{formId}/remind |  |
| `update_form_settings` | PATCH | /form/{formId}/settings | Update form settings |

### Elements

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `get_form_elements` | GET | /form/{formId}/elements | List of elements for answering form |
| `update_form_element` | GET | /form/{formId}/elements | List of elements for answering form |
| `replace_form_elements` | PUT | /form/{formId}/elements |  |

### Submissions - Read

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `list_my_submissions` | GET | /form/submission/me |  |
| `get_submission` | GET | /form/submission/{submissionId} |  |
| `get_submission_pdf` | GET | /form/submission/{submissionId}/pdf |  |
| `get_submission_metadata` | GET | /form/{formId}/submission-metadata |  |
| `get_postponed_submission_metadata` | GET | /form/{formId}/submission-metadata-postponed |  |

### Submissions - Write

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `submit_form_for_invitation` | POST | /form/invitation/{invitationId}/submission |  |
| `delete_submissions` | DELETE | /form/{formId}/submission | Delete list of submissions |
| `submit_form` | POST | /form/{formId}/submission |  |
| `delete_all_submissions` | DELETE | /form/{formId}/submissions | Delete all submissions |

### Answers & Attachments

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `get_answer_attachment` | GET | /form/submission/attachment/{answerAttachmentId} |  |
| `upload_submission_attachment` | PUT | /form/submission/{submissionId}/attachment |  |
| `get_form_answers` | GET | /form/{formId}/answers |  |
| `retranscribe_attachment` | POST | /submission/attachment/{answerAttachmentId}/retranscribe |  |
| `get_attachment_transcription` | GET | /submission/attachment/{answerAttachmentId}/transcribed/json |  |

### Data Export

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `export_form_csv` | GET | /form/{formId}/csv-report | CSV text file with semicolon (;) as delimiter |
| `export_form_excel` | GET | /form/{formId}/excel-report | Excel file |
| `get_spss_syntax` | GET | /form/{formId}/spss-syntax | SPSS syntax file |

### Codebooks & Images

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `upload_codebook` | PUT | /form/{formId}/codebook |  |
| `upload_image` | POST | /image | Laster opp et bilde til Vortex |
| `get_image` | GET | /image/{imageId} |  |

### Out of Scope

| Tool | Method | Route | Description |
|------|--------|-------|-------------|
| `(not implemented)` | DELETE | /form/{formId}/invitation | v1 invitation management; v2 is private — handle invitation deletion in the frontend |
| `(not implemented)` | DELETE | /form/{formId}/invitations | v1 invitation management; v2 is private — handle invitation deletion in the frontend |
| `(not implemented)` | GET | /form/{formId}/invitations | v1 invitation management; v2 is private — handle invitation creation in the frontend |
| `(not implemented)` | POST | /form/{formId}/invitations | v1 invitation management; v2 is private — handle invitation creation in the frontend |

