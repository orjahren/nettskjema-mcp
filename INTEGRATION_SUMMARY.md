# Integration Summary: AI-Assisted Form Building

This document summarizes all changes made to support AI-assisted form building in your Nettskjema admin UI.

## Overview

You can now let your editors describe forms in natural language, and AI will automatically build them using the Nettskjema API through the MCP server.

**Example:**
> "Create a customer satisfaction survey with 5 rating questions about product quality, delivery speed, customer service, price, and likelihood to recommend"

The AI will:
1. Create the form
2. Add all 5 questions with appropriate rating scales
3. Return the form ID and summary

## Changes Made

### 1. Nettskjema MCP Server (`nettskjema-mcp/`)

#### New Tools Added

Added comprehensive form element manipulation tools:

- **`add_form_element`** - Add questions to forms
  - Supports multiple question types: text, textarea, radio, checkbox, select, number, email, date
  - Configurable options for choice-based questions
  - Position control for ordering

- **`update_form_element`** - Modify existing questions
  - Update question text, description, options
  - Change required status

- **`delete_form_element`** - Remove questions

- **`reorder_form_elements`** - Change question order

- **`duplicate_form_element`** - Copy existing questions

#### Files Modified

- `nettskjema_mcp/__init__.py` - Added new tool implementations
- `CLAUDE.md` - Updated with new tools documentation
- `README.md` - Added Next.js integration section

#### New Documentation

- `NEXTJS_INTEGRATION.md` - Complete guide for Next.js integration
- `INTEGRATION_SUMMARY.md` - This file
- `nextjs-example/` - Directory with example code
  - `types.ts` - TypeScript type definitions
  - `api-route.ts` - API route implementation
  - `AIFormBuilder.tsx` - React component
  - `README.md` - Quick start guide

### 2. Nettskjema Frontend (`nettskjema-frontend/`)

#### New Files Created

**Types:**
- `src/types/ai-form-builder.ts` - Type definitions for the AI form builder

**API Route:**
- `src/pages/api/ai-form-builder.ts` - Next.js API endpoint
  - Spawns MCP server
  - Integrates with OpenAI GPT-4
  - Executes MCP tools
  - Returns results

**Component:**
- `src/components/AIFormBuilder/AIFormBuilder.tsx` - React component
- `src/components/AIFormBuilder/aiFormBuilder.module.scss` - Styles
- `src/components/AIFormBuilder/index.ts` - Exports

**Documentation:**
- `AI_FORM_BUILDER_SETUP.md` - Setup and usage guide

#### Dependencies Added

```json
{
  "@modelcontextprotocol/sdk": "^1.0.4",
  "openai": "^4.77.3"
}
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser UI                               │
│                  (AIFormBuilder Component)                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ POST /api/ai-form-builder
                         │ { userPrompt: "Create a form..." }
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Next.js API Route                              │
│                (Pages Router Handler)                            │
│  • Receives user prompt                                         │
│  • Spawns Python MCP server subprocess                          │
│  • Gets available tools from MCP                                │
│  • Calls OpenAI GPT-4 with prompt + tools                       │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ Chat completion with tools
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OpenAI GPT-4                                │
│  • Analyzes user prompt                                         │
│  • Decides which tools to call                                  │
│  • Generates tool calls (create_form, add_form_element, etc.)   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ Tool execution requests
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Python MCP Server                                │
│                  (FastMCP / subprocess)                          │
│  • Receives tool calls via stdio                                │
│  • Authenticates with OAuth 2.1                                 │
│  • Makes API requests                                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ HTTPS requests
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Nettskjema API                                │
│                  (https://nettskjema.no)                         │
│  • Creates forms                                                │
│  • Adds form elements                                           │
│  • Returns results                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Setup Instructions

### Prerequisites

1. Python 3.10+ installed
2. Node.js 18+ installed
3. `uv` package manager: `pip install uv`
4. OpenAI API key
5. Nettskjema MCP credentials

### Quick Setup

#### 1. Install MCP Server

```bash
cd nettskjema-mcp
uv pip install -e .
```

#### 2. Configure MCP Server

Create `nettskjema-mcp/.env`:
```env
NETTSKJEMA_CLIENT_ID=your_client_id
NETTSKJEMA_CLIENT_SECRET=your_client_secret
```

#### 3. Install Frontend Dependencies

```bash
cd nettskjema-frontend
npm install
```

#### 4. Configure Frontend

Add to `nettskjema-frontend/.env`:
```env
OPENAI_API_KEY=sk-your-api-key
NETTSKJEMA_CLIENT_ID=your_client_id
NETTSKJEMA_CLIENT_SECRET=your_client_secret
NETTSKJEMA_MCP_PATH=../nettskjema-mcp
```

#### 5. Add to Your Application

Create a page (e.g., `src/pages/admin/ai-form-builder.tsx`):

```tsx
import { AIFormBuilder } from 'components/AIFormBuilder';

