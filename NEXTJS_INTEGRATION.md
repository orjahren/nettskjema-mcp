# Next.js Integration Guide

This guide shows how to integrate the Nettskjema MCP server with a Next.js application for AI-assisted form building.

## Architecture

```
[Next.js Browser UI] ←→ [Next.js API Routes/Server Actions] ←MCP stdio→ [Python MCP Server] ←→ [Nettskjema API]
                        [+ GPT API calls]                      (FastMCP)
```

The MCP client runs on your Next.js server (API routes or Server Actions), not in the browser.

## Prerequisites

1. Next.js application (App Router or Pages Router)
2. Access to an LLM API (OpenAI GPT, Anthropic Claude, etc.)
3. This MCP server installed and configured
4. Node.js 18+ and Python 3.10+

## Installation

### 1. Install MCP SDK in Your Next.js Project

```bash
npm install @modelcontextprotocol/sdk
```

### 2. Install OpenAI SDK (or your preferred LLM)

```bash
npm install openai
```

### 3. Set Up Environment Variables

Add to your `.env.local`:

```env
OPENAI_API_KEY=sk-...
NETTSKJEMA_CLIENT_ID=your_client_id
NETTSKJEMA_CLIENT_SECRET=your_client_secret
NETTSKJEMA_MCP_PATH=/absolute/path/to/nettskjema-mcp
```

## Implementation

### Option 1: API Route (Recommended)

Create `app/api/ai-form-builder/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export async function POST(request: NextRequest) {
  try {
    const { userPrompt } = await request.json();

    if (!userPrompt) {
      return NextResponse.json(
        { error: 'User prompt is required' },
        { status: 400 }
      );
    }

    // 1. Spawn the Python MCP server as a subprocess
    const transport = new StdioClientTransport({
      command: 'uv',
      args: [
        '--directory',
        process.env.NETTSKJEMA_MCP_PATH || '/path/to/nettskjema-mcp',
        'run',
        'nettskjema-mcp',
      ],
      env: {
        NETTSKJEMA_CLIENT_ID: process.env.NETTSKJEMA_CLIENT_ID!,
        NETTSKJEMA_CLIENT_SECRET: process.env.NETTSKJEMA_CLIENT_SECRET!,
      },
    });

    const mcpClient = new Client(
      {
        name: 'nextjs-nettskjema',
        version: '1.0.0',
      },
      {
        capabilities: {},
      }
    );

    await mcpClient.connect(transport);

    // 2. Get available tools from the MCP server
    const { tools } = await mcpClient.listTools();

    // 3. Convert MCP tools to OpenAI function format
    const openaiTools = tools.map((tool) => ({
      type: 'function' as const,
      function: {
        name: tool.name,
        description: tool.description,
        parameters: tool.inputSchema,
      },
    }));

    // 4. Call GPT with the user prompt and available tools
    const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
      {
        role: 'system',
        content: `You are a Nettskjema form builder assistant. Help users create and modify survey forms using the available tools.

When creating forms:
- Use create_form to create a new form first
- Use add_form_element to add questions one by one
- Common element types: text, textarea, radio, checkbox, select, number, email, date
- For radio/checkbox/select, provide options array
- Be helpful and ask clarifying questions if needed`,
      },
      {
        role: 'user',
        content: userPrompt,
      },
    ];

    let response = await openai.chat.completions.create({
      model: 'gpt-4-turbo',
      messages,
      tools: openaiTools,
      tool_choice: 'auto',
    });

    const results = [];
    let iterations = 0;
    const maxIterations = 10; // Prevent infinite loops

    // 5. Execute tool calls in a loop (allows multi-turn conversations)
    while (response.choices[0].message.tool_calls && iterations < maxIterations) {
      iterations++;
      const toolCalls = response.choices[0].message.tool_calls;

      // Add assistant message to conversation
      messages.push(response.choices[0].message);

      // Execute each tool call
      for (const toolCall of toolCalls) {
        const functionName = toolCall.function.name;
        const functionArgs = JSON.parse(toolCall.function.arguments);

        console.log(`Executing tool: ${functionName}`, functionArgs);

        try {
          const result = await mcpClient.callTool({
            name: functionName,
            arguments: functionArgs,
          });

          results.push({
            tool: functionName,
            arguments: functionArgs,
            result: result.content,
          });

          // Add tool result to conversation
          messages.push({
            role: 'tool',
            tool_call_id: toolCall.id,
            content: JSON.stringify(result.content),
          });
        } catch (error) {
          console.error(`Error calling tool ${functionName}:`, error);
          messages.push({
            role: 'tool',
            tool_call_id: toolCall.id,
            content: JSON.stringify({
              error: error instanceof Error ? error.message : 'Unknown error',
            }),
          });
        }
      }

      // Get next response from GPT
      response = await openai.chat.completions.create({
        model: 'gpt-4-turbo',
        messages,
        tools: openaiTools,
        tool_choice: 'auto',
      });
    }

    // 6. Clean up MCP connection
    await mcpClient.close();

    // 7. Return final response
    return NextResponse.json({
      message: response.choices[0].message.content,
      toolResults: results,
      success: true,
    });
  } catch (error) {
    console.error('Error in AI form builder:', error);
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : 'Unknown error',
        success: false,
      },
      { status: 500 }
    );
  }
}
```

### Option 2: Server Action

Create `app/actions/ai-form-builder.ts`:

```typescript
'use server';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export async function buildFormWithAI(userPrompt: string) {
  // Implementation similar to API route above
  // ...
}
```

## React Component

Create `components/AIFormBuilder.tsx`:

