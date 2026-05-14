import React, { useEffect, useRef, useState, useCallback } from "react";

export default function EquityChart({ curve, syntheticCurve = [], trades = [], T, compact = false }) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);
  const builtRef  = useRef(false);
  const [range, setRange] = useState("1D");
  const BASE_EQUITY = 1000000;

  const getSlice = useCallback((r) => {
    // Use synthetic curve for long-range views
    const src = (["ALL","1Y","YTD","3M"].includes(r) && syntheticCurve.length >= 2)
      ? syntheticCurve : curve;
    if (!src || src.length < 2) return src || [];
    const now    = new Date(src[src.length - 1].t);
    const cutoff = new Date(now);
    if      (r === "1H")  cutoff.setHours(cutoff.getHours() - 1);
    else if (r === "3H")  cutoff.setHours(cutoff.getHours() - 3);
    else if (r === "1D")  cutoff.setDate(cutoff.getDate() - 1);
    else if (r === "1W")  cutoff.setDate(cutoff.getDate() - 7);
    else if (r === "1M")  cutoff.setDate(cutoff.getDate() - 30);
    else if (r === "3M")  cutoff.setDate(cutoff.getDate() - 90);
    else if (r === "YTD") cutoff.setMonth(0, 1);
    else if (r === "1Y")  cutoff.setDate(cutoff.getDate() - 365);
    else                  cutoff.setFullYear(2000);
    const sliced = src.filter(p => new Date(p.t) >= cutoff);
    return sliced.length >= 2 ? sliced : src;
  }, [curve, syntheticCurve]);

  const fmtPnl = (v) => {
    const a = Math.abs(v);
    const s = v >= 0 ? "+" : "-";
    return s + "$" + (a >= 1000 ? (a / 1000).toFixed(1) + "k" : Math.round(a));
  };

  const buildChart = useCallback((r) => {
    if (!canvasRef.current || typeof window.Chart !== "function") return;
    const data = getSlice(r);
    if (!data || data.length < 2) return;

    const absVals  = data.map(p => p.v);
    const baseVal  = r === "ALL" ? BASE_EQUITY : absVals[0];
    const vals     = r === "ALL" ? absVals : absVals.map(v => v - baseVal);
    const lastVal  = absVals[absVals.length - 1];
    const liveDiff = lastVal - (r === "ALL" ? BASE_EQUITY : absVals[0]);
    const livePct  = baseVal > 0 ? ((liveDiff / baseVal) * 100).toFixed(2) : "0.00";
    const liveSign = liveDiff >= 0 ? "+" : "";
    const showXAxis = ["ALL", "3M", "1Y", "YTD", "1M", "1W"].includes(r);

    const labels = data.map(p => {
      const d = new Date(p.t);
      if (showXAxis) return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      if (r === "1D") {
        // Show date + time so yesterday vs today is clear
        return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + " " +
               d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
      }
      return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    });

    const winPts  = new Array(vals.length).fill(null);
    const lossPts = new Array(vals.length).fill(null);
    const tmap    = {};
    // Normalize timestamp — treat naive times as UTC
    const toMs = (s) => {
      if (!s) return 0;
      // If no timezone info, treat as UTC by appending Z
      const normalized = s.includes("+") || s.endsWith("Z") ? s : s + "Z";
      return new Date(normalized).getTime();
    };
    const sliceStart = toMs(data[0].t);
    const sliceEnd   = toMs(data[data.length - 1].t);

    trades.forEach(tr => {
      if (!tr.exit_time) return;
      const te = toMs(tr.exit_time);
      // Add 24h buffer on start so trades just before slice still show
      if (te < sliceStart - 86400000 || te > sliceEnd) return;
      let ni = 0, nd = Infinity;
      data.forEach((pt, i) => {
        const df = Math.abs(toMs(pt.t) - te);
        if (df < nd) { nd = df; ni = i; }
      });
      if (tr.pnl >= 0) winPts[ni]  = vals[ni];
      else             lossPts[ni] = vals[ni];
      if (!tmap[ni]) tmap[ni] = [];
      tmap[ni].push(tr);
    });

    // Tight fit always - line fills chart height
    const vv     = vals.filter(v => v != null);
    const vmax   = Math.max(...vv);
    const vmin   = r === "ALL" ? Math.min(...vv, BASE_EQUITY) : Math.min(...vv);
    const spread = Math.max(vmax - vmin, 500);
    // Generous padding so trends are visually obvious
    const pad    = spread * 0.30;
    const yMax   = vmax + pad;
    const yMin   = vmin - pad;

    const peakG = Math.max(...vv, 0);
    const peakL = Math.min(...vv, 0);
    const tradeCount = Object.values(tmap).reduce((s, a) => s + a.length, 0);

    const set = (id, text, color) => {
      const el = document.getElementById(id);
      if (el) { el.textContent = text; if (color) el.style.color = color; }
    };
    set("eq-header-val", "$" + Math.round(lastVal).toLocaleString("en-US"));
    set("eq-header-pnl",
      (liveDiff >= 0 ? "up" : "dn") + " " + liveSign + "$" +
      Math.abs(Math.round(liveDiff)).toLocaleString() + " (" + liveSign + livePct + "%)",
      liveDiff >= 0 ? "#1D9E75" : "#E24B4A");
    const rangeLabels = {
      "1H": "Past hour", "3H": "Past 3 hours", "1D": "Today",
      "1W": "Past week", "1M": "Past month",   "3M": "Past 3 months",
      "YTD": "Year to date", "1Y": "Past year", "ALL": "All time",
    };
    set("eq-header-range", rangeLabels[r] || r);
    set("eq-stat-gain",   fmtPnl(peakG),   "#1D9E75");
    set("eq-stat-loss",   fmtPnl(peakL),   "#E24B4A");
    set("eq-stat-trades", String(tradeCount || "--"));
    set("eq-stat-net",    fmtPnl(liveDiff), liveDiff >= 0 ? "#1D9E75" : "#E24B4A");

    if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; }

    const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

    // ALL: no fill, just the line. Others: green/red split fill around zero.
    const baseline  = r === "ALL" ? BASE_EQUITY : 0;
    const greenFill = r === "ALL"
      ? new Array(vals.length).fill(null)
      : vals.map(v => v >= 0 ? Math.min(v, yMax) : 0);
    const redFill = r === "ALL"
      ? new Array(vals.length).fill(null)
      : vals.map(v => v < 0 ? Math.max(v, yMin) : 0);

    const xhairPlugin = {
      id: "xhair",
      afterDraw(chart) {
        if (!chart._lx) return;
        const { ctx, chartArea: { top, bottom, left, right } } = chart;
        if (chart._lx < left || chart._lx > right) return;
        ctx.save();
        ctx.beginPath(); ctx.moveTo(chart._lx, top); ctx.lineTo(chart._lx, bottom);
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = isDark ? "rgba(255,255,255,0.75)" : "rgba(0,0,0,0.5)";
        ctx.setLineDash([]); ctx.stroke();
        const idx   = Math.round(chart.scales.x.getValueForPixel(chart._lx));
        const label = chart.data.labels[Math.max(0, Math.min(idx, chart.data.labels.length - 1))] || "";
        if (label) {
          const pad2 = 6;
          ctx.font = "500 10px sans-serif";
          const tw = ctx.measureText(label).width;
          const bx = Math.min(Math.max(chart._lx - tw / 2 - pad2, left), right - tw - pad2 * 2);
          const by = top - 2;
          ctx.fillStyle = isDark ? "rgba(40,40,40,0.92)" : "rgba(255,255,255,0.92)";
          ctx.beginPath(); ctx.roundRect(bx, by, tw + pad2 * 2, 20, 4); ctx.fill();
          ctx.strokeStyle = isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.12)";
          ctx.lineWidth = 0.5; ctx.stroke();
          ctx.fillStyle = isDark ? "rgba(255,255,255,0.9)" : "rgba(0,0,0,0.8)";
          ctx.fillText(label, bx + pad2, by + 14);
        }
        ctx.restore();
      },
      beforeEvent(chart, args) {
        if (args.event.type === "mouseleave") chart._lx = null;
        else chart._lx = args.event.x;
      }
    };

    const baselinePlugin = {
      id: "baseline",
      afterDraw(chart) {
        const { ctx, chartArea: { left, right }, scales: { y } } = chart;
        const bv = r === "ALL" ? BASE_EQUITY : 0;
        const z  = y.getPixelForValue(bv);
        if (z < chart.chartArea.top || z > chart.chartArea.bottom) return;
        ctx.save();
        ctx.beginPath(); ctx.moveTo(left, z); ctx.lineTo(right, z);
        ctx.lineWidth = 1;
        ctx.strokeStyle = isDark ? "rgba(255,255,255,0.30)" : "rgba(0,0,0,0.20)";
        ctx.setLineDash([5, 5]); ctx.stroke();
        ctx.font = "500 9px sans-serif";
        ctx.fillStyle = isDark ? "rgba(255,255,255,0.35)" : "rgba(0,0,0,0.30)";
        ctx.setLineDash([]);
        ctx.fillText(r === "ALL" ? "$1M start" : "start", left + 4, z - 4);
        ctx.restore();
      }
    };

    chartRef.current = new window.Chart(canvasRef.current, {
      type: "line",
      plugins: [xhairPlugin, baselinePlugin],
      data: {
        labels,
        datasets: [
          {
            label: "_GF",
            data: greenFill,
            borderWidth: 0, pointRadius: 0,
            fill: "origin",
            backgroundColor: isDark ? "rgba(29,158,117,0.18)" : "rgba(29,158,117,0.13)",
            tension: 0.3, order: 5,
          },
          {
            label: "_RF",
            data: redFill,
            borderWidth: 0, pointRadius: 0,
            fill: "origin",
            backgroundColor: isDark ? "rgba(226,75,74,0.22)" : "rgba(226,75,74,0.15)",
            tension: 0.3, order: 5,
          },
          {
            label: "Equity",
            data: vals,
            borderColor: "#1D9E75",
            borderWidth: r === "ALL" ? 2 : 2, pointRadius: 0,
            fill: false, tension: 0.4, order: 3,
          },
          {
            label: "Win",
            data: winPts,
            type: "scatter",
            pointRadius: compact ? 5 : 7,
            pointHoverRadius: compact ? 8 : 10,
            pointBackgroundColor: "#1D9E75",
            pointBorderColor: isDark ? "#111" : "#fff",
            pointBorderWidth: 1.5, order: 1,
          },
          {
            label: "Loss",
            data: lossPts,
            type: "scatter",
            pointRadius: compact ? 5 : 7,
            pointHoverRadius: compact ? 8 : 10,
            pointBackgroundColor: "#E24B4A",
            pointBorderColor: isDark ? "#111" : "#fff",
            pointBorderWidth: 1.5, order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          xhair: {}, baseline: {},
          tooltip: {
            enabled: false,
            external: (ctx) => {
              const tEl = document.getElementById("eq-header-trade");
              if (ctx.tooltip.opacity === 0) {
                set("eq-header-val", "$" + Math.round(lastVal).toLocaleString("en-US"));
                set("eq-header-pnl",
                  (liveDiff >= 0 ? "up" : "dn") + " " + liveSign + "$" +
                  Math.abs(Math.round(liveDiff)).toLocaleString() + " (" + liveSign + livePct + "%)",
                  liveDiff >= 0 ? "#1D9E75" : "#E24B4A");
                if (tEl) tEl.innerHTML = "";
                return;
              }
              const pt = ctx.tooltip.dataPoints && ctx.tooltip.dataPoints.find(p => p.dataset.label === "Equity");
              if (!pt) return;
              const delta = r === "ALL" ? pt.parsed.y - BASE_EQUITY : pt.parsed.y;
              const absV  = r === "ALL" ? pt.parsed.y : absVals[pt.dataIndex] || (baseVal + delta);
              const d2    = baseVal > 0 ? ((delta / baseVal) * 100).toFixed(2) : "0.00";
              const s2    = delta >= 0 ? "+" : "";
              set("eq-header-val", "$" + Math.round(absV).toLocaleString("en-US"));
              set("eq-header-pnl",
                (delta >= 0 ? "up" : "dn") + " " + s2 + "$" +
                Math.abs(Math.round(delta)).toLocaleString() + " (" + s2 + d2 + "%)",
                delta >= 0 ? "#1D9E75" : "#E24B4A");
              if (tEl) {
                const nearby = []
                  .concat(tmap[pt.dataIndex - 1] || [])
                  .concat(tmap[pt.dataIndex]     || [])
                  .concat(tmap[pt.dataIndex + 1] || []);
                tEl.innerHTML = nearby.map(tr =>
                  "<span style=\"font-size:10px;padding:2px 8px;border-radius:8px;" +
                  "font-weight:500;margin-right:3px;" +
                  "background:" + (tr.pnl >= 0 ? "rgba(29,158,117,0.15)" : "rgba(226,75,74,0.15)") + ";" +
                  "color:" + (tr.pnl >= 0 ? "#1D9E75" : "#E24B4A") + "\">" +
                  tr.symbol + " " + (tr.pnl >= 0 ? "+" : "") + "$" + tr.pnl.toFixed(2) + "</span>"
                ).join("");
              }
            },
          },
        },
        scales: {
          x: {
            display: showXAxis,
            grid: { display: false },
            ticks: {
              color: isDark ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.22)",
              font: { size: 9 },
              maxTicksLimit: 5,
              maxRotation: 0,
            },
            border: { display: false },
          },
          y: { display: false, min: yMin, max: yMax },
        },
      },
    });

    // Pan listeners
    const canvas = canvasRef.current;
    let panStart = null, panMinStart = null, panMaxStart = null;
    const onMouseDown = (e) => {
      const c = chartRef.current; if (!c) return;
      const x = c.scales.x, total = c.data.labels.length;
      panStart    = e.clientX;
      panMinStart = x.min != null ? x.min : 0;
      panMaxStart = x.max != null ? x.max : total - 1;
      canvas.style.cursor = "grabbing";
    };
    const onMouseMove = (e) => {
      if (panStart == null) return;
      const c = chartRef.current; if (!c) return;
      const total = c.data.labels.length;
      const span  = panMaxStart - panMinStart;
      const pxPerPt = c.chartArea.width / Math.max(span, 1);
      const shift = Math.round((panStart - e.clientX) / pxPerPt);
      if (shift === 0) return;
      let newMin = panMinStart + shift;
      let newMax = panMaxStart + shift;
      if (newMin < 0)        { newMax -= newMin; newMin = 0; }
      if (newMax > total -1) { newMin -= (newMax - (total - 1)); newMax = total - 1; }
      c.options.scales.x.min = Math.max(0, Math.round(newMin));
      c.options.scales.x.max = Math.min(total - 1, Math.round(newMax));
      c.update("none");
    };
    const onMouseUp = () => {
      panStart = null; panMinStart = null; panMaxStart = null;
      if (canvas) canvas.style.cursor = "crosshair";
    };
    if (canvas) {
      canvas.addEventListener("mousedown", onMouseDown);
      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup",   onMouseUp);
      canvas._panCleanup = () => {
        canvas.removeEventListener("mousedown", onMouseDown);
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup",   onMouseUp);
      };
    }
    builtRef.current = true;
  }, [getSlice, trades, compact, T]);

  useEffect(() => {
    const init = () => buildChart(range);
    if (typeof window.Chart === "function") { init(); return; }
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
    s.onload = () => setTimeout(init, 30);
    document.head.appendChild(s);
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  }, []);

  const lastKey = useRef("");
  useEffect(() => {
    if (!builtRef.current) return;
    const key = (curve || []).length + "-" + ((curve || []).slice(-1)[0] || {}).v + "-" + (trades || []).length;
    if (key === lastKey.current) return;
    lastKey.current = key;
    buildChart(range);
  }, [curve, trades, range, buildChart]);

  const handleRange = (r) => { setRange(r); buildChart(r); };

  const handleZoom = (dir) => {
    const chart = chartRef.current; if (!chart) return;
    const x = chart.scales.x, total = chart.data.labels.length;
    const curMin = x.min != null ? x.min : 0;
    const curMax = x.max != null ? x.max : total - 1;
    const center = Math.round((curMin + curMax) / 2);
    const newSpan = Math.max(3, Math.min(total - 1, Math.round((curMax - curMin) * (dir === "in" ? 0.6 : 1.6))));
    chart.options.scales.x.min = Math.max(0, center - Math.round(newSpan / 2));
    chart.options.scales.x.max = Math.min(total - 1, chart.options.scales.x.min + newSpan);
    chart.update("active");
  };

  const handleZoomReset = () => {
    const chart = chartRef.current; if (!chart) return;
    chart.options.scales.x.min = undefined;
    chart.options.scales.x.max = undefined;
    chart.update("active");
  };

  const slice    = getSlice(range);
  const baseVal2 = range === "ALL" ? BASE_EQUITY : (slice && slice[0] ? slice[0].v : 0);
  const lastVal2 = slice && slice.length ? slice[slice.length - 1].v : 0;
  const liveDiff2 = lastVal2 - baseVal2;
  const livePct2  = baseVal2 > 0 ? ((liveDiff2 / baseVal2) * 100).toFixed(2) : "0.00";

  const btnStyle = (r) => ({
    fontSize: 10, fontWeight: 500, padding: "3px 8px", borderRadius: 20,
    border: "none", cursor: "pointer",
    background: range === r
      ? (liveDiff2 >= 0 ? "rgba(29,158,117,0.15)" : "rgba(226,75,74,0.15)")
      : "transparent",
    color: range === r
      ? (liveDiff2 >= 0 ? "#1D9E75" : "#E24B4A")
      : T.textMuted,
  });

  const zbStyle = {
    fontSize: 13, fontWeight: 500, width: 24, height: 24, borderRadius: 6,
    border: "0.5px solid " + T.border, background: T.bg3,
    color: T.textSecondary, cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center",
  };

  if (!curve || curve.length < 2) {
    return (
      React.createElement("div", {
        style: { height: compact ? 100 : 180, display: "flex",
          alignItems: "center", justifyContent: "center",
          color: T.textMuted, fontSize: 12 }
      }, "Curve appears after first completed trade")
    );
  }

  return (
    React.createElement("div", null,

      !compact && React.createElement("div", { style: { marginBottom: 8 } },
        React.createElement("div", {
          id: "eq-header-val",
          style: { fontSize: 22, fontWeight: 500, color: T.textPrimary,
            fontVariantNumeric: "tabular-nums", lineHeight: 1.1, marginBottom: 3 }
        }, "$" + Math.round(lastVal2).toLocaleString("en-US")),
        React.createElement("div", { style: { display: "flex", alignItems: "center", gap: 8, marginBottom: 2 } },
          React.createElement("span", {
            id: "eq-header-pnl",
            style: { fontSize: 13, fontWeight: 500, color: liveDiff2 >= 0 ? "#1D9E75" : "#E24B4A" }
          }, (liveDiff2 >= 0 ? "up " : "dn ") + (liveDiff2 >= 0 ? "+" : "") +
             "$" + Math.abs(Math.round(liveDiff2)).toLocaleString() +
             " (" + (liveDiff2 >= 0 ? "+" : "") + livePct2 + "%)"),
          React.createElement("span", {
            id: "eq-header-range",
            style: { fontSize: 11, color: T.textMuted }
          }, "All time")
        ),
        React.createElement("div", {
          id: "eq-header-trade",
          style: { minHeight: 18, display: "flex", gap: 5, flexWrap: "wrap" }
        })
      ),

      React.createElement("div", {
        style: { position: "relative", width: "100%",
          height: compact ? 100 : 180, cursor: "crosshair" }
      }, React.createElement("canvas", { ref: canvasRef })),

      !compact && React.createElement("div", {
        style: { display: "flex", justifyContent: "space-between",
          alignItems: "center", marginTop: 4 }
      },
        React.createElement("div", { style: { display: "flex", gap: 10, fontSize: 10, color: T.textMuted } },
          React.createElement("span", null,
            React.createElement("span", {
              style: { width: 7, height: 7, borderRadius: "50%", background: "#1D9E75",
                display: "inline-block", marginRight: 3 }
            }), "Win"),
          React.createElement("span", null,
            React.createElement("span", {
              style: { width: 7, height: 7, borderRadius: "50%", background: "#E24B4A",
                display: "inline-block", marginRight: 3 }
            }), "Loss")
        ),
        React.createElement("div", { style: { fontSize: 9, color: T.textMuted } }, "Drag to pan")
      ),

      !compact && React.createElement("div", {
        style: { display: "flex", gap: 0, marginTop: 10,
          borderTop: "0.5px solid " + T.border, paddingTop: 10 }
      },
        [{ id: "eq-stat-gain", label: "Peak gain" },
         { id: "eq-stat-loss", label: "Peak loss" },
         { id: "eq-stat-trades", label: "Trades" },
         { id: "eq-stat-net", label: "Net P&L" }]
        .map((s, i, arr) =>
          React.createElement("div", {
            key: s.id,
            style: { flex: 1, textAlign: "center",
              borderRight: i < arr.length - 1 ? "0.5px solid " + T.border : "none" }
          },
            React.createElement("div", {
              style: { fontSize: 9, color: T.textMuted, marginBottom: 2 }
            }, s.label),
            React.createElement("div", {
              id: s.id,
              style: { fontSize: 12, fontWeight: 500, color: T.textPrimary,
                fontVariantNumeric: "tabular-nums" }
            }, "--")
          )
        )
      ),

      React.createElement("div", {
        style: { display: "flex", alignItems: "center", justifyContent: "space-between",
          marginTop: 10, flexWrap: "wrap", gap: 4 }
      },
        React.createElement("div", { style: { display: "flex", gap: 2, flexWrap: "wrap" } },
          ["1H","3H","1D","1W","1M","3M","YTD","1Y","ALL"].map(r =>
            React.createElement("button", {
              key: r, style: btnStyle(r), onClick: () => handleRange(r)
            }, r)
          )
        ),
        React.createElement("div", { style: { display: "flex", gap: 3, alignItems: "center" } },
          React.createElement("button", { onClick: () => handleZoom("in"),  style: zbStyle }, "+"),
          React.createElement("button", { onClick: () => handleZoom("out"), style: zbStyle }, "-"),
          React.createElement("button", {
            onClick: handleZoomReset,
            style: { fontSize: 9, padding: "2px 7px", height: 24, borderRadius: 6,
              border: "0.5px solid " + T.border, background: T.bg3,
              color: T.textMuted, cursor: "pointer" }
          }, "reset")
        )
      )
    )
  );
}
