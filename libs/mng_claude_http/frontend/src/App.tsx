import { useCallback, useEffect, useRef, useState } from "react";
import { ChatInput } from "~/components/ChatInput";
import { Header } from "~/components/Header";
import { MessageView } from "~/components/MessageView";
import { ToolApprovalBanner } from "~/components/ToolApprovalBanner";
import { useClaudeSession } from "~/hooks/useClaudeSession";

export const App = () => {
  const {
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
  } = useClaudeSession();

  const bottomRef = useRef<HTMLDivElement>(null);
  const [hasSession, setHasSession] = useState(false);

  const handleSend = useCallback(
    (text: string) => {
      if (!hasSession) {
        startSession(text);
        setHasSession(true);
      } else {
        sendMessage(text);
      }
    },
    [hasSession, startSession, sendMessage]
  );

  // Auto-scroll on new messages
  useEffect(() => {
    const timeout = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 50);
    return () => clearTimeout(timeout);
  }, [messages]);

  const canSend = status === "connected" || status === "session_active";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      <Header
        status={status}
        metadata={metadata}
        isProcessing={isProcessing}
        onInterrupt={interrupt}
      />

      {error && (
        <div
          style={{
            padding: "8px 16px",
            backgroundColor: "rgba(248, 113, 113, 0.1)",
            borderBottom: "1px solid var(--error)",
            color: "var(--error)",
            fontSize: "14px",
          }}
        >
          {error}
        </div>
      )}

      {pendingApprovals.length > 0 && (
        <ToolApprovalBanner
          approvals={pendingApprovals}
          onApprove={approveToolUse}
          onDeny={denyToolUse}
        />
      )}

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px",
        }}
      >
        <div style={{ maxWidth: "800px", margin: "0 auto" }}>
          {messages.length === 0 && !error && (
            <div
              style={{
                textAlign: "center",
                color: "var(--text-muted)",
                padding: "80px 20px",
              }}
            >
              {status === "disconnected" || status === "connecting" ? (
                <p>Connecting to server...</p>
              ) : (
                <>
                  <h2 style={{ marginBottom: "8px", color: "var(--text-secondary)" }}>
                    Claude HTTP
                  </h2>
                  <p>Send a message to start a session with Claude Code.</p>
                </>
              )}
            </div>
          )}

          {messages.map((msg) => (
            <MessageView key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      <ChatInput onSend={handleSend} disabled={!canSend} isProcessing={isProcessing} />
    </div>
  );
};
