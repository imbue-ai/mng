import { useState } from "react";
import { MarkdownContent } from "~/components/MarkdownContent";
import type {
  ContentBlock,
  DisplayMessage,
  ToolResultContentBlock,
  ToolUseContentBlock,
} from "~/types";
import { isTextBlock, isThinkingBlock, isToolResultBlock, isToolUseBlock } from "~/types";

interface MessageViewProps {
  message: DisplayMessage;
}

const roleLabels: Record<string, string> = {
  user: "You",
  assistant: "Claude",
  system: "System",
  result: "Result",
};

const roleBgColors: Record<string, string> = {
  user: "var(--user-bg)",
  assistant: "var(--assistant-bg)",
  system: "var(--bg-tertiary)",
  result: "var(--result-bg)",
};

export const MessageView = ({ message }: MessageViewProps) => {
  // Group content blocks: text blocks together, tool use/result pairs together
  const groups = groupContentBlocks(message.content);

  return (
    <div
      style={{
        marginBottom: "16px",
        padding: "12px 16px",
        backgroundColor: roleBgColors[message.role] || "var(--bg-secondary)",
        borderRadius: "8px",
        border: "1px solid var(--border)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "8px",
        }}
      >
        <span
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: message.role === "user" ? "var(--accent)" : "var(--text-secondary)",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
          }}
        >
          {roleLabels[message.role] || message.role}
        </span>
        {message.isStreaming && (
          <span
            style={{
              fontSize: "11px",
              color: "var(--warning)",
              animation: "pulse 1.5s infinite",
            }}
          >
            streaming...
          </span>
        )}
        {message.cost !== undefined && message.cost > 0 && (
          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
            ${message.cost.toFixed(4)}
          </span>
        )}
        {message.duration_ms !== undefined && message.duration_ms > 0 && (
          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
            {(message.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
      </div>

      {groups.map((group, i) => (
        <ContentGroup key={i} blocks={group} />
      ))}
    </div>
  );
};

interface ContentGroupProps {
  blocks: ContentBlock[];
}

const ContentGroup = ({ blocks }: ContentGroupProps) => {
  if (blocks.length === 0) return null;

  const first = blocks[0];

  if (isTextBlock(first)) {
    // Render all consecutive text blocks together
    const text = blocks
      .filter(isTextBlock)
      .map((b) => b.text)
      .join("\n");
    return <MarkdownContent text={text} />;
  }

  if (isThinkingBlock(first)) {
    return <ThinkingDisplay text={first.thinking} />;
  }

  if (isToolUseBlock(first)) {
    // Render tool use blocks (possibly with their results paired)
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {blocks.map((block, i) => {
          if (isToolUseBlock(block)) {
            // Look for a matching result in the remaining blocks
            const result = blocks.find(
              (b) => isToolResultBlock(b) && b.tool_use_id === block.id
            ) as ToolResultContentBlock | undefined;
            return <ToolUseDisplay key={i} tool={block} result={result} />;
          }
          // Skip standalone tool results (they're paired above)
          if (isToolResultBlock(block)) return null;
          return null;
        })}
      </div>
    );
  }

  if (isToolResultBlock(first)) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {blocks.filter(isToolResultBlock).map((block, i) => (
          <ToolResultDisplay key={i} result={block} />
        ))}
      </div>
    );
  }

  return null;
};

const ThinkingDisplay = ({ text }: { text: string }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div
      style={{
        margin: "4px 0",
        border: "1px solid var(--border)",
        borderRadius: "6px",
        overflow: "hidden",
      }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: "100%",
          padding: "6px 12px",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          backgroundColor: "rgba(251, 191, 36, 0.05)",
          border: "none",
          color: "var(--warning)",
          fontSize: "12px",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span>{isOpen ? "v" : ">"}</span>
        Thinking
      </button>
      {isOpen && (
        <div
          style={{
            padding: "8px 12px",
            fontSize: "13px",
            color: "var(--text-secondary)",
            backgroundColor: "rgba(251, 191, 36, 0.02)",
            whiteSpace: "pre-wrap",
          }}
        >
          {text}
        </div>
      )}
    </div>
  );
};

interface ToolUseDisplayProps {
  tool: ToolUseContentBlock;
  result?: ToolResultContentBlock;
}

const TOOL_DISPLAY_NAMES: Record<string, string> = {
  Bash: "Running command",
  Read: "Reading file",
  Write: "Writing file",
  Edit: "Editing file",
  Glob: "Searching files",
  Grep: "Searching content",
  Task: "Running task",
  WebSearch: "Searching web",
  WebFetch: "Fetching URL",
};

