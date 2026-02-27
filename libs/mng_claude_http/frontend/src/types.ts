/**
 * Types for the Claude Code SDK WebSocket protocol and UI state.
 */

// === SDK Protocol Messages (CLI -> Server -> Browser) ===

export interface SystemInitMessage {
  type: "system";
  subtype: "init";
  session_id: string;
  model: string;
  tools: string[];
  cwd?: string;
  permissionMode?: string;
  claude_code_version?: string;
  uuid?: string;
}

export interface SystemStatusMessage {
  type: "system";
  subtype: "status";
  status: string | null;
  uuid?: string;
  session_id?: string;
}

export interface SystemMessage {
  type: "system";
  subtype: string;
  [key: string]: unknown;
}

export interface TextContentBlock {
  type: "text";
  text: string;
}

export interface ThinkingContentBlock {
  type: "thinking";
  thinking: string;
}

export interface ToolUseContentBlock {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ToolResultContentBlock {
  type: "tool_result";
  tool_use_id: string;
  content: string;
  is_error?: boolean;
}

export type ContentBlock =
  | TextContentBlock
  | ThinkingContentBlock
  | ToolUseContentBlock
  | ToolResultContentBlock;

export interface AssistantMessagePayload {
  id: string;
  type: "message";
  role: "assistant";
  model: string;
  content: ContentBlock[];
  stop_reason: string | null;
  usage?: {
    input_tokens: number;
    output_tokens: number;
  };
}

export interface AssistantMessage {
  type: "assistant";
  message: AssistantMessagePayload;
  parent_tool_use_id?: string | null;
  uuid?: string;
  session_id?: string;
}

export interface UserMessage {
  type: "user";
  message: {
    role: "user";
    content: ContentBlock[] | string;
  };
  parent_tool_use_id?: string | null;
  uuid?: string;
  session_id?: string;
}

export interface ResultMessage {
  type: "result";
  subtype: string;
  is_error: boolean;
  result?: string;
  duration_ms?: number;
  total_cost_usd?: number;
  num_turns?: number;
  uuid?: string;
  session_id?: string;
}

export interface StreamEvent {
  type: "stream_event";
  event: {
    type: string;
    delta?: {
      type: string;
      text?: string;
    };
    index?: number;
    content_block?: {
      type: string;
      text?: string;
      id?: string;
      name?: string;
    };
  };
  parent_tool_use_id?: string | null;
  uuid?: string;
  session_id?: string;
}

export interface ToolProgressMessage {
  type: "tool_progress";
  tool_use_id: string;
  tool_name: string;
  elapsed_time_seconds?: number;
  uuid?: string;
  session_id?: string;
}

export interface ControlRequest {
  type: "control_request";
  request_id: string;
  request: {
    subtype: string;
    tool_name?: string;
    input?: Record<string, unknown>;
    permission_suggestions?: unknown[];
    description?: string;
    tool_use_id?: string;
    [key: string]: unknown;
  };
}

export type SdkMessage =
  | SystemMessage
  | AssistantMessage
  | UserMessage
  | ResultMessage
  | StreamEvent
  | ToolProgressMessage
  | ControlRequest;

// === Browser -> Server Messages ===

export interface StartSessionMessage {
  type: "start_session";
  prompt: string;
  model?: string;
}

export interface SendMessageMessage {
  type: "send_message";
  content: string;
}

export interface ToolResponseMessage {
  type: "tool_response";
  response: {
    type: "control_response";
    response: {
      subtype: "success";
      request_id: string;
      response: {
        behavior: "allow" | "deny";
        updatedInput?: Record<string, unknown>;
        message?: string;
      };
    };
  };
}

export interface InterruptMessage {
  type: "interrupt";
}

export type BrowserMessage =
  | StartSessionMessage
  | SendMessageMessage
  | ToolResponseMessage
  | InterruptMessage;

// === Server -> Browser Messages ===

export interface ConnectionStateMessage {
  type: "connection_state";
  cli_connected: boolean;
  metadata: SessionMetadata | null;
  messages: AssistantMessage[];
}

export interface ErrorMessage {
  type: "error";
  error: string;
}

// === UI State Types ===

export interface SessionMetadata {
  session_id: string;
  model: string;
  tools: string[];
}

export interface PendingToolApproval {
  request_id: string;
  tool_name: string;
  input: Record<string, unknown>;
  description?: string;
}

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "session_active";

// === Display Message Type (for rendering) ===

export interface DisplayMessage {
  id: string;
  role: "user" | "assistant" | "system" | "result";
  content: ContentBlock[];
  timestamp: number;
  isStreaming?: boolean;
  cost?: number;
  duration_ms?: number;
}

// Type guards
export function isTextBlock(block: ContentBlock): block is TextContentBlock {
  return block.type === "text";
}

export function isToolUseBlock(block: ContentBlock): block is ToolUseContentBlock {
  return block.type === "tool_use";
}

export function isToolResultBlock(block: ContentBlock): block is ToolResultContentBlock {
  return block.type === "tool_result";
}

export function isThinkingBlock(block: ContentBlock): block is ThinkingContentBlock {
  return block.type === "thinking";
}
