import { Box, Flex, ScrollArea, Text } from "@radix-ui/themes";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatInput } from "~/components/ChatInput";
import { Header } from "~/components/Header";
import { Message } from "~/components/Message";
import type { ParsedMessage, SessionMetadata, SSEEvent } from "~/types";
import { isTextBlock } from "~/types";

import styles from "./App.module.scss";

/**
 * Check if a message contains only tool blocks (no text).
 */
function isToolOnlyMessage(message: ParsedMessage): boolean {
  if (message.role !== "assistant") return false;
  return message.content.length > 0 && message.content.every((b) => !isTextBlock(b));
}

/**
 * Merge consecutive tool-only assistant messages into single messages.
 * This groups multiple tool calls that happen in sequence without intervening text.
 */
function mergeConsecutiveToolMessages(messages: ParsedMessage[]): ParsedMessage[] {
  const result: ParsedMessage[] = [];

  for (const message of messages) {
    const lastMessage = result[result.length - 1];

    // If current is tool-only assistant and previous was also tool-only assistant, merge
    if (lastMessage && isToolOnlyMessage(message) && isToolOnlyMessage(lastMessage)) {
      // Merge content blocks into the previous message
      lastMessage.content = [...lastMessage.content, ...message.content];
    } else {
      // Add as new message (make a copy to avoid mutating original)
      result.push({
        ...message,
        content: [...message.content],
      });
    }
  }

  return result;
}

export const App = () => {
  const [messages, setMessages] = useState<ParsedMessage[]>([]);
  const [metadata, setMetadata] = useState<SessionMetadata | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    const eventSource = new EventSource("/api/sse");
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    eventSource.onmessage = (event) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);

        switch (data.type) {
          case "init":
            setMetadata(data.metadata);
            setMessages(data.messages);
            break;

          case "message":
            setMessages((prev) => [...prev, data.message]);
            break;

          case "complete":
            // Session complete - could show summary
            break;

          case "error":
            setError(data.error);
            break;
        }
      } catch (e) {
        console.error("Failed to parse SSE event:", e);
      }
    };

    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();

      // Attempt reconnect after delay
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect();
      }, 3000);
    };
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      eventSourceRef.current?.close();
    };
  }, [connect]);

  // Merge consecutive tool-only assistant messages for cleaner display
  const displayMessages = useMemo(() => mergeConsecutiveToolMessages(messages), [messages]);

  // Auto-scroll to bottom on new messages (and initial load)
  useEffect(() => {
    // Defer to next event loop tick to ensure content is rendered
    const timeoutId = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "instant" });
    }, 0);
    return () => clearTimeout(timeoutId);
  }, [displayMessages]);

  return (
    <Flex direction="column" className={styles.app}>
      <Header metadata={metadata} isConnected={isConnected} />

      {error && (
        <Box className={styles.errorBanner} px="4" py="2">
          <Text color="red" size="2">
            {error}
          </Text>
        </Box>
      )}

      <ScrollArea ref={scrollRef} className={styles.messageContainer} scrollbars="vertical">
        <Flex direction="column" className={styles.messageList}>
          {displayMessages.length === 0 && !error && (
            <Box py="8">
              <Text color="gray" align="center" as="p">
                {isConnected ? "No messages yet..." : "Connecting..."}
              </Text>
            </Box>
          )}
          {displayMessages.map((message, index) => (
            <Message
              key={message.id || index}
              message={message}
              isStreaming={index === displayMessages.length - 1}
            />
          ))}
          <div ref={bottomRef} />
        </Flex>
      </ScrollArea>

      <ChatInput disabled={!isConnected} />
    </Flex>
  );
};
