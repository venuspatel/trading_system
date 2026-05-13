import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';
import EquityChart from '../components/EquityChart';

const C = { bg:'#0a0a0a', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', green:'#4ade80', red:'#f87171', amber:'#fbbf24', white:'#ffffff', muted:'#555555', dim:'#333333' };

function fmt(n) { return '$' + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits:0 }); }

export default function HomeScreen() {
  const { apiBase } = useApp();
  const [state, setState]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [updated, setUpdated] = useState(null);
  const [scrollEnabled, setScrollEnabled] = useState(true);

  useEffect(() => {
    fetchState();
    const t = setInterval(fetchState, 30000);
    return () => clearInterval(t);
  }, []);

  async function fetchState() {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 10000);
      const res  = await fetch(`${apiBase}/api/state`, { signal: controller.signal });
      clearTimeout(timer);
      const data = await res.json();
      setState(data);
      setError(null);
      setUpdated(new Date());
    } catch (e) {
      setError('Cannot reach agent');
    } finally {
      setLoading(false);
    }
  }

  if (loading) return (
    <View style={s.center}>
      <ActivityIndicator color={C.blue} />
      <Text style={s.loadTxt}>Connecting to agent...</Text>
    </View>
  );

  if (error) return (
    <View style={s.center}>
      <Text style={s.errIcon}>⚠</Text>
      <Text style={s.errTxt}>{error}</Text>
      <Text style={s.errSub}>Make sure cloudflared is running on your Mac</Text>
      <TouchableOpacity style={s.retryBtn} onPress={fetchState}>
        <Text style={s.retryTxt}>Retry</Text>
      </TouchableOpacity>
    </View>
  );

  const rep       = state?.reporting  || {};
  const cfg       = state?.config     || {};
  const acct      = state?.account    || {};
  const port      = state?.portfolio  || {};
  const status    = state?.agent_status || 'unknown';
  const equity    = acct.equity       || acct.portfolio_value || 0;
  const dayPnl    = acct.daily_pnl    || rep.day_pnl || 0;
  const winRate   = port.win_rate     || rep.win_rate || 0;
  const posObj   = state?.positions || state?.open_positions || {};
  const positions = Object.entries(posObj).map(([sym, p]) => ({ symbol:sym, ...p }));
  const cycle     = state?.cycle_count || 0;
  const isRunning = ['running','scanning'].includes(status);
  const pnlColor  = dayPnl >= 0 ? C.green : C.red;
  const grade     = state?.performance?.grade || '';

  // Top signals from recent decisions that are BUY and not blocked by market close
  const signals = (state?.recent_decisions || [])
    .filter(d => d.action === 'BUY' || (d.conviction_score > 2.0 && d.buy_signals >= 2))
    .slice(0, 3);

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView style={s.scroll} showsVerticalScrollIndicator={false} scrollEnabled={scrollEnabled}>

        <View style={s.header}>
          <View>
            <Text style={s.agentName}>TradeAgent V1</Text>
            <Text style={s.agentSub}>{cfg.approach || 'Profit Maximizer'}</Text>
          </View>
          <View style={s.headerRight}>
            <View style={[s.badge, { borderColor: isRunning ? C.green : C.dim }]}>
              <View style={[s.dot, { backgroundColor: isRunning ? C.green : C.dim }]} />
              <Text style={[s.badgeTxt, { color: isRunning ? C.green : C.muted }]}>
                {isRunning ? 'Running' : status}
              </Text>
            </View>
            <Text style={s.cycleTxt}>Cycle {cycle} {grade ? `· Grade ${grade}` : ''}</Text>
          </View>
        </View>

        <EquityChart
          equityCurve={state?.equity_curve}
          syntheticCurve={state?.synthetic_curve}
          recentTrades={state?.recent_trades}
          onDragStart={() => setScrollEnabled(false)}
          onDragEnd={() => setScrollEnabled(true)}
        />

        <View style={s.grid}>
          <View style={s.metric}>
            <Text style={s.mLabel}>Win rate</Text>
            <Text style={s.mVal}>{(winRate*100).toFixed(0)}%</Text>
          </View>
          <View style={s.metric}>
            <Text style={s.mLabel}>Positions</Text>
            <Text style={[s.mVal,{color:C.blue}]}>{positions.length} / {cfg.max_open_positions||10}</Text>
          </View>
          <View style={s.metric}>
            <Text style={s.mLabel}>Stop</Text>
            <Text style={s.mVal}>{((cfg.stop_loss_pct||0.01)*100).toFixed(1)}%</Text>
          </View>
          <View style={s.metric}>
            <Text style={s.mLabel}>TP</Text>
            <Text style={s.mVal}>{((cfg.take_profit_pct||0.03)*100).toFixed(1)}%</Text>
          </View>
        </View>

        {/* Stats panels — mirrors dashboard top row */}
        <View style={s.statPanels}>
          <View style={s.statPanel}>
            <Text style={s.spLabel}>Day P&L</Text>
            <Text style={[s.spVal, { color: dayPnl >= 0 ? C.green : C.red }]}>
              {dayPnl >= 0 ? '+' : '-'}{fmt(dayPnl)}
            </Text>
            <Text style={s.spSub}>{rep.day_trades || 0} trades · {((rep.day_win_rate||0)*100).toFixed(0)}% win</Text>
          </View>
          <View style={s.statPanel}>
            <Text style={s.spLabel}>Total P&L</Text>
            <Text style={[s.spVal, { color: (port.total_pnl||0) >= 0 ? C.green : C.red }]}>
              {(port.total_pnl||0) >= 0 ? '+' : '-'}{fmt(port.total_pnl||0)}
            </Text>
            <Text style={s.spSub}>{port.total_trades||0} trades all-time</Text>
          </View>
          <View style={s.statPanel}>
            <Text style={s.spLabel}>Win rate</Text>
            <Text style={s.spVal}>{((port.win_rate||0)*100).toFixed(1)}%</Text>
            <Text style={s.spSub}>{port.winners||0}W · {port.losers||0}L</Text>
          </View>
          <View style={s.statPanel}>
            <Text style={s.spLabel}>Max drawdown</Text>
            <Text style={[s.spVal, { color: C.amber }]}>{((port.max_drawdown||0)*100).toFixed(1)}%</Text>
            <Text style={s.spSub}>Sharpe {(port.sharpe||0).toFixed(2)}</Text>
          </View>
        </View>



        {/* Open Positions Table — matches dashboard style */}
        <View style={s.tableCard}>
          <View style={s.tableHeader}>
            <Text style={s.tableTitle}>Open positions</Text>
            <Text style={s.tableSlots}>{positions.length} / {cfg.max_open_positions||10} slots</Text>
          </View>
          {positions.length === 0 ? (
            <Text style={s.tableEmptyTxt}>No open positions</Text>
          ) : <>
            <View style={s.tableColRow}>
              <Text style={[s.tableCol, {flex:1.5}]}>Symbol</Text>
              <Text style={[s.tableCol, {flex:2}]}>Qty @ Entry</Text>
              <Text style={[s.tableCol, {flex:1.2, textAlign:'right'}]}>Price</Text>
              <Text style={[s.tableCol, {flex:1.2, textAlign:'right'}]}>P&L</Text>
            </View>
            {positions.map((p, i) => {
              const pnl     = parseFloat(p.pnl || 0);
              const entry   = parseFloat(p.entry_price || 0);
              const current = parseFloat(p.current_price || 0);
              const pnlCol  = pnl >= 0 ? C.green : C.red;
              return (
                <View key={i} style={[s.tableRow, i < positions.length-1 && s.tableRowBorder]}>
                  <View style={{flex:1.5}}>
                    <Text style={s.tableSym}>{p.symbol}</Text>
                    <Text style={s.tableQty}>{p.qty} shares</Text>
                  </View>
                  <View style={{flex:2}}>
                    <Text style={s.tableEntry}>{p.qty} @ ${entry.toFixed(2)}</Text>
                    {p.stop_loss ? <Text style={s.tableStop}>SL ${parseFloat(p.stop_loss).toFixed(2)}</Text> : null}
                  </View>
                  <View style={{flex:1.2, alignItems:'flex-end'}}>
                    <Text style={s.tableCurrent}>${current.toFixed(2)}</Text>
                  </View>
                  <View style={{flex:1.2, alignItems:'flex-end'}}>
                    <Text style={[s.tablePnl, {color:pnlCol}]}>
                      {pnl>=0?'+':''}{pnl.toFixed(2)}
                    </Text>
                    <Text style={[s.tablePnlPct, {color:pnlCol}]}>
                      {((p.pnl_pct||0)*100).toFixed(2)}%
                    </Text>
                  </View>
                </View>
              );
            })}
          </>}
        </View>

        {signals.length > 0 && <>
          <Text style={s.secLabel}>Top signals</Text>
          {signals.map((sig,i) => (
            <View key={i} style={s.row}>
              <Text style={s.rowSym}>{sig.symbol}</Text>
              <Text style={s.rowSub}>conv {sig.conviction_score>0?'+':''}{sig.conviction_score?.toFixed(2)}</Text>
              <View style={s.buyBadge}><Text style={s.buyTxt}>BUY</Text></View>
            </View>
          ))}
        </>}

        <View style={s.statsRow}>
          <View style={s.stat}>
            <Text style={s.statLabel}>Total P&L</Text>
            <Text style={[s.statVal, {color: (port.total_pnl||0)>=0 ? C.green : C.red}]}>
              {(port.total_pnl||0)>=0?'+':''}{fmt(port.total_pnl||0)}
            </Text>
          </View>
          <View style={s.stat}>
            <Text style={s.statLabel}>Total trades</Text>
            <Text style={s.statVal}>{port.total_trades||0}</Text>
          </View>
          <View style={s.stat}>
            <Text style={s.statLabel}>Max drawdown</Text>
            <Text style={[s.statVal,{color:C.amber}]}>{((port.max_drawdown||0)*100).toFixed(1)}%</Text>
          </View>
        </View>

        <Text style={s.updTxt}>
          Updated {updated?.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',hour12:true})} · auto-refreshes every 30s
        </Text>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:      { flex:1, backgroundColor:C.bg },
  scroll:    { flex:1, paddingHorizontal:16 },
  center:    { flex:1, backgroundColor:C.bg, alignItems:'center', justifyContent:'center', padding:32 },
  loadTxt:   { color:C.muted, fontSize:13, marginTop:12 },
  errIcon:   { fontSize:32, color:C.amber, marginBottom:12 },
  errTxt:    { fontSize:15, fontWeight:'500', color:C.white, marginBottom:6 },
  errSub:    { fontSize:12, color:C.muted, textAlign:'center', marginBottom:20 },
  retryBtn:  { paddingVertical:10, paddingHorizontal:24, backgroundColor:C.surface, borderRadius:20, borderWidth:0.5, borderColor:C.border },
  retryTxt:  { color:C.white, fontSize:13 },
  header:    { flexDirection:'row', justifyContent:'space-between', alignItems:'flex-start', paddingTop:12, marginBottom:20 },
  agentName: { fontSize:20, fontWeight:'500', color:C.white },
  agentSub:  { fontSize:12, color:C.muted, marginTop:2 },
  headerRight:{ alignItems:'flex-end', gap:4 },
  badge:     { flexDirection:'row', alignItems:'center', gap:5, paddingVertical:4, paddingHorizontal:10, borderRadius:20, borderWidth:0.5 },
  dot:       { width:5, height:5, borderRadius:3 },
  badgeTxt:  { fontSize:11, fontWeight:'500' },
  cycleTxt:  { fontSize:10, color:C.muted },
  equityCard:{ backgroundColor:C.surface, borderRadius:16, padding:20, marginBottom:12, borderWidth:0.5, borderColor:C.border, alignItems:'center' },
  eqLabel:   { fontSize:12, color:C.muted, marginBottom:6 },
  eqVal:     { fontSize:36, fontWeight:'500', color:C.white, marginBottom:4 },
  pnlVal:    { fontSize:16, fontWeight:'500' },
  grid:      { flexDirection:'row', gap:8, marginBottom:16 },
  metric:    { flex:1, backgroundColor:C.surface, borderRadius:12, padding:12, borderWidth:0.5, borderColor:C.border },
  mLabel:    { fontSize:10, color:C.muted, marginBottom:4 },
  mVal:      { fontSize:16, fontWeight:'500', color:C.white },
  secLabel:  { fontSize:10, fontWeight:'500', color:C.muted, letterSpacing:0.6, textTransform:'uppercase', marginBottom:8, marginTop:4 },
  row:       { flexDirection:'row', alignItems:'center', backgroundColor:C.surface, borderRadius:10, padding:12, marginBottom:6, borderWidth:0.5, borderColor:C.border },
  rowSym:    { fontSize:13, fontWeight:'500', color:C.white, flex:1 },
  rowSub:    { fontSize:11, color:C.muted, flex:1 },
  rowPnl:    { fontSize:13, fontWeight:'500' },
  buyBadge:  { backgroundColor:'#14532d', paddingVertical:3, paddingHorizontal:10, borderRadius:12 },
  buyTxt:    { fontSize:10, fontWeight:'500', color:C.green },
  statsRow:  { flexDirection:'row', gap:8, marginTop:8, marginBottom:8 },
  stat:      { flex:1, backgroundColor:C.surface, borderRadius:12, padding:12, borderWidth:0.5, borderColor:C.border, alignItems:'center' },
  statLabel: { fontSize:10, color:C.muted, marginBottom:4 },
  statVal:   { fontSize:14, fontWeight:'500', color:C.white },
  updTxt:    { fontSize:10, color:C.dim, textAlign:'center', paddingVertical:20 },
  tableCard:      { backgroundColor:C.surface, borderRadius:12, padding:12, marginBottom:12, borderWidth:0.5, borderColor:C.border },
  tableHeader:    { flexDirection:'row', justifyContent:'space-between', alignItems:'center', marginBottom:8 },
  tableTitle:     { fontSize:12, fontWeight:'500', color:C.white },
  tableSlots:     { fontSize:10, color:C.muted },
  tableColRow:    { flexDirection:'row', paddingBottom:6, borderBottomWidth:0.5, borderBottomColor:C.border, marginBottom:2 },
  tableCol:       { fontSize:9, color:C.muted, textTransform:'uppercase', letterSpacing:0.4 },
  tableRow:       { flexDirection:'row', alignItems:'center', paddingVertical:7 },
  tableRowBorder: { borderBottomWidth:0.5, borderBottomColor:C.dim },
  tableSym:       { fontSize:13, fontWeight:'600', color:C.white },
  tableQty:       { fontSize:10, color:C.muted },
  tableEntry:     { fontSize:11, color:C.muted },
  tableStop:      { fontSize:9, color:C.red, marginTop:1 },
  tableCurrent:   { fontSize:12, color:C.white },
  tablePnl:       { fontSize:12, fontWeight:'500' },
  tablePnlPct:    { fontSize:9, marginTop:1 },
  tableEmptyTxt:  { fontSize:12, color:C.muted, paddingVertical:12, textAlign:'center' },
  tableHeader:    { flexDirection:'row', justifyContent:'space-between', alignItems:'center', marginBottom:10 },
  tableTitle:     { fontSize:12, fontWeight:'500', color:C.white },
  tableSlots:     { fontSize:10, color:C.muted },
  tableColRow:    { flexDirection:'row', paddingBottom:6, borderBottomWidth:0.5, borderBottomColor:C.border, marginBottom:4 },
  tableCol:       { fontSize:10, color:C.muted, textTransform:'uppercase', letterSpacing:0.4 },
  tableRow:       { flexDirection:'row', alignItems:'center', paddingVertical:8 },
  tableRowBorder: { borderBottomWidth:0.5, borderBottomColor:C.dim },
  tableSym:       { fontSize:13, fontWeight:'600', color:C.white },
  tableEntry:     { fontSize:11, color:C.muted },
  tableCurrent:   { fontSize:12, color:C.white },
  tablePnl:       { fontSize:13, fontWeight:'500' },
  tableEmpty:     { paddingVertical:16, alignItems:'center' },
  tableEmptyTxt:  { fontSize:12, color:C.muted },
  statPanels: { flexDirection:'row', flexWrap:'wrap', gap:6, marginBottom:12 },
  statPanel:  { flex:1, minWidth:'45%', backgroundColor:C.surface, borderRadius:10, padding:9, borderWidth:0.5, borderColor:C.border },
  spLabel:    { fontSize:9, color:C.muted, marginBottom:2, textTransform:'uppercase', letterSpacing:0.4 },
  spVal:      { fontSize:15, fontWeight:'500', color:C.white, marginBottom:1 },
  spSub:      { fontSize:9, color:C.muted },
  chartWrap:   { backgroundColor:C.surface, borderRadius:14, padding:14, marginBottom:12, borderWidth:0.5, borderColor:C.border },
  chartLabel:  { fontSize:10, color:C.muted, marginBottom:8, textTransform:'uppercase', letterSpacing:0.6 },
  chartBars:   { flexDirection:'row', alignItems:'flex-end', height:52, gap:2 },
  chartBar:    { flex:1, borderRadius:2 },
  chartFooter: { flexDirection:'row', justifyContent:'space-between', marginTop:4 },
  chartMin:    { fontSize:9, color:C.dim },
  chartMax:    { fontSize:9, color:C.dim },
});
