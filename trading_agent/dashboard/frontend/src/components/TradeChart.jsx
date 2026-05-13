import React, { useEffect, useRef, useState } from "react";

/**
 * TradeChart — individual trade P&L bar chart
 * Each trade = one bar (green UP for win, red DOWN for loss)
 * Cumulative P&L line overlaid
 * Only shows trades within curve time range
 */
export default function TradeChart({ trades = [], curve = [], T, compact = false }) {
  const barRef  = useRef(null);
  const barInst = useRef(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    if (typeof window.Chart === "function") { buildChart(); return; }
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
    s.onload = () => setTimeout(buildChart, 30);
    document.head.appendChild(s);
  }, [trades, filter]);

  useEffect(() => () => { barInst.current?.destroy(); }, []);

  function buildChart() {
    if (!barRef.current || typeof window.Chart !== "function") return;
    if (!trades.length) return;

    barInst.current?.destroy();

    const isDark  = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const textCol = isDark ? "rgba(255,255,255,0.38)" : "rgba(0,0,0,0.3)";
    const gridCol = isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)";

    // Filter to today or within curve range
    const curveStart = curve.length ? new Date(curve[0].t).getTime() : 0;
    const curveEnd   = curve.length ? new Date(curve[curve.length-1].t).getTime() : Infinity;
    const today      = new Date().toLocaleDateString("en-US", { timeZone: "America/New_York" });

    let filtered = trades.filter(t => {
      if (!t.exit_time) return false;
      const te = new Date(t.exit_time).getTime();
      return te >= curveStart - 600000 && te <= curveEnd + 600000;
    });

    if (filter === "wins")   filtered = filtered.filter(t => t.pnl >= 0);
    if (filter === "losses") filtered = filtered.filter(t => t.pnl < 0);

    if (!filtered.length) return;

    // Sort chronologically
    filtered.sort((a, b) => new Date(a.exit_time) - new Date(b.exit_time));

    const labels  = filtered.map(t => {
      const d = new Date(t.exit_time);
      return t.symbol + "\n" + d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZone: "America/New_York" });
    });
    const pnls = filtered.map(t => +t.pnl.toFixed(2));

    // Cumulative P&L line
    let running = 0;
    const cumulative = pnls.map(p => { running += p; return +running.toFixed(2); });

    const barColors = pnls.map(p => p >= 0
      ? (isDark ? "rgba(29,158,117,0.85)" : "rgba(29,158,117,0.8)")
      : (isDark ? "rgba(226,75,74,0.85)"  : "rgba(226,75,74,0.8)")
    );

    const tip = {
      backgroundColor: isDark ? "#2a2a2a" : "#fff",
      borderColor: isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.12)",
      borderWidth: 1, titleColor: isDark ? "#eee" : "#111",
      bodyColor: isDark ? "rgba(255,255,255,0.65)" : "rgba(0,0,0,0.6)",
      padding: 10, displayColors: false
    };

    barInst.current = new window.Chart(barRef.current, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Trade P&L",
            data: pnls,
            backgroundColor: barColors,
            borderRadius: 3,
            borderWidth: 0,
            order: 2,
            yAxisID: "yBar"
          },
          {
            label: "Cumulative",
            data: cumulative,
            type: "line",
            borderColor: "#185FA5",
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            fill: false,
            tension: 0.3,
            order: 1,
            yAxisID: "yCum"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            ...tip,
            callbacks: {
              title: ctx => {
                const t = filtered[ctx[0]?.dataIndex];
                if (!t) return "";
                return t.symbol + " — " + new Date(t.exit_time).toLocaleTimeString("en-US",
                  { hour: "2-digit", minute: "2-digit", timeZone: "America/New_York" });
              },
              label: ctx => {
                if (ctx.dataset.label === "Trade P&L") {
                  const v = ctx.parsed.y;
                  return " " + (v >= 0 ? "✓ WIN  +" : "✗ LOSS  ") + "$" + Math.abs(v).toFixed(2);
                }
                if (ctx.dataset.label === "Cumulative") {
                  return " Cumulative: " + (ctx.parsed.y >= 0 ? "+" : "") + "$" + ctx.parsed.y.toFixed(2);
                }
                return null;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { color: gridCol },
            ticks: {
              color: textCol, font: { size: 9 }, maxTicksLimit: 12,
              callback: (val, i) => filtered[i]?.symbol || ""
            }
          },
          yBar: {
            position: "left",
            grid: { color: gridCol },
            ticks: {
              color: textCol, font: { size: 9 }, maxTicksLimit: 4,
              callback: v => (v >= 0 ? "+" : "") + "$" + v.toFixed(0)
            },
            title: { display: !compact, text: "Trade P&L ($)", color: textCol, font: { size: 9 } }
          },
          yCum: {
            position: "right",
            grid: { display: false },
            ticks: {
              color: "#185FA5", font: { size: 9 }, maxTicksLimit: 4,
              callback: v => (v >= 0 ? "+" : "") + "$" + v.toFixed(0)
            },
            title: { display: !compact, text: "Cumulative ($)", color: "#185FA5", font: { size: 9 } }
          }
        }
      }
    });
  }

  if (!trades.length) {
    return (
      <div style={{ height: compact ? 80 : 160, display: "flex", alignItems: "center",
        justifyContent: "center", color: T.textMuted, fontSize: 12 }}>
        No trades yet today
      </div>
    );
  }

  const fBtn = f => ({
    fontSize: 10, padding: "3px 9px", borderRadius: 5, cursor: "pointer",
    border: `0.5px solid ${filter === f ? "#185FA5" : T.border}`,
    background: filter === f ? "rgba(24,95,165,0.1)" : T.bg3,
    color: filter === f ? "#185FA5" : T.textMuted,
    fontWeight: filter === f ? 500 : 400
  });

  // Stats
  const curveStart = curve.length ? new Date(curve[0].t).getTime() : 0;
  const curveEnd   = curve.length ? new Date(curve[curve.length-1].t).getTime() : Infinity;
  const relevant   = trades.filter(t => {
    if (!t.exit_time) return false;
    const te = new Date(t.exit_time).getTime();
    return te >= curveStart - 600000 && te <= curveEnd + 600000;
  });
  const wins   = relevant.filter(t => t.pnl >= 0);
  const losses = relevant.filter(t => t.pnl < 0);
  const total  = relevant.reduce((s, t) => s + t.pnl, 0);

  return (
    <div>
      {/* Stats row */}
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        {[
          { label: "Trades",    value: relevant.length,            color: T.textPrimary },
          { label: "Wins",      value: wins.length,                color: "#1D9E75"     },
          { label: "Losses",    value: losses.length,              color: "#E24B4A"     },
          { label: "Total P&L", value: (total >= 0 ? "+$" : "-$") + Math.abs(total).toFixed(2), color: total >= 0 ? "#1D9E75" : "#E24B4A" },
          { label: "Avg win",   value: wins.length ? "+$" + (wins.reduce((s,t) => s+t.pnl, 0)/wins.length).toFixed(2) : "—", color: "#1D9E75" },
          { label: "Avg loss",  value: losses.length ? "-$" + Math.abs(losses.reduce((s,t) => s+t.pnl, 0)/losses.length).toFixed(2) : "—", color: "#E24B4A" },
        ].map(m => (
          <div key={m.label} style={{ background: T.bg3, borderRadius: 6, padding: "6px 10px", flex: "1", minWidth: 70 }}>
            <div style={{ fontSize: 9, color: T.textMuted, textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 2 }}>{m.label}</div>
            <div style={{ fontSize: 13, fontWeight: 500, color: m.color, fontVariantNumeric: "tabular-nums" }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Filter buttons */}
      <div style={{ display: "flex", gap: 5, marginBottom: 8, alignItems: "center" }}>
        {["all", "wins", "losses"].map(f => (
          <button key={f} style={fBtn(f)} onClick={() => setFilter(f)}>
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <div style={{ display: "flex", gap: 10, marginLeft: "auto", fontSize: 10, color: T.textMuted }}>
          <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "#1D9E75", display: "inline-block" }}/>Win
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: "#E24B4A", display: "inline-block" }}/>Loss
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
            <span style={{ width: 18, height: 2, borderRadius: 1, background: "#185FA5", display: "inline-block" }}/>Cumulative
          </span>
        </div>
      </div>

      {/* Chart */}
      <div style={{ position: "relative", width: "100%", height: compact ? 140 : 200, cursor: "default" }}>
        <canvas ref={barRef} role="img" aria-label="Trade P&L bar chart with green bars for wins and red bars for losses, with a blue cumulative P&L line overlaid">
          Trade P&L bar chart.
        </canvas>
      </div>
    </div>
  );
}