export default function AIFormBuilderPage() {
  return <AIFormBuilder />;
}
```

#### 6. Test

```bash
cd nettskjema-frontend
npm run dev
```

Navigate to your new page and try creating a form!

## Usage Examples

### Simple Form
```
Lag et kontaktskjema med navn, e-post og melding
```

Result: Form with 3 fields

### Survey with Ratings
```
Lag en kundetilfredshetundersøkelse med vurderinger (1-5) for:
- Produktkvalitet
- Levering
- Kundeservice
```

Result: Form with 3 rating questions (1-5 radio buttons each)

### Complex Form
```
Lag et påmeldingsskjema med:
- Navn (påkrevd)
- E-post (påkrevd)
- Telefon
- Kosthold (vegetar, vegan, glutenfri, ingen)
- Spesielle behov (valgfritt felt)
```

Result: Form with mixed field types and requirements

## Key Features

### Multi-Language Support

The component is integrated with your Lingui i18n setup:
- System prompts in Norwegian
- UI text translatable via Lingui
- Supports nb, nn, en locales

### Error Handling

- Network errors
- API failures
- MCP server startup issues
- Timeout handling
- User-friendly error messages

### Progress Indication

- Loading states
- Busy indicators on buttons
- Success/error notifications
- Tool execution details

### Security

- API keys never exposed to client
- Server-side execution only
- Environment variable configuration
- Ready for authentication integration

## Deployment Considerations

### Development

Works out of the box with `npm run dev`

### Production

1. **Environment Variables**: Set in production environment
2. **Python Runtime**: Ensure Python is available
3. **Process Management**: MCP server spawns as subprocess
4. **Timeouts**: May need adjustment for complex forms
5. **Monitoring**: Add logging for API calls

### Platform-Specific Notes

**Vercel:**
- Works on Pro plan and higher
- Set `export const maxDuration = 60` in API route
- May have cold start delays

**Docker:**
- Include Python and uv in Dockerfile
- Install MCP server during build
- See NEXTJS_INTEGRATION.md for example

**Self-Hosted:**
- No special requirements
- Standard Node.js + Python setup

## Troubleshooting

See `AI_FORM_BUILDER_SETUP.md` for detailed troubleshooting guide.

Common issues:
- MCP server not starting → Check Python and uv installation
- Tool execution failing → Verify API credentials
- Timeout errors → Increase API route timeout

## Next Steps

### Recommended Enhancements

1. **Add to Navigation**
   - Add link in admin menu
   - Add permissions check

2. **User Training**
   - Create documentation with examples
   - Add tooltips and help text

3. **Monitoring**
   - Log all AI form creations
   - Track success/failure rates
   - Monitor API usage

4. **Feedback Loop**
   - Gather user feedback
   - Improve prompts
   - Add more example prompts

5. **Advanced Features**
   - Form templates
   - Bulk form creation
   - Form modification (not just creation)
   - Preview before creation

6. **Testing**
   - Add unit tests
   - Integration tests for API route
   - E2E tests for complete flow

## API Reference

### MCP Tools

All available tools are documented in the MCP server:

```bash
cd nettskjema-mcp
python -c "from nettskjema_mcp import __all__; print(__all__)"
```

Key tools:
- `create_form(title, language)`
- `add_form_element(form_id, element_type, question_text, ...)`
- `update_form_element(form_id, element_id, ...)`
- `delete_form_element(form_id, element_id)`
- `get_form_elements(form_id)`
- And many more...

Full API docs: https://nettskjema.no/api/v3/v3/api-docs

## Support

For questions or issues:

1. **MCP Server Issues**: Check `nettskjema-mcp/README.md`
2. **Frontend Integration**: See `AI_FORM_BUILDER_SETUP.md`
3. **API Documentation**: https://nettskjema.no/api/v3/v3/api-docs
4. **OpenAI Issues**: https://platform.openai.com/docs

## License

Same as the parent projects (MIT)
