import React, { useState, useEffect, useRef } from "react";

const _fp = parseInt(window.location.port) || 3000;
const _ap = 8000 + (_fp - 3000);
const API_BASE = `http://localhost:${_ap}`;
import { useTheme } from "./ThemeContext";

const PRESET_DEFAULTS = {
  "Conservative":    { minStrats:5, confThresh:75, portRisk:3,  maxPos:2, stopLoss:2, takeProfit:5,  dailyLoss:2, sizing:"Confidence-Scaled" },
  "Balanced":        { minStrats:3, confThresh:65, portRisk:5,  maxPos:3, stopLoss:3, takeProfit:6,  dailyLoss:3, sizing:"Confidence-Scaled" },
  "Aggressive":      { minStrats:2, confThresh:55, portRisk:10, maxPos:5, stopLoss:5, takeProfit:10, dailyLoss:5, sizing:"Kelly Criterion"    },
  "Profit Maximizer":{ minStrats:3, confThresh:65, portRisk:8,  maxPos:5, stopLoss:2, takeProfit:3,  dailyLoss:4, sizing:"Confidence-Scaled" },
  "Long Term":       { minStrats:6, confThresh:80, portRisk:5,  maxPos:4, stopLoss:7, takeProfit:20, dailyLoss:5, sizing:"Fixed Fractional"   },
};
const MOMENTUM_PICKS = {
  "Profit Maximizer": ["TSLA","NVDA","AMD","MU","AVGO","META","AMZN","ORCL"],
  "Aggressive":       ["TSLA","COIN","NVDA","AMD","PLTR","MSTR","SNAP"],
  "Balanced":         ["AAPL","NVDA","MSFT","AMZN","META","GOOGL","JPM"],
  "Conservative":     ["AAPL","MSFT","GOOGL","JPM","WMT","HD","SPY"],
  "Long Term":        ["AAPL","NVDA","MSFT","AMZN","META","GOOGL","AVGO"],
};

function Chip({ label, active, onClick, T, color }) {
  const c = color || T.accent;
  return (
    <div onClick={onClick} style={{padding:"7px 14px",borderRadius:20,fontSize:13,
      border: active ? `2px solid ${c}` : `1px solid ${T.border}`,cursor:"pointer",
      color: active ? c : T.textMuted,background: active ? c+"18" : "transparent",
      fontWeight: active ? 500 : 400,transition:"all .15s"}}>{label}</div>
  );
}

function SliderRow({ label, value, min, max, step=1, unit="", onChange, T, highlight }) {
  return (
    <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:10}}>
      <span style={{fontSize:12,color:T.textSecondary,minWidth:160}}>{label}</span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e=>onChange(Number(e.target.value))}
        style={{flex:1,accentColor:highlight?T.profit:T.accent}}/>
      <span style={{fontSize:12,fontWeight:500,color:highlight?T.profit:T.textPrimary,
        minWidth:48,textAlign:"right"}}>{value}{unit}</span>
    </div>
  );
}

function Toggle({ label, sub, checked, onChange, T }) {
  return (
    <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",
      padding:"9px 0",borderBottom:`1px solid ${T.border}`}}>
      <div>
        <div style={{fontSize:13,color:T.textPrimary}}>{label}</div>
        {sub && <div style={{fontSize:11,color:T.textMuted,marginTop:2}}>{sub}</div>}
      </div>
      <div onClick={()=>onChange(!checked)} style={{position:"relative",width:34,height:18,
        borderRadius:9,background:checked?T.profit:T.bg3,cursor:"pointer",transition:"background .2s",
        flexShrink:0,border:`1px solid ${T.border}`}}>
        <div style={{position:"absolute",top:2,left:checked?15:2,width:12,height:12,
          borderRadius:"50%",background:"#fff",transition:"left .2s"}}/>
      </div>
    </div>
  );
}

