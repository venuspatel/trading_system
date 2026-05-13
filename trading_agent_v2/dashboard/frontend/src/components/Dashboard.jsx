import React, { useEffect, useRef, useState } from "react";
import EquityChart from "./EquityChart";
import TradeChart from "./TradeChart";
import { useTheme } from "./ThemeContext";

function MetricCard({ label, value, color, T, compact }) {
  return (
    <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:compact?"8px 10px":"10px 12px"}}>
      <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:3}}>{label}</div>
      <div style={{fontSize:compact?15:18,fontWeight:500,color,fontVariantNumeric:"tabular-nums"}}>{value}</div>


    </div>
  );
}


function SignalHeatmap({ decisions, watchlist, T, trendStates, rallySignals, vwapData }) {
  const SC = { BUY:T.profit, SELL:T.loss, HOLD:T.textMuted, BLOCKED:T.warning };
  const SB = { BUY:T.profit+"15", SELL:T.loss+"15", HOLD:T.bg3, BLOCKED:T.warning+"15" };
  const unique = decisions.reduce((a, d) => { if (!a.find(x => x.symbol === d.symbol)) a.push(d); return a; }, []);
  const items = unique.length > 0
    ? unique.slice(0, 12)
    : watchlist.slice(0, 12).map(s => ({ symbol: s, action: "HOLD", conviction_score: null }));
  // Sort: BUY first, then by conviction descending
  const sorted = [...items].sort((a, b) => {
    const order = { BUY:0, BLOCKED:1, HOLD:2, SELL:3 };
    if ((order[a.action]||2) !== (order[b.action]||2)) return (order[a.action]||2) - (order[b.action]||2);
    return (b.conviction_score||0) - (a.conviction_score||0);
  });
  const cols = Math.min(sorted.length, 6);
  return (
    <div style={{display:"grid",gridTemplateColumns:`repeat(${cols}, 1fr)`,gap:5}}>
      {sorted.map(d => {
        const col = SC[d.action] || T.textMuted;
        return (
          <div key={d.symbol} style={{background:SB[d.action]||T.bg3,border:`1px solid ${col}33`,borderRadius:6,padding:"7px 4px",textAlign:"center"}}>
            <div style={{fontSize:11,fontWeight:600,color:col,marginBottom:2}}>{d.symbol}</div>
            <div style={{fontSize:10,color:col,fontVariantNumeric:"tabular-nums"}}>
              {d.conviction_score != null ? `${d.conviction_score > 0 ? "+" : ""}${Number(d.conviction_score).toFixed(2)}` : "—"}
            </div>
            <div style={{fontSize:9,color:col,marginTop:1,opacity:.8}}>{d.action}
              {d.momentum_override && <div style={{fontSize:9,color:"var(--color-text-warning)",marginTop:1}}>override</div>}
            </div>
            {trendStates && trendStates[d.symbol] && (
              <div style={{fontSize:8,marginTop:2,padding:"1px 4px",borderRadius:3,fontWeight:500,
                background: trendStates[d.symbol]==="UPTREND" ? T.profit+"25" :
                            trendStates[d.symbol]==="DOWNTREND" ? T.loss+"25" : T.warning+"20",
                color:      trendStates[d.symbol]==="UPTREND" ? T.profit :
                            trendStates[d.symbol]==="DOWNTREND" ? T.loss : T.warning}}>
                {trendStates[d.symbol]==="UPTREND" ? "↑ up" :
                 trendStates[d.symbol]==="DOWNTREND" ? "↓ down" : "→ neutral"}
              </div>
            )}
            {rallySignals && rallySignals[d.symbol] && (
              <div style={{fontSize:8,marginTop:1,padding:"1px 4px",borderRadius:3,fontWeight:600,
                background:T.profit+"35",color:T.profit}}>
                RALLY {rallySignals[d.symbol].intraday_pct > 0 ? "+" : ""}{rallySignals[d.symbol].intraday_pct?.toFixed(1)}%
              </div>
            )}
            {vwapData && vwapData[d.symbol] && (
              <div style={{fontSize:8,marginTop:1,padding:"1px 3px",borderRadius:3,
                color: vwapData[d.symbol].above_vwap ? T.profit : T.loss}}>
                {vwapData[d.symbol].above_vwap ? "↑" : "↓"} VWAP ${vwapData[d.symbol].vwap?.toFixed(1)}
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

  // Poll intraday state every 5s so button always reflects truth
  React.useEffect(() => {
    const sync = () => fetch(`${BASE}/api/state`).then(r=>r.json()).then(d=>{
      if (d.intraday_mode !== undefined) setIntradayOn(d.intraday_mode);
    }).catch(()=>{});
    sync();                                    // immediate on mount
    const id = setInterval(sync, 5000);        // then every 5s
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
      if (d.success) {
        setIntradayOn(next);
        setMsg(next ? 'Scanning every 2 min · Auto-close 3:45 PM ET' : 'Back to 10-min scans');
      } else setMsg(d.error || 'Failed');
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
    <div style={{display:'flex',alignItems:'center',gap:6,marginLeft:'auto',flexShrink:0}}>
      {msg && <span style={{fontSize:9,color:T.profit,maxWidth:160}}>{msg}</span>}
      <button onClick={closeAll}
        style={{fontSize:9,padding:'2px 8px',borderRadius:6,cursor:'pointer',border:`0.5px solid ${T.loss}55`,
          background:T.loss+'15', color:T.loss, fontWeight:500}}>
        Close all
      </button>
      <button onClick={toggle} disabled={loading}
        style={{fontSize:9,padding:'2px 10px',borderRadius:6,cursor:'pointer',fontWeight:500,
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

  // Auto-load once on mount
  React.useEffect(()=>{ load(); }, []);

  if (!loaded && !loading) return null;
  if (scores.length === 0 && !loading) return null;

  const top5 = scores.slice(0,8);
  return (
    <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 16px",marginTop:8}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
        <div>
          <span style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em"}}>
            Pre-market heat
          </span>
          {scores[0] && (
            <span style={{fontSize:10,marginLeft:8,color:T.profit,fontWeight:500}}>
              top pick: {scores[0].symbol} ({scores[0].heat_score.toFixed(1)}/10)
            </span>
          )}
        </div>
        <button onClick={load} disabled={loading}
          style={{fontSize:10,padding:"2px 10px",borderRadius:8,cursor:"pointer",border:"none",
            background:loading?T.bg3:T.accent+"33",color:loading?T.textMuted:T.accent}}>
          {loading?"...":"Refresh"}
        </button>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:4}}>
        {top5.map((s,i)=>{
          const heat = s.heat_score;
          const color = heat>=7?T.profit:heat>=5?T.accent:T.textMuted;
          return (
            <div key={s.symbol} style={{padding:"6px 8px",borderRadius:6,
              background: i===0 ? T.profit+"15" : T.bg3,
              border:`0.5px solid ${i===0?T.profit+"44":T.border}`}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                <span style={{fontSize:11,fontWeight:600,color:T.textPrimary}}>{s.symbol}</span>
                <span style={{fontSize:11,fontWeight:500,color}}>{heat.toFixed(1)}</span>
              </div>
              <div style={{fontSize:9,color:T.textMuted,marginTop:1,overflow:"hidden",
                textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{s.reason||`RSI ${s.rsi}`}</div>
              {s.gap_pct !== 0 && (
                <div style={{fontSize:9,color:s.gap_pct>0?T.profit:T.loss,marginTop:1}}>
                  {s.gap_pct>0?"+":""}{s.gap_pct.toFixed(1)}% gap
                </div>
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

  if (!state) return <div style={{padding:20,color:T.textMuted,fontSize:13}}>Connecting to agent...</div>;

  const acct      = state.account || {};
  const perf      = state.performance || {};
  const positions = state.positions || {};
  const watchlist = state.watchlist || [];
  const decisions = state.recent_decisions || [];
  const curve     = state.equity_curve || [];

  const fmt$   = v => v != null ? `$${Number(v).toLocaleString("en-US", {minimumFractionDigits:2,maximumFractionDigits:2})}` : "—";
  const fmtPnl = v => v != null ? `${v >= 0 ? "+" : ""}$${Math.abs(v).toFixed(2)}` : "—";
  const fmtPct = v => v != null ? `${(v * 100).toFixed(1)}%` : "—";

  const SC = { BUY:T.profit, SELL:T.loss, HOLD:T.textMuted, BLOCKED:T.warning };
  const SB = { BUY:T.profit+"15", SELL:T.loss+"15", HOLD:T.bg3, BLOCKED:T.warning+"15" };

  return (
    <div style={{padding:p,display:"flex",flexDirection:"column",gap:compact?8:12}}>

      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <span style={{fontSize:11,color:T.textMuted,textTransform:"uppercase",letterSpacing:".08em"}}>Dashboard</span>
        <span style={{fontSize:11,color:perf.grade&&perf.grade!=="N/A"?T.signal:T.textMuted}}>Grade: {perf.grade||"N/A"}</span>
      </div>

      {/* Mode banner */}
      {state?.config?.approach && (
        <div style={{display:"flex",alignItems:"center",gap:10,padding:"8px 12px",background:
          state.config.approach==="Profit Maximizer"?T.profit+"15":
          state.config.approach==="Long Term"?T.accent+"15":
          state.config.approach==="Micro Momentum"?"#ff9f0015":T.bg3,
          borderRadius:7,border:`1px solid ${
          state.config.approach==="Profit Maximizer"?T.profit+"33":
          state.config.approach==="Long Term"?T.accent+"33":
          state.config.approach==="Micro Momentum"?"#ff9f0055":T.border}`}}>
          <div style={{width:6,height:6,borderRadius:"50%",background:
            state.config.approach==="Profit Maximizer"?T.profit:
            state.config.approach==="Long Term"?T.accent:
            state.config.approach==="Micro Momentum"?"#ff9f00":T.textMuted}}/>
          <span style={{fontSize:12,fontWeight:500,color:
            state.config.approach==="Profit Maximizer"?T.profit:
            state.config.approach==="Long Term"?T.accent:T.textPrimary}}>
            {state.config.approach}
          </span>
          <span style={{fontSize:11,color:T.textMuted,marginLeft:4}}>
            {state.config.approach==="Profit Maximizer" && "· Trailing stop · Candlestick exits · Partial profit locking · Max 2 day hold"}
            {state.config.approach==="Long Term"        && "· Wide 7% stop · 20% target · Patient high-conviction holds"}
            {state.config.approach==="Micro Momentum"  && "· 0.25% stop · 0.5% target · 1-min scans · Scalp mode"}
            {state.config.approach==="Balanced"         && `· 3% stop · 6% target · ${state.config.max_open_positions} max positions`}
            {state.config.approach==="Conservative"     && "· 2% stop · 5% target · EOD only"}
            {state.config.approach==="Aggressive"       && "· 5% stop · 10% target · Hourly scans"}
          </span>
          <IntradayControls T={T} api={api}/>
        </div>
      )}

      <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:8}}>
        <MetricCard T={T} compact={compact} label="Portfolio"    value={fmt$(acct.portfolio_value)} color={T.textPrimary}/>
        <MetricCard T={T} compact={compact} label="Day P&L"
          value={fmtPnl(state.reporting?.day_pnl ?? acct.daily_pnl)}
          sub={`${state.reporting?.day_trades ?? 0} trades · ${((state.reporting?.day_win_rate??0)*100).toFixed(0)}% win`}
          color={(state.reporting?.day_pnl??0)>=0?T.profit:T.loss}/>
        <MetricCard T={T} compact={compact} label="Session P&L"
          value={fmtPnl(state.reporting?.session_pnl ?? 0)}
          sub={`${state.reporting?.session_trades ?? 0} trades this session`}
          color={(state.reporting?.session_pnl??0)>=0?T.profit:T.loss}/>
        <MetricCard T={T} compact={compact} label="Week P&L"
          value={fmtPnl(state.reporting?.week_pnl ?? 0)}
          sub={`Month: ${fmtPnl(state.reporting?.month_pnl??0)}`}
          color={(state.reporting?.week_pnl??0)>=0?T.profit:T.loss}/>
        <MetricCard T={T} compact={compact} label="Total P&L"    value={fmtPnl(perf.total_pnl)}    color={perf.total_pnl>=0?T.profit:T.loss}/>
        <MetricCard T={T} compact={compact} label="Buying power" value={fmt$(acct.buying_power)}   color={T.textPrimary}/>
      </div>

      <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"}}>
        <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:8}}>Equity curve</div>
        {curve.length >= 2
          ? <div>
              <EquityChart curve={curve} T={T} compact={true}/>
              <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",margin:"10px 0 6px"}}>
                Trade P&amp;L
              </div>
              <TradeChart trades={state.all_trades || state.recent_trades || []} curve={curve} T={T} compact={true}/>
            </div>
          : <div style={{height:110,display:"flex",alignItems:"center",justifyContent:"center",color:T.textMuted,fontSize:12}}>Curve appears after first completed trades</div>
        }
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:compact?8:12}}>

        <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"}}>
          <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:10}}>Signal heatmap</div>
          <SignalHeatmap decisions={decisions} watchlist={watchlist} T={T} trendStates={state?.trend_states} rallySignals={state?.rally_signals} vwapData={state?.intraday_vwap}/>
        </div>

        <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"}}>
          <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:10}}>Performance</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
            {[
              {label:"Win rate",     value:fmtPct(perf.win_rate),                          color: perf.win_rate>0.5?T.profit:T.accent},
              {label:"Profit factor",value:perf.profit_factor?.toFixed(2)||"—",            color:T.profit},
              {label:"Sharpe",       value:perf.sharpe_ratio?.toFixed(2)||"—",             color:T.accent},
              {label:"Max drawdown", value:fmtPct(perf.max_drawdown),                      color:T.loss},
              {label:"Total trades", value:(perf.total_trades||0).toString(),              color:T.textPrimary},
              {label:"Winners / Losers", value:`${perf.winners||0}W · ${perf.losers||0}L`, color:T.profit},
            ].map(s => (
              <div key={s.label} style={{background:T.bg3,borderRadius:6,padding:"8px 10px"}}>
                <div style={{fontSize:10,color:T.textMuted,marginBottom:3,textTransform:"uppercase",letterSpacing:".04em"}}>{s.label}</div>
                <div style={{fontSize:13,fontWeight:500,color:s.color,fontVariantNumeric:"tabular-nums"}}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>

      </div>

      {Object.keys(positions).length > 0 && (
        <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"}}>
          <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:10}}>Open positions</div>
          {Object.entries(positions).map(([sym, pos]) => {
            const overnight = state?.hold_overnight?.[sym];
            return (
            <div key={sym} style={{display:"flex",alignItems:"center",padding:"7px 0",borderBottom:`1px solid ${T.borderSub}`,gap:6}}>
              <span style={{fontSize:13,fontWeight:600,color:T.textPrimary,width:52}}>{sym}</span>
              {overnight && (
                <span title={overnight.reasons?.join(' · ')} style={{fontSize:9,padding:"1px 6px",borderRadius:4,
                  background:T.profit+"25",color:T.profit,fontWeight:600,whiteSpace:"nowrap"}}>
                  🌙 GAP {overnight.gap_pct>0?"+":""}{(overnight.gap_pct*100).toFixed(1)}%
                </span>
              )}
              <span style={{fontSize:12,color:T.textSecondary,flex:1}}>{pos.qty} @ ${pos.entry_price?.toFixed(2)}</span>
              <span style={{fontSize:12,color:T.textSecondary,fontVariantNumeric:"tabular-nums"}}>now ${pos.current_price?.toFixed(2)}</span>
              <span style={{fontSize:13,fontWeight:500,color:pos.pnl>=0?T.profit:T.loss,fontVariantNumeric:"tabular-nums",marginLeft:8,minWidth:70,textAlign:"right"}}>
                {pos.pnl >= 0 ? "+" : ""}${pos.pnl?.toFixed(2)}
              </span>
            </div>
          );})}
        </div>
      )}

      <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px"}}>
        {/* Discipline panel */}
        {state?.discipline && state.discipline.max_trades_today > 0 && (
          <div style={{
            background:T.cardBg,
            border:`1px solid ${
              state.discipline.week_stopped || state.discipline.cooldown_active
                ? T.loss+"55"
                : state.discipline.profit_lock_active
                ? T.profit+"55"
                : T.border}`,
            borderRadius:8,padding:"12px 14px",marginBottom:8
          }}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
              <span style={{fontSize:11,color:T.textMuted,textTransform:"uppercase",letterSpacing:".06em"}}>Trading discipline</span>
              <span style={{fontSize:11,fontWeight:500,padding:"2px 10px",borderRadius:10,
                background: state.discipline.week_stopped||state.discipline.cooldown_active ? T.loss+"20" : state.discipline.profit_lock_active ? T.profit+"20" : T.profit+"20",
                color: state.discipline.week_stopped||state.discipline.cooldown_active ? T.loss : state.discipline.profit_lock_active ? T.profit : T.profit,
                border:`1px solid ${state.discipline.week_stopped||state.discipline.cooldown_active ? T.loss+"44" : T.profit+"44"}`}}>
                {state.discipline.week_stopped ? "WEEK STOPPED" : state.discipline.cooldown_active ? "COOL-DOWN ACTIVE" : state.discipline.profit_lock_active ? "PROFIT LOCKED" : "TRADING ACTIVE"}
              </span>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:8,marginBottom:6}}>
              {[
                {label:"Trades today", val:`${state.discipline.trades_today} / ${state.discipline.max_trades_today}`, warn: state.discipline.trades_today >= state.discipline.max_trades_today},
                {label:"Wins / Losses", val:`${state.discipline.wins_today}W · ${state.discipline.losses_today}L`, warn: false},
                {label:"Consec. losses", val: state.discipline.consecutive_losses, warn: state.discipline.consecutive_losses >= 2},
                {label:"Week P&L", val:`${state.discipline.pnl_week_pct >= 0 ? "+" : ""}${(state.discipline.pnl_week_pct||0).toFixed(2)}%`, warn: (state.discipline.pnl_week_pct||0) < -3},
              ].map(({label,val,warn})=>(
                <div key={label} style={{background:T.bg3,borderRadius:6,padding:"8px 10px"}}>
                  <div style={{fontSize:10,color:T.textMuted,marginBottom:3}}>{label}</div>
                  <div style={{fontSize:13,fontWeight:500,color:warn?T.loss:T.textPrimary}}>{val}</div>
                </div>
              ))}
              <div style={{background:T.bg3,borderRadius:6,padding:"8px 10px"}}>
                <div style={{fontSize:10,color:T.textMuted,marginBottom:3}}>Auto scans today</div>
                <div style={{fontSize:13,fontWeight:500,color:(state.cycle_count||0)>0?T.profit:T.warn}}>
                  {state.cycle_count||0}
                  <span style={{fontSize:10,fontWeight:400,color:T.textMuted,marginLeft:5}}>
                    {(state.cycle_count||0)>0?"auto ✓":"manual"}
                  </span>
                </div>
              </div>
            </div>
            {/* Progress bar */}
            <div style={{height:3,background:T.border,borderRadius:2,overflow:"hidden",marginBottom:6}}>
              <div style={{height:"100%",borderRadius:2,transition:"width .3s",
                background: state.discipline.trades_today >= state.discipline.max_trades_today ? T.loss : T.profit,
                width:`${Math.min(100, (state.discipline.trades_today/state.discipline.max_trades_today)*100)}%`}}/>
            </div>
            {state.discipline.cooldown_active && (
              <div style={{fontSize:11,color:T.loss,padding:"5px 10px",background:T.loss+"12",borderRadius:5,marginTop:4}}>
                Cool-down active — {state.discipline.cooldown_remaining_min} min until trading resumes
              </div>
            )}
            {state.discipline.profit_lock_active && (
              <div style={{fontSize:11,color:T.profit,padding:"5px 10px",background:T.profit+"12",borderRadius:5,marginTop:4}}>
                Profit lock active — trailing stops tightened to protect today's gains
              </div>
            )}
            {state.discipline.week_stopped && (
              <div style={{fontSize:11,color:T.loss,padding:"5px 10px",background:T.loss+"12",borderRadius:5,marginTop:4}}>
                Weekly circuit breaker — trading stopped until Monday 9:30am ET
              </div>
            )}
          </div>
        )}

        {/* Market Regime Badge */}
      {state?.market_regime?.regime && state.market_regime.regime !== 'UNKNOWN' && (() => {
        const r = state.market_regime;
        const colors = {
          BULL:     {bg:"var(--color-background-success)", border:"var(--color-border-success)", text:"var(--color-text-success)"},
          BEAR:     {bg:"var(--color-background-danger)",  border:"var(--color-border-danger)",  text:"var(--color-text-danger)"},
          VOLATILE: {bg:"var(--color-background-warning)", border:"var(--color-border-warning)", text:"var(--color-text-warning)"},
          RANGING:  {bg:"var(--color-background-secondary)",border:"var(--color-border-secondary)",text:"var(--color-text-secondary)"},
        };
        const c = colors[r.regime] || colors.RANGING;
        return (
          <div style={{display:"flex",alignItems:"center",gap:10,padding:"8px 14px",
            background:c.bg,border:`0.5px solid ${c.border}`,borderRadius:8,marginBottom:8}}>
            <div style={{width:8,height:8,borderRadius:"50%",background:c.text,flexShrink:0}}/>
            <span style={{fontSize:12,fontWeight:500,color:c.text}}>{r.regime} market</span>
            <span style={{fontSize:11,color:c.text,opacity:.8,flex:1}}>{r.reason}</span>
            <span style={{fontSize:11,color:c.text,opacity:.8}}>
              SPY {r.spy_trend} · RSI {r.spy_rsi} · VIX~{r.vix_est}
            </span>
            <span style={{fontSize:11,color:c.text,opacity:.8}}>
              gates: conv≥{r.conviction_threshold} conf≥{(r.confidence_threshold*100).toFixed(0)}%
            </span>
            <span style={{fontSize:10,padding:"1px 7px",borderRadius:8,
              background:"var(--color-background-secondary)",color:"var(--color-text-secondary)",
              border:"0.5px solid var(--color-border-tertiary)"}}>
              Layer 1 + 2 active
            </span>
          </div>
        );
      })()}

      {/* Strategy Health Panel */}
        {state?.recent_decisions?.length > 0 && (() => {
          // Compute strategy vote distribution from decisions
          const roleColors = {
            "Trend":         {bg:"var(--color-background-success)", border:"var(--color-border-success)", text:"var(--color-text-success)"},
            "Counter-trend": {bg:"var(--color-background-danger)",  border:"var(--color-border-danger)",  text:"var(--color-text-danger)"},
            "Neutral":       {bg:"var(--color-background-info)",    border:"var(--color-border-info)",    text:"var(--color-text-info)"},
          };
          const roleMap = {
            "Momentum":"Trend","Breakout":"Trend","TrendStrength":"Trend","EarningsMomentum":"Trend",
            "MeanReversion":"Counter-trend","Fibonacci":"Counter-trend",
            "CandleReversal":"Neutral","CandleContinuation":"Neutral","Divergence":"Neutral",
            "VolumeConfirmation":"Neutral","MultiTimeframe":"Neutral","TrendRegime":"Neutral",
          };
          const agg = {};
          (state.recent_decisions||[]).forEach(dec => {
            (dec.strategy_signals||[]).forEach(sig => {
              const name = sig.strategy || "Unknown";
              const action = sig.action || "HOLD";
              const sym = dec.symbol || "";
              if (!agg[name]) agg[name] = {role: roleMap[name]||"Neutral", buys:[], sells:[], holds:[]};
              if (action==="BUY") agg[name].buys.push(sym);
              else if (action==="SELL") agg[name].sells.push(sym);
              else agg[name].holds.push(sym);
            });
          });

          const strategies = Object.entries(agg)
            .map(([name,d]) => ({name, ...d}))
            .sort((a,b) => b.buys.length - a.buys.length);

          // Compute net effect — find cancellation pairs
          const trendBuys = new Set();
          const counterSells = new Set();
          (state.recent_decisions||[]).forEach(dec => {
            (dec.strategy_signals||[]).forEach(sig => {
              if ((roleMap[sig.strategy]==="Trend") && sig.action==="BUY") trendBuys.add(dec.symbol);
              if ((roleMap[sig.strategy]==="Counter-trend") && sig.action==="SELL") counterSells.add(dec.symbol);
            });
          });
          const cancelled = [...trendBuys].filter(s => counterSells.has(s));

          if (strategies.length === 0) return null;
          return (
            <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px",marginBottom:8}}>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
                <span style={{fontSize:11,color:T.textMuted,textTransform:"uppercase",letterSpacing:".06em"}}>Strategy vote distribution</span>
                {cancelled.length > 0 && (
                  <span style={{fontSize:11,padding:"2px 10px",borderRadius:10,
                    background:"var(--color-background-warning)",color:"var(--color-text-warning)",
                    border:"0.5px solid var(--color-border-warning)"}}>
                    {cancelled.length} collision{cancelled.length>1?"s":""} detected
                  </span>
                )}
              </div>

              {strategies.map(s => {
                const rc = roleColors[s.role] || roleColors["Neutral"];
                const hasCollision = s.role==="Counter-trend" && s.sells.some(sym => trendBuys.has(sym));
                return (
                  <div key={s.name} style={{
                    display:"flex",alignItems:"flex-start",gap:10,padding:"7px 0",
                    borderBottom:`0.5px solid ${T.border}`
                  }}>
                    {/* Strategy name + role badge */}
                    <div style={{minWidth:160}}>
                      <div style={{fontSize:12,fontWeight:500,color:T.textPrimary,marginBottom:3}}>{s.name}</div>
                      <span style={{fontSize:9,padding:"2px 8px",borderRadius:4,fontWeight:500,letterSpacing:".03em",
                        background:rc.bg,color:rc.text,border:`0.5px solid ${rc.border}`,textTransform:"uppercase"}}>{s.role}</span>
                    </div>

                    {/* BUY symbols */}
                    <div style={{flex:1}}>
                      {s.buys.length > 0 && (
                        <div style={{display:"flex",gap:4,flexWrap:"wrap",alignItems:"center",marginBottom:3}}>
                          <span style={{fontSize:9,fontWeight:500,color:"var(--color-text-success)",
                            background:"var(--color-background-success)",border:"0.5px solid var(--color-border-success)",
                            padding:"1px 5px",borderRadius:4,minWidth:24,textAlign:"center"}}>BUY</span>
                          {s.buys.map(sym => (
                            <span key={sym} style={{fontSize:10,padding:"2px 7px",borderRadius:6,fontWeight:500,
                              background:"#1a3a2a",color:"#4ade80",
                              border:"0.5px solid #2d6a47"}}>{sym}</span>
                          ))}
                        </div>
                      )}
                      {s.sells.length > 0 && (
                        <div style={{display:"flex",gap:4,flexWrap:"wrap",alignItems:"center",marginBottom:3}}>
                          <span style={{fontSize:9,fontWeight:500,color:"var(--color-text-danger)",
                            background:"var(--color-background-danger)",border:"0.5px solid var(--color-border-danger)",
                            padding:"1px 5px",borderRadius:4,minWidth:24,textAlign:"center"}}>SELL</span>
                          {s.sells.map(sym => (
                            <span key={sym} style={{
                              fontSize:10,padding:"2px 7px",borderRadius:6,fontWeight:500,
                              background: trendBuys.has(sym) ? "#3a1a1a" : "var(--color-background-secondary)",
                              color: trendBuys.has(sym) ? "#f87171" : "var(--color-text-secondary)",
                              border: trendBuys.has(sym) ? "0.5px solid #7a3030" : "0.5px solid var(--color-border-tertiary)",
                            }}>{sym}{trendBuys.has(sym) && <span style={{fontSize:8,marginLeft:3,opacity:.7}}>clash</span>}</span>
                          ))}
                          {hasCollision && <span style={{fontSize:10,color:"var(--color-text-warning)",marginLeft:2}}>cancelling trend</span>}
                        </div>
                      )}
                      {s.buys.length===0 && s.sells.length===0 && (
                        <span style={{fontSize:10,color:T.textMuted,fontStyle:"italic"}}>no signal</span>
                      )}
                    </div>

                    {/* Net score contribution */}
                    <div style={{minWidth:60,textAlign:"right",fontSize:11,color:
                      s.buys.length > s.sells.length ? "var(--color-text-success)" :
                      s.sells.length > s.buys.length ? "var(--color-text-danger)" : T.textMuted}}>
                      <span style={{color:s.buys.length>s.sells.length?"var(--color-text-success)":s.sells.length>s.buys.length?"var(--color-text-danger)":"var(--color-text-tertiary)"}}>
                        {s.buys.length > 0 && `+${s.buys.length}`}
                        {s.buys.length>0 && s.sells.length>0 && " / "}
                        {s.sells.length > 0 && `−${s.sells.length}`}
                        {s.buys.length===0 && s.sells.length===0 && "—"}
                      </span>
                    </div>
                  </div>
                );
              })}

              {/* Net effect summary */}
              {cancelled.length > 0 && (
                <div style={{marginTop:8,padding:"7px 10px",background:"var(--color-background-warning)",
                  border:"0.5px solid var(--color-border-warning)",borderRadius:6,fontSize:11,
                  color:"var(--color-text-warning)",lineHeight:1.6}}>
                  Counter-trend strategies are cancelling trend BUYs on: <strong>{cancelled.join(", ")}</strong>.
                  {" "}Mean Reversion + Fibonacci are filtered in Profit Maximizer mode.
                </div>
              )}
            </div>
          );
        })()}

        {/* Conviction breakdown strip — shows what pushed each score */}
        {state?.recent_decisions?.length > 0 && (
          <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"10px 14px",marginBottom:8}}>
            <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".06em",marginBottom:8}}>Conviction breakdown — how each score was built</div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(180px,1fr))",gap:6}}>
              {(state.recent_decisions||[]).slice(0,8).map((d, idx) => {
                const score = d.conviction_score || 0;
                const pct = Math.min(100, Math.max(0, (score / 5) * 100));
                const color = score >= 2.5 ? T.profit : score >= 1.5 ? T.warn : score >= 0 ? T.textMuted : T.loss;
                return (
                  <div key={`${d.symbol}-${idx}`} style={{background:T.bg3,borderRadius:6,padding:"7px 10px"}}>
                    <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
                      <span style={{fontSize:12,fontWeight:500,color:T.textPrimary}}>{d.symbol}</span>
                      <span style={{fontSize:12,fontWeight:500,color}}>{score >= 0 ? "+" : ""}{score.toFixed(2)}</span>
                    </div>
                    <div style={{height:4,background:T.border,borderRadius:2,overflow:"hidden",position:"relative"}}>
                      <div style={{height:"100%",width:`${pct}%`,background:color,borderRadius:2,transition:"width .3s"}}/>
                      <div style={{position:"absolute",left:"50%",top:0,width:1,height:"100%",background:T.border}}/>
                    </div>
                    <div style={{fontSize:10,color:T.textMuted,marginTop:3}}>
                    {d.action}
                    {d.conviction_score >= 1.5 && <span style={{fontSize:9,marginLeft:4,color:"var(--color-text-success)"}}>MTF</span>}
                  </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:8}}>Recent decisions</div>
        {decisions.length === 0
          ? <div style={{fontSize:12,color:T.textMuted,padding:"8px 0"}}>No decisions yet — hit Scan now to run the agent</div>
          : decisions.slice(0, 6).map((d, i) => {
              const col = SC[d.action] || T.textMuted;
              return (
                <div key={i} style={{display:"flex",alignItems:"center",padding:"6px 0",borderBottom:`1px solid ${T.borderSub}`}}>
                  <span style={{fontSize:10,color:T.textMuted,fontVariantNumeric:"tabular-nums",width:48}}>{d.timestamp?.slice(11,16)||"—"}</span>
                  <span style={{fontSize:12,fontWeight:600,color:T.textPrimary,width:48}}>{d.symbol}</span>
                  <span style={{fontSize:10,fontWeight:700,padding:"2px 7px",borderRadius:4,background:SB[d.action]||T.bg3,color:col,marginRight:8,minWidth:48,textAlign:"center"}}>{d.action}</span>
                  <span style={{fontSize:11,color:T.textSecondary,flex:1,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{(d.top_reasons||[])[0]||d.reason||""}</span>
                </div>
              );
            })
        }
      </div>



      {/* Phase 3: Adaptive Intelligence Panel */}
      {state.adaptive && (
        <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 16px",marginTop:8}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
            <span style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em"}}>
              Adaptive intelligence · Phase 3
            </span>
            <span style={{fontSize:10,padding:"2px 8px",borderRadius:10,
              background:state.adaptive.recommendation ? T.profit+"20" : T.warn+"20",
              color:state.adaptive.recommendation ? T.profit : T.warn,
              border:`0.5px solid ${state.adaptive.recommendation ? T.profit+"44" : T.warn+"44"}`}}>
              {state.adaptive.recommendation
                ? `${(state.adaptive.recommendation.confidence*100).toFixed(0)}% confident`
                : `${state.adaptive.trades_until_next} trades until active`}
            </span>
          </div>
          {state.adaptive.recommendation ? (
            <div>
              <div style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:8,marginBottom:8}}>
                {[
                  {label:"Conviction floor",
                   val: state.adaptive.recommendation.conviction_floor?.toFixed(1),
                   color:T.profit},
                  {label:"Min strategies",
                   val: state.adaptive.recommendation.min_strategies,
                   color:T.accent},
                  {label:"Based on trades",
                   val: state.adaptive.recommendation.based_on_trades,
                   color:T.textPrimary},
                ].map(m=>(
                  <div key={m.label} style={{background:T.bg3,borderRadius:6,padding:"7px 10px"}}>
                    <div style={{fontSize:9,color:T.textMuted,textTransform:"uppercase",letterSpacing:".04em",marginBottom:2}}>{m.label}</div>
                    <div style={{fontSize:14,fontWeight:500,color:m.color}}>{m.val}</div>
                  </div>
                ))}
              </div>
              <div style={{fontSize:11,color:T.textSecondary,background:T.bg3,
                borderRadius:6,padding:"7px 10px",lineHeight:1.6}}>
                {state.adaptive.recommendation.summary}
              </div>
            </div>
          ) : (
            <div style={{fontSize:11,color:T.textMuted,lineHeight:1.7}}>
              Learning from your trade history. Need {state.adaptive.trades_until_next} more trade{state.adaptive.trades_until_next!==1?"s":""} to activate.
              Once active, conviction thresholds auto-adjust every 5 trades based on what's actually working.
            </div>
          )}
        </div>
      )}

      {/* Phase 3: Intraday mode controls */}
      <IntradayControls T={T} api={api}/>

      {/* Live rally detector */}
      {state?.rally_signals && Object.keys(state.rally_signals).length > 0 && (
        <div style={{background:T.profit+"15",border:`1px solid ${T.profit}44`,borderRadius:8,padding:"10px 16px",marginTop:8}}>
          <div style={{fontSize:10,color:T.profit,textTransform:"uppercase",letterSpacing:".05em",marginBottom:8,fontWeight:500}}>
            Rally alert — {Object.keys(state.rally_signals).length} stock{Object.keys(state.rally_signals).length>1?"s":""} running today
          </div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            {Object.entries(state.rally_signals)
              .sort((a,b)=>b[1].rally_score-a[1].rally_score)
              .map(([sym,sig])=>(
                <div key={sym} style={{background:T.profit+"20",borderRadius:6,padding:"5px 10px",
                  border:`0.5px solid ${T.profit}66`}}>
                  <span style={{fontSize:12,fontWeight:600,color:T.profit}}>{sym}</span>
                  <span style={{fontSize:11,color:T.profit,marginLeft:6}}>
                    {sig.intraday_pct>0?"+":""}{sig.intraday_pct?.toFixed(1)}%
                  </span>
                  <span style={{fontSize:10,color:T.textMuted,marginLeft:4}}>{sig.vol_ratio?.toFixed(1)}x vol</span>
                  {sig.breaking_high && <span style={{fontSize:9,color:T.profit,marginLeft:4}}>↑ 20d high</span>}
                </div>
              ))
            }
          </div>
        </div>
      )}

      {/* Pre-market heat map */}
      <PremarketPanel T={T} api={api}/>

      {/* Recent completed trades */}
      {(state.all_trades || state.recent_trades) && (state.all_trades || state.recent_trades).length > 0 && (
        <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"12px 14px",marginTop:8}}>
          <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:10}}>
            Completed trades <span style={{color:T.textMuted,fontWeight:400}}>({(state.all_trades||state.recent_trades||[]).length} of {state.portfolio?.total_trades||0})</span>
          </div>
          {(state.all_trades||state.recent_trades||[]).slice().reverse().map((t,i)=>{
            const won = t.pnl >= 0;
            return (
              <div key={i} style={{display:"flex",alignItems:"center",gap:10,padding:"6px 0",
                borderBottom:`0.5px solid ${T.border}44`,fontSize:11}}>
                <span style={{fontWeight:600,minWidth:44,color:T.textPrimary}}>{t.symbol}</span>
                <span style={{fontSize:10,padding:"2px 7px",borderRadius:10,fontWeight:600,
                  background:won?T.profit+"20":T.loss+"20",color:won?T.profit:T.loss}}>
                  {won?"WIN":"LOSS"}
                </span>
                <span style={{color:won?T.profit:T.loss,fontWeight:500,minWidth:60,fontVariantNumeric:"tabular-nums"}}>
                  {won?"+":""}${t.pnl?.toFixed(2)}
                </span>
                <span style={{color:T.textMuted,flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                  {t.exit_reason}
                </span>
                <span style={{color:T.textMuted,fontSize:10}}>
                  {t.exit_time?.substring(11,16)} UTC
                </span>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
}
