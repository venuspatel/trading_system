import { useState, useEffect, useRef, useCallback } from "react";
import { ThemeProvider, useTheme } from "./components/ThemeContext";
import ThemeSettings from "./components/ThemeSettings";
import Dashboard   from "./components/Dashboard";
import ConfigPanel from "./components/ConfigPanel";
import Positions   from "./components/Positions";
import DecisionLog from "./components/DecisionLog";
import Performance from "./components/Performance";
import NewsTab     from "./components/NewsTab";

// Dynamically pick API port based on which frontend port is running
// Port 3000 → API 8000
const _frontendPort = parseInt(window.location.port) || 3000;
const _apiPort = 8000 + (_frontendPort - 3000);
const API = `http://localhost:${_apiPort}`;

function NavIcon({ type, active, color }) {
  const c = active ? color : "#555";
  if (type==="grid")   return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="5" height="5" rx="1" fill={c}/><rect x="9" y="2" width="5" height="5" rx="1" fill={c} opacity=".4"/><rect x="2" y="9" width="5" height="5" rx="1" fill={c} opacity=".4"/><rect x="9" y="9" width="5" height="5" rx="1" fill={c} opacity=".4"/></svg>;
  if (type==="chart")  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 12L6 8L9 10L14 4" stroke={c} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>;
  if (type==="log")    return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 4h10M3 8h7M3 12h9" stroke={c} strokeWidth="1.2" strokeLinecap="round"/></svg>;
  if (type==="stats")  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2" y="9" width="3" height="5" rx="1" fill={c}/><rect x="6.5" y="6" width="3" height="8" rx="1" fill={c} opacity=".7"/><rect x="11" y="3" width="3" height="11" rx="1" fill={c} opacity=".5"/></svg>;
  if (type==="news")   return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="2" rx="1" fill={c} opacity=".9"/><rect x="2" y="7" width="9" height="1.5" rx=".75" fill={c} opacity=".7"/><rect x="2" y="11" width="10" height="1.5" rx=".75" fill={c} opacity=".5"/></svg>;
  if (type==="config") return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="2.5" stroke={c} strokeWidth="1.2"/><path d="M8 2v1.5M8 12.5V14M2 8h1.5M12.5 8H14" stroke={c} strokeWidth="1.2" strokeLinecap="round"/></svg>;
  if (type==="theme")  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5" stroke={c} strokeWidth="1.2"/><path d="M8 3v10M3 8h10" stroke={c} strokeWidth="1" strokeLinecap="round" opacity=".5"/><circle cx="8" cy="8" r="2" fill={c} opacity=".6"/></svg>;
  return null;
}

const PAGES = [
  { id:"dashboard",   icon:"grid",   label:"Dashboard" },
  { id:"positions",   icon:"chart",  label:"Positions" },
  { id:"decisions",   icon:"log",    label:"Decisions" },
  { id:"performance", icon:"stats",  label:"Performance" },
  { id:"config",      icon:"config", label:"Configure" },
  { id:"news",        icon:"news",   label:"News" },
];

