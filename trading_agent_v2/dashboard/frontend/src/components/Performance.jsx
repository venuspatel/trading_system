import { useState, useEffect, useRef } from "react";
import EquityChart from "./EquityChart";
import TradeChart from "./TradeChart";
import { useTheme } from "./ThemeContext";


/* ─── Main Performance Page ───────────────────────────────────────── */
export default function Performance({ state, api }) {
  const { theme: T, compact } = useTheme();
  const [perfData, setPerfData] = useState(null);
  const [filter,   setFilter]   = useState("all");

  const perf   = state?.performance || {};
  const port   = state?.portfolio   || {};

  useEffect(() => {
    const load = () => {
      fetch(`${api}/api/performance`)
        .then(r => r.json())
        .then(d => setPerfData(d))
        .catch(() => {});
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [api]);

  const trades  = perfData?.trades  || [];
  // Use state.equity_curve (same source as home — proven to render)
  // Fall back to perfData.equity if state curve is empty
  const equity  = (state?.equity_curve?.length >= 2 ? state.equity_curve : perfData?.equity) || [];
  const report  = perfData?.report  || {};
  // Use all trades from perfData (richer than state)
  const allTrades = trades.length > 0 ? trades : (state?.all_trades || state?.recent_trades || []);

  const filtered = trades.filter(t =>
    filter === "all"    ? true :
    filter === "wins"   ? t.pnl >= 0 :
    t.pnl < 0
  ).slice().reverse();

  const fmt$   = v => v != null ? `${v >= 0 ? "+" : ""}$${Math.abs(v).toFixed(2)}` : "—";
  const fmtPct = v => v != null ? `${(v * 100).toFixed(2)}%` : "—";
  const fmtTime = s => {
    if (!s) return "—";
    try { return new Date(s).toLocaleString("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
    catch { return s.substring(0, 16); }
  };

  const card = { background: T.cardBg, border: `1px solid ${T.border}`, borderRadius: 8, padding: "12px 16px", marginBottom: 10 };

  return (
    <div style={{ padding: compact ? 12 : 16 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{ fontSize: 11, color: T.textMuted, textTransform: "uppercase", letterSpacing: ".08em" }}>
          Performance
        </span>
        <span style={{ fontSize: 24, fontWeight: 500, color: perf.grade && perf.grade !== "N/A" ? T.profit : T.textMuted }}>
          {perf.grade || "N/A"}
        </span>
      </div>

      {/* Stats grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8, marginBottom: 12 }}>
        {[
          { label: "Win rate",      value: fmtPct(perf.win_rate),               color: perf.win_rate > 0.5 ? T.profit : T.accent },
          { label: "Total P&L",     value: fmt$(perf.total_pnl),                color: perf.total_pnl >= 0 ? T.profit : T.loss },
          { label: "Profit factor", value: perf.profit_factor?.toFixed(2) || "—", color: T.profit },
          { label: "Sharpe",        value: perf.sharpe_ratio?.toFixed(2) || "—",  color: T.accent },
          { label: "Total trades",  value: report.total_trades || trades.length || 0, color: T.textPrimary },
          { label: "Winners",       value: report.winners || 0,                    color: T.profit },
          { label: "Losers",        value: report.losers || 0,                     color: T.loss },
          { label: "Max drawdown",  value: fmtPct(perf.max_drawdown),           color: T.loss },
        ].map(m => (
          <div key={m.label} style={{ background: T.bg3, borderRadius: 6, padding: "8px 10px" }}>
            <div style={{ fontSize: 10, color: T.textMuted, textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 3 }}>{m.label}</div>
            <div style={{ fontSize: 15, fontWeight: 500, color: m.color, fontVariantNumeric: "tabular-nums" }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Equity curve — same mechanism as home page */}
      <div style={card}>
        <div style={{ fontSize: 10, color: T.textMuted, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 10 }}>
          Equity curve
        </div>
        {equity.length >= 2
          ? <EquityChart curve={equity} trades={allTrades} T={T} compact={false}/>
          : <div style={{height:240,display:"flex",alignItems:"center",justifyContent:"center",color:T.textMuted,fontSize:12}}>
              Curve appears after first completed trades
            </div>
        }
      </div>

      {/* Trade P&L chart */}
      <div style={card}>
        <div style={{ fontSize: 10, color: T.textMuted, textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 10 }}>
          Trade P&L — each bar = one trade
        </div>
        <TradeChart trades={allTrades} curve={equity} T={T} compact={false}/>
      </div>

      {/* Trade log */}
      <div style={card}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: T.textMuted, textTransform: "uppercase", letterSpacing: ".05em" }}>
            Completed trades
            <span style={{ marginLeft: 6, color: T.textMuted, fontWeight: 400 }}>({trades.length})</span>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {["all", "wins", "losses"].map(f => (
              <button key={f} onClick={() => setFilter(f)}
                style={{ fontSize: 10, padding: "3px 10px", borderRadius: 12, cursor: "pointer", border: "none",
                  background: filter === f ? (f === "wins" ? T.profit : f === "losses" ? T.loss : T.accent) : T.bg3,
                  color: filter === f ? "#000" : T.textMuted }}>
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div style={{ fontSize: 12, color: T.textMuted, padding: "12px 0", textAlign: "center" }}>
            {trades.length === 0 ? "No completed trades yet — agent is running" : "No trades match this filter"}
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                {["Symbol","Qty","Entry price","Entry time","Exit price","Exit time","P&L","Result","Exit reason"].map(h => (
                  <th key={h} style={{ padding: "5px 8px", textAlign: "left", fontSize: 9,
                    color: T.textMuted, textTransform: "uppercase", letterSpacing: ".04em", fontWeight: 500 }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((t, i) => {
                const won = t.pnl >= 0;
                return (
                  <tr key={i} style={{ borderBottom: `0.5px solid ${T.border}44`,
                    background: i % 2 === 0 ? "transparent" : T.bg3 + "44" }}>
                    <td style={{ padding: "7px 8px", fontWeight: 600, color: T.textPrimary }}>{t.symbol}</td>
                    <td style={{ padding: "7px 8px", color: T.textSecondary }}>{t.qty}</td>
                    <td style={{ padding: "7px 8px", color: T.textSecondary, fontVariantNumeric: "tabular-nums" }}>${t.entry_price?.toFixed(2)}</td>
                    <td style={{ padding: "7px 8px", color: T.textMuted, fontSize: 10 }}>{fmtTime(t.entry_time)}</td>
                    <td style={{ padding: "7px 8px", color: T.textSecondary, fontVariantNumeric: "tabular-nums" }}>${t.exit_price?.toFixed(2)}</td>
                    <td style={{ padding: "7px 8px", color: T.textMuted, fontSize: 10 }}>{fmtTime(t.exit_time)}</td>
                    <td style={{ padding: "7px 8px", fontWeight: 500, fontVariantNumeric: "tabular-nums", color: won ? T.profit : T.loss }}>
                      {fmt$(t.pnl)}
                      <span style={{ fontSize: 9, marginLeft: 4, opacity: .8 }}>({fmtPct(t.pnl_pct)})</span>
                    </td>
                    <td style={{ padding: "7px 8px" }}>
                      <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 10, fontWeight: 600,
                        background: won ? T.profit + "20" : T.loss + "20", color: won ? T.profit : T.loss }}>
                        {won ? "WIN" : "LOSS"}
                      </span>
                    </td>
                    <td style={{ padding: "7px 8px", color: T.textMuted, fontSize: 10, maxWidth: 180,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.exit_reason}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {trades.length > 0 && (
          <div style={{ marginTop: 10, paddingTop: 8, borderTop: `1px solid ${T.border}`,
            display: "flex", gap: 20, fontSize: 11 }}>
            <span style={{ color: T.textMuted }}>Total:</span>
            <span style={{ color: T.profit }}>{trades.filter(t => t.pnl >= 0).length} wins</span>
            <span style={{ color: T.loss }}>{trades.filter(t => t.pnl < 0).length} losses</span>
            <span style={{ fontWeight: 500, color: trades.reduce((s, t) => s + t.pnl, 0) >= 0 ? T.profit : T.loss }}>
              {fmt$(trades.reduce((s, t) => s + (t.pnl || 0), 0))} total
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
