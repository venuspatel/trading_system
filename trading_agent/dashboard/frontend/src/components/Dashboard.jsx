import React, { useEffect, useRef, useState } from "react";
import EquityChart from "./EquityChart";
import TradeChart from "./TradeChart";
import { useTheme } from "./ThemeContext";

function MetricCard({ label, value, sub, color, T, compact }) {
  return (
    <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:compact?"8px 10px":"10px 12px"}}>
      <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:3}}>{label}</div>
      <div style={{fontSize:compact?14:16,fontWeight:500,color,fontVariantNumeric:"tabular-nums"}}>{value}</div>
      {sub && <div style={{fontSize:9,color:T.textMuted,marginTop:2}}>{sub}</div>}
    </div>
  );
}

function SignalHeatmap({ decisions, watchlist, T, trendStates, rallySignals, vwapData }) {
  const SC = { BUY:T.profit, SELL:T.loss, HOLD:T.textMuted, BLOCKED:T.warning };
  const SB = { BUY:T.profit+"15", SELL:T.loss+"15", HOLD:T.bg3, BLOCKED:T.warning+"15" };
  const unique = decisions.reduce((a, d) => { if (!a.find(x => x.symbol === d.symbol)) a.push(d); return a; }, []);
  // Show ALL symbols — full watchlist not just 12
  const allItems = unique.length > 0
    ? unique
    : watchlist.map(s => ({ symbol: s, action: "HOLD", conviction_score: null }));
  const sorted = [...allItems].sort((a, b) => {
    const order = { BUY:0, BLOCKED:1, HOLD:2, SELL:3 };
    if ((order[a.action]||2) !== (order[b.action]||2)) return (order[a.action]||2) - (order[b.action]||2);
    return (b.conviction_score||0) - (a.conviction_score||0);
  });
  return (
    <div style={{display:"grid",gridTemplateColumns:"repeat(6,1fr)",gap:4}}>
      {sorted.map(d => {
        const col = SC[d.action] || T.textMuted;
        const isNear = d.action === "HOLD" && (d.conviction_score||0) >= 1.5;
        const bg = isNear ? T.warning+"18" : (SB[d.action]||T.bg3);
        const borderCol = isNear ? T.warning+"55" : col+"33";
        return (
          <div key={d.symbol} style={{background:bg,border:`0.5px solid ${borderCol}`,borderRadius:6,padding:"6px 3px",textAlign:"center"}}>
            <div style={{fontSize:10,fontWeight:600,color:isNear?T.warning:col,marginBottom:1}}>{d.symbol}</div>
            <div style={{fontSize:9,color:isNear?T.warning:col,fontVariantNumeric:"tabular-nums"}}>
              {d.conviction_score != null ? `${d.conviction_score > 0 ? "+" : ""}${Number(d.conviction_score).toFixed(2)}` : "—"}
            </div>
            <div style={{fontSize:8,color:isNear?T.warning:col,marginTop:1,opacity:.8}}>{d.action}</div>
            {d.momentum_override && <div style={{fontSize:8,color:"var(--color-text-warning)"}}>↑ override</div>}
            {trendStates && trendStates[d.symbol] && (
              <div style={{fontSize:7,marginTop:1,padding:"1px 3px",borderRadius:3,fontWeight:500,
                background: trendStates[d.symbol]==="UPTREND" ? T.profit+"25" : trendStates[d.symbol]==="DOWNTREND" ? T.loss+"25" : T.warning+"20",
                color:      trendStates[d.symbol]==="UPTREND" ? T.profit : trendStates[d.symbol]==="DOWNTREND" ? T.loss : T.warning}}>
                {trendStates[d.symbol]==="UPTREND" ? "↑" : trendStates[d.symbol]==="DOWNTREND" ? "↓" : "→"}
              </div>
            )}
            {rallySignals && rallySignals[d.symbol] && (
              <div style={{fontSize:7,marginTop:1,padding:"1px 3px",borderRadius:3,fontWeight:600,background:T.profit+"35",color:T.profit}}>
                +{rallySignals[d.symbol].intraday_pct?.toFixed(1)}%
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function IntradayControls({ T, api }) {
  const [intradayOn, setIntradayOn] = React.useState(false);
  const [loading, setLoading]       = React.useState(false);
  const [msg, setMsg]               = React.useState('');
  const BASE = api || 'http://localhost:8000';

  React.useEffect(() => {
    const sync = () => fetch(`${BASE}/api/state`).then(r=>r.json()).then(d=>{
      if (d.intraday_mode !== undefined) setIntradayOn(d.intraday_mode);
    }).catch(()=>{});
    sync();
    const id = setInterval(sync, 5000);
    return () => clearInterval(id);
  }, []);

  const toggle = async () => {
    setLoading(true);
    const next = !intradayOn;
    try {
      const r = await fetch(`${BASE}/api/intraday_mode`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({enabled: next, interval_minutes: 2})
      });
      const d = await r.json();
      if (d.success) { setIntradayOn(next); setMsg(next ? 'Scanning every 2 min' : 'Back to 10-min scans'); }
      else setMsg(d.error || 'Failed');
    } catch(e) { setMsg(e.message); }
    setLoading(false);
    setTimeout(() => setMsg(''), 4000);
  };

  const closeAll = async () => {
    if (!window.confirm('Close ALL open positions now?')) return;
    const r = await fetch(`${BASE}/api/close_all`, {method:'POST'});
    const d = await r.json();
    setMsg(d.success ? '✓ All positions closed' : d.error);
    setTimeout(() => setMsg(''), 4000);
  };

  return (
    <div style={{display:'flex',alignItems:'center',gap:6,flexShrink:0}}>
      {msg && <span style={{fontSize:9,color:T.profit,maxWidth:160}}>{msg}</span>}
      <button onClick={closeAll} style={{fontSize:9,padding:'2px 8px',borderRadius:6,cursor:'pointer',
        border:`0.5px solid ${T.loss}55`,background:T.loss+'15',color:T.loss,fontWeight:500}}>
        Close all
      </button>
      <button onClick={toggle} disabled={loading} style={{fontSize:9,padding:'2px 10px',borderRadius:6,cursor:'pointer',fontWeight:500,
        border:`0.5px solid ${intradayOn ? T.profit : T.border}`,
        background: intradayOn ? T.profit+'25' : T.bg3,
        color: intradayOn ? T.profit : T.textMuted}}>
        {loading ? '...' : intradayOn ? '⚡ 2-min ON' : 'Intraday mode'}
      </button>
    </div>
  );
}

function PremarketPanel({ T, api }) {
  const [scores, setScores] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const API_URL = api || 'http://localhost:8000';

  const load = () => {
    setLoading(true);
    fetch(`${API_URL}/api/premarket`)
      .then(r=>r.json())
      .then(d=>{ setScores(d.scores||[]); setLoaded(true); })
      .catch(()=>{})
      .finally(()=>setLoading(false));
  };

  React.useEffect(()=>{ load(); }, []);

  if ((!loaded && !loading) || (scores.length === 0 && !loading)) return (
    <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:6}}>
        <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em"}}>Pre-market heat</div>
        <button onClick={load} style={{fontSize:10,padding:"2px 10px",borderRadius:8,cursor:"pointer",border:"none",
          background:T.accent+"33",color:T.accent}}>{loading?"...":"Refresh"}</button>
      </div>
      <div style={{fontSize:11,color:T.textMuted,padding:"8px 0",textAlign:"center"}}>
        {loading ? "Loading..." : "Pre-market data — click Refresh"}
      </div>
    </div>
  );

  return (
    <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
        <div>
          <span style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em"}}>Pre-market heat</span>
          {scores[0] && <span style={{fontSize:10,marginLeft:8,color:T.profit,fontWeight:500}}>
            top: {scores[0].symbol} ({scores[0].heat_score.toFixed(1)}/10)
          </span>}
        </div>
        <button onClick={load} disabled={loading} style={{fontSize:10,padding:"2px 10px",borderRadius:8,cursor:"pointer",border:"none",
          background:loading?T.bg3:T.accent+"33",color:loading?T.textMuted:T.accent}}>
          {loading?"...":"Refresh"}
        </button>
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:4}}>
        {scores.slice(0,6).map((s,i)=>{
          const heat = s.heat_score;
          const color = heat>=7?T.profit:heat>=5?T.accent:T.textMuted;
          return (
            <div key={s.symbol} style={{display:"flex",alignItems:"center",gap:8,padding:"4px 0",
              borderBottom:`0.5px solid ${T.border}`,}}>
              <span style={{fontSize:11,fontWeight:600,color:T.textPrimary,minWidth:44}}>{s.symbol}</span>
              <span style={{fontSize:11,fontWeight:500,color,minWidth:32}}>{heat.toFixed(1)}</span>
              <span style={{fontSize:9,color:T.textMuted,flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                {s.reason||`RSI ${s.rsi}`}
              </span>
              {s.gap_pct !== 0 && (
                <span style={{fontSize:9,color:s.gap_pct>0?T.profit:T.loss}}>{s.gap_pct>0?"+":""}{s.gap_pct.toFixed(1)}%</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Dashboard({ state, events, api }) {
  const { theme: T, compact } = useTheme();
  const p = compact ? 12 : 16;
  const g = compact ? 8 : 10;

  if (!state) return <div style={{padding:20,color:T.textMuted,fontSize:13}}>Connecting to agent...</div>;

  const acct      = state.account || {};
  const perf      = state.performance || {};
  const positions = state.open_positions || state.positions || {};
  const watchlist = state.watchlist || [];
  const decisions = state.recent_decisions || [];
  const curve     = state.equity_curve || [];
  const syntheticCurve = state.synthetic_curve || [];
  const trades    = state.all_trades || state.recent_trades || [];

  const [tradePage, setTradePage] = React.useState(0);

  const fmt$   = v => v != null ? `$${Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}` : "—";
  const fmtPnl = v => v != null ? `${v>=0?"+":""}$${Math.abs(v).toFixed(2)}` : "—";
  const fmtPct = v => v != null ? `${(v*100).toFixed(1)}%` : "—";
  const SC = { BUY:T.profit, SELL:T.loss, HOLD:T.textMuted, BLOCKED:T.warning };
  const SB = { BUY:T.profit+"15", SELL:T.loss+"15", HOLD:T.bg3, BLOCKED:T.warning+"15" };

  const card = {background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"};
  const sectionLabel = {fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:8};

  // Regime colors
  const regimeColors = {
    BULL:     {bg:"var(--color-background-success)",border:"var(--color-border-success)",text:"var(--color-text-success)"},
    BEAR:     {bg:"var(--color-background-danger)", border:"var(--color-border-danger)", text:"var(--color-text-danger)"},
    VOLATILE: {bg:"var(--color-background-warning)",border:"var(--color-border-warning)",text:"var(--color-text-warning)"},
    RANGING:  {bg:"var(--color-background-secondary)",border:"var(--color-border-secondary)",text:"var(--color-text-secondary)"},
  };
  const regime = state?.market_regime;
  const rc = regime ? (regimeColors[regime.regime] || regimeColors.RANGING) : null;

  // Strategy vote computation (preserved from original)
  const roleMap = {
    "Momentum":"Trend","Breakout":"Trend","TrendStrength":"Trend","EarningsMomentum":"Trend",
    "MeanReversion":"Counter-trend","Fibonacci":"Counter-trend",
    "CandleReversal":"Neutral","CandleContinuation":"Neutral","Divergence":"Neutral",
    "VolumeConfirmation":"Neutral","MultiTimeframe":"Neutral","TrendRegime":"Neutral",
  };
  const roleColors = {
    "Trend":        {bg:"var(--color-background-success)",border:"var(--color-border-success)",text:"var(--color-text-success)"},
    "Counter-trend":{bg:"var(--color-background-danger)", border:"var(--color-border-danger)", text:"var(--color-text-danger)"},
    "Neutral":      {bg:"var(--color-background-info)",   border:"var(--color-border-info)",   text:"var(--color-text-info)"},
  };
  const agg = {};
  const trendBuys = new Set();
  const counterSells = new Set();
  decisions.forEach(dec => {
    (dec.strategy_signals||[]).forEach(sig => {
      const name = sig.strategy || "Unknown";
      const action = sig.action || "HOLD";
      const sym = dec.symbol || "";
      if (!agg[name]) agg[name] = {role: roleMap[name]||"Neutral", buys:[], sells:[], holds:[]};
      if (action==="BUY") { agg[name].buys.push(sym); if (roleMap[name]==="Trend") trendBuys.add(sym); }
      else if (action==="SELL") { agg[name].sells.push(sym); if (roleMap[name]==="Counter-trend") counterSells.add(sym); }
      else agg[name].holds.push(sym);
    });
  });
  const strategies = Object.entries(agg).map(([name,d])=>({name,...d})).sort((a,b)=>b.buys.length-a.buys.length);
  const cancelled = [...trendBuys].filter(s => counterSells.has(s));

  return (
    <div style={{padding:p,display:"flex",flexDirection:"column",gap:g}}>

      {/* ── TOP BAR ─────────────────────────────────────────────── */}
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:8}}>
        <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
          {state?.config?.approach && (
            <div style={{display:"flex",alignItems:"center",gap:6,padding:"5px 10px",borderRadius:6,
              background: state.config.approach==="Profit Maximizer"?T.profit+"15":
                          state.config.approach==="Long Term"?T.accent+"15":"#ff9f0015",
              border:`0.5px solid ${state.config.approach==="Profit Maximizer"?T.profit+"44":
                                     state.config.approach==="Long Term"?T.accent+"44":"#ff9f0055"}`}}>
              <div style={{width:6,height:6,borderRadius:"50%",background:
                state.config.approach==="Profit Maximizer"?T.profit:
                state.config.approach==="Long Term"?T.accent:"#ff9f00"}}/>
              <span style={{fontSize:11,fontWeight:500,color:
                state.config.approach==="Profit Maximizer"?T.profit:
                state.config.approach==="Long Term"?T.accent:T.textPrimary}}>
                {state.config.approach}
              </span>
            </div>
          )}
          {rc && regime && (
            <div style={{display:"flex",alignItems:"center",gap:5,padding:"5px 10px",borderRadius:6,
              background:rc.bg,border:`0.5px solid ${rc.border}`}}>
              <div style={{width:6,height:6,borderRadius:"50%",background:rc.text}}/>
              <span style={{fontSize:11,fontWeight:500,color:rc.text}}>{regime.regime}</span>
              <span style={{fontSize:10,color:rc.text,opacity:.8}}>
                SPY {regime.spy_trend} · RSI {regime.spy_rsi} · VIX~{regime.vix_est}
              </span>
            </div>
          )}
          <span style={{fontSize:10,color:T.textMuted}}>
            cycle #{state.cycle_count||0} · {state.agent_status||"—"}
          </span>
          {perf.grade && perf.grade !== "N/A" && (
            <span style={{fontSize:10,padding:"2px 8px",borderRadius:8,
              background:T.profit+"20",color:T.profit,border:`0.5px solid ${T.profit}44`}}>
              grade {perf.grade}
            </span>
          )}
        </div>
        <IntradayControls T={T} api={api}/>
      </div>

      {/* ── ZONE 1: STATUS BAR ──────────────────────────────────── */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,minmax(0,1fr))",gap:6}}>
        <MetricCard T={T} compact={true} label="Portfolio"
          value={fmt$(acct.portfolio_value)} color={T.textPrimary}/>
        <MetricCard T={T} compact={true} label="Day P&L"
          value={fmtPnl(state.reporting?.day_pnl ?? acct.daily_pnl)}
          sub={`${state.reporting?.day_trades??0} trades · ${((state.reporting?.day_win_rate??0)*100).toFixed(0)}% win`}
          color={(state.reporting?.day_pnl??0)>=0?T.profit:T.loss}/>
        <MetricCard T={T} compact={true} label="Total P&L"
          value={fmtPnl(perf.total_pnl)}
          sub={`${perf.total_trades||0} trades all-time`}
          color={(perf.total_pnl||0)>=0?T.profit:T.loss}/>
        <MetricCard T={T} compact={true} label="Win rate"
          value={fmtPct(perf.win_rate)}
          sub={`${perf.winners||0}W · ${perf.losers||0}L`}
          color={(perf.win_rate||0)>0.5?T.profit:T.accent}/>
        <MetricCard T={T} compact={true} label="Max drawdown"
          value={fmtPct(perf.max_drawdown)}
          sub={`Sharpe ${perf.sharpe_ratio?.toFixed(2)||"—"}`}
          color={T.loss}/>
      </div>

      {/* ── ZONE 2: LIVE VIEW ───────────────────────────────────── */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:g,alignItems:"start"}}>

        {/* LEFT: equity curve fixed height */}
        <div style={card}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",...sectionLabel}}>
            <span>Equity curve</span>
            <span style={{fontSize:9,color:T.textMuted}}>zoom enabled</span>
          </div>
          {curve.length >= 2
            ? <>
                <EquityChart curve={curve} syntheticCurve={syntheticCurve} trades={trades} T={T} compact={false}/>
                <div style={{...sectionLabel,marginTop:8}}>Trade P&L</div>
                <div style={{height:70,overflow:"hidden"}}>
                  <TradeChart trades={trades} curve={curve} T={T} compact={true}/>
                </div>
              </>
            : <div style={{height:290,display:"flex",alignItems:"center",justifyContent:"center",
                color:T.textMuted,fontSize:12}}>
                Curve appears after first completed trades
              </div>
          }
        </div>

        {/* RIGHT: open positions + today's trades with pagination */}
        {(()=>{
          const TRADES_PER_PAGE = 6;
          const reversedTrades = trades.slice().reverse();
          const totalPages = Math.max(1, Math.ceil(reversedTrades.length / TRADES_PER_PAGE));
          const pageTrades = reversedTrades.slice(tradePage * TRADES_PER_PAGE, (tradePage + 1) * TRADES_PER_PAGE);
          const totalPnl   = trades.reduce((s,t)=>s+(t.pnl||0),0);
          const posArr     = Object.entries(positions);
          return (
            <div style={{display:"flex",flexDirection:"column",gap:g}}>

              {/* Open positions — full table like screenshot */}
              <div style={card}>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",...sectionLabel}}>
                  <span>Open positions</span>
                  <span style={{fontSize:9,color:T.textMuted}}>
                    {posArr.length} / {state.config?.max_open_positions||10} slots
                  </span>
                </div>
                {posArr.length === 0
                  ? <div style={{height:48,display:"flex",alignItems:"center",justifyContent:"center",
                      fontSize:11,color:T.textMuted}}>
                      No open positions
                    </div>
                  : <>
                      {/* Column headers */}
                      <div style={{display:"grid",gridTemplateColumns:"60px 1fr 80px 80px 70px",
                        gap:4,padding:"4px 0",borderBottom:`0.5px solid ${T.border}`,
                        fontSize:9,color:T.textMuted,textTransform:"uppercase",letterSpacing:".04em"}}>
                        <span>Symbol</span>
                        <span>Qty @ Entry</span>
                        <span style={{textAlign:"right"}}>Current</span>
                        <span style={{textAlign:"right"}}>Stop</span>
                        <span style={{textAlign:"right"}}>P&L</span>
                      </div>
                      {/* Position rows */}
                      {posArr.map(([sym, pos]) => {
                        const won = (pos.pnl||0) >= 0;
                        const stopPrice = pos.entry_price
                          ? pos.entry_price * (1 - (state.config?.stop_loss_pct||0.01))
                          : null;
                        const tp = pos.entry_price
                          ? pos.entry_price * (1 + (state.config?.take_profit_pct||0.03))
                          : null;
                        const overnight = state?.hold_overnight?.[sym];
                        return (
                          <div key={sym} style={{display:"grid",
                            gridTemplateColumns:"60px 1fr 80px 80px 70px",
                            gap:4,padding:"7px 0",borderBottom:`0.5px solid ${T.border}44`,
                            alignItems:"center"}}>
                            <div>
                              <span style={{fontSize:12,fontWeight:600,color:T.textPrimary}}>{sym}</span>
                              {overnight && (
                                <span style={{fontSize:8,padding:"1px 4px",borderRadius:3,marginLeft:4,
                                  background:T.profit+"25",color:T.profit,fontWeight:600}}>🌙</span>
                              )}
                            </div>
                            <div>
                              <div style={{fontSize:11,color:T.textSecondary}}>
                                {pos.qty} @ ${pos.entry_price?.toFixed(2)}
                              </div>
                              {tp && <div style={{fontSize:9,color:T.profit,marginTop:1}}>
                                TP ${tp.toFixed(2)}
                              </div>}
                            </div>
                            <span style={{fontSize:11,color:T.textSecondary,
                              textAlign:"right",fontVariantNumeric:"tabular-nums"}}>
                              ${pos.current_price?.toFixed(2)||"—"}
                            </span>
                            <span style={{fontSize:11,color:T.loss,
                              textAlign:"right",fontVariantNumeric:"tabular-nums"}}>
                              ${stopPrice?.toFixed(2)||"—"}
                            </span>
                            <div style={{textAlign:"right"}}>
                              <div style={{fontSize:12,fontWeight:500,fontVariantNumeric:"tabular-nums",
                                color:won?T.profit:T.loss}}>
                                {won?"+":""}${pos.pnl?.toFixed(2)||"0.00"}
                              </div>
                              <div style={{fontSize:9,color:won?T.profit:T.loss,marginTop:1}}>
                                {pos.pnl_pct!=null
                                  ? `${won?"+":""}${(pos.pnl_pct*100).toFixed(2)}%`
                                  : pos.entry_price && pos.current_price
                                    ? `${((pos.current_price-pos.entry_price)/pos.entry_price*100)>=0?"+":""}${((pos.current_price-pos.entry_price)/pos.entry_price*100).toFixed(2)}%`
                                    : ""}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </>
                }
              </div>

              {/* Today's trades — with IN→OUT prices + times */}
              <div style={card}>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",...sectionLabel}}>
                  <span>Today's trades</span>
                  <div style={{display:"flex",alignItems:"center",gap:6}}>
                    {totalPages > 1 && (
                      <span style={{fontSize:9,color:T.textMuted}}>
                        page {tradePage+1}/{totalPages}
                      </span>
                    )}
                    <div style={{display:"flex",gap:2}}>
                      <button onClick={()=>setTradePage(p=>Math.max(0,p-1))}
                        disabled={tradePage===0}
                        style={{fontSize:9,padding:"1px 6px",borderRadius:3,cursor:"pointer",
                          border:`0.5px solid ${T.border}`,background:T.bg3,
                          color:tradePage===0?T.textMuted:T.textPrimary}}>‹</button>
                      <button onClick={()=>setTradePage(p=>Math.min(totalPages-1,p+1))}
                        disabled={tradePage===totalPages-1}
                        style={{fontSize:9,padding:"1px 6px",borderRadius:3,cursor:"pointer",
                          border:`0.5px solid ${T.border}`,background:T.bg3,
                          color:tradePage===totalPages-1?T.textMuted:T.textPrimary}}>›</button>
                    </div>
                  </div>
                </div>

                {/* Column headers */}
                {trades.length > 0 && (
                  <div style={{display:"grid",
                    gridTemplateColumns:"40px 48px 1fr 115px 130px 70px",
                    gap:6,padding:"4px 0",borderBottom:`0.5px solid ${T.border}`,
                    fontSize:9,color:T.textMuted,textTransform:"uppercase",letterSpacing:".04em"}}>
                    <span></span>
                    <span>Symbol</span>
                    <span>Reason</span>
                    <span style={{textAlign:"right"}}>In → Out</span>
                    <span style={{textAlign:"right"}}>Entry → Exit</span>
                    <span style={{textAlign:"right"}}>P&L</span>
                  </div>
                )}

                {/* Trade rows */}
                <div style={{minHeight:120}}>
                  {trades.length === 0
                    ? <div style={{height:120,display:"flex",alignItems:"center",justifyContent:"center",
                        fontSize:11,color:T.textMuted}}>
                        No trades today yet
                      </div>
                    : pageTrades.map((t,i) => {
                        const won = t.pnl >= 0;
                        const entryT = t.entry_time ? new Date(t.entry_time).toLocaleTimeString("en-US",
                          {hour:"2-digit",minute:"2-digit",hour12:true}) : "—";
                        const exitT  = t.exit_time  ? new Date(t.exit_time).toLocaleTimeString("en-US",
                          {hour:"2-digit",minute:"2-digit",hour12:true}) : "—";
                        return (
                          <div key={i} style={{display:"grid",
                            gridTemplateColumns:"40px 48px 1fr 115px 130px 70px",
                            gap:6,padding:"6px 0",borderBottom:`0.5px solid ${T.border}22`,
                            alignItems:"center",fontSize:11}}>
                            <span style={{fontSize:8,padding:"2px 5px",borderRadius:8,fontWeight:600,
                              background:won?T.profit+"20":T.loss+"20",
                              color:won?T.profit:T.loss,textAlign:"center"}}>
                              {won?"WIN":"LOSS"}
                            </span>
                            <div>
                              <div style={{fontWeight:600,color:T.textPrimary,fontSize:12}}>{t.symbol}</div>
                              {t.exit_time && (
                                <div style={{fontSize:8,color:T.textSecondary,marginTop:1}}>
                                  {new Date(t.exit_time).toLocaleDateString("en-US",{month:"short",day:"numeric"})}
                                </div>
                              )}
                            </div>
                            <span style={{color:T.textSecondary,overflow:"hidden",textOverflow:"ellipsis",
                              fontSize:10}}>
                              {t.exit_reason}
                            </span>
                            <span style={{textAlign:"right",fontSize:10,color:T.textPrimary,
                              fontVariantNumeric:"tabular-nums"}}>
                              ${t.entry_price?.toFixed(2)}→${t.exit_price?.toFixed(2)}
                            </span>
                            <span style={{textAlign:"right",fontSize:10,color:T.textSecondary,
                              fontVariantNumeric:"tabular-nums"}}>
                              {entryT}→{exitT}
                            </span>
                            <span style={{textAlign:"right",fontWeight:500,
                              fontVariantNumeric:"tabular-nums",
                              color:won?T.profit:T.loss}}>
                              {won?"+":""}${t.pnl?.toFixed(2)}
                            </span>
                          </div>
                        );
                      })
                  }
                </div>

                {/* Summary bar */}
                {trades.length > 0 && (
                  <div style={{borderTop:`0.5px solid ${T.border}`,paddingTop:5,marginTop:4,
                    display:"flex",gap:12,fontSize:9}}>
                    <span style={{color:T.profit}}>{trades.filter(t=>t.pnl>=0).length} wins</span>
                    <span style={{color:T.loss}}>{trades.filter(t=>t.pnl<0).length} losses</span>
                    <span style={{fontWeight:500,color:totalPnl>=0?T.profit:T.loss}}>
                      {fmtPnl(totalPnl)} total
                    </span>
                  </div>
                )}
              </div>

              {/* Rally alerts */}
              {state?.rally_signals && Object.keys(state.rally_signals).length > 0 && (
                <div style={{...card,background:T.profit+"12",border:`0.5px solid ${T.profit}44`}}>
                  <div style={{...sectionLabel,color:T.profit}}>
                    Rally — {Object.keys(state.rally_signals).length} running
                  </div>
                  <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
                    {Object.entries(state.rally_signals)
                      .sort((a,b)=>b[1].rally_score-a[1].rally_score)
                      .map(([sym,sig])=>(
                        <div key={sym} style={{background:T.profit+"20",borderRadius:5,padding:"3px 7px",
                          border:`0.5px solid ${T.profit}55`}}>
                          <span style={{fontSize:11,fontWeight:600,color:T.profit}}>{sym}</span>
                          <span style={{fontSize:10,color:T.profit,marginLeft:4}}>
                            {sig.intraday_pct>0?"+":""}{sig.intraday_pct?.toFixed(1)}%
                          </span>
                        </div>
                      ))
                    }
                  </div>
                </div>
              )}
            </div>
          );
        })()}
      </div>

      {/* HEATMAP — full width below both columns */}
      <div style={card}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",...sectionLabel}}>
          <span>Signal heatmap</span>
          <span style={{fontSize:9,color:T.textMuted}}>
            {watchlist.length} symbols · cycle #{state.cycle_count||0}
          </span>
        </div>
        <SignalHeatmap decisions={decisions} watchlist={watchlist} T={T}
          trendStates={state?.trend_states} rallySignals={state?.rally_signals}
          vwapData={state?.intraday_vwap}/>
      </div>

      {/* ── ZONE 3: INTELLIGENCE ────────────────────────────────── */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:g}}>

        {/* Strategy votes */}
        {strategies.length > 0 && (
          <div style={card}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",...sectionLabel}}>
              <span>Strategy votes</span>
              {cancelled.length > 0 && (
                <span style={{fontSize:9,padding:"1px 7px",borderRadius:8,
                  background:"var(--color-background-warning)",color:"var(--color-text-warning)",
                  border:"0.5px solid var(--color-border-warning)"}}>
                  {cancelled.length} clash
                </span>
              )}
            </div>
            {strategies.slice(0,8).map(s => {
              const rc2 = roleColors[s.role] || roleColors["Neutral"];
              return (
                <div key={s.name} style={{display:"flex",alignItems:"center",gap:6,padding:"4px 0",
                  borderBottom:`0.5px solid ${T.border}`}}>
                  <span style={{fontSize:10,color:T.textPrimary,flex:1,minWidth:0,overflow:"hidden",
                    textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{s.name}</span>
                  <span style={{fontSize:8,padding:"1px 5px",borderRadius:3,
                    background:rc2.bg,color:rc2.text,border:`0.5px solid ${rc2.border}`,flexShrink:0}}>
                    {s.role.split("-")[0]}
                  </span>
                  <span style={{fontSize:10,fontWeight:500,flexShrink:0,
                    color:s.buys.length>s.sells.length?"var(--color-text-success)":
                          s.sells.length>s.buys.length?"var(--color-text-danger)":T.textMuted}}>
                    {s.buys.length>0&&`+${s.buys.length}`}
                    {s.buys.length>0&&s.sells.length>0&&"/"}
                    {s.sells.length>0&&`-${s.sells.length}`}
                    {s.buys.length===0&&s.sells.length===0&&"—"}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Conviction scores */}
        {decisions.length > 0 && (
          <div style={card}>
            <div style={sectionLabel}>Conviction scores</div>
            {decisions.slice(0,8).map((d,idx) => {
              const score = d.conviction_score || 0;
              const pct = Math.min(100, Math.max(0, (score/5)*100));
              const color = score>=2.5?T.profit:score>=1.5?T.warning:score>=0?T.textMuted:T.loss;
              return (
                <div key={`${d.symbol}-${idx}`} style={{marginBottom:6}}>
                  <div style={{display:"flex",justifyContent:"space-between",marginBottom:2}}>
                    <span style={{fontSize:11,fontWeight:500,color:T.textPrimary}}>{d.symbol}</span>
                    <span style={{fontSize:11,fontWeight:500,color}}>{score>=0?"+":""}{score.toFixed(2)}</span>
                  </div>
                  <div style={{height:4,background:T.border,borderRadius:2,overflow:"hidden",position:"relative"}}>
                    <div style={{height:"100%",width:`${pct}%`,background:color,borderRadius:2,transition:"width .3s"}}/>
                    <div style={{position:"absolute",left:"50%",top:0,width:1,height:"100%",background:T.border}}/>
                  </div>
                  <div style={{fontSize:9,color:T.textMuted,marginTop:1}}>{d.action}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pre-market heat */}
        <PremarketPanel T={T} api={api}/>
      </div>

      {/* ── BELOW FOLD: DETAIL PANELS ───────────────────────────── */}
      <div style={{borderTop:`0.5px solid ${T.border}`,paddingTop:g,display:"flex",flexDirection:"column",gap:g}}>

        {/* Discipline panel */}
        {state?.discipline && state.discipline.max_trades_today > 0 && (
          <div style={{...card,border:`1px solid ${
            state.discipline.week_stopped||state.discipline.cooldown_active ? T.loss+"55" :
            state.discipline.profit_lock_active ? T.profit+"55" : T.border}`}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
              <span style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".06em"}}>
                Trading discipline
              </span>
              <span style={{fontSize:10,fontWeight:500,padding:"2px 10px",borderRadius:10,
                background:state.discipline.week_stopped||state.discipline.cooldown_active?T.loss+"20":T.profit+"20",
                color:state.discipline.week_stopped||state.discipline.cooldown_active?T.loss:T.profit,
                border:`0.5px solid ${state.discipline.week_stopped||state.discipline.cooldown_active?T.loss+"44":T.profit+"44"}`}}>
                {state.discipline.week_stopped?"WEEK STOPPED":state.discipline.cooldown_active?"COOL-DOWN":
                 state.discipline.profit_lock_active?"PROFIT LOCKED":"TRADING ACTIVE"}
              </span>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(5,minmax(0,1fr))",gap:6,marginBottom:6}}>
              {[
                {label:"Trades today",val:`${state.discipline.trades_today} / ${state.discipline.max_trades_today}`,warn:state.discipline.trades_today>=state.discipline.max_trades_today},
                {label:"Wins / Losses",val:`${state.discipline.wins_today}W · ${state.discipline.losses_today}L`,warn:false},
                {label:"Consec. losses",val:state.discipline.consecutive_losses,warn:state.discipline.consecutive_losses>=2},
                {label:"Week P&L",val:`${state.discipline.pnl_week_pct>=0?"+":""}${(state.discipline.pnl_week_pct||0).toFixed(2)}%`,warn:(state.discipline.pnl_week_pct||0)<-3},
                {label:"Auto scans",val:`${state.cycle_count||0}${(state.cycle_count||0)>0?" ✓":""}`,warn:false},
              ].map(({label,val,warn})=>(
                <div key={label} style={{background:T.bg3,borderRadius:6,padding:"7px 9px"}}>
                  <div style={{fontSize:9,color:T.textMuted,marginBottom:2}}>{label}</div>
                  <div style={{fontSize:12,fontWeight:500,color:warn?T.loss:T.textPrimary}}>{val}</div>
                </div>
              ))}
            </div>
            <div style={{height:3,background:T.border,borderRadius:2,overflow:"hidden"}}>
              <div style={{height:"100%",borderRadius:2,transition:"width .3s",
                background:state.discipline.trades_today>=state.discipline.max_trades_today?T.loss:T.profit,
                width:`${Math.min(100,(state.discipline.trades_today/state.discipline.max_trades_today)*100)}%`}}/>
            </div>
            {state.discipline.cooldown_active && (
              <div style={{fontSize:11,color:T.loss,padding:"5px 10px",background:T.loss+"12",borderRadius:5,marginTop:6}}>
                Cool-down active — {state.discipline.cooldown_remaining_min} min until trading resumes
              </div>
            )}
            {state.discipline.profit_lock_active && (
              <div style={{fontSize:11,color:T.profit,padding:"5px 10px",background:T.profit+"12",borderRadius:5,marginTop:6}}>
                Profit lock active — trailing stops tightened to protect today's gains
              </div>
            )}
            {state.discipline.week_stopped && (
              <div style={{fontSize:11,color:T.loss,padding:"5px 10px",background:T.loss+"12",borderRadius:5,marginTop:6}}>
                Weekly circuit breaker — trading stopped until Monday 9:30am ET
              </div>
            )}
          </div>
        )}

        {/* Recent decisions */}
        {decisions.length > 0 && (
          <div style={card}>
            <div style={sectionLabel}>Recent decisions</div>
            {decisions.slice(0,8).map((d,i) => {
              const col = SC[d.action] || T.textMuted;
              return (
                <div key={i} style={{display:"flex",alignItems:"center",padding:"5px 0",
                  borderBottom:`0.5px solid ${T.border}`,gap:6}}>
                  <span style={{fontSize:10,color:T.textMuted,fontVariantNumeric:"tabular-nums",width:44}}>
                    {d.timestamp?.slice(11,16)||"—"}
                  </span>
                  <span style={{fontSize:12,fontWeight:600,color:T.textPrimary,width:44}}>{d.symbol}</span>
                  <span style={{fontSize:9,fontWeight:700,padding:"2px 7px",borderRadius:4,
                    background:SB[d.action]||T.bg3,color:col,minWidth:40,textAlign:"center"}}>
                    {d.action}
                  </span>
                  <span style={{fontSize:11,color:T.textSecondary,flex:1,whiteSpace:"nowrap",
                    overflow:"hidden",textOverflow:"ellipsis"}}>
                    {(d.top_reasons||[])[0]||d.reason||""}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Strategy vote distribution (detailed) */}
        {strategies.length > 0 && (
          <div style={card}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
              <div style={sectionLabel}>Strategy vote distribution</div>
              {cancelled.length > 0 && (
                <span style={{fontSize:10,padding:"2px 10px",borderRadius:10,
                  background:"var(--color-background-warning)",color:"var(--color-text-warning)",
                  border:"0.5px solid var(--color-border-warning)"}}>
                  {cancelled.length} collision{cancelled.length>1?"s":""} detected
                </span>
              )}
            </div>
            {strategies.map(s => {
              const rc2 = roleColors[s.role] || roleColors["Neutral"];
              const hasCollision = s.role==="Counter-trend" && s.sells.some(sym => trendBuys.has(sym));
              return (
                <div key={s.name} style={{display:"flex",alignItems:"flex-start",gap:10,padding:"6px 0",
                  borderBottom:`0.5px solid ${T.border}`}}>
                  <div style={{minWidth:150}}>
                    <div style={{fontSize:12,fontWeight:500,color:T.textPrimary,marginBottom:3}}>{s.name}</div>
                    <span style={{fontSize:9,padding:"2px 6px",borderRadius:4,fontWeight:500,
                      background:rc2.bg,color:rc2.text,border:`0.5px solid ${rc2.border}`,
                      textTransform:"uppercase",letterSpacing:".03em"}}>{s.role}</span>
                  </div>
                  <div style={{flex:1}}>
                    {s.buys.length > 0 && (
                      <div style={{display:"flex",gap:3,flexWrap:"wrap",alignItems:"center",marginBottom:3}}>
                        <span style={{fontSize:9,fontWeight:500,color:"var(--color-text-success)",
                          background:"var(--color-background-success)",border:"0.5px solid var(--color-border-success)",
                          padding:"1px 5px",borderRadius:4}}>BUY</span>
                        {s.buys.map(sym => (
                          <span key={sym} style={{fontSize:10,padding:"2px 6px",borderRadius:5,fontWeight:500,
                            background:"#1a3a2a",color:"#4ade80",border:"0.5px solid #2d6a47"}}>{sym}</span>
                        ))}
                      </div>
                    )}
                    {s.sells.length > 0 && (
                      <div style={{display:"flex",gap:3,flexWrap:"wrap",alignItems:"center",marginBottom:3}}>
                        <span style={{fontSize:9,fontWeight:500,color:"var(--color-text-danger)",
                          background:"var(--color-background-danger)",border:"0.5px solid var(--color-border-danger)",
                          padding:"1px 5px",borderRadius:4}}>SELL</span>
                        {s.sells.map(sym => (
                          <span key={sym} style={{fontSize:10,padding:"2px 6px",borderRadius:5,fontWeight:500,
                            background:trendBuys.has(sym)?"#3a1a1a":"var(--color-background-secondary)",
                            color:trendBuys.has(sym)?"#f87171":"var(--color-text-secondary)",
                            border:trendBuys.has(sym)?"0.5px solid #7a3030":"0.5px solid var(--color-border-tertiary)"}}>
                            {sym}{trendBuys.has(sym)&&<span style={{fontSize:8,marginLeft:2,opacity:.7}}>clash</span>}
                          </span>
                        ))}
                        {hasCollision && <span style={{fontSize:10,color:"var(--color-text-warning)",marginLeft:2}}>cancelling trend</span>}
                      </div>
                    )}
                    {s.buys.length===0 && s.sells.length===0 && (
                      <span style={{fontSize:10,color:T.textMuted,fontStyle:"italic"}}>no signal</span>
                    )}
                  </div>
                  <div style={{minWidth:40,textAlign:"right",fontSize:11,
                    color:s.buys.length>s.sells.length?"var(--color-text-success)":
                          s.sells.length>s.buys.length?"var(--color-text-danger)":T.textMuted}}>
                    {s.buys.length>0&&`+${s.buys.length}`}
                    {s.buys.length>0&&s.sells.length>0&&" / "}
                    {s.sells.length>0&&`−${s.sells.length}`}
                    {s.buys.length===0&&s.sells.length===0&&"—"}
                  </div>
                </div>
              );
            })}
            {cancelled.length > 0 && (
              <div style={{marginTop:8,padding:"7px 10px",background:"var(--color-background-warning)",
                border:"0.5px solid var(--color-border-warning)",borderRadius:6,fontSize:11,
                color:"var(--color-text-warning)",lineHeight:1.6}}>
                Counter-trend strategies cancelling trend BUYs on: <strong>{cancelled.join(", ")}</strong>.
              </div>
            )}
          </div>
        )}

        {/* Adaptive intelligence */}
        {state.adaptive && (
          <div style={card}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
              <div style={sectionLabel}>Adaptive intelligence</div>
              <span style={{fontSize:10,padding:"2px 8px",borderRadius:10,
                background:state.adaptive.recommendation?T.profit+"20":T.warning+"20",
                color:state.adaptive.recommendation?T.profit:T.warning,
                border:`0.5px solid ${state.adaptive.recommendation?T.profit+"44":T.warning+"44"}`}}>
                {state.adaptive.recommendation
                  ? `${(state.adaptive.recommendation.confidence*100).toFixed(0)}% confident`
                  : `${state.adaptive.trades_until_next} trades until active`}
              </span>
            </div>
            {state.adaptive.recommendation ? (
              <>
                <div style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:6,marginBottom:8}}>
                  {[
                    {label:"Conviction floor",val:state.adaptive.recommendation.conviction_floor?.toFixed(1),color:T.profit},
                    {label:"Min strategies",val:state.adaptive.recommendation.min_strategies,color:T.accent},
                    {label:"Based on trades",val:state.adaptive.recommendation.based_on_trades,color:T.textPrimary},
                  ].map(m=>(
                    <div key={m.label} style={{background:T.bg3,borderRadius:6,padding:"7px 10px"}}>
                      <div style={{fontSize:9,color:T.textMuted,textTransform:"uppercase",letterSpacing:".04em",marginBottom:2}}>{m.label}</div>
                      <div style={{fontSize:14,fontWeight:500,color:m.color}}>{m.val}</div>
                    </div>
                  ))}
                </div>
                <div style={{fontSize:11,color:T.textSecondary,background:T.bg3,borderRadius:6,padding:"7px 10px",lineHeight:1.6}}>
                  {state.adaptive.recommendation.summary}
                </div>
              </>
            ) : (
              <div style={{fontSize:11,color:T.textMuted,lineHeight:1.7}}>
                Learning from your trade history. Need {state.adaptive.trades_until_next} more trade
                {state.adaptive.trades_until_next!==1?"s":""} to activate adaptive thresholds.
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