function TickerSearch({ watchlist, setWatchlist, T }) {
  const [query,   setQuery]   = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const debRef = useRef(null);

  const search = (q) => {
    if (!q) { setResults([]); return; }
    setLoading(true);
    clearTimeout(debRef.current);
    debRef.current = setTimeout(() => {
      fetch(`${API_BASE}/api/tickers/search?q=${encodeURIComponent(q.toUpperCase())}&limit=8`)
        .then(r=>r.json()).then(d=>{ setResults(d.results||[]); setLoading(false); })
        .catch(()=>setLoading(false));
    }, 150);
  };

  const add = (sym) => {
    if (!watchlist.includes(sym)) setWatchlist(w=>[...w,sym]);
    setQuery(""); setResults([]);
  };

  return (
    <div style={{position:"relative"}}>
      <div style={{display:"flex",gap:8}}>
        <div style={{flex:1,position:"relative"}}>
          <input value={query}
            onChange={e=>{setQuery(e.target.value);search(e.target.value);}}
            onFocus={()=>setFocused(true)}
            onBlur={()=>setTimeout(()=>setFocused(false),150)}
            onKeyDown={e=>{
              if(e.key==="Enter"&&query.trim()){
                results.length>0 ? add(results[0].symbol) : add(query.trim().toUpperCase());
              }
              if(e.key==="Escape"){setQuery("");setResults([]);}
            }}
            placeholder="Search ticker or company name..."
            style={{width:"100%",padding:"8px 12px",borderRadius:8,fontSize:12,
              background:T.bg3,border:`0.5px solid ${focused?T.profit+"88":T.border}`,
              color:T.textPrimary,outline:"none"}}
          />
          {loading&&<div style={{position:"absolute",right:10,top:"50%",transform:"translateY(-50%)",
            fontSize:10,color:T.textMuted}}>...</div>}
        </div>
        {query&&<button onClick={()=>{setQuery("");setResults([]);}}
          style={{fontSize:11,padding:"6px 10px",borderRadius:6,border:`0.5px solid ${T.border}`,
            background:T.bg3,color:T.textMuted,cursor:"pointer"}}>Clear</button>}
      </div>

      {focused&&results.length>0&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,marginTop:4,
          background:T.bg2,border:`0.5px solid ${T.border}`,borderRadius:8,overflow:"hidden",
          boxShadow:"0 4px 20px rgba(0,0,0,.3)"}}>
          {results.map((r,i)=>{
            const already=watchlist.includes(r.symbol);
            return(
              <div key={r.symbol} onMouseDown={()=>add(r.symbol)}
                style={{display:"flex",alignItems:"center",gap:10,padding:"9px 14px",cursor:"pointer",
                  background:i%2===0?T.bg2:T.bg3,borderBottom:`0.5px solid ${T.border}44`,opacity:already?.5:1}}
                onMouseEnter={e=>e.currentTarget.style.background=T.profit+"15"}
                onMouseLeave={e=>e.currentTarget.style.background=i%2===0?T.bg2:T.bg3}>
                <span style={{fontSize:12,fontWeight:600,color:T.profit,minWidth:52}}>{r.symbol}</span>
                <span style={{flex:1,fontSize:11,color:T.textMuted,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{r.name}</span>
                <span style={{fontSize:10,color:T.textMuted,opacity:.6}}>{r.exchange}</span>
                {already&&<span style={{fontSize:10,color:T.profit}}>✓</span>}
              </div>
            );
          })}
        </div>
      )}
      {focused&&query.length>0&&results.length===0&&!loading&&(
        <div style={{position:"absolute",top:"100%",left:0,right:0,zIndex:999,marginTop:4,
          background:T.bg2,border:`0.5px solid ${T.border}`,borderRadius:8,padding:"12px 14px",
          fontSize:11,color:T.textMuted}}>
          No results — press Enter to add "{query.toUpperCase()}" anyway
        </div>
      )}
    </div>
  );
}

