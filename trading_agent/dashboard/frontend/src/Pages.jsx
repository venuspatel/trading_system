import React, { useState, useEffect } from 'react';

// ── Positions page ────────────────────────────────────────────
export function Positions() {
  const [positions, setPositions] = useState([]);
  const [acct, setAcct]           = useState(null);

  useEffect(() => {
    fetch('/api/positions').then(r => r.json()).then(d => setPositions(d.positions || []));
    fetch('/api/state').then(r => r.json()).then(setAcct);
    const t = setInterval(() => {
      fetch('/api/positions').then(r => r.json()).then(d => setPositions(d.positions || []));
    }, 10000);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{ background:'#0f0f0f', flex:1, overflowY:'auto', padding:'20px 24px' }}>
      <h1 style={{ fontSize:18, fontWeight:500, color:'#e0e0e0', margin:'0 0 4px' }}>Open positions</h1>
      <p style={{ fontSize:13, color:'#444', margin:'0 0 20px' }}>Live positions managed by the agent</p>

      {acct && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:20 }}>
          {[
            { label:'Portfolio value', value:`$${(acct.portfolio_value||0).toLocaleString('en-US',{minimumFractionDigits:2})}`, color:'#e0e0e0' },
            { label:'Day P&L',         value:`${(acct.daily_pnl||0) >= 0 ? '+' : ''}$${Math.abs(acct.daily_pnl||0).toFixed(2)}`, color:(acct.daily_pnl||0) >= 0 ? '#22c55e' : '#ef4444' },
            { label:'Buying power',    value:`$${(acct.buying_power||0).toLocaleString('en-US',{minimumFractionDigits:2})}`, color:'#4d9cf8' },
          ].map(m => (
            <div key={m.label} style={{ background:'#0a0a0a', border:'1px solid #1c1c1c', borderRadius:8, padding:'12px 14px' }}>
              <div style={{ fontSize:10, color:'#333', textTransform:'uppercase', letterSpacing:'.05em', marginBottom:4 }}>{m.label}</div>
              <div style={{ fontSize:20, fontWeight:500, color:m.color, fontVariantNumeric:'tabular-nums' }}>{m.value}</div>
            </div>
          ))}
        </div>
      )}

      {positions.length === 0 ? (
        <div style={{ background:'#0a0a0a', border:'1px solid #1c1c1c', borderRadius:8, padding:'32px',
                      textAlign:'center', color:'#333', fontSize:13 }}>
          No open positions — agent will enter positions at the next EOD scan
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {positions.map(p => (
            <div key={p.symbol} style={{ background:'#0a0a0a', border:'1px solid #1c1c1c',
                                         borderRadius:8, padding:'14px 16px' }}>
              <div style={{ display:'flex', alignItems:'center', marginBottom:10 }}>
                <span style={{ fontSize:16, fontWeight:600, color:'#e0e0e0' }}>{p.symbol}</span>
                <span style={{ fontSize:12, color:'#555', marginLeft:10 }}>{p.qty} shares</span>
                <span style={{ fontSize:16, fontWeight:500, marginLeft:'auto', fontVariantNumeric:'tabular-nums',
                               color: p.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                  {p.pnl >= 0 ? '+' : ''}${p.pnl?.toFixed(2)}
                  <span style={{ fontSize:12, marginLeft:6 }}>({(p.pnl_pct*100).toFixed(2)}%)</span>
                </span>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8 }}>
                {[
                  { label:'Entry price',  value:`$${p.entry_price?.toFixed(2)}`,   color:'#888'   },
                  { label:'Current',      value:`$${p.current_price?.toFixed(2)}`,  color:'#e0e0e0'},
                  { label:'Stop loss',    value:`$${p.stop_loss?.toFixed(2)}`,      color:'#ef4444'},
                  { label:'Take profit',  value:`$${p.take_profit?.toFixed(2)}`,    color:'#22c55e'},
                ].map(f => (
                  <div key={f.label}>
                    <div style={{ fontSize:10, color:'#333', marginBottom:2 }}>{f.label}</div>
                    <div style={{ fontSize:13, fontWeight:500, color:f.color, fontVariantNumeric:'tabular-nums' }}>{f.value}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── History page ──────────────────────────────────────────────
export function History() {
  const [decisions, setDecisions] = useState([]);
  const [portfolio, setPortfolio] = useState(null);

  useEffect(() => {
    fetch('/api/decisions?limit=100').then(r => r.json()).then(d => setDecisions(d.decisions || []));
    fetch('/api/trades').then(r => r.json()).then(d => { setPortfolio({ recent_trades: d.trades||[], all_trades: d.trades||[], count: d.count, total_pnl: d.total_pnl, win_rate: d.win_rate }); });
  }, []);

  return (
    <div style={{ background:'#0f0f0f', flex:1, overflowY:'auto', padding:'20px 24px' }}>
      <h1 style={{ fontSize:18, fontWeight:500, color:'#e0e0e0', margin:'0 0 4px' }}>Trade history</h1>
      <p style={{ fontSize:13, color:'#444', margin:'0 0 20px' }}>All agent decisions with full reasoning</p>

      {(portfolio?.all_trades||portfolio?.recent_trades||[]).length > 0 && (
        <div style={{ marginBottom:20 }}>
          <div style={{ fontSize:11, color:'#444', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:10 }}>
            Completed trades
          </div>
          {(portfolio.all_trades||portfolio.recent_trades||[]).map((t, i) => (
            <div key={i} style={{ background:'#0a0a0a', border:'1px solid #1c1c1c', borderRadius:8,
                                   padding:'12px 14px', marginBottom:6 }}>
              <div style={{ display:'flex', alignItems:'center' }}>
                <span style={{ fontSize:14, fontWeight:600, color:'#e0e0e0' }}>{t.symbol}</span>
                <span style={{ fontSize:11, color:'#555', marginLeft:8 }}>{t.qty} shares</span>
                <span style={{ fontSize:12, color:'#444', marginLeft:8 }}>{t.exit_reason}</span>
                <span style={{ fontSize:14, fontWeight:500, marginLeft:'auto', fontVariantNumeric:'tabular-nums',
                               color: t.pnl >= 0 ? '#22c55e' : '#ef4444' }}>
                  {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(2)} ({(t.pnl_pct*100)?.toFixed(1)}%)
                </span>
              </div>
              <div style={{ fontSize:11, color:'#333', marginTop:4, fontVariantNumeric:'tabular-nums' }}>
                Entry ${t.entry_price?.toFixed(2)} → Exit ${t.exit_price?.toFixed(2)} · {t.strategy}
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize:11, color:'#444', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:10 }}>
        All decisions
      </div>
      {decisions.length === 0 ? (
        <div style={{ background:'#0a0a0a', border:'1px solid #1c1c1c', borderRadius:8,
                      padding:'32px', textAlign:'center', color:'#333', fontSize:13 }}>
          No decisions logged yet — start the agent to begin
        </div>
      ) : decisions.map((d, i) => {
        const isUp  = d.action === 'BUY';
        const isDn  = d.action === 'SELL';
        const isBlk = d.action === 'BLOCKED';
        const ac    = isUp ? '#22c55e' : isDn ? '#ef4444' : isBlk ? '#f59e0b' : '#444';
        const abg   = isUp ? '#0a1a0a' : isDn ? '#1a0a0a' : isBlk ? '#1a1000' : '#111';
        return (
          <div key={i} style={{ background:'#0a0a0a', border:'1px solid #1c1c1c', borderRadius:6,
                                 padding:'10px 14px', marginBottom:4 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
              <span style={{ fontSize:10, color:'#333', fontVariantNumeric:'tabular-nums' }}>
                {d.timestamp ? new Date(d.timestamp).toLocaleString() : '—'}
              </span>
              <span style={{ fontSize:13, fontWeight:600, color:'#e0e0e0' }}>{d.symbol}</span>
              <span style={{ fontSize:11, fontWeight:700, padding:'2px 8px', borderRadius:4,
                             background:abg, color:ac }}>{d.action}</span>
              <span style={{ fontSize:11, color:'#555', marginLeft:'auto' }}>
                conviction {d.conviction_score >= 0 ? '+' : ''}{d.conviction_score?.toFixed(2)}
              </span>
            </div>
            {d.top_reasons?.[0] && (
              <div style={{ fontSize:11, color:'#444' }}>{d.top_reasons[0]}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Settings page ─────────────────────────────────────────────
export function Settings() {
  return (
    <div style={{ background:'#0f0f0f', flex:1, overflowY:'auto', padding:'20px 24px' }}>
      <h1 style={{ fontSize:18, fontWeight:500, color:'#e0e0e0', margin:'0 0 4px' }}>Settings</h1>
      <p style={{ fontSize:13, color:'#444', margin:'0 0 24px' }}>Agent configuration and account settings</p>

      {[
        { title:'Alpaca connection', items:[
          { label:'API mode',     value:'Paper trading' },
          { label:'Account',      value:'Connected' },
          { label:'Data feed',    value:'IEX (free tier)' },
        ]},
        { title:'Scan schedule', items:[
          { label:'Conservative', value:'4:05pm ET daily' },
          { label:'Balanced',     value:'8:30am + 4:05pm ET' },
          { label:'Aggressive',   value:'Hourly 9:30am–4:00pm ET' },
        ]},
        { title:'Revisit list (post-testing)', items:[
          { label:'Multi-timeframe scan',       value:'Planned' },
          { label:'IBKR integration',           value:'Stub ready' },
          { label:'Binance crypto',             value:'Stub ready' },
          { label:'Strategy backtester',        value:'Planned' },
          { label:'ML weight optimiser',        value:'Planned' },
          { label:'News sentiment layer',       value:'Planned' },
          { label:'Options strategies',         value:'Planned' },
        ]},
      ].map(section => (
        <div key={section.title} style={{ background:'#0a0a0a', border:'1px solid #1c1c1c',
                                          borderRadius:8, padding:'14px 16px', marginBottom:12 }}>
          <div style={{ fontSize:13, fontWeight:500, color:'#e0e0e0', marginBottom:12 }}>{section.title}</div>
          {section.items.map(item => (
            <div key={item.label} style={{ display:'flex', justifyContent:'space-between',
                                           padding:'6px 0', borderBottom:'1px solid #111',
                                           fontSize:13 }}>
              <span style={{ color:'#555' }}>{item.label}</span>
              <span style={{ color:'#888' }}>{item.value}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export default Positions;
