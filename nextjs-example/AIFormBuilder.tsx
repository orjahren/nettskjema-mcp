/**
 * Example React Component for AI Form Builder
 * Place this in: components/AIFormBuilder.tsx
 */

'use client';

import { useState } from 'react';
import type { AIFormBuilderResponse, ToolExecutionResult } from './types';

export function AIFormBuilder() {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<AIFormBuilderResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!prompt.trim()) {
      return;
    }

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

      const data: AIFormBuilderResponse = await res.json();

      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to build form');
      }

      setResponse(data);
      setPrompt(''); // Clear input on success
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
    } finally {
      setLoading(false);
    }
  };

  const examplePrompts = [
    'Create a customer feedback form with name, email, rating (1-5), and comments',
    'Create an event registration form with name, email, dietary restrictions (vegetarian, vegan, gluten-free, none), and special requests',
    'Create a simple contact form with name, email, subject, and message',
    'Create a product satisfaction survey with 5 rating questions about quality, price, delivery, service, and recommendation likelihood',
  ];

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">AI Form Builder</h1>
        <p className="text-gray-600">
          Describe the form you want to create, and AI will build it for you in Nettskjema.
        </p>
      </div>

      {/* Example prompts */}
      <div className="mb-6">
        <p className="text-sm font-medium text-gray-700 mb-2">Try these examples:</p>
        <div className="flex flex-wrap gap-2">
          {examplePrompts.map((example, idx) => (
            <button
              key={idx}
              onClick={() => setPrompt(example)}
              className="text-xs px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded-full transition-colors"
              disabled={loading}
            >
              {example.length > 60 ? example.substring(0, 60) + '...' : example}
            </button>
          ))}
        </div>
      </div>

      {/* Form input */}
      <form onSubmit={handleSubmit} className="space-y-4 mb-8">
        <div>
          <label htmlFor="prompt" className="block text-sm font-medium mb-2">
            Describe your form
          </label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Example: Create a customer satisfaction survey with 5 rating questions about product quality, delivery speed, customer service, price, and likelihood to recommend"
            className="w-full min-h-32 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
            disabled={loading}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors font-medium"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <svg
                className="animate-spin h-5 w-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Building form...
            </span>
          ) : (
            'Create Form'
          )}
        </button>
      </form>

      {/* Error message */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 text-red-600 mt-0.5"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clipRule="evenodd"
              />
            </svg>
            <div>
              <p className="font-medium text-red-800">Error</p>
              <p className="text-red-700 text-sm mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Success response */}
      {response && (
        <div className="space-y-6">
          <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 text-green-600 mt-0.5"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
              <div className="flex-1">
                <p className="font-medium text-green-800">Success!</p>
                <p className="text-green-700 text-sm mt-1 whitespace-pre-wrap">
                  {response.message}
                </p>
              </div>
            </div>
          </div>

          {/* Tool execution results */}
          {response.toolResults.length > 0 && (
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-3 border-b">
                <h3 className="font-semibold text-gray-900">
                  Actions Performed ({response.toolResults.length})
                </h3>
              </div>
              <div className="divide-y">
                {response.toolResults.map((result, idx) => (
                  <ToolResultItem key={idx} result={result} index={idx} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ToolResultItem({
  result,
  index,
}: {
  result: ToolExecutionResult;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="p-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-left hover:bg-gray-50 -m-4 p-4 rounded transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-xs font-medium">
            {index + 1}
          </span>
          <span className="font-mono text-sm text-blue-600">{result.tool}</span>
        </div>
        <svg
          className={`w-5 h-5 text-gray-400 transition-transform ${
            expanded ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">Arguments:</p>
            <pre className="p-3 bg-gray-50 rounded text-xs overflow-x-auto">
              {JSON.stringify(result.arguments, null, 2)}
            </pre>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">Result:</p>
            <pre className="p-3 bg-gray-50 rounded text-xs overflow-x-auto">
              {JSON.stringify(result.result, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