const ToolUseDisplay = ({ tool, result }: ToolUseDisplayProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const displayName = TOOL_DISPLAY_NAMES[tool.name] || tool.name;
  const preview = getToolPreview(tool);
  const hasError = result?.is_error === true;

  return (
    <div
      style={{
        margin: "4px 0",
        border: "1px solid var(--border)",
        borderRadius: "6px",
        overflow: "hidden",
      }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: "100%",
          padding: "8px 12px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          backgroundColor: "var(--tool-bg)",
          border: "none",
          color: "var(--text-primary)",
          fontSize: "13px",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
          {isOpen ? "v" : ">"}
        </span>
        <span style={{ fontWeight: 500 }}>{displayName}</span>
        {preview && (
          <span
            style={{
              color: "var(--text-muted)",
              fontSize: "12px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              flex: 1,
            }}
          >
            {preview}
          </span>
        )}
        {result && (
          <span
            style={{
              fontSize: "11px",
              color: hasError ? "var(--error)" : "var(--success)",
              marginLeft: "auto",
              flexShrink: 0,
            }}
          >
            {hasError ? "error" : "done"}
          </span>
        )}
      </button>

      {isOpen && (
        <div style={{ borderTop: "1px solid var(--border)" }}>
          <div
            style={{
              padding: "8px 12px",
              backgroundColor: "var(--code-bg)",
              fontSize: "12px",
            }}
          >
            <div style={{ color: "var(--text-muted)", marginBottom: "4px" }}>Input:</div>
            <pre
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: "12px",
              }}
            >
              {JSON.stringify(tool.input, null, 2)}
            </pre>
          </div>

          {result && (
            <div
              style={{
                padding: "8px 12px",
                backgroundColor: hasError
                  ? "rgba(248, 113, 113, 0.05)"
                  : "rgba(74, 222, 128, 0.05)",
                borderTop: "1px solid var(--border)",
                fontSize: "12px",
              }}
            >
              <div
                style={{
                  color: hasError ? "var(--error)" : "var(--success)",
                  marginBottom: "4px",
                }}
              >
                {hasError ? "Error:" : "Output:"}
              </div>
              <pre
                style={{
                  margin: 0,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontSize: "12px",
                  maxHeight: "300px",
                  overflow: "auto",
                }}
              >
                {result.content}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const ToolResultDisplay = ({ result }: { result: ToolResultContentBlock }) => {
  const [isOpen, setIsOpen] = useState(false);
  const hasError = result.is_error === true;

  return (
    <div
      style={{
        margin: "4px 0",
        border: "1px solid var(--border)",
        borderRadius: "6px",
        overflow: "hidden",
      }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: "100%",
          padding: "6px 12px",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          backgroundColor: hasError
            ? "rgba(248, 113, 113, 0.05)"
            : "rgba(74, 222, 128, 0.05)",
          border: "none",
          color: hasError ? "var(--error)" : "var(--success)",
          fontSize: "12px",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span>{isOpen ? "v" : ">"}</span>
        Tool Result {hasError ? "(error)" : ""}
      </button>
      {isOpen && (
        <div
          style={{
            padding: "8px 12px",
            fontSize: "12px",
            maxHeight: "300px",
            overflow: "auto",
          }}
        >
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {result.content}
          </pre>
        </div>
      )}
    </div>
  );
};

function getToolPreview(tool: ToolUseContentBlock): string {
  const input = tool.input;
  switch (tool.name) {
    case "Bash":
      return typeof input.command === "string" ? input.command : "";
    case "Read":
      return typeof input.file_path === "string" ? input.file_path : "";
    case "Write":
      return typeof input.file_path === "string" ? input.file_path : "";
    case "Edit":
      return typeof input.file_path === "string" ? input.file_path : "";
    case "Glob":
      return typeof input.pattern === "string" ? input.pattern : "";
    case "Grep":
      return typeof input.pattern === "string" ? input.pattern : "";
    case "WebSearch":
      return typeof input.query === "string" ? input.query : "";
    case "WebFetch":
      return typeof input.url === "string" ? input.url : "";
    default:
      return "";
  }
}

function groupContentBlocks(blocks: ContentBlock[]): ContentBlock[][] {
  const groups: ContentBlock[][] = [];
  let currentGroup: ContentBlock[] = [];
  let currentType: string | null = null;

  for (const block of blocks) {
    const blockCategory = getBlockCategory(block);

    if (blockCategory !== currentType && currentGroup.length > 0) {
      groups.push(currentGroup);
      currentGroup = [];
    }

    currentGroup.push(block);
    currentType = blockCategory;
  }

  if (currentGroup.length > 0) {
    groups.push(currentGroup);
  }

  return groups;
}

function getBlockCategory(block: ContentBlock): string {
  if (isTextBlock(block)) return "text";
  if (isThinkingBlock(block)) return "thinking";
  if (isToolUseBlock(block) || isToolResultBlock(block)) return "tool";
  return "other";
}
