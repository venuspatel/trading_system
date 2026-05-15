// AIReviewerBadge.jsx
// Drop this into dashboard/frontend/src/components/
// Then add <AIReviewerBadge reviewer={state.ai_reviewer} /> anywhere in Dashboard.jsx

import { useState } from "react";

const STATUS_CONFIG = {
  enabled: {
    dot: "#1D9E75",
    bg: "#E1F5EE",
    border: "#9FE1CB",
    text: "#085041",
    label: "AI reviewer active",
  },
  no_credits: {
    dot: "#E24B4A",
    bg: "#FCEBEB",
    border: "#F7C1C1",
    text: "#791F1F",
    label: "Credits exhausted",
  },
  bad_model: {
    dot: "#E24B4A",
    bg: "#FCEBEB",
    border: "#F7C1C1",
    text: "#791F1F",
    label: "Bad model string",
  },
  bad_key: {
    dot: "#E24B4A",
    bg: "#FCEBEB",
    border: "#F7C1C1",
    text: "#791F1F",
    label: "Invalid API key",
  },
  error: {
    dot: "#BA7517",
    bg: "#FAEEDA",
    border: "#FAC775",
    text: "#633806",
    label: "Reviewer error",
  },
  not_configured: {
    dot: "#888780",
    bg: "#F1EFE8",
    border: "#D3D1C7",
    text: "#444441",
    label: "Not configured",
  },
  no_api_key: {
    dot: "#888780",
    bg: "#F1EFE8",
    border: "#D3D1C7",
    text: "#444441",
    label: "No API key",
  },
};

export default function AIReviewerBadge({ reviewer }) {
  const [expanded, setExpanded] = useState(false);

  // Default to not_configured if no data
  const data = reviewer || { status: "not_configured", calls_succeeded: 0, calls_failed: 0, last_error: "", model: "" };
  const cfg = STATUS_CONFIG[data.status] || STATUS_CONFIG["error"];

  const totalCalls = (data.calls_succeeded || 0) + (data.calls_failed || 0);
  const successRate = totalCalls > 0
    ? Math.round((data.calls_succeeded / totalCalls) * 100)
    : 0;

  return (
    <div style={{ display: "inline-block" }}>
      {/* Badge pill */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 10px",
          background: cfg.bg,
          border: `0.5px solid ${cfg.border}`,
          borderRadius: 20,
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        {/* Pulsing dot when enabled */}
        <span style={{ position: "relative", display: "inline-flex", width: 8, height: 8 }}>
          <span style={{
            position: "absolute",
            width: "100%", height: "100%",
            borderRadius: "50%",
            background: cfg.dot,
            opacity: data.status === "enabled" ? 0.4 : 0,
            animation: data.status === "enabled" ? "aiPulse 2s ease-in-out infinite" : "none",
          }} />
          <span style={{
            position: "relative",
            width: 8, height: 8,
            borderRadius: "50%",
            background: cfg.dot,
          }} />
        </span>
        <span style={{ fontSize: 12, fontWeight: 500, color: cfg.text }}>
          {cfg.label}
        </span>
        {data.status === "enabled" && data.calls_succeeded > 0 && (
          <span style={{ fontSize: 11, color: cfg.text, opacity: 0.7 }}>
            {data.calls_succeeded} reviewed
          </span>
        )}
        <span style={{ fontSize: 10, color: cfg.text, opacity: 0.6 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {/* Expanded detail panel */}
      {expanded && (
        <div style={{
          marginTop: 6,
          background: "var(--color-background-primary)",
          border: `0.5px solid ${cfg.border}`,
          borderRadius: 10,
          padding: "10px 14px",
          minWidth: 260,
          fontSize: 12,
        }}>
          {/* Status row */}
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ color: "var(--color-text-secondary)" }}>Status</span>
            <span style={{ fontWeight: 500, color: cfg.text }}>{data.status}</span>
          </div>

          {/* Model row */}
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ color: "var(--color-text-secondary)" }}>Model</span>
            <code style={{
              fontSize: 11,
              background: "var(--color-background-secondary)",
              padding: "1px 6px",
              borderRadius: 4,
              color: "var(--color-text-primary)",
            }}>
              {data.model || "—"}
            </code>
          </div>

          {/* Call stats */}
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
            <span style={{ color: "var(--color-text-secondary)" }}>Reviews this session</span>
            <span style={{ color: "var(--color-text-primary)" }}>
              {data.calls_succeeded} ok / {data.calls_failed} failed
            </span>
          </div>

          {/* Success rate bar */}
          {totalCalls > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span style={{ color: "var(--color-text-secondary)" }}>Success rate</span>
                <span style={{ color: "var(--color-text-primary)" }}>{successRate}%</span>
              </div>
              <div style={{ height: 4, background: "var(--color-background-secondary)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                  height: "100%",
                  width: `${successRate}%`,
                  background: successRate > 80 ? "#1D9E75" : successRate > 50 ? "#BA7517" : "#E24B4A",
                  borderRadius: 2,
                  transition: "width 0.3s",
                }} />
              </div>
            </div>
          )}

          {/* Error message if any */}
          {data.last_error && (
            <div style={{
              marginTop: 8,
              padding: "6px 8px",
              background: "#FCEBEB",
              borderRadius: 6,
              color: "#791F1F",
              fontSize: 11,
              wordBreak: "break-word",
            }}>
              {data.last_error.length > 120
                ? data.last_error.slice(0, 120) + "…"
                : data.last_error}
            </div>
          )}

          {/* Action links for non-enabled states */}
          {data.status === "no_credits" && (
            <a
              href="https://console.anthropic.com/settings/billing"
              target="_blank"
              rel="noreferrer"
              style={{
                display: "block",
                marginTop: 8,
                padding: "5px 10px",
                background: "#FCEBEB",
                border: "0.5px solid #F7C1C1",
                borderRadius: 6,
                color: "#791F1F",
                fontWeight: 500,
                textAlign: "center",
                textDecoration: "none",
                fontSize: 12,
              }}
            >
              Top up at console.anthropic.com →
            </a>
          )}
        </div>
      )}

      {/* Pulse animation */}
      <style>{`
        @keyframes aiPulse {
          0%, 100% { transform: scale(1); opacity: 0.4; }
          50% { transform: scale(2.2); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
