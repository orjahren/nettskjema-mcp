/**
 * TypeScript type definitions for Nettskjema MCP tools
 * These types help with type-safe integration in Next.js/TypeScript projects
 */

export interface NettskjemaForm {
  formId: number;
  title: string;
  language: string;
  created: string;
  modified: string;
  owner: string;
}

export interface FormElement {
  elementId: number;
  elementType: string;
  questionText: string;
  description?: string;
  required: boolean;
  options?: string[];
  position: number;
}

export interface FormSubmission {
  submissionId: number;
  formId: number;
  submitted: string;
  answers: Record<string, unknown>;
}

export type ElementType =
  | 'text'
  | 'textarea'
  | 'radio'
  | 'checkbox'
  | 'select'
  | 'number'
  | 'email'
  | 'date'
  | 'matrix';

export interface CreateFormParams {
  title: string;
  language?: string;
}

export interface AddElementParams {
  form_id: number;
  element_type: ElementType;
  question_text: string;
  description?: string;
  required?: boolean;
  options?: string[];
  position?: number;
}

export interface UpdateElementParams {
  form_id: number;
  element_id: number;
  question_text?: string;
  description?: string;
  required?: boolean;
  options?: string[];
}

export interface MCPToolResult {
  content: Array<{
    type: string;
    text: string;
  }>;
}

export interface AIFormBuilderRequest {
  userPrompt: string;
}

export interface AIFormBuilderResponse {
  message: string;
  toolResults: ToolExecutionResult[];
  success: boolean;
  error?: string;
}

export interface ToolExecutionResult {
  tool: string;
  arguments: Record<string, unknown>;
  result: unknown;
}