function ScannerPanel({ T, api, watchlist, setWatchlist }) {
  const [scanning, setScanning] = React.useState(false);
  const [candidates, setCandidates] = React.useState([]);
  const [selected, setSelected] = React.useState([]);
  const [error, setError] = React.useState(null);

  const runScan = async () => {
    setScanning(true); setError(null); setCandidates([]); setSelected([]);
    try {
      const r = await fetch(`${api}/api/scan_stocks?top_n=15`, {method:"POST"});
      const d = await r.json();
      if (d.error) { setError(d.error); } else { setCandidates(d.candidates||[]); }
    } catch(e) { setError(e.message); }
    setScanning(false);
  };

  const toggleSelect = (sym) => {
    setSelected(s => s.includes(sym) ? s.filter(x=>x!==sym) : [...s, sym]);
  };

  const addSelected = () => {
    const toAdd = selected.filter(s => !watchlist.includes(s));
    if (toAdd.length > 0) setWatchlist(w => [...w, ...toAdd]);
    setSelected([]);
  };

  return (
    <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 16px",marginBottom:12}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
        <span style={{fontSize:11,fontWeight:500,color:T.textSecondary}}>Dynamic stock scanner</span>
        <button onClick={runScan} disabled={scanning}
          style={{fontSize:11,padding:"4px 14px",borderRadius:8,cursor:"pointer",border:"none",
            background:scanning?T.bg3:T.profit,color:scanning?T.textMuted:"#000",fontWeight:500}}>
          {scanning ? "Scanning..." : "Scan now"}
        </button>
      </div>
      <div style={{fontSize:10,color:T.textMuted,marginBottom:8}}>
        Finds top trending stocks from a universe of 40+ symbols. Score based on RSI, ADX, volume and momentum.
      </div>
      {error && <div style={{fontSize:11,color:T.loss,marginBottom:8}}>{error}</div>}
      {candidates.length > 0 && (
        <div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:4,marginBottom:8}}>
            {candidates.map(c => {
              const inList = watchlist.includes(c.symbol);
              const isSel  = selected.includes(c.symbol);
              return (
                <div key={c.symbol} onClick={()=>!inList && toggleSelect(c.symbol)}
                  style={{padding:"6px 8px",borderRadius:6,cursor:inList?"default":"pointer",
                    border:`1px solid ${isSel?T.profit:inList?T.border:T.border}`,
                    background:isSel?T.profit+"20":inList?T.bg3+"80":"transparent",
                    opacity:inList?0.5:1}}>
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                    <span style={{fontSize:11,fontWeight:600,color:T.textPrimary}}>{c.symbol}</span>
                    <span style={{fontSize:10,fontWeight:500,color:T.profit}}>{c.score.toFixed(1)}</span>
                  </div>
                  <div style={{fontSize:9,color:T.textMuted,marginTop:1}}>{c.reason||`RSI ${c.rsi} ADX ${c.adx}`}</div>
                  {inList && <div style={{fontSize:9,color:T.textMuted}}>already in list</div>}
                </div>
              );
            })}
          </div>
          {selected.length > 0 && (
            <button onClick={addSelected}
              style={{fontSize:11,padding:"5px 14px",borderRadius:8,cursor:"pointer",
                border:"none",background:T.profit,color:"#000",fontWeight:500,width:"100%"}}>
              Add {selected.length} selected to watchlist
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function ConfigPanel({ api, currentConfig, onSaved }) {
  const { theme: T } = useTheme();
  const [tab,        setTab]        = useState("strategies");
  const [approach,   setApproach]   = useState("Balanced");
  const [sizing,     setSizing]     = useState("Confidence-Scaled");
  const [portRisk,   setPortRisk]   = useState(5);
  const [maxPos,     setMaxPos]     = useState(3);
  const [stopLoss,   setStopLoss]   = useState(3);
  const [takeProfit, setTakeProfit] = useState(6);
  const [dailyLoss,  setDailyLoss]  = useState(3);
  const [minStrats,  setMinStrats]  = useState(3);
  const [confThresh, setConfThresh] = useState(65);
  const [paper,      setPaper]      = useState(true);
  const [mktHours,   setMktHours]   = useState(true);
  const [earnings,   setEarnings]   = useState(true);
  const [regime,     setRegime]     = useState(true);
  const [watchlist,  setWatchlist]  = useState(["AAPL","TSLA","NVDA","MSFT","AMZN"]);
  const [saving,     setSaving]     = useState(false);
  const [saved,      setSaved]      = useState(false);
  const [scanFreq,     setScanFreq]     = useState(10);
  const [maxTradesDay, setMaxTradesDay] = useState(10);
  const [unlimitedTrades, setUnlimitedTrades] = useState(false);
  const [maxConsecLoss,setMaxConsecLoss]= useState(3);
  const [cooldownMins, setCooldownMins] = useState(45);
  const [profitLockPct,setProfitLockPct]= useState(3);
  const [weeklyLossPct,setWeeklyLossPct]= useState(10);
  const [expandedStrat,setExpandedStrat]= useState(null);
  const loadedRef = useRef(false);

  const [flagTrailActivation,  setFlagTrailActivation]  = useState(false);
  const [flagSectorConc,       setFlagSectorConc]        = useState(false);
  const [flagDrawdownCB,       setFlagDrawdownCB]        = useState(false);
  const [flagATRStops,         setFlagATRStops]          = useState(false);
  const [flagNewsSentiment,    setFlagNewsSentiment]     = useState(false);

  useEffect(() => {
    if (!currentConfig || Object.keys(currentConfig).length===0) return;
    if (loadedRef.current) return;
    loadedRef.current = true;
    if (currentConfig.approach)               setApproach(currentConfig.approach);
    if (currentConfig.max_portfolio_risk_pct) setPortRisk(Math.round(currentConfig.max_portfolio_risk_pct*100));
    if (currentConfig.max_open_positions)     setMaxPos(currentConfig.max_open_positions);
    if (currentConfig.stop_loss_pct)          setStopLoss(Math.round(currentConfig.stop_loss_pct*100));
    if (currentConfig.take_profit_pct)        setTakeProfit(Math.round(currentConfig.take_profit_pct*100));
    if (currentConfig.daily_loss_limit_pct)   setDailyLoss(Math.round(currentConfig.daily_loss_limit_pct*100));
    if (currentConfig.min_strategies_agree)   setMinStrats(currentConfig.min_strategies_agree);
    if (currentConfig.confidence_threshold)   setConfThresh(Math.round(currentConfig.confidence_threshold*100));
    if (currentConfig.paper_trading!=null)    setPaper(currentConfig.paper_trading);
    if (currentConfig.watchlist)              setWatchlist(currentConfig.watchlist);
    if (currentConfig.feature_flags) {
      const ff = currentConfig.feature_flags;
      if (ff.trail_activation         != null) setFlagTrailActivation(ff.trail_activation);
      if (ff.sector_concentration     != null) setFlagSectorConc(ff.sector_concentration);
      if (ff.drawdown_circuit_breaker != null) setFlagDrawdownCB(ff.drawdown_circuit_breaker);
      if (ff.atr_trailing_stops       != null) setFlagATRStops(ff.atr_trailing_stops);
      if (ff.news_sentiment           != null) setFlagNewsSentiment(ff.news_sentiment);
    }
    if (currentConfig.max_trades_per_day != null) {
      if (currentConfig.max_trades_per_day >= 9999) {
        setUnlimitedTrades(true);
      } else {
        setMaxTradesDay(Math.min(currentConfig.max_trades_per_day, 50));
      }
    }
  }, [currentConfig]);

  const applyPreset = (a) => {
    setApproach(a);
    const d = PRESET_DEFAULTS[a]; if (!d) return;
    setMinStrats(d.minStrats); setConfThresh(d.confThresh); setPortRisk(d.portRisk);
    setMaxPos(d.maxPos); setStopLoss(d.stopLoss); setTakeProfit(d.takeProfit);
    setDailyLoss(d.dailyLoss); setSizing(d.sizing);
    loadedRef.current = false; // allow reload if config changes externally
    const dd={
      "Conservative":{sf:0,mt:3,ml:2,cm:120,pl:2,wl:5},
      "Balanced":{sf:30,mt:5,ml:3,cm:60,pl:3,wl:8},
      "Aggressive":{sf:30,mt:8,ml:4,cm:30,pl:5,wl:12},
      "Profit Maximizer":{sf:10,mt:10,ml:3,cm:45,pl:3,wl:10},
      "Long Term":{sf:0,mt:2,ml:2,cm:240,pl:5,wl:8}
    }[a]||{sf:60,mt:5,ml:3,cm:60,pl:3,wl:8};
    setScanFreq(dd.sf); setMaxTradesDay(dd.mt); setMaxConsecLoss(dd.ml);
    setCooldownMins(dd.cm); setProfitLockPct(dd.pl); setWeeklyLossPct(dd.wl);
  };

  const isPM = approach==="Profit Maximizer";
  const isLT = approach==="Long Term";

  const save = async () => {
    setSaving(true);
    try {
      await fetch(`${api}/api/configure`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          approach, sizing_method:sizing,
          max_portfolio_risk_pct:portRisk, max_open_positions:maxPos,
          stop_loss_pct:stopLoss, take_profit_pct:takeProfit,
          daily_loss_limit_pct:dailyLoss, min_strategies_agree:minStrats,
          confidence_threshold:confThresh/100, paper_trading:paper,
          market_hours_only:mktHours, earnings_blackout_days:earnings?3:0,
          regime_filter:regime, watchlist,
          trailing_stop:isPM, candle_exit:isPM, momentum_exit:isPM,
          max_hold_days:isPM?2:0, scan_frequency_minutes:scanFreq,
          max_trades_per_day: unlimitedTrades ? 9999 : maxTradesDay, max_consecutive_losses:maxConsecLoss,
          cooldown_minutes:cooldownMins, profit_lock_pct:profitLockPct,
          weekly_loss_limit_pct:weeklyLossPct,
          feature_flags:{
            trail_activation:         flagTrailActivation,
            sector_concentration:     flagSectorConc,
            drawdown_circuit_breaker: flagDrawdownCB,
            atr_trailing_stops:       flagATRStops,
            news_sentiment:           flagNewsSentiment,
          },
        }),
      });
      setSaved(true); onSaved?.();
      setTimeout(()=>setSaved(false),2500);
    } catch(e) { alert("Save failed: "+e.message); }
    setSaving(false);
  };

  const card = {background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"14px 16px",marginBottom:10};
  const tabStyle = (t) => ({padding:"7px 16px",borderRadius:6,fontSize:12,fontWeight:500,cursor:"pointer",border:"none",
    background:tab===t?T.accent:T.bg3,color:tab===t?"#000":T.textSecondary});

  const STRATS = [
    {name:"Momentum",type:"Trend",ind:"RSI + MACD + Volume",desc:"Buys when price momentum is accelerating with rising volume.",candle:false},
    {name:"Mean Reversion",type:"Counter-trend",ind:"Bollinger Bands + RSI",desc:"Buys when price is oversold below the lower Bollinger Band.",candle:false},
    {name:"Breakout",type:"Trend",ind:"Support/Resistance + Volume",desc:"Enters when price breaks above key resistance with a volume surge.",candle:false},
    {name:"Candle Reversal",type:"Candlestick",ind:"Hammer · Doji · Engulfing · Shooting Star",desc:"Classic reversal patterns — Hammer, Doji, Bullish/Bearish Engulfing, Shooting Star.",candle:true},
    {name:"Candle Continuation",type:"Candlestick",ind:"Marubozu · Three White Soldiers · Three Black Crows",desc:"Strong continuation patterns showing conviction in the current trend direction.",candle:true},
    {name:"Divergence",type:"Advanced",ind:"RSI Divergence + MACD Divergence",desc:"Detects when price makes new highs/lows but indicators don't confirm — early reversal signal.",candle:false},
    {name:"Fibonacci",type:"Advanced",ind:"Fibonacci Retracement Levels",desc:"Identifies entries at key Fibonacci levels (38.2%, 50%, 61.8%) within established trends.",candle:false},
    {name:"Volume Confirmation",type:"Advanced",ind:"OBV + Volume MA + Price Action",desc:"Only takes signals confirmed by above-average volume, filtering out weak moves.",candle:false},
    {name:"Multi-Timeframe",type:"Advanced",ind:"Daily + Weekly alignment",desc:"Checks that the daily signal aligns with the weekly trend. Trades only when both agree.",candle:false},
    {name:"Trend Regime",type:"Advanced",ind:"ADX + 200 SMA + Market regime",desc:"Detects whether the market is trending or ranging, adjusting strategy selection accordingly.",candle:false},
    {name:"Trend Strength",type:"Advanced",ind:"ADX + 20/50 MA + Weekly momentum",desc:"Catches multi-week momentum moves. Fires when ADX>25, price above both MAs, 10-bar momentum > 5%.",candle:false},
    {name:"Earnings Momentum",type:"Advanced",ind:"Earnings gap + Volume surge + Gap hold",desc:"Detects post-earnings momentum gaps >3% with 2x volume, confirms price holds the gap.",candle:false},
  ];
  const TC = {
    "Trend":{bg:"#0a1a30",color:"#4d9cf8",border:"#1a3a5a"},
    "Counter-trend":{bg:"#1a0a2a",color:"#a78bfa",border:"#3a1a5a"},
    "Candlestick":{bg:"#0a1a0a",color:"#22c55e",border:"#1a3a1a"},
    "Advanced":{bg:"#1a1200",color:"#f59e0b",border:"#3a2a00"},
  };

  return (
    <div style={{padding:16,maxWidth:760}}>
      <div style={{fontSize:11,color:T.textMuted,textTransform:"uppercase",letterSpacing:".08em",marginBottom:14}}>Configure agent</div>
      <div style={{display:"flex",gap:6,marginBottom:16,flexWrap:"wrap"}}>
        {[["strategies","Strategies"],["risk","Risk & Sizing"],["watchlist","Watchlist"],["safeguards","Safeguards"]].map(([id,label])=>(
          <button key={id} style={tabStyle(id)} onClick={()=>setTab(id)}>{label}</button>
        ))}
      </div>

      {tab==="strategies"&&(
        <div>
          <div style={card}>
            <div style={{fontSize:12,fontWeight:500,color:T.textSecondary,marginBottom:10}}>Trading approach</div>
            <div style={{display:"flex",gap:8,marginBottom:10,flexWrap:"wrap"}}>
              {["Conservative","Balanced","Aggressive",
      "Micro Momentum","Profit Maximizer","Long Term"].map(a=>(
                <Chip key={a} label={a} active={approach===a} onClick={()=>applyPreset(a)} T={T} color={a==="Profit Maximizer"?T.profit:T.accent}/>
              ))}
            </div>
            <div style={{padding:"8px 12px",background:T.bg3,borderRadius:6,fontSize:11,color:isPM?T.profit:isLT?T.accent:T.textMuted,lineHeight:1.6}}>
              {approach==="Conservative"    &&"5+ strategies must agree · 2% stop · 5% target · EOD only · Safe capital preservation"}
              {approach==="Balanced"        &&"3+ strategies must agree · 3% stop · 6% target · Pre-market + EOD · Standard growth"}
              {approach==="Aggressive"      &&"2+ strategies must agree · 5% stop · 10% target · Hourly scans · Higher risk/reward"}
              {approach==="Profit Maximizer"&&"Quick profits · 1.5% trailing stop · 2.5% target · Hourly scans · Candlestick exits · Partial profit locking · Max 2 day hold"}
              {approach==="Long Term"       &&"6+ strategies agree · 7% wide stop · 20% target · EOD only · Patient high-conviction holds"}
            </div>
          </div>
          <div style={{fontSize:11,color:T.textMuted,textTransform:"uppercase",letterSpacing:".06em",marginBottom:10}}>All {STRATS.length} active strategies — click to expand</div>
          {STRATS.map((s,i)=>{
            const tc=TC[s.type]||TC["Advanced"];
            const isOpen=expandedStrat===i;
            return(
              <div key={s.name} onClick={()=>setExpandedStrat(isOpen?null:i)}
                style={{background:T.cardBg,border:`1px solid ${isOpen?T.accent:T.border}`,borderRadius:8,padding:"10px 14px",marginBottom:6,cursor:"pointer"}}>
                <div style={{display:"flex",alignItems:"center",gap:10}}>
                  <div style={{width:3,height:32,borderRadius:2,background:tc.color,flexShrink:0}}/>
                  <div style={{flex:1}}>
                    <div style={{display:"flex",alignItems:"center",gap:8}}>
                      <span style={{fontSize:13,fontWeight:500,color:T.textPrimary}}>{s.name}</span>
                      <span style={{fontSize:10,padding:"2px 8px",borderRadius:10,background:tc.bg,color:tc.color,border:`1px solid ${tc.border}`}}>{s.type}</span>
                      {s.candle&&<span style={{fontSize:10,padding:"2px 8px",borderRadius:10,background:"#0a1a0a",color:"#22c55e",border:"1px solid #1a3a1a"}}>Candlestick ✓</span>}
                      {isPM&&s.candle&&<span style={{fontSize:10,padding:"2px 7px",borderRadius:10,background:T.profit+"15",color:T.profit,border:`1px solid ${T.profit}33`}}>Used for exit</span>}
                    </div>
                    <div style={{fontSize:11,color:T.textMuted,marginTop:2}}>{s.ind}</div>
                  </div>
                  <div style={{fontSize:12,color:T.textMuted}}>{isOpen?"▲":"▼"}</div>
                </div>
                {isOpen&&<div style={{marginTop:10,paddingTop:10,borderTop:`1px solid ${T.border}`,fontSize:12,color:T.textSecondary,lineHeight:1.7}}>{s.desc}</div>}
              </div>
            );
          })}
        </div>
      )}

      {tab==="risk"&&(
        <div>
          {isPM&&<div style={{...card,background:T.profit+"10",border:`1px solid ${T.profit}33`,marginBottom:12}}>
            <div style={{fontSize:12,fontWeight:500,color:T.profit,marginBottom:4}}>Profit Maximizer — optimized settings loaded</div>
            <div style={{fontSize:11,color:T.textSecondary,lineHeight:1.6}}>Tight 1.5% stop · Quick 2.5% target · 5 max positions · Trailing stop enabled</div>
          </div>}
          {isLT&&<div style={{...card,background:T.accent+"10",border:`1px solid ${T.accent}33`,marginBottom:12}}>
            <div style={{fontSize:12,fontWeight:500,color:T.accent}}>Long Term mode · Max 4 positions · 7% stop · 20% target</div>
          </div>}
          <div style={card}>
            <div style={{fontSize:12,fontWeight:500,color:T.textSecondary,marginBottom:12}}>Position sizing</div>
            <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:14}}>
              {["Kelly Criterion","Fixed Fractional","Confidence-Scaled"].map(s=>(
                <div key={s} onClick={()=>setSizing(s)} style={{padding:"6px 14px",borderRadius:20,fontSize:12,fontWeight:500,cursor:"pointer",
                  border:sizing===s?`2px solid ${isPM?T.profit:T.accent}`:`1px solid ${T.border}`,
                  background:sizing===s?(isPM?T.profit:T.accent)+"18":T.bg3,
                  color:sizing===s?(isPM?T.profit:T.accent):T.textMuted}}>{s}</div>
              ))}
            </div>
            <SliderRow T={T} label="Portfolio risk %"     value={portRisk}   min={1} max={20} unit="%" onChange={setPortRisk}   highlight={isPM}/>
            <SliderRow T={T} label="Max open positions"   value={maxPos}     min={1} max={10}      onChange={setMaxPos}     highlight={isPM}/>
            <SliderRow T={T} label="Stop loss %"          value={stopLoss}   min={1} max={15} unit="%" onChange={setStopLoss}   highlight={isPM}/>
            <SliderRow T={T} label="Take profit %"        value={takeProfit} min={1} max={30} unit="%" onChange={setTakeProfit} highlight={isPM}/>
            <SliderRow T={T} label="Daily loss limit %"   value={dailyLoss}  min={1} max={10} unit="%" onChange={setDailyLoss}  highlight={false}/>
            <SliderRow T={T} label="Min strategies agree" value={minStrats}  min={1} max={8}       onChange={setMinStrats}  highlight={false}/>
            <SliderRow T={T} label="Min confidence %"     value={confThresh} min={40} max={95} unit="%" onChange={setConfThresh} highlight={false}/>
          </div>
        </div>
      )}

      {tab==="watchlist"&&(
        <div>
          <div style={card}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
              <span style={{fontSize:13,fontWeight:500}}>
                Watchlist <span style={{color:T.textMuted,fontWeight:400}}>({watchlist.length} selected)</span>
              </span>
              <button onClick={async ()=>{
                // Try live API first, fall back to preset picks
                try {
                  const r = await fetch(`${API_BASE}/api/top_movers?approach=${encodeURIComponent(approach)}`);
                  const d = await r.json();
                  const picks = (d.symbols||[]).filter(s=>!watchlist.includes(s));
                  if(picks.length>0) setWatchlist(prev=>[...new Set([...prev,...picks])]);
                  else alert("All top movers already in your watchlist!");
                } catch {
                  // Fallback to static picks
                  const picks=(MOMENTUM_PICKS[approach]||[]).filter(s=>!watchlist.includes(s));
                  if(picks.length>0) setWatchlist(prev=>[...new Set([...prev,...picks])]);
                }
              }} style={{fontSize:11,padding:"3px 10px",borderRadius:6,cursor:"pointer",
                border:`0.5px solid ${T.profit}44`,background:T.profit+"15",color:T.profit}}>
                Find top movers
              </button>
            </div>
            <TickerSearch watchlist={watchlist} setWatchlist={setWatchlist} T={T} />
            <div style={{display:"flex",flexWrap:"wrap",gap:6,marginTop:12}}>
              {watchlist.map(sym=>(
                <div key={sym} style={{display:"flex",alignItems:"center",gap:4,padding:"3px 8px 3px 10px",
                  borderRadius:16,background:T.profit+"18",border:`0.5px solid ${T.profit}55`,
                  fontSize:11,fontWeight:500,color:T.profit}}>
                  {sym}
                  <span onClick={()=>setWatchlist(w=>w.filter(s=>s!==sym))}
                    style={{cursor:"pointer",opacity:.6,marginLeft:2,fontSize:13,lineHeight:1}}>×</span>
                </div>
              ))}
            </div>
            <div style={{fontSize:10,color:T.textMuted,marginTop:10}}>All selected symbols scanned on every cycle.</div>
          </div>
          <div style={{...card,marginTop:8}}>
            <div style={{fontSize:11,color:T.textMuted,marginBottom:8}}>Quick add by sector</div>
            <div style={{display:"flex",flexWrap:"wrap",gap:6}}>
              {[
                {label:"Big Tech",  syms:["AAPL","MSFT","GOOGL","META","AMZN","NVDA"]},
                {label:"Semis",     syms:["AMD","INTC","MU","AVGO","QCOM","AMAT"]},
                {label:"EV / Auto", syms:["TSLA","RIVN","GM","F","NIO","LCID"]},
                {label:"Fintech",   syms:["COIN","HOOD","SOFI","SQ","PYPL","PLTR"]},
                {label:"AI plays",  syms:["NVDA","PLTR","AI","PATH","CRWD","SNOW"]},
                {label:"Crypto",    syms:["MSTR","MARA","COIN","RIOT","HUT","CLSK"]},
                {label:"ETFs",      syms:["SPY","QQQ","IWM","XLK","SOXX","SMH"]},
              ].map(({label,syms})=>(
                <button key={label} onClick={()=>{
                  const toAdd=syms.filter(s=>!watchlist.includes(s));
                  if(toAdd.length>0) setWatchlist(prev=>[...new Set([...prev,...toAdd])]);
                }} style={{fontSize:10,padding:"3px 10px",borderRadius:12,cursor:"pointer",
                  border:`0.5px solid ${T.border}`,background:T.bg3,color:T.textMuted}}>
                  + {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab==="safeguards"&&(
        <div>
          <div style={card}>
            <div style={{fontSize:12,fontWeight:500,color:T.textSecondary,marginBottom:10}}>Scan frequency</div>
            <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:8}}>
              {[{label:"5 min",val:5},{label:"10 min",val:10},{label:"30 min",val:30},{label:"1 hour",val:60},{label:"EOD only",val:0}].map(({label,val})=>(
                <div key={val} onClick={()=>setScanFreq(val)} style={{padding:"6px 14px",borderRadius:20,fontSize:12,fontWeight:500,cursor:"pointer",
                  border:scanFreq===val?`2px solid ${isPM?T.profit:T.accent}`:`1px solid ${T.border}`,
                  background:scanFreq===val?(isPM?T.profit:T.accent)+"18":T.bg3,
                  color:scanFreq===val?(isPM?T.profit:T.accent):T.textMuted}}>{label}</div>
              ))}
            </div>
          </div>
          <div style={card}>
            <div style={{fontSize:12,fontWeight:500,color:T.textSecondary,marginBottom:12}}>Trading discipline</div>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"8px 0",
              borderBottom:`0.5px solid ${T.border}`}}>
              <div style={{display:"flex",alignItems:"center",gap:10,flex:1}}>
                <span style={{fontSize:12,color:T.textSecondary,minWidth:140}}>Max trades per day</span>
                {!unlimitedTrades && (
                  <input type="range" min={1} max={50} step={1} value={maxTradesDay}
                    onChange={e=>setMaxTradesDay(+e.target.value)}
                    style={{flex:1,accentColor:T.profit}}/>
                )}
                <span style={{fontSize:12,fontWeight:500,color:T.profit,minWidth:40,textAlign:"right"}}>
                  {unlimitedTrades ? "∞" : maxTradesDay}
                </span>
              </div>
              <button onClick={()=>setUnlimitedTrades(u=>!u)}
                style={{marginLeft:12,fontSize:10,padding:"3px 10px",borderRadius:12,cursor:"pointer",
                  border:"none",fontWeight:500,
                  background: unlimitedTrades ? T.profit+"33" : T.bg3,
                  color: unlimitedTrades ? T.profit : T.textMuted}}>
                {unlimitedTrades ? "Unlimited ON" : "Set unlimited"}
              </button>
            </div>
            <SliderRow T={T} label="Max consecutive losses"  value={maxConsecLoss} min={1}  max={10}      onChange={setMaxConsecLoss} highlight={false}/>
            <SliderRow T={T} label="Cool-down after losses"  value={cooldownMins}  min={15} max={480} unit=" min" onChange={setCooldownMins} highlight={false}/>
            <SliderRow T={T} label="Profit lock trigger"     value={profitLockPct} min={1}  max={10} unit="%" onChange={setProfitLockPct} highlight={false}/>
            <SliderRow T={T} label="Weekly loss circuit"     value={weeklyLossPct} min={2}  max={20} unit="%" onChange={setWeeklyLossPct} highlight={false}/>
          </div>
          <div style={card}>
            <div style={{fontSize:12,fontWeight:500,color:T.textSecondary,marginBottom:4}}>Safety rules</div>
            <Toggle T={T} label="Paper trading mode"      sub="Simulate all trades — no real money at risk"    checked={paper}    onChange={setPaper}/>
            <Toggle T={T} label="Market hours only"       sub="No pre/post market trading"                      checked={mktHours} onChange={setMktHours}/>
            <Toggle T={T} label="Earnings blackout"       sub="Avoid trading 3 days before scheduled earnings"  checked={earnings} onChange={setEarnings}/>
            <Toggle T={T} label="Market crash protection" sub="Pause if SPY drops 5%+ in a rolling week"        checked={regime}   onChange={setRegime}/>
            {!paper&&<div style={{marginTop:10,padding:"10px 14px",background:T.loss+"15",border:`1px solid ${T.loss}44`,borderRadius:8,fontSize:12,color:T.loss}}>
              Live mode is ON — real money will be used. Review paper trading results first.
            </div>}
          </div>
          <div style={card}>
            <div style={{fontSize:12,fontWeight:500,color:T.textSecondary,marginBottom:2}}>Feature flags</div>
            <div style={{fontSize:11,color:T.textMuted,marginBottom:10,lineHeight:1.5}}>
              Enable one at a time. Measure win rate vs 76% baseline for 5 days before enabling the next.
            </div>
            <Toggle T={T}
              label="Flag 5 — trail activation (0.5%)"
              sub="Trail only starts after +0.5% gain from entry. Fixed stop holds until then — prevents wick-noise exits."
              checked={flagTrailActivation} onChange={setFlagTrailActivation}/>
            <Toggle T={T}
              label="Flag 4 — sector concentration limit"
              sub="Block new BUY if >40% of open positions already in same sector. Prevents correlated losses."
              checked={flagSectorConc} onChange={setFlagSectorConc}/>
            <Toggle T={T}
              label="Flag 3 — drawdown circuit breaker"
              sub="5-day rolling drawdown >3% → reduce sizing. >5% → halt new positions until recovery."
              checked={flagDrawdownCB} onChange={setFlagDrawdownCB}/>
            <Toggle T={T}
              label="Flag 2 — ATR-based trailing stops"
              sub="Replace fixed 1% trail with 2×ATR14. Adapts stop width to current volatility automatically."
              checked={flagATRStops} onChange={setFlagATRStops}/>
            <Toggle T={T}
              label="Flag 1 — news sentiment → conviction"
              sub="Wire news/sentiment.py into conviction engine. ±1.5 boost based on headlines. Build before enabling."
              checked={flagNewsSentiment} onChange={setFlagNewsSentiment}/>
            <div style={{marginTop:8,padding:"8px 12px",background:T.profit+"12",border:`1px solid ${T.profit}33`,borderRadius:6,fontSize:11,color:T.profit,lineHeight:1.5}}>
              {[flagTrailActivation,flagSectorConc,flagDrawdownCB,flagATRStops,flagNewsSentiment].filter(Boolean).length === 0
                ? "All flags OFF — baseline mode"
                : `${[flagTrailActivation,flagSectorConc,flagDrawdownCB,flagATRStops,flagNewsSentiment].filter(Boolean).length} flag(s) active — save to apply`}
            </div>
          </div>
        </div>
      )}

      <div style={{marginTop:14}}>
        <button onClick={save} disabled={saving}
          style={{width:"100%",padding:"10px 0",borderRadius:8,fontSize:13,fontWeight:600,border:"none",cursor:"pointer",
            background:saved?T.profit:saving?T.profit+"44":isPM?T.profit:T.accent,color:"#000",transition:"background .2s"}}>
          {saved?"✓ Saved!":saving?"Saving...":`Save — ${approach}`}
        </button>
      </div>
    </div>
  );
}
