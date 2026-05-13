import React, { useEffect, useRef, useState } from "react";

/**
 * EquityChart — shared zoomable equity + drawdown
 * Uses Chart.js loaded once. Data updates without rebuilding chart.
 * Zoom state persists across live data refreshes.
 */
export default function EquityChart({ curve, trades = [], T, compact = false }) {
  const eqRef   = useRef(null);
  const ddRef   = useRef(null);
  const built   = useRef(false);      // chart built flag
  const zoomRef = useRef({ min: undefined, max: undefined });
  const [selRange, setSelRange] = useState("all");

  // ── Helpers ───────────────────────────────────────────────────────
  const getCharts = () => {
    if (!window.Chart?.instances) return { eq: null, dd: null };
    const all = Object.values(window.Chart.instances);
    return {
      eq: all.find(c => c.canvas === eqRef.current)  || null,
      dd: all.find(c => c.canvas === ddRef.current)  || null,
    };
  };

  const syncZoom = (mn, mx) => {
    const { dd } = getCharts();
    if (!dd) return;
    dd.options.scales.x.min = mn;
    dd.options.scales.x.max = mx;
    dd.update("none");
  };

  const applyZoom = (mn, mx) => {
    const { eq, dd } = getCharts();
    zoomRef.current = { min: mn, max: mx };
    if (eq) { eq.options.scales.x.min = mn; eq.options.scales.x.max = mx; eq.update("active"); }
    if (dd) { dd.options.scales.x.min = mn; dd.options.scales.x.max = mx; dd.update("active"); }
  };

  const resetZoom = () => {
    applyZoom(undefined, undefined);
    setSelRange("all");
  };

  // ── Load Chart.js once ────────────────────────────────────────────
  useEffect(() => {
    if (typeof window.Chart === "function") { initChart(); return; }
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
    s.onload = () => setTimeout(initChart, 30);
    document.head.appendChild(s);
  }, []);

  // ── Update data when curve/trades change (NO rebuild) ────────────
  useEffect(() => {
    if (!built.current) return;   // not built yet — skip
    if (!curve || curve.length < 2) return;
    const { eq, dd } = getCharts();
    if (!eq || !dd) { built.current = false; initChart(); return; }

    const vals  = curve.map(p => Math.round(p.v));
    const ddPct = curve.map(p => parseFloat((-p.dd * 100).toFixed(2)));
    const labels = makeLabels(curve);
    const { winPts, losePts } = makeTradePoints(curve, trades);

    // Update equity chart data
    eq.data.labels = labels;
    eq.data.datasets[0].data = vals;
    if (trades.length && eq.data.datasets[1]) {
      eq.data.datasets[1].data = winPts;
      eq.data.datasets[2].data = losePts;
    }
    // Update Y range
    const { yMin, yMax } = smartYRange(vals);
    eq.options.scales.y.min = yMin;
    eq.options.scales.y.max = yMax;

    // Restore zoom
    if (zoomRef.current.min !== undefined) {
      eq.options.scales.x.min = zoomRef.current.min;
      eq.options.scales.x.max = zoomRef.current.max;
    }
    eq.update("none");

    // Update drawdown chart
    dd.data.labels = labels;
    dd.data.datasets[0].data = ddPct;
    dd.data.datasets[0].backgroundColor = ddPct.map(d => d < -20 ? "#E24B4A" : "#F09595");
    if (zoomRef.current.min !== undefined) {
      dd.options.scales.x.min = zoomRef.current.min;
      dd.options.scales.x.max = zoomRef.current.max;
    }
    dd.update("none");
  }, [curve, trades]);

  // ── Build chart (once) ───────────────────────────────────────────
  function initChart() {
    if (!eqRef.current || !ddRef.current) return;
    if (!curve || curve.length < 2) return;
    if (typeof window.Chart !== "function") return;

    // Destroy existing
    const { eq: oldEq, dd: oldDd } = getCharts();
    oldEq?.destroy(); oldDd?.destroy();

    const vals   = curve.map(p => Math.round(p.v));
    const ddPct  = curve.map(p => parseFloat((-p.dd * 100).toFixed(2)));
    const labels = makeLabels(curve);
    const { winPts, losePts } = makeTradePoints(curve, trades);
    const { yMin, yMax } = smartYRange(vals);

    const isDark  = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const textCol = isDark ? "rgba(255,255,255,0.35)" : "rgba(0,0,0,0.28)";
    const gridCol = isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)";
    const fmtK    = v => "$" + (v >= 1000 ? Math.round(v/1000)+"k" : Math.round(v));
    const tip = {
      backgroundColor: isDark?"#2a2a2a":"#fff",
      borderColor: isDark?"rgba(255,255,255,0.1)":"rgba(0,0,0,0.1)",
      borderWidth:1, titleColor:isDark?"#fff":"#000",
      bodyColor:isDark?"rgba(255,255,255,0.65)":"rgba(0,0,0,0.65)", padding:8
    };
    const base = { grid:{color:gridCol}, ticks:{color:textCol, font:{size:compact?9:10}, maxTicksLimit:5} };

    const datasets = [{
      label:"Equity", data:vals, borderColor:"#185FA5", borderWidth:2,
      pointRadius:0, fill:true,
      backgroundColor:isDark?"rgba(24,95,165,0.12)":"rgba(24,95,165,0.07)",
      tension:0.25, order:3
    }];
    if (trades.length) {
      datasets.push({
        label:"Win", data:winPts, type:"scatter",
        pointRadius:compact?5:7, pointHoverRadius:compact?7:10,
        pointBackgroundColor:"#1D9E75",
        pointBorderColor:isDark?"#1a1a1a":"#fff", pointBorderWidth:1.5, order:1
      });
      datasets.push({
        label:"Loss", data:losePts, type:"scatter",
        pointRadius:compact?5:7, pointHoverRadius:compact?7:10,
        pointBackgroundColor:"#E24B4A",
        pointBorderColor:isDark?"#1a1a1a":"#fff", pointBorderWidth:1.5, order:1
      });
    }

    new window.Chart(eqRef.current, {
      type:"line", data:{labels, datasets},
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        plugins:{
          legend:{display:false},
          tooltip:{...tip, callbacks:{
          title: ctx => labels[ctx[0]?.dataIndex] || "",
          label: ctx => " $" + ctx.parsed.y.toLocaleString()
        }}
        },
        scales:{
          x:{...base, display:false,
            min: zoomRef.current.min, max: zoomRef.current.max},
          y:{...base, min:yMin, max:yMax, ticks:{...base.ticks, callback:v=>fmtK(v)}}
        }
      }
    });

    new window.Chart(ddRef.current, {
      type:"bar",
      data:{labels, datasets:[{
        label:"Drawdown", data:ddPct,
        backgroundColor:ddPct.map(d=>d<-20?"#E24B4A":"#F09595"),
        borderWidth:0, barPercentage:1.0, categoryPercentage:1.0
      }]},
      options:{
        responsive:true, maintainAspectRatio:false, animation:false,
        plugins:{legend:{display:false}, tooltip:{...tip, callbacks:{label:ctx=>" "+ctx.parsed.y.toFixed(1)+"%"}}},
        scales:{
          x:{...base, ticks:{...base.ticks, maxTicksLimit:4},
            min:zoomRef.current.min, max:zoomRef.current.max},
          y:{...base, max:0, ticks:{...base.ticks, callback:v=>v+"%", maxTicksLimit:3}}
        }
      }
    });

    // ── Native wheel zoom ────────────────────────────────────────
    const canvas = eqRef.current;
    const onWheel = e => {
      e.preventDefault();
      const { eq } = getCharts(); if (!eq) return;
      const x = eq.scales.x;
      const tot = vals.length;
      const curMin = x.min ?? 0;
      const curMax = x.max ?? tot-1;
      const range  = curMax - curMin;
      const factor = e.deltaY < 0 ? 0.75 : 1.33;
      const center = Math.round((curMin+curMax)/2);
      const newRange = Math.max(5, Math.min(tot, Math.round(range*factor)));
      const newMin   = Math.max(0, center - Math.round(newRange/2));
      const newMax   = Math.min(tot-1, newMin+newRange);
      applyZoom(newMin, newMax);
    };

    let dragStart = null, dragMinAtStart = 0;
    const onDown = e => { dragStart=e.clientX; const {eq}=getCharts(); dragMinAtStart=eq?.scales?.x?.min??0; };
    const onMove = e => {
      if (dragStart===null) return;
      const {eq}=getCharts(); if(!eq) return;
      const x=eq.scales.x;
      const pxPer = (x.right-x.left)/Math.max(1,((x.max??vals.length-1)-(x.min??0)));
      const delta = Math.round((dragStart-e.clientX)/pxPer);
      const range = (x.max??vals.length-1)-(x.min??0);
      const mn    = Math.max(0, Math.min(vals.length-range-1, dragMinAtStart+delta));
      applyZoom(mn, mn+range);
    };
    const onUp = () => { dragStart=null; };
    const onDbl = () => resetZoom();

    canvas.addEventListener("wheel", onWheel, {passive:false});
    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mouseup", onUp);
    canvas.addEventListener("dblclick", onDbl);

    built.current = true;
  }

  // ── Helpers ───────────────────────────────────────────────────────
  const makeLabels = c => c.map(p =>
    new Date(p.t).toLocaleTimeString("en-US",{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit",timeZone:"America/New_York"})
  );

  const makeTradePoints = (c, t) => {
    const winPts  = new Array(c.length).fill(null);
    const losePts = new Array(c.length).fill(null);
    if (!t || !t.length) return { winPts, losePts };

    const curveStart = new Date(c[0].t).getTime();
    const curveEnd   = new Date(c[c.length - 1].t).getTime();

    // Aggregate trades per curve index
    const winMap  = {};
    const lossMap = {};

    t.forEach(tr => {
      if (!tr.exit_time) return;
      const te = new Date(tr.exit_time).getTime();
      if (te < curveStart - 60000 || te > curveEnd + 300000) return;

      // Find nearest curve point
      let nearestIdx = 0, nearestDiff = Infinity;
      c.forEach((pt, i) => {
        const d = Math.abs(new Date(pt.t).getTime() - te);
        if (d < nearestDiff) { nearestDiff = d; nearestIdx = i; }
      });
      if (nearestDiff > 600000) return;

      const map = tr.pnl >= 0 ? winMap : lossMap;
      if (!map[nearestIdx]) map[nearestIdx] = { total: 0, count: 0, trades: [], v: c[nearestIdx].v };
      map[nearestIdx].total  += tr.pnl;
      map[nearestIdx].count  += 1;
      map[nearestIdx].trades.push(`${tr.symbol} ${tr.pnl >= 0 ? "+" : ""}$${tr.pnl.toFixed(2)}`);
    });

    // Flatten to per-index arrays
    Object.entries(winMap).forEach(([i, d]) => { winPts[+i]  = d.v; });
    Object.entries(lossMap).forEach(([i, d]) => { losePts[+i] = d.v; });

    // Store aggregated data on window for tooltip access
    window._tradeWinMap  = winMap;
    window._tradeLossMap = lossMap;

    return { winPts, losePts };
  };

  const smartYRange = vals => {
    const sorted=[...vals].sort((a,b)=>a-b);
    const median=sorted[Math.floor(sorted.length/2)];
    const maxVal=Math.max(...vals);
    const recent=maxVal>median*3?vals.slice(Math.floor(vals.length*0.4)):vals;
    return { yMin:Math.floor(Math.min(...recent)*0.995), yMax:Math.ceil(Math.max(...recent)*1.005) };
  };

  // ── Range buttons ─────────────────────────────────────────────────
  const applyRange = r => {
    setSelRange(r);
    if (!curve?.length) return;
    if (r==="all") { resetZoom(); return; }
    const today  = new Date().toLocaleDateString("en-US",{timeZone:"America/New_York"});
    const etD    = curve.map(p=>new Date(p.t).toLocaleDateString("en-US",{timeZone:"America/New_York"}));
    const idxs   = etD.reduce((a,d,i)=>{if(d===today)a.push(i);return a;},[]);
    if (!idxs.length) return;
    const etH = curve.map(p=>parseInt(new Date(p.t).toLocaleTimeString("en-US",{hour:"2-digit",hour12:false,timeZone:"America/New_York"})));
    let sel = idxs;
    if (r==="morning")   sel=idxs.filter(i=>etH[i]<12);
    if (r==="afternoon") sel=idxs.filter(i=>etH[i]>=12);
    if (!sel.length) return;
    applyZoom(sel[0], sel[sel.length-1]);
  };

  // ── Cleanup ───────────────────────────────────────────────────────
  useEffect(() => () => {
    const {eq,dd}=getCharts(); eq?.destroy(); dd?.destroy(); built.current=false;
  }, []);

  if (!curve || curve.length < 2) {
    return <div style={{height:compact?100:180,display:"flex",alignItems:"center",justifyContent:"center",color:T.textMuted,fontSize:12}}>
      Equity curve appears after first completed trade
    </div>;
  }

  const rBtn = r => ({
    fontSize:compact?10:11, padding:compact?"3px 8px":"4px 12px",
    borderRadius:6, cursor:"pointer",
    border:`0.5px solid ${selRange===r?"#185FA5":T.border}`,
    background:selRange===r?"rgba(24,95,165,0.1)":T.bg3,
    color:selRange===r?"#185FA5":T.textMuted,
    fontWeight:selRange===r?500:400
  });
  const totLen = curve.length;

  return (
    <div>
      {/* Toolbar */}
      <div style={{display:"flex",gap:5,marginBottom:8,alignItems:"center",flexWrap:"wrap"}}>
        {!compact && <>
          <button style={rBtn(null)} onClick={()=>{const {eq}=getCharts();if(!eq)return;const x=eq.scales.x;const tot=totLen;const c=Math.round(((x.min??0)+(x.max??tot-1))/2);const r=Math.max(5,Math.round(((x.max??tot-1)-(x.min??0))*0.65));const mn=Math.max(0,c-Math.round(r/2));applyZoom(mn,Math.min(tot-1,mn+r));}}>+ Zoom in</button>
          <button style={rBtn(null)} onClick={()=>{const {eq}=getCharts();if(!eq)return;const x=eq.scales.x;const tot=totLen;const c=Math.round(((x.min??0)+(x.max??tot-1))/2);const r=Math.min(tot,Math.round(((x.max??tot-1)-(x.min??0))*1.4));const mn=Math.max(0,c-Math.round(r/2));applyZoom(mn,Math.min(tot-1,mn+r));}}>− Zoom out</button>
          <button style={rBtn(null)} onClick={resetZoom}>Reset</button>
          <div style={{width:1,height:14,background:T.border}}/>
        </>}
        {["all","today","morning","afternoon"].map(r=>(
          <button key={r} style={rBtn(r)} onClick={()=>applyRange(r)}>
            {r.charAt(0).toUpperCase()+r.slice(1)}
          </button>
        ))}
        <span style={{fontSize:9,color:T.textMuted,marginLeft:"auto"}}>Scroll · drag · dbl-click reset</span>
      </div>

      {/* Equity panel */}
      <div style={{position:"relative",width:"100%",height:compact?130:240,cursor:"crosshair"}}>
        <canvas ref={eqRef}/>
      </div>

      {/* Drawdown label */}
      <div style={{fontSize:9,color:T.textMuted,textTransform:"uppercase",letterSpacing:".04em",marginTop:5,marginBottom:2}}>Drawdown</div>

      {/* Drawdown panel */}
      <div style={{position:"relative",width:"100%",height:compact?40:80}}>
        <canvas ref={ddRef}/>
      </div>

      {/* Legend — full size only */}
      {!compact && (
        <div style={{display:"flex",gap:12,marginTop:8,fontSize:11,color:T.textMuted,flexWrap:"wrap"}}>
          {[["#185FA5","Equity",true],["#F09595","Drawdown"],["#E24B4A","Deep >20%"]].map(([color,label,line])=>(
            <span key={label} style={{display:"flex",alignItems:"center",gap:4}}>
              <span style={{width:line?18:10,height:line?2:10,borderRadius:line?1:2,background:color,display:"inline-block"}}/>
              {label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