function AppInner() {
  const { theme: T, fontSize, compact, newsColorScheme, FONT_SIZES } = useTheme();
  const [page,         setPage]         = useState("dashboard");
  const [state,        setState]        = useState(null);
  const [wsLive,       setWsLive]       = useState(false);
  const [events,       setEvents]       = useState([]);
  const [showSettings, setShowSettings] = useState(false);
  const wsRef = useRef(null);

  const fetchState = useCallback(async () => {
    try { const r = await fetch(`${API}/api/state`); setState(await r.json()); } catch(e) {}
  }, []);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(`ws://localhost:${_apiPort}/ws`);
      wsRef.current = ws;
      ws.onopen = () => setWsLive(true);
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type==="connected" && msg.state) setState(msg.state);
        if (msg.type==="decision") { setEvents(p=>[{...msg, ts:new Date().toLocaleTimeString()}, ...p.slice(0,49)]); fetchState(); }
        if (["status","config_updated"].includes(msg.type)) fetchState();
      };
      const ping = setInterval(() => ws.readyState===1 && ws.send("ping"), 20000);
      ws.onclose = () => { clearInterval(ping); setWsLive(false); setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
    }
    connect(); fetchState();
    const poll = setInterval(fetchState, 3000);
    return () => { clearInterval(poll); wsRef.current?.close(); };
  }, [fetchState]);

  const cmd = async (c) => {
    try {
      const res = await fetch(`${API}/api/agent/${c}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
      });
      const data = await res.json();
      console.log(`cmd ${c}:`, data);
      setTimeout(fetchState, 800);
      setTimeout(fetchState, 2000);
    } catch(e) {
      console.error(`cmd ${c} failed:`, e);
      alert(`Failed to ${c} agent: ${e.message}. Check backend is running on port 8000.`);
    }
  };

  const status    = state?.agent_status || "idle";
  const account   = state?.account || {};
  const perf      = state?.performance || {};
  const config    = state?.config || {};
  const isRunning = status === "running";
  const isPaper   = config.paper_trading !== false;
  const sc        = {running:T.profit, paused:T.warning, stopped:T.loss, idle:"#444", error:T.loss}[status]||"#444";
  const fs        = FONT_SIZES[fontSize] || 13;
  const p         = compact ? 10 : 14;

  const fmt$   = v => v!=null ? `$${Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}` : "—";
  const fmtPnl = v => v!=null ? `${v>=0?"+":""}$${Math.abs(v).toFixed(2)}` : "—";

  const btnBase = { padding:`5px ${p+8}px`, borderRadius:5, fontSize:11, fontWeight:600, border:"none", cursor:"pointer" };

  return (
    <div style={{ display:"grid", gridTemplateColumns:"52px 1fr", gridTemplateRows:"44px 1fr", height:"100vh", background:T.bg0, fontFamily:"system-ui,-apple-system,sans-serif", color:T.textPrimary, fontSize:fs }}>

      {/* Top bar */}
      <div style={{ gridColumn:"1/3", background:T.bg1, borderBottom:`1px solid ${T.border}`, display:"flex", alignItems:"center", padding:"0 14px", gap:12 }}>
        <span style={{ fontSize:13, fontWeight:600, color:T.accent, letterSpacing:".02em", marginRight:8 }}>TradeAgent</span>

        <div style={{ display:"flex", alignItems:"center", gap:5 }}>
          <div style={{ width:7, height:7, borderRadius:"50%", background:sc, boxShadow:isRunning?`0 0 5px ${sc}`:"none" }}/>
          <span style={{ fontSize:12, color:sc, textTransform:"capitalize" }}>{status}</span>
        </div>

        {isPaper && <span style={{ padding:"2px 8px", borderRadius:4, fontSize:10, fontWeight:600, background:T.warning+"22", color:T.warning, border:`1px solid ${T.warning}44` }}>PAPER</span>}

        <div style={{ width:1, height:20, background:T.border, margin:"0 4px" }}/>

        {[
          { label:"Portfolio", value:fmt$(account.portfolio_value),      color:T.textPrimary },
          { label:"Day P&L",   value:fmtPnl(state?.reporting?.day_pnl ?? account.daily_pnl), color:(state?.reporting?.day_pnl ?? account.daily_pnl)>=0?T.profit:T.loss },
          { label:"Win rate",  value:perf.win_rate!=null?`${(perf.win_rate*100).toFixed(0)}%`:"—", color:T.accent },
          { label:"Drawdown",  value:perf.max_drawdown!=null?`${(perf.max_drawdown*100).toFixed(1)}%`:"—", color:T.loss },
          { label:"Grade",     value:perf.grade||"N/A",                  color:T.signal },
          { label:"Approach",  value:config.approach||"—",               color:T.textPrimary },
        ].map(m => (
          <div key={m.label} style={{ display:"flex", flexDirection:"column" }}>
            <span style={{ fontSize:10, color:T.textMuted, lineHeight:1 }}>{m.label}</span>
            <span style={{ fontSize:13, fontWeight:500, color:m.color, fontVariantNumeric:"tabular-nums", lineHeight:1.3 }}>{m.value}</span>
          </div>
        ))}

        {/* Controls */}
        <div style={{ display:"flex", gap:6, marginLeft:"auto", alignItems:"center" }}>
          {!isRunning && <button onClick={()=>cmd("start")}  style={{...btnBase, background:T.profit, color:"#000"}}>Start</button>}
          {isRunning  && <button onClick={()=>cmd("pause")}  style={{...btnBase, background:T.bg3, color:T.textSecondary, border:`1px solid ${T.border}`}}>Pause</button>}
          {status==="paused" && <button onClick={()=>cmd("resume")} style={{...btnBase, background:T.warning, color:"#000"}}>Resume</button>}
          <button onClick={()=>cmd("stop")}  style={{...btnBase, background:T.loss+"22", color:T.loss, border:`1px solid ${T.loss}44`}}>Stop</button>
          <button onClick={()=>cmd("scan")}  style={{...btnBase, background:T.accent+"22", color:T.accent, border:`1px solid ${T.accent}44`}}>Scan now</button>

          {/* Theme settings button */}
          <div style={{ width:1, height:20, background:T.border, margin:"0 4px" }}/>
          <button onClick={()=>setShowSettings(true)}
            title="Dashboard settings"
            style={{ width:30, height:30, borderRadius:7, display:"flex", alignItems:"center", justifyContent:"center", cursor:"pointer", background:showSettings?T.accent+"22":T.bg3, border:`1px solid ${showSettings?T.accent:T.border}`, flexShrink:0 }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="2.5" stroke={showSettings?T.accent:T.textSecondary} strokeWidth="1.2"/>
              <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M11.2 4.8l1.4-1.4M3.4 12.6l1.4-1.4" stroke={showSettings?T.accent:T.textSecondary} strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div style={{ width:7, height:7, borderRadius:"50%", background:wsLive?T.profit:"#333", marginLeft:4 }} title={wsLive?"Live":"Disconnected"}/>
      </div>

      {/* Sidebar */}
      <div style={{ background:T.bg1, borderRight:`1px solid ${T.border}`, display:"flex", flexDirection:"column", alignItems:"center", padding:"10px 0", gap:4 }}>
        {PAGES.map(n => (
          <div key={n.id} onClick={()=>setPage(n.id)} title={n.label}
            style={{ width:36, height:36, borderRadius:8, display:"flex", alignItems:"center", justifyContent:"center", cursor:"pointer", background:page===n.id?T.navActive:"transparent" }}>
            <NavIcon type={n.icon} active={page===n.id} color={T.accent}/>
          </div>
        ))}
      </div>

      {/* Main content */}
      <div style={{ background:T.bg2, overflow:"auto" }}>
        {page==="dashboard"   && <Dashboard   state={state} events={events} api={API}/>}
        {page==="positions"   && <Positions   state={state}/>}
        {page==="decisions"   && <DecisionLog state={state} events={events} api={API}/>}
        {page==="performance" && <Performance state={state} api={API}/>}
        {page==="config"      && <ConfigPanel api={API} currentConfig={config} onSaved={fetchState}/>}
        {page==="news"        && <NewsTab     state={state} api={API}/>}
      </div>

      {/* Theme settings modal */}
      {showSettings && <ThemeSettings onClose={()=>setShowSettings(false)}/>}
    </div>
  );
}

export default function App() {
  return <ThemeProvider><AppInner/></ThemeProvider>;
}
