/**
 * TypeScript types mirroring the Python backend models.
 */

export type MessageRole = "user" | "assistant" | "system";

export interface TextBlock {
  type: "text";
  text: string;
}

export interface ToolUseBlock {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ToolResultBlock {
  type: "tool_result";
  tool_use_id: string;
  content: string;
  is_error: boolean;
}

export type ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock;

export interface ParsedMessage {
  id: string;
  role: MessageRole;
  content: ContentBlock[];
  timestamp?: string;
}

export interface SessionMetadata {
  session_id: string;
  model: string;
  tools: string[];
}

export type Theme = "light" | "dark" | "system";

// SSE event types
export interface SSEInitEvent {
  type: "init";
  metadata: SessionMetadata | null;
  messages: ParsedMessage[];
}

export interface SSEMessageEvent {
  type: "message";
  message: ParsedMessage;
}

export interface SSECompleteEvent {
  type: "complete";
  duration_ms: number | null;
  total_cost_usd: number | null;
}

export interface SSEErrorEvent {
  type: "error";
  error: string;
}

export type SSEEvent = SSEInitEvent | SSEMessageEvent | SSECompleteEvent | SSEErrorEvent;

// Type guards
export function isTextBlock(block: ContentBlock): block is TextBlock {
  return block.type === "text";
}

export function isToolUseBlock(block: ContentBlock): block is ToolUseBlock {
  return block.type === "tool_use";
}

export function isToolResultBlock(block: ContentBlock): block is ToolResultBlock {
  return block.type === "tool_result";
}
