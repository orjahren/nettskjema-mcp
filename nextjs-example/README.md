# Next.js Integration Examples

This directory contains example code for integrating the Nettskjema MCP server with Next.js for AI-assisted form building.

## Files

- **`types.ts`** - TypeScript type definitions for type-safe integration
- **`api-route.ts`** - Complete API route example (App Router)
- **`AIFormBuilder.tsx`** - React component for the form builder UI

## Quick Start

### 1. Copy Files to Your Next.js Project

```bash
# Copy types
cp types.ts your-nextjs-app/lib/types/nettskjema.ts

# Copy API route (App Router)
cp api-route.ts your-nextjs-app/app/api/ai-form-builder/route.ts

# Copy React component
cp AIFormBuilder.tsx your-nextjs-app/components/AIFormBuilder.tsx
```

### 2. Install Dependencies

```bash
npm install @modelcontextprotocol/sdk openai
```

### 3. Set Environment Variables

Add to `.env.local`:

```env
OPENAI_API_KEY=sk-...
NETTSKJEMA_CLIENT_ID=your_client_id
NETTSKJEMA_CLIENT_SECRET=your_client_secret
NETTSKJEMA_MCP_PATH=/absolute/path/to/nettskjema-mcp
```

### 4. Use the Component

```tsx
// app/page.tsx or app/forms/page.tsx
import { AIFormBuilder } from '@/components/AIFormBuilder';

export default function FormsPage() {
  return (
    <main>
      <AIFormBuilder />
    </main>
  );
}
```

## How It Works

1. **User Input**: Editor types a natural language description of the form they want
2. **API Route**: Next.js API route receives the prompt
3. **MCP Client**: Spawns the Python MCP server as a subprocess
4. **LLM Processing**: Sends prompt + available tools to GPT/Claude
5. **Tool Execution**: LLM decides which tools to call (create_form, add_form_element, etc.)
6. **MCP Calls**: Next.js executes those tools through the MCP server
7. **Response**: Returns results to the user with form details

## Customization

### Using Claude Instead of GPT

Replace the OpenAI client with Anthropic:

```typescript
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

// Use Claude's tool calling API
const response = await anthropic.messages.create({
  model: 'claude-3-5-sonnet-20241022',
  max_tokens: 4096,
  tools: openaiTools, // Same format works
  messages: [
    { role: 'user', content: userPrompt }
  ],
});
```

### Adding Authentication

Protect the API route with your auth system:

```typescript
import { auth } from '@/lib/auth';

export async function POST(request: NextRequest) {
  const session = await auth();

  if (!session) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401 }
    );
  }

  // ... rest of the code
}
```

### Rate Limiting

Add rate limiting to prevent abuse:

```typescript
import { Ratelimit } from '@upstash/ratelimit';
import { Redis } from '@upstash/redis';

const ratelimit = new Ratelimit({
  redis: Redis.fromEnv(),
  limiter: Ratelimit.slidingWindow(10, '1 m'), // 10 requests per minute
});

export async function POST(request: NextRequest) {
  const ip = request.ip ?? 'anonymous';
  const { success } = await ratelimit.limit(ip);

  if (!success) {
    return NextResponse.json(
      { error: 'Rate limit exceeded' },
      { status: 429 }
    );
  }

  // ... rest of the code
}
```

### Custom Styling

The component uses Tailwind CSS. Customize the classes to match your design system:

```tsx
// Change button colors
className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"

// Change input styles
className="w-full min-h-32 p-3 border-2 border-purple-300 rounded-xl"
```

## Deployment

### Vercel

Works on Vercel Pro and higher (requires longer execution times for subprocess):

```typescript
// app/api/ai-form-builder/route.ts
export const maxDuration = 60; // seconds
```

### Self-Hosted (Docker)

For better control, use Docker:

```dockerfile
FROM node:20-alpine

# Install Python and uv
RUN apk add --no-cache python3 py3-pip
RUN pip3 install uv

# Install MCP server
COPY nettskjema-mcp /app/nettskjema-mcp
WORKDIR /app/nettskjema-mcp
RUN uv pip install -e .

# Install Next.js app
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

CMD ["npm", "start"]
```

## Troubleshooting

### "MCP server failed to start"

- Check that Python and `uv` are installed
- Verify `NETTSKJEMA_MCP_PATH` is correct
- Check environment variables are set

### "Tool execution failed"

- Verify Nettskjema credentials are valid
- Check that your API client has form editing permissions
- Review the Nettskjema API docs: https://nettskjema.no/api/v3/v3/api-docs

### Timeout errors

Increase the timeout:

```typescript
export const maxDuration = 120; // 2 minutes
```

## See Also

- [Full Integration Guide](../NEXTJS_INTEGRATION.md)
- [Nettskjema API Docs](https://nettskjema.no/api/v3/v3/api-docs)
- [MCP Documentation](https://modelcontextprotocol.io/)
