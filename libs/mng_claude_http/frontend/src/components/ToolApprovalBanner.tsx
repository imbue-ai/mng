import type { PendingToolApproval } from "~/types";

interface ToolApprovalBannerProps {
  approvals: PendingToolApproval[];
  onApprove: (requestId: string, input: Record<string, unknown>) => void;
  onDeny: (requestId: string) => void;
}

export const ToolApprovalBanner = ({
  approvals,
  onApprove,
  onDeny,
}: ToolApprovalBannerProps) => {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--warning)",
        backgroundColor: "rgba(251, 191, 36, 0.08)",
        flexShrink: 0,
      }}
    >
      {approvals.map((approval) => (
        <div
          key={approval.request_id}
          style={{
            padding: "10px 16px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            borderBottom: "1px solid rgba(251, 191, 36, 0.15)",
          }}
        >
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontSize: "13px",
                fontWeight: 500,
                color: "var(--warning)",
                marginBottom: "2px",
              }}
            >
              Tool approval required: {approval.tool_name}
            </div>
            {approval.description && (
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                {approval.description}
              </div>
            )}
            <div
              style={{
                fontSize: "11px",
                color: "var(--text-muted)",
                marginTop: "2px",
                maxWidth: "600px",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {JSON.stringify(approval.input).slice(0, 120)}
            </div>
          </div>

          <button
            onClick={() => onApprove(approval.request_id, approval.input)}
            style={{
              padding: "5px 14px",
              fontSize: "12px",
              fontWeight: 500,
              backgroundColor: "var(--success)",
              color: "#000",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Allow
          </button>

          <button
            onClick={() => onDeny(approval.request_id)}
            style={{
              padding: "5px 14px",
              fontSize: "12px",
              fontWeight: 500,
              backgroundColor: "transparent",
              color: "var(--error)",
              border: "1px solid var(--error)",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Deny
          </button>
        </div>
      ))}
    </div>
  );
};
