import React, { useEffect, useRef, useState, useCallback } from "react";

/**
 * EquityChart — Robinhood-style equity curve
 * - Large portfolio value header that updates on hover
 * - Single clean line, Y-axis on right only
 * - Drawdown zone: red fill between peak line and equity line
 * - Trade dots: green = win, red = loss
 * - Range buttons: 1D / 1W / 1M / ALL
 * - Tooltip shows value + time + trade on hover
 */
export default function EquityChart({ curve, trades = [], T, compact = false }) {
  const canvasRef  = useRef(null);
  const chartRef   = useRef(null);
  const builtRef   = useRef(false);
  const [range,    setRange]    = useState("ALL");
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const headerRef  = useRef(null);
  const pnlRef     = useRef(null);
  const tradeRef   = useRef(null);

  // ── Data helpers ───────────────────────────────────────────────
  const getSlice = useCallback((r) => {
    if (!curve || curve.length < 2) return curve || [];
    const now     = new Date(curve[curve.length - 1].t);
    const cutoffs = { "1D": 1, "1W": 7, "1M": 30, "ALL": 9999 };
    const days    = cutoffs[r] || 9999;
    const cutoff  = new Date(now); cutoff.setDate(cutoff.getDate() - days);
    const sliced  = curve.filter(p => new Date(p.t) >= cutoff);
    return sliced.length >= 2 ? sliced : curve;
  }, [curve]);

  const fmtVal  = v => "$" + Math.round(v).toLocaleString("en-US");
  const fmtPnl  = (diff, base) => {
    const pct = base > 0 ? ((diff / base) * 100).toFixed(2) : "0.00";
    const sign = diff >= 0 ? "+" : "";
    return `${diff >= 0 ? "▲" : "▼"} ${sign}$${Math.abs(Math.round(diff)).toLocaleString()} (${sign}${pct}%)`;
  };

  // ── Build / rebuild chart ──────────────────────────────────────
  const buildChart = useCallback((r) => {
    if (!canvasRef.current) return;
    if (typeof window.Chart !== "function") return;

    const data   = getSlice(r);
    if (!data || data.length < 2) return;

    // Normalized: base = $1M for ALL, first point for other ranges
    const BASE_EQUITY = 1_000_000;
    const absVals  = data.map(p => p.v);
    const baseVal  = r === "ALL" ? BASE_EQUITY : absVals[0];
    const vals     = absVals.map(v => v - baseVal);  // P&L delta, zero-centered

    const labels = data.map(p => {
      const d = new Date(p.t);
      if (r === "ALL" || r === "1M") {
        return d.toLocaleString("en-US", {
          timeZone: "America/New_York",
          month: "short", day: "numeric"
        });
      }
      return d.toLocaleString("en-US", {
        timeZone: "America/New_York",
        month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit"
      });
    });

    // Trade dots mapped to curve indices — use normalized values
    const winPts  = new Array(data.length).fill(null);
    const lossPts = new Array(data.length).fill(null);
    const tradeMap = {};

    trades.forEach(tr => {
      if (!tr.exit_time) return;
      const te = new Date(tr.exit_time).getTime();
      let nearIdx = 0, nearDiff = Infinity;
      data.forEach((pt, i) => {
        const d = Math.abs(new Date(pt.t).getTime() - te);
        if (d < nearDiff) { nearDiff = d; nearIdx = i; }
      });
      if (nearDiff > 900000) return;
      if (tr.pnl >= 0) winPts[nearIdx]  = vals[nearIdx];
      else             lossPts[nearIdx] = vals[nearIdx];
      if (!tradeMap[nearIdx]) tradeMap[nearIdx] = [];
      tradeMap[nearIdx].push(tr);
    });

    // Destroy old
    if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }

    const isDark  = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const textCol = isDark ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.22)";
    const gridCol = isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)";

    // Split fill: green above zero, red below — computed AFTER yAxis so we can clamp
    // Temporarily compute axis range first
    const _validVals0 = vals.filter(v => v != null);
    const _pnlMax0    = Math.max(..._validVals0, 0);
    const _pnlMin0    = Math.min(..._validVals0, 0);
    const _spread0    = Math.max(_pnlMax0 - _pnlMin0, 200);
    const _pad0       = _spread0 * 0.20;
    const _yMin0      = _pnlMin0 - _pad0;
    const _yMax0      = _pnlMax0 + _pad0;
    const greenFill   = vals.map(v => v == null ? null : Math.min(Math.max(v, 0), _yMax0));
    const redFill     = vals.map(v => v == null ? null : Math.max(Math.min(v, 0), _yMin0));

    // Y axis range — tight fit with 20% padding, NOT symmetric
    // This keeps the line filling the chart regardless of all-time vs daily scale
    const _validVals = vals.filter(v => v != null);
    const _pnlMax    = Math.max(..._validVals, 0);
    const _pnlMin    = Math.min(..._validVals, 0);
    const _spread    = Math.max(_pnlMax - _pnlMin, 200);
    const _pad       = _spread * 0.20;
    const yAxisMin   = _pnlMin - _pad;
    const yAxisMax   = _pnlMax + _pad;

    // Crosshair plugin — draws vertical line at hover point
    const crosshairPlugin = {
      id: "crosshair",
      afterDraw(chart) {
        if (!chart._lastEvent) return;
        const {ctx, chartArea:{top,bottom,left,right}} = chart;
        const x = chart._lastEvent.x;
        if (x < left || x > right) return;

        // Find nearest label
        const xScale = chart.scales.x;
        const idx = xScale.getValueForPixel(x);
        const label = chart.data.labels[Math.round(idx)] || "";

        ctx.save();

        // Crosshair line — bold white
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.lineWidth = 2;
        ctx.strokeStyle = isDark ? "rgba(255,255,255,0.85)" : "rgba(0,0,0,0.6)";
        ctx.setLineDash([]);
        ctx.stroke();

        // Date/time label above the line
        if (label) {
          const pad = 6;
          ctx.font = "500 11px sans-serif";
          const tw = ctx.measureText(label).width;
          const bx = Math.min(Math.max(x - tw/2 - pad, left), right - tw - pad*2);
          const by = top;

          // Background pill
          ctx.fillStyle = isDark ? "rgba(40,40,40,0.92)" : "rgba(255,255,255,0.92)";
          ctx.beginPath();
          ctx.roundRect(bx, by, tw + pad*2, 20, 4);
          ctx.fill();

          // Border
          ctx.strokeStyle = isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.12)";
          ctx.lineWidth = 0.5;
          ctx.setLineDash([]);
          ctx.stroke();

          // Text
          ctx.fillStyle = isDark ? "rgba(255,255,255,0.9)" : "rgba(0,0,0,0.8)";
          ctx.fillText(label, bx + pad, by + 14);
        }

        ctx.restore();
      },
      beforeEvent(chart, args) {
        chart._lastEvent = args.event.type === "mouseleave" ? null : args.event;
      }
    };

    chartRef.current = new window.Chart(canvasRef.current, {
      type: "line",
      plugins: [crosshairPlugin],
      data: {
        labels,
        datasets: [
          // Green fill — above zero
          {
            label: "_GreenFill",
            data: greenFill,
            borderWidth: 0,
            pointRadius: 0,
            fill: "origin",
            backgroundColor: isDark
              ? "rgba(29,158,117,0.18)"
              : "rgba(29,158,117,0.12)",
            tension: 0.3,
            order: 5,
          },
          // Red fill — below zero
          {
            label: "_RedFill",
            data: redFill,
            borderWidth: 0,
            pointRadius: 0,
            fill: "origin",
            backgroundColor: isDark
              ? "rgba(226,75,74,0.18)"
              : "rgba(226,75,74,0.12)",
            tension: 0.3,
            order: 5,
          },
          // Main P&L line — color based on current value
          {
            label: "Equity",
            data: vals,
            borderColor: vals[vals.length-1] >= 0 ? "#1D9E75" : "#E24B4A",
            borderWidth: 2,
            pointRadius: 0,
            fill: false,
            tension: 0.3,
            order: 3,
          },
          // Win dots
          {
            label: "Win",
            data: winPts,
            type: "scatter",
            pointRadius: compact ? 5 : 8,
            pointHoverRadius: compact ? 8 : 12,
            pointBackgroundColor: "#1D9E75",
            pointBorderColor: isDark ? "#111" : "#fff",
            pointBorderWidth: 1.5,
            order: 1,
          },
          // Loss dots
          {
            label: "Loss",
            data: lossPts,
            type: "scatter",
            pointRadius: compact ? 5 : 8,
            pointHoverRadius: compact ? 8 : 12,
            pointBackgroundColor: "#E24B4A",
            pointBorderColor: isDark ? "#111" : "#fff",
            pointBorderWidth: 1.5,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        interaction: { mode: "index", intersect: false },
        onHover: (evt) => {
          if (evt.native) evt.native.target.style.cursor = "crosshair";
        },
        plugins: {
          legend: { display: false },
          crosshair: {},
          tooltip: {
            enabled: false,
            external: (ctx) => {
              const hEl = document.getElementById('eq-header-val');
              const pEl = document.getElementById('eq-header-pnl');
              const tEl = document.getElementById('eq-header-trade');

              const liveVal  = absVals[absVals.length-1];
              const liveDelta = liveVal - baseVal;
              const livePct2  = baseVal > 0 ? ((liveDelta/baseVal)*100).toFixed(2) : "0.00";
              const liveSign2 = liveDelta >= 0 ? "+" : "";
              if (ctx.tooltip.opacity === 0) {
                if (hEl) hEl.textContent = "$" + Math.round(liveVal).toLocaleString("en-US");
                if (pEl) { pEl.textContent = (liveDelta>=0?"▲":"▼") + " " + liveSign2 + "$" + Math.abs(Math.round(liveDelta)).toLocaleString("en-US") + " (" + liveSign2 + livePct2 + "%)"; pEl.style.color = liveDelta >= 0 ? "#1D9E75" : "#E24B4A"; }
                if (tEl) tEl.innerHTML = "";
                return;
              }
              const pt = ctx.tooltip.dataPoints?.find(p => p.dataset.label === "Equity");
              if (!pt) return;
              const delta = pt.parsed.y;  // already normalized P&L
              const absV  = absVals[pt.dataIndex] || (baseVal + delta);
              const pct   = baseVal > 0 ? ((delta/baseVal)*100).toFixed(2) : "0.00";
              const sign  = delta >= 0 ? "+" : "";
              if (hEl) hEl.textContent = "$" + Math.round(absV).toLocaleString("en-US");
              if (pEl) { pEl.textContent = (delta>=0?"▲":"▼") + " " + sign + "$" + Math.abs(Math.round(delta)).toLocaleString("en-US") + " (" + sign + pct + "%)"; pEl.style.color = delta >= 0 ? "#1D9E75" : "#E24B4A"; }
              // Trade info
              if (tEl) {
                const trs = [
                  ...(tradeMap[pt.dataIndex-1]||[]),
                  ...(tradeMap[pt.dataIndex]||[]),
                  ...(tradeMap[pt.dataIndex+1]||[]),
                ];
                tEl.innerHTML = trs.map(tr =>
                  '<span style="font-size:10px;padding:1px 7px;border-radius:8px;font-weight:500;margin-right:4px;background:' +
                  (tr.pnl>=0?"rgba(29,158,117,0.15)":"rgba(226,75,74,0.15)") +
                  ';color:' + (tr.pnl>=0?"#1D9E75":"#E24B4A") + '">' +
                  tr.symbol + ' ' + (tr.pnl>=0?"+":"") + "$" + tr.pnl.toFixed(2) + '</span>'
                ).join("");
              }
            },
          },
        },
        scales: {
          x: {
            display: r === "ALL" || r === "1M",
            grid: { display: false },
            ticks: {
              color: textCol,
              font: { size: 9 },
              maxTicksLimit: 5,
              maxRotation: 0,
            },
            border: { display: false },
          },
          y: {
            display: true,
            position: "right",
            border: { display: false },
            grid: { color: gridCol },
            ticks: {
              color: textCol,
              font: { size: 9 },
              maxTicksLimit: compact ? 3 : 5,
              callback: v => {
                const abs = Math.abs(v);
                const fmt = abs >= 1000 ? (v>=0?"+":"−")+"$"+Math.round(abs/1000)+"k"
                                        : (v>=0?"+":"−")+"$"+Math.round(abs);
                return v === 0 ? "$0" : fmt;
              },
            },
            min: yAxisMin,
            max: yAxisMax,
          },
        },
      },
    });

    // Reset header on mouse leave
    const canvas = canvasRef.current;
    const onLeave = () => {
      const hEl = document.getElementById('eq-header-val');
      const pEl = document.getElementById('eq-header-pnl');
      const tEl = document.getElementById('eq-header-trade');
      if (!hEl || !pEl) return;
      const slice2 = getSlice(range);
      const v2 = slice2?.[slice2.length-1]?.v || 0;
      const b2 = slice2?.[0]?.v || 0;
      const d2 = v2 - b2;
      const p2 = b2 > 0 ? ((d2/b2)*100).toFixed(2) : "0.00";
      const s2 = d2 >= 0 ? "+" : "";
      hEl.textContent = "$" + Math.round(v2).toLocaleString("en-US");
      pEl.textContent = (d2>=0?"▲":"▼") + " " + s2 + "$" + Math.abs(Math.round(d2)).toLocaleString("en-US") + " (" + s2 + p2 + "%)";
      pEl.style.color = d2 >= 0 ? "#1D9E75" : "#E24B4A";
      if (tEl) tEl.innerHTML = "";
    };
    if (canvas) canvas.addEventListener("mouseleave", onLeave);

    builtRef.current = true;
  }, [getSlice, trades, compact]);

  // ── Load Chart.js ──────────────────────────────────────────────
  useEffect(() => {
    const init = () => buildChart(range);
    if (typeof window.Chart === "function") { init(); return; }
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
    s.onload = () => setTimeout(init, 30);
    document.head.appendChild(s);
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  }, []);

  // ── Rebuild only when data meaningfully changes ──────────────────
  const lastCurveKey = useRef("");
  useEffect(() => {
    if (!builtRef.current) return;
    const key = `${(curve||[]).length}-${(curve||[]).slice(-1)[0]?.v||0}-${(trades||[]).length}`;
    if (key === lastCurveKey.current) return;
    lastCurveKey.current = key;
    buildChart(range);
  }, [curve, trades, range]);

  // ── Range change ───────────────────────────────────────────────
  const handleRange = (r) => {
    setRange(r);
    // Reset header DOM to live values
    const hEl = document.getElementById('eq-header-val');
    const pEl = document.getElementById('eq-header-pnl');
    const tEl = document.getElementById('eq-header-trade');
    if (tEl) tEl.innerHTML = "";
    buildChart(r);
  };

  // ── Computed header values ─────────────────────────────────────
  const slice    = getSlice(range);
  const baseVal  = slice?.[0]?.v || 0;
  const lastVal  = slice?.[slice.length - 1]?.v || 0;
  const liveDiff = lastVal - baseVal;
  const livePct  = baseVal > 0 ? ((liveDiff / baseVal) * 100).toFixed(2) : "0.00";

  const rangeLabels = { "1D": "Today", "1W": "Past week", "1M": "Past month", "ALL": "All time" };

  const handleZoom = (direction) => {
    const chart = chartRef.current;
    if (!chart) return;
    const x     = chart.scales.x;
    const total = chart.data.labels.length;
    const curMin = x.min ?? 0;
    const curMax = x.max ?? total - 1;
    const center = Math.round((curMin + curMax) / 2);
    const range2 = curMax - curMin;
    const factor = direction === "in" ? 0.6 : 1.6;
    const newRange = Math.max(3, Math.min(total - 1, Math.round(range2 * factor)));
    const newMin   = Math.max(0, center - Math.round(newRange / 2));
    const newMax   = Math.min(total - 1, newMin + newRange);
    chart.options.scales.x.min = newMin;
    chart.options.scales.x.max = newMax;
    chart.update("active");
    setZoomLevel(direction === "in" ? zoomLevel * 1.6 : zoomLevel / 1.6);
  };

  const handleZoomReset = () => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.options.scales.x.min = undefined;
    chart.options.scales.x.max = undefined;
    chart.update("active");
    setZoomLevel(1.0);
  };

  const btnStyle = (r) => ({
    fontSize: 11, fontWeight: 500,
    padding: "3px 10px", borderRadius: 6,
    border: "none", cursor: "pointer",
    background: range === r
      ? (liveDiff >= 0 ? "rgba(29,158,117,0.15)" : "rgba(226,75,74,0.15)")
      : "transparent",
    color: range === r
      ? (liveDiff >= 0 ? "#1D9E75" : "#E24B4A")
      : T.textMuted,
  });

  if (!curve || curve.length < 2) {
    return (
      <div style={{ height: compact ? 100 : 180, display: "flex",
        alignItems: "center", justifyContent: "center",
        color: T.textMuted, fontSize: 12 }}>
        Curve appears after first completed trade
      </div>
    );
  }


  return (
    <div>
      {/* ── Header: portfolio value + P&L — updated via DOM to avoid re-render ── */}
      {!compact && (
        <div style={{ marginBottom: 10 }}>
          <div id="eq-header-val" style={{ fontSize: 22, fontWeight: 500,
            color: T.textPrimary, fontVariantNumeric: "tabular-nums",
            lineHeight: 1.1, marginBottom: 4 }}>
            {fmtVal(lastVal)}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span id="eq-header-pnl" style={{ color: liveDiff >= 0 ? "#1D9E75" : "#E24B4A", fontWeight: 500 }}>
              {liveDiff >= 0 ? "▲" : "▼"}{" "}
              {liveDiff >= 0 ? "+" : ""}${Math.abs(Math.round(liveDiff)).toLocaleString()}
              {" "}({liveDiff >= 0 ? "+" : ""}{livePct}%)
            </span>
            <span style={{ color: T.textMuted, fontSize: 11 }}>{rangeLabels[range]}</span>
          </div>
          <div id="eq-header-trade" style={{ marginTop: 4 }}/>
        </div>
      )}

      {/* ── Chart canvas ── */}
      <div style={{ position: "relative", width: "100%",
        height: compact ? 100 : 160, cursor: "crosshair" }}>
        <canvas ref={canvasRef}/>
      </div>

      {/* ── Compact trade info — shows on dot hover ── */}
      {compact && (
        <div id="eq-header-trade" style={{
          minHeight: 18, marginTop: 3,
          display:"flex", gap:5, flexWrap:"wrap"
        }}/>
      )}

      {/* ── Range buttons + zoom ── */}
      <div style={{ display: "flex", alignItems: "center",
        justifyContent: "space-between", marginTop: 8 }}>
        <div style={{ display: "flex", gap: 2 }}>
          {["1D", "1W", "1M", "ALL"].map(r => (
            <button key={r} style={btnStyle(r)} onClick={() => handleRange(r)}>{r}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 3, alignItems: "center" }}>
          <button onClick={() => handleZoom("in")} title="Zoom in"
            style={{ fontSize: 14, fontWeight: 500, width: 26, height: 26,
              borderRadius: 6, border: `0.5px solid ${T.border}`,
              background: T.bg3, color: T.textSecondary, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              lineHeight: 1 }}>+</button>
          <button onClick={() => handleZoom("out")} title="Zoom out"
            style={{ fontSize: 14, fontWeight: 500, width: 26, height: 26,
              borderRadius: 6, border: `0.5px solid ${T.border}`,
              background: T.bg3, color: T.textSecondary, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              lineHeight: 1 }}>−</button>
          <button onClick={handleZoomReset} title="Reset zoom"
            style={{ fontSize: 9, padding: "2px 7px", height: 26,
              borderRadius: 6, border: `0.5px solid ${T.border}`,
              background: T.bg3, color: T.textMuted, cursor: "pointer" }}>reset</button>
        </div>
        {!compact && (
          <div style={{ display: "flex", gap: 10, fontSize: 10, color: T.textMuted }}>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%",
                background: "#1D9E75", display: "inline-block" }}/>
              Win
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%",
                background: "#E24B4A", display: "inline-block" }}/>
              Loss
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 12, height: 8, borderRadius: 2,
                background: "rgba(226,75,74,0.25)", display: "inline-block" }}/>
              Loss zone
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 12, height: 8, borderRadius: 2,
                background: "rgba(29,158,117,0.25)", display: "inline-block" }}/>
              Gain zone
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
