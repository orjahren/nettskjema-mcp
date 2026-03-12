/**
 * Example Next.js API Route for AI Form Builder
 * Place this in: app/api/ai-form-builder/route.ts (App Router)
 * or: pages/api/ai-form-builder.ts (Pages Router)
 */

import { NextRequest, NextResponse } from 'next/server';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import OpenAI from 'openai';
import type { AIFormBuilderRequest, AIFormBuilderResponse } from './types';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export const maxDuration = 60; // For Vercel, set max execution time

export async function POST(request: NextRequest) {
  let mcpClient: Client | null = null;

  try {
    const body: AIFormBuilderRequest = await request.json();
    const { userPrompt } = body;

    if (!userPrompt || typeof userPrompt !== 'string') {
      return NextResponse.json(
        { error: 'Valid user prompt is required', success: false },
        { status: 400 }
      );
    }

    // Validate environment variables
    if (!process.env.NETTSKJEMA_CLIENT_ID || !process.env.NETTSKJEMA_CLIENT_SECRET) {
      return NextResponse.json(
        { error: 'Nettskjema credentials not configured', success: false },
        { status: 500 }
      );
    }

    console.log('[AI Form Builder] Starting MCP client...');

    // 1. Create and connect to MCP server
    const transport = new StdioClientTransport({
      command: 'uv',
      args: [
        '--directory',
        process.env.NETTSKJEMA_MCP_PATH || '/path/to/nettskjema-mcp',
        'run',
        'nettskjema-mcp',
      ],
      env: {
        NETTSKJEMA_CLIENT_ID: process.env.NETTSKJEMA_CLIENT_ID,
        NETTSKJEMA_CLIENT_SECRET: process.env.NETTSKJEMA_CLIENT_SECRET,
      },
    });

    mcpClient = new Client(
      { name: 'nextjs-nettskjema', version: '1.0.0' },
      { capabilities: {} }
    );

    await mcpClient.connect(transport);
    console.log('[AI Form Builder] MCP client connected');

    // 2. Get available tools
    const { tools } = await mcpClient.listTools();
    console.log(`[AI Form Builder] Loaded ${tools.length} tools`);

    // 3. Convert MCP tools to OpenAI format
    const openaiTools = tools.map((tool) => ({
      type: 'function' as const,
      function: {
        name: tool.name,
        description: tool.description,
        parameters: tool.inputSchema,
      },
    }));

    // 4. Set up conversation with system prompt
    const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
      {
        role: 'system',
        content: `You are an expert Nettskjema form builder assistant. Help users create and modify survey forms.

Guidelines:
- Always create a form first using create_form before adding elements
- Use descriptive, clear question text
- For rating questions, use radio buttons with options like ["1", "2", "3", "4", "5"]
- For yes/no questions, use radio with ["Yes", "No"]
- For multiple choice, use checkbox if multiple answers allowed, radio if single answer
- Set required=true for essential questions
- Add helpful descriptions to complex questions
- After creating forms, provide the form ID and a summary of what was created

Available element types:
- text: Single-line text input
- textarea: Multi-line text input
- radio: Single choice (use for ratings, yes/no, single select)
- checkbox: Multiple choice
- select: Dropdown selection
- number: Numeric input
- email: Email address
- date: Date picker

Be helpful and ask clarifying questions if the user's request is unclear.`,
      },
      {
        role: 'user',
        content: userPrompt,
      },
    ];

    // 5. Call GPT and execute tools in a loop
    const toolResults: AIFormBuilderResponse['toolResults'] = [];
    let iterations = 0;
    const maxIterations = 15; // Prevent infinite loops

    let response = await openai.chat.completions.create({
      model: 'gpt-4-turbo',
      messages,
      tools: openaiTools,
      tool_choice: 'auto',
    });

    while (response.choices[0].message.tool_calls && iterations < maxIterations) {
      iterations++;
      console.log(`[AI Form Builder] Iteration ${iterations}`);

      const toolCalls = response.choices[0].message.tool_calls;

      // Add assistant's message to conversation
      messages.push(response.choices[0].message);

      // Execute each tool call
      for (const toolCall of toolCalls) {
        const functionName = toolCall.function.name;
        const functionArgs = JSON.parse(toolCall.function.arguments);

        console.log(`[AI Form Builder] Calling tool: ${functionName}`, functionArgs);

        try {
          const result = await mcpClient.callTool({
            name: functionName,
            arguments: functionArgs,
          });

          console.log(`[AI Form Builder] Tool result:`, result.content);

          toolResults.push({
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
          console.error(`[AI Form Builder] Tool error:`, error);

          const errorMessage = error instanceof Error ? error.message : 'Unknown error';

          toolResults.push({
            tool: functionName,
            arguments: functionArgs,
            result: { error: errorMessage },
          });

          messages.push({
            role: 'tool',
            tool_call_id: toolCall.id,
            content: JSON.stringify({ error: errorMessage }),
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

    console.log('[AI Form Builder] Conversation complete');

    // 6. Return final response
    const finalResponse: AIFormBuilderResponse = {
      message: response.choices[0].message.content || 'Form created successfully',
      toolResults,
      success: true,
    };

    return NextResponse.json(finalResponse);
  } catch (error) {
    console.error('[AI Form Builder] Error:', error);

    const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';

    const errorResponse: AIFormBuilderResponse = {
      message: '',
      toolResults: [],
      success: false,
      error: errorMessage,
    };

    return NextResponse.json(errorResponse, { status: 500 });
  } finally {
    // 7. Always clean up MCP client
    if (mcpClient) {
      try {
        await mcpClient.close();
        console.log('[AI Form Builder] MCP client closed');
      } catch (error) {
        console.error('[AI Form Builder] Error closing MCP client:', error);
      }
    }
  }
}
