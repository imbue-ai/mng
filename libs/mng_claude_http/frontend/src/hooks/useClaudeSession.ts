import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AssistantMessage,
  BrowserMessage,
  ConnectionStatus,
  ContentBlock,
  ControlRequest,
  DisplayMessage,
  PendingToolApproval,
  ResultMessage,
  SessionMetadata,
  SdkMessage,
  StreamEvent,
  TextContentBlock,
  ToolResultContentBlock,
  ToolUseContentBlock,
} from "~/types";

declare global {
  interface Window {
    __WS_URL__: string;
  }
}

interface StreamingState {
  currentMessageId: string | null;
  contentBlocks: ContentBlock[];
  blockTexts: Map<number, string>;
}

export function useClaudeSession() {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [metadata, setMetadata] = useState<SessionMetadata | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<PendingToolApproval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamingRef = useRef<StreamingState>({
    currentMessageId: null,
    contentBlocks: [],
    blockTexts: new Map(),
  });

  const send = useCallback((msg: BrowserMessage) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }, []);

  const handleAssistantMessage = useCallback((msg: AssistantMessage) => {
    const content = msg.message.content;
    const displayMsg: DisplayMessage = {
      id: msg.message.id || crypto.randomUUID(),
      role: "assistant",
      content,
      timestamp: Date.now(),
    };

    // Finalize any streaming state
    streamingRef.current = {
      currentMessageId: null,
      contentBlocks: [],
      blockTexts: new Map(),
    };

    setMessages((prev) => {
      // If the last message was a streaming placeholder, replace it
      const last = prev[prev.length - 1];
      if (last && last.isStreaming) {
        return [...prev.slice(0, -1), displayMsg];
      }
      return [...prev, displayMsg];
    });
  }, []);

  const handleStreamEvent = useCallback((msg: StreamEvent) => {
    const event = msg.event;
    const streaming = streamingRef.current;

    if (event.type === "content_block_start") {
      const block = event.content_block;
      const index = event.index ?? streaming.contentBlocks.length;

      if (block) {
        if (block.type === "text") {
          streaming.contentBlocks[index] = { type: "text", text: block.text || "" } as TextContentBlock;
          streaming.blockTexts.set(index, block.text || "");
        } else if (block.type === "tool_use") {
          streaming.contentBlocks[index] = {
            type: "tool_use",
            id: block.id || "",
            name: block.name || "",
            input: {},
          } as ToolUseContentBlock;
        }
      }
    } else if (event.type === "content_block_delta") {
      const index = event.index ?? 0;
      const delta = event.delta;

      if (delta?.type === "text_delta" && delta.text) {
        const existing = streaming.blockTexts.get(index) || "";
        const updated = existing + delta.text;
        streaming.blockTexts.set(index, updated);
        streaming.contentBlocks[index] = { type: "text", text: updated } as TextContentBlock;
      }
    }

    // Update the streaming display message
    if (streaming.contentBlocks.length > 0) {
      const displayMsg: DisplayMessage = {
        id: streaming.currentMessageId || crypto.randomUUID(),
        role: "assistant",
        content: [...streaming.contentBlocks],
        timestamp: Date.now(),
        isStreaming: true,
      };

      if (!streaming.currentMessageId) {
        streaming.currentMessageId = displayMsg.id;
      }

      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.isStreaming) {
          return [...prev.slice(0, -1), displayMsg];
        }
        return [...prev, displayMsg];
      });
    }
  }, []);

  const handleControlRequest = useCallback((msg: ControlRequest) => {
    const req = msg.request;
    if (req.subtype === "can_use_tool") {
      setPendingApprovals((prev) => [
        ...prev,
        {
          request_id: msg.request_id,
          tool_name: req.tool_name || "unknown",
          input: (req.input as Record<string, unknown>) || {},
          description: req.description as string | undefined,
        },
      ]);
    }
  }, []);

  const handleResultMessage = useCallback((msg: ResultMessage) => {
    setIsProcessing(false);

    // Finalize streaming
    streamingRef.current = {
      currentMessageId: null,
      contentBlocks: [],
      blockTexts: new Map(),
    };

    const displayMsg: DisplayMessage = {
      id: crypto.randomUUID(),
      role: "result",
      content: msg.result
        ? [{ type: "text", text: msg.result } as TextContentBlock]
        : [],
      timestamp: Date.now(),
      cost: msg.total_cost_usd,
      duration_ms: msg.duration_ms,
    };

    if (msg.is_error) {
      setError(`Session ended with error: ${msg.subtype}`);
    }

    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.isStreaming) {
        return [...prev.slice(0, -1), displayMsg];
      }
      return [...prev, displayMsg];
    });
  }, []);

  const handleSdkMessage = useCallback(
    (msg: SdkMessage) => {
      switch (msg.type) {
        case "system": {
          if (msg.subtype === "init") {
            setMetadata({
              session_id: (msg as Record<string, string>).session_id || "",
              model: (msg as Record<string, string>).model || "",
              tools: ((msg as Record<string, unknown>).tools as string[]) || [],
            });
            setStatus("session_active");
            setIsProcessing(true);
          }
          break;
        }
        case "assistant":
          handleAssistantMessage(msg as AssistantMessage);
          break;
        case "stream_event":
          handleStreamEvent(msg as StreamEvent);
          break;
        case "control_request":
          handleControlRequest(msg as ControlRequest);
          break;
        case "result":
          handleResultMessage(msg as ResultMessage);
          break;
        case "user": {
          // Tool results from CLI - add as display messages
          const userMsg = msg as unknown as Record<string, unknown>;
          const userMsgContent = userMsg.message as Record<string, unknown> | undefined;
          if (userMsgContent) {
            const content = userMsgContent.content;
            if (Array.isArray(content)) {
              // Check for tool results
              const toolResults = content.filter(
                (b: Record<string, unknown>) => b.type === "tool_result"
              ) as ToolResultContentBlock[];
              if (toolResults.length > 0) {
                // Merge tool results into the last assistant message
                setMessages((prev) => {
                  const newMessages = [...prev];
                  for (let i = newMessages.length - 1; i >= 0; i--) {
                    if (newMessages[i].role === "assistant") {
                      newMessages[i] = {
                        ...newMessages[i],
                        content: [...newMessages[i].content, ...toolResults],
                      };
                      break;
                    }
                  }
                  return newMessages;
                });
              }
            }
          }
          break;
        }
      }
    },
    [handleAssistantMessage, handleStreamEvent, handleControlRequest, handleResultMessage]
  );

  const connect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    const wsUrl =
      typeof window.__WS_URL__ === "string" && window.__WS_URL__ !== "__WS_URL__"
        ? window.__WS_URL__
        : `ws://${window.location.host}/ws/browser`;

    setStatus("connecting");
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle server-specific messages
        if (data.type === "connection_state") {
          if (data.cli_connected) {
            setStatus("session_active");
          }
          if (data.metadata) {
            setMetadata(data.metadata);
          }
          // Replay historical messages
          if (data.messages && Array.isArray(data.messages)) {
            for (const msg of data.messages) {
              handleSdkMessage(msg);
            }
          }
          return;
        }

        if (data.type === "error") {
          setError(data.error);
          return;
        }

        // Handle SDK messages from CLI
        handleSdkMessage(data as SdkMessage);
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };

    ws.onclose = () => {
      setStatus("disconnected");
      wsRef.current = null;
      // Reconnect after delay
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      setError("WebSocket connection error");
    };
  }, [handleSdkMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  const startSession = useCallback(
    (prompt: string, model?: string) => {
      setMessages([
        {
          id: crypto.randomUUID(),
          role: "user",
          content: [{ type: "text", text: prompt }],
          timestamp: Date.now(),
        },
      ]);
      setIsProcessing(true);
      setError(null);
      setPendingApprovals([]);
      send({ type: "start_session", prompt, model });
    },
    [send]
  );

  const sendMessage = useCallback(
    (content: string) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "user",
          content: [{ type: "text", text: content }],
          timestamp: Date.now(),
        },
      ]);
      setIsProcessing(true);
      send({ type: "send_message", content });
    },
    [send]
  );

  const approveToolUse = useCallback(
    (requestId: string, input: Record<string, unknown>) => {
      send({
        type: "tool_response",
        response: {
          type: "control_response",
          response: {
            subtype: "success",
            request_id: requestId,
            response: {
              behavior: "allow",
              updatedInput: input,
            },
          },
        },
      });
      setPendingApprovals((prev) => prev.filter((a) => a.request_id !== requestId));
    },
    [send]
  );

  const denyToolUse = useCallback(
    (requestId: string) => {
      send({
        type: "tool_response",
        response: {
          type: "control_response",
          response: {
            subtype: "success",
            request_id: requestId,
            response: {
              behavior: "deny",
              message: "User denied this tool use",
            },
          },
        },
      });
      setPendingApprovals((prev) => prev.filter((a) => a.request_id !== requestId));
    },
    [send]
  );

  const interrupt = useCallback(() => {
    send({ type: "interrupt" });
  }, [send]);

  return {
    status,
    metadata,
    messages,
    pendingApprovals,
    error,
    isProcessing,
    startSession,
    sendMessage,
    approveToolUse,
    denyToolUse,
    interrupt,
  };
}