```tsx
'use client';

import { useState } from 'react';

interface ToolResult {
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

interface AIResponse {
  message: string;
  toolResults: ToolResult[];
  success: boolean;
}

export function AIFormBuilder() {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<AIResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const res = await fetch('/api/ai-form-builder', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ userPrompt: prompt }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || 'Failed to build form');
      }

      setResponse(data);
      setPrompt(''); // Clear input on success
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">AI Form Builder</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="prompt" className="block text-sm font-medium mb-2">
            Describe the form you want to create
          </label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Example: Create a customer satisfaction survey with 5 rating questions about product quality, delivery speed, customer service, price, and likelihood to recommend"
            className="w-full min-h-32 p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {loading ? 'Building form...' : 'Create Form'}
        </button>
      </form>

      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-800">
            <strong>Error:</strong> {error}
          </p>
        </div>
      )}

      {response && (
        <div className="mt-6 space-y-4">
          <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
            <p className="text-green-800">
              <strong>Success!</strong> {response.message}
            </p>
          </div>

          {response.toolResults.length > 0 && (
            <div className="p-4 bg-gray-50 border rounded-lg">
              <h3 className="font-semibold mb-2">Actions Performed:</h3>
              <ul className="space-y-2">
                {response.toolResults.map((result, idx) => (
                  <li key={idx} className="text-sm">
                    <span className="font-mono text-blue-600">{result.tool}</span>
                    <pre className="mt-1 p-2 bg-white rounded text-xs overflow-x-auto">
                      {JSON.stringify(result.arguments, null, 2)}
                    </pre>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

## Usage Examples

### Example 1: Simple Form Creation

User prompt:
```
Create a feedback form with fields for name, email, and comments
```

GPT will:
1. Call `create_form(title="Feedback Form")`
2. Call `add_form_element(form_id=X, element_type="text", question_text="Name", required=true)`
3. Call `add_form_element(form_id=X, element_type="email", question_text="Email", required=true)`
4. Call `add_form_element(form_id=X, element_type="textarea", question_text="Comments")`

### Example 2: Survey with Rating Questions

User prompt:
```
Create a customer satisfaction survey with 5-star ratings for product quality, shipping, and customer service
```

GPT will:
1. Call `create_form(title="Customer Satisfaction Survey")`
2. For each question, call `add_form_element()` with `element_type="radio"` and `options=["1", "2", "3", "4", "5"]`

### Example 3: Form Modification

User prompt:
```
Add a question about dietary restrictions with options for vegetarian, vegan, gluten-free, and none
```

GPT will:
1. First call `list_my_forms()` to find the relevant form
2. Call `add_form_element()` with `element_type="checkbox"` and the appropriate options

## Best Practices

### 1. Error Handling

Always handle errors gracefully:
- MCP server spawn failures
- Tool execution failures
- LLM API failures
- Network timeouts

### 2. Timeout Management

Set appropriate timeouts:
```typescript
const transport = new StdioClientTransport({
  command: 'uv',
  args: [...],
  env: {...},
  timeout: 30000, // 30 seconds
});
```

### 3. Cleanup

Always close the MCP client connection:
```typescript
try {
  // ... your code
} finally {
  await mcpClient.close();
}
```

### 4. Rate Limiting

Implement rate limiting to prevent abuse:
```typescript
import { Ratelimit } from '@upstash/ratelimit';

const ratelimit = new Ratelimit({
  redis: /* your redis instance */,
  limiter: Ratelimit.slidingWindow(10, '1 m'),
});
```

### 5. Caching

Consider caching MCP tool lists if they don't change often:
```typescript
let cachedTools: Tool[] | null = null;

if (!cachedTools) {
  const { tools } = await mcpClient.listTools();
  cachedTools = tools;
}
```

### 6. Security

- Never expose API keys to the client
- Validate user input before processing
- Implement authentication/authorization
- Use environment variables for sensitive data

## Deployment Considerations

### Vercel

The MCP server spawns a Python subprocess, which works on Vercel but has limitations:
- Works on Pro plan and higher
- May have cold start delays
- Consider using serverless functions with longer timeouts

### Docker

For better control, deploy with Docker:
```dockerfile
FROM node:18-alpine

# Install Python and dependencies
RUN apk add --no-cache python3 py3-pip

# Copy and install Python MCP server
COPY nettskjema-mcp /app/nettskjema-mcp
WORKDIR /app/nettskjema-mcp
RUN pip install -e .

# Copy and install Next.js app
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

CMD ["npm", "start"]
```

### Environment Variables

In production, set:
```bash
NETTSKJEMA_CLIENT_ID=...
NETTSKJEMA_CLIENT_SECRET=...
OPENAI_API_KEY=...
NETTSKJEMA_MCP_PATH=/app/nettskjema-mcp
```

## Troubleshooting

### MCP Server Not Starting

Check:
- Python is installed and accessible
- `uv` is installed (`pip install uv`)
- Path to MCP server is correct
- Environment variables are set

### Tool Calls Failing

Check:
- Nettskjema API credentials are valid
- Form permissions are set correctly
- Network connectivity to Nettskjema API

### Timeouts

Increase timeouts if needed:
```typescript
await openai.chat.completions.create({
  // ...
  timeout: 60000, // 60 seconds
});
```

## Alternative: Direct API Integration

If MCP overhead is too high, you can skip the MCP protocol and import the Python functions directly using a Python bridge, or rewrite the API client in TypeScript.

However, using MCP provides:
- Standardized tool interface
- Better LLM integration
- Reusability across different clients
- Separation of concerns

## Resources

- [MCP SDK Documentation](https://modelcontextprotocol.io/)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Nettskjema API Docs](https://nettskjema.no/api/v3/v3/api-docs)
