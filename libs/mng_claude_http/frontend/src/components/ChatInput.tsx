import { useCallback, useRef, useState } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
  isProcessing: boolean;
}

export const ChatInput = ({ onSend, disabled, isProcessing }: ChatInputProps) => {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setText("");
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  }, [text, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    // Auto-resize
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, []);

  return (
    <div
      style={{
        padding: "12px 16px",
        borderTop: "1px solid var(--border)",
        backgroundColor: "var(--bg-secondary)",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          maxWidth: "800px",
          margin: "0 auto",
          display: "flex",
          gap: "8px",
          alignItems: "flex-end",
        }}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={
            disabled
              ? "Waiting for connection..."
              : isProcessing
              ? "Claude is working... (you can still send messages)"
              : "Send a message to Claude Code..."
          }
          rows={1}
          style={{
            flex: 1,
            padding: "10px 14px",
            fontSize: "14px",
            lineHeight: "1.5",
            backgroundColor: "var(--bg-input)",
            color: "var(--text-primary)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            resize: "none",
            outline: "none",
            fontFamily: "inherit",
            minHeight: "42px",
          }}
        />

        <button
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
          style={{
            padding: "10px 20px",
            fontSize: "14px",
            fontWeight: 500,
            backgroundColor:
              disabled || !text.trim() ? "var(--bg-tertiary)" : "var(--accent)",
            color:
              disabled || !text.trim() ? "var(--text-muted)" : "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: disabled || !text.trim() ? "not-allowed" : "pointer",
            minHeight: "42px",
            transition: "background-color 0.15s",
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
};
