import type { ConnectionStatus, SessionMetadata } from "~/types";

interface HeaderProps {
  status: ConnectionStatus;
  metadata: SessionMetadata | null;
  isProcessing: boolean;
  onInterrupt: () => void;
}

const statusLabels: Record<ConnectionStatus, string> = {
  disconnected: "Disconnected",
  connecting: "Connecting...",
  connected: "Connected",
  session_active: "Session Active",
};

const statusColors: Record<ConnectionStatus, string> = {
  disconnected: "var(--error)",
  connecting: "var(--warning)",
  connected: "var(--success)",
  session_active: "var(--success)",
};

export const Header = ({ status, metadata, isProcessing, onInterrupt }: HeaderProps) => {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 20px",
        backgroundColor: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <h1
          style={{
            fontSize: "16px",
            fontWeight: 600,
            color: "var(--text-primary)",
          }}
        >
          Claude HTTP
        </h1>

        {metadata && (
          <span
            style={{
              fontSize: "12px",
              color: "var(--text-muted)",
              backgroundColor: "var(--bg-tertiary)",
              padding: "2px 8px",
              borderRadius: "4px",
            }}
          >
            {metadata.model}
          </span>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        {isProcessing && (
          <button
            onClick={onInterrupt}
            style={{
              padding: "4px 12px",
              fontSize: "12px",
              backgroundColor: "transparent",
              color: "var(--error)",
              border: "1px solid var(--error)",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Stop
          </button>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              backgroundColor: statusColors[status],
            }}
          />
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
            {statusLabels[status]}
          </span>
        </div>
      </div>
    </header>
  );
};
