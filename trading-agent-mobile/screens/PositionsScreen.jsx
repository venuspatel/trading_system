import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';

const C = { bg:'#0a0a0a', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', green:'#4ade80', red:'#f87171', amber:'#fbbf24', white:'#ffffff', muted:'#555555', dim:'#222222' };

function fmt(n) { return '$' + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits:0 }); }
function fmtP(n) { return (n >= 0 ? '+' : '') + (n * 100).toFixed(2) + '%'; }

export default function PositionsScreen() {
  const { apiBase } = useApp();
  const [state, setState]       = useState(null);
  const [loading, setLoading]   = useState(true);
  const [refreshing, setRefresh] = useState(false);
  const [error, setError]       = useState(null);

  useEffect(() => { fetchState(); const t = setInterval(fetchState, 15000); return () => clearInterval(t); }, []);

  async function fetchState(isRefresh = false) {
    if (isRefresh) setRefresh(true);
    try {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 10000);
      const res  = await fetch(`${apiBase}/api/state`, { signal: controller.signal });
      const data = await res.json();
      setState(data);
      setError(null);
    } catch (e) { setError('Cannot reach agent'); }
    finally { setLoading(false); setRefresh(false); }
  }

  if (loading) return <View style={s.center}><ActivityIndicator color={C.blue}/></View>;

  if (error) return (
    <View style={s.center}>
      <Text style={s.errIcon}>⚠</Text>
      <Text style={s.errTxt}>{error}</Text>
      <TouchableOpacity style={s.retryBtn} onPress={() => fetchState()}>
        <Text style={s.retryTxt}>Retry</Text>
      </TouchableOpacity>
    </View>
  );

  const positions = Object.values(state?.positions || {});
  const cfg       = state?.config || {};
  const acct      = state?.account || {};
  const equity    = acct.equity || acct.portfolio_value || 0;

  // Total unrealized P&L
  const totalUnrealized = positions.reduce((sum, p) => sum + parseFloat(p.unrealized_pl || 0), 0);

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView
        style={s.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => fetchState(true)} tintColor={C.blue}/>}
      >
        <Text style={s.pageTitle}>Positions</Text>

        {/* Summary bar */}
        <View style={s.summaryRow}>
          <View style={s.summaryItem}>
            <Text style={s.summaryLabel}>Open</Text>
            <Text style={s.summaryVal}>{positions.length} / {cfg.max_open_positions || 10}</Text>
          </View>
          <View style={s.summaryItem}>
            <Text style={s.summaryLabel}>Unrealized P&L</Text>
            <Text style={[s.summaryVal, { color: totalUnrealized >= 0 ? C.green : C.red }]}>
              {totalUnrealized >= 0 ? '+' : '-'}{fmt(totalUnrealized)}
            </Text>
          </View>
          <View style={s.summaryItem}>
            <Text style={s.summaryLabel}>Cash</Text>
            <Text style={s.summaryVal}>{fmt(acct.cash || 0)}</Text>
          </View>
        </View>

        {positions.length === 0 ? (
          <View style={s.emptyBox}>
            <Text style={s.emptyIcon}>◎</Text>
            <Text style={s.emptyTxt}>No open positions</Text>
            <Text style={s.emptySub}>
              {state?.agent_status === 'running'
                ? 'Market is closed — positions will open at 6:30 AM PST'
                : 'Agent is not running'}
            </Text>
          </View>
        ) : (
          positions.map((p, i) => {
            const pnl     = parseFloat(p.unrealized_pl || 0);
            const pnlPct  = parseFloat(p.unrealized_plpc || 0);
            const entry   = parseFloat(p.avg_entry_price || p.entry_price || 0);
            const current = parseFloat(p.current_price || 0);
            const qty     = parseInt(p.qty || 0);
            const mktVal  = parseFloat(p.market_value || current * qty || 0);
            const stopPct = cfg.stop_loss_pct || 0.01;
            const tpPct   = cfg.take_profit_pct || 0.03;
            const stopPx  = entry * (1 - stopPct);
            const tpPx    = entry * (1 + tpPct);
            const pnlColor = pnl >= 0 ? C.green : C.red;

            return (
              <View key={i} style={s.card}>
                <View style={s.cardHeader}>
                  <View>
                    <Text style={s.symbol}>{p.symbol}</Text>
                    <Text style={s.qty}>{qty} shares · {fmt(mktVal)}</Text>
                  </View>
                  <View style={s.pnlBlock}>
                    <Text style={[s.pnlMain, { color: pnlColor }]}>
                      {pnl >= 0 ? '+' : '-'}{fmt(pnl)}
                    </Text>
                    <Text style={[s.pnlPct, { color: pnlColor }]}>{fmtP(pnlPct)}</Text>
                  </View>
                </View>

                <View style={s.priceRow}>
                  <View style={s.priceItem}>
                    <Text style={s.priceLabel}>Entry</Text>
                    <Text style={s.priceVal}>${entry.toFixed(2)}</Text>
                  </View>
                  <View style={s.priceItem}>
                    <Text style={s.priceLabel}>Current</Text>
                    <Text style={[s.priceVal, { color: current >= entry ? C.green : C.red }]}>
                      ${current.toFixed(2)}
                    </Text>
                  </View>
                  <View style={s.priceItem}>
                    <Text style={s.priceLabel}>Stop</Text>
                    <Text style={[s.priceVal, { color: C.red }]}>${stopPx.toFixed(2)}</Text>
                  </View>
                  <View style={s.priceItem}>
                    <Text style={s.priceLabel}>Target</Text>
                    <Text style={[s.priceVal, { color: C.green }]}>${tpPx.toFixed(2)}</Text>
                  </View>
                </View>

                {/* Progress bar — how far from stop to target */}
                {entry > 0 && current > 0 && (() => {
                  const range    = tpPx - stopPx;
                  const progress = Math.max(0, Math.min(1, (current - stopPx) / range));
                  return (
                    <View style={s.progressWrap}>
                      <View style={s.progressBg}>
                        <View style={[s.progressFill, { width: `${progress * 100}%`, backgroundColor: pnl >= 0 ? C.green : C.red }]} />
                      </View>
                      <Text style={s.progressLabel}>Stop → Target</Text>
                    </View>
                  );
                })()}
              </View>
            );
          })
        )}

        <Text style={s.pullHint}>Pull down to refresh</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:         { flex:1, backgroundColor:C.bg },
  scroll:       { flex:1, paddingHorizontal:16 },
  center:       { flex:1, backgroundColor:C.bg, alignItems:'center', justifyContent:'center' },
  errIcon:      { fontSize:28, color:C.amber, marginBottom:8 },
  errTxt:       { fontSize:14, color:C.white, marginBottom:16 },
  retryBtn:     { paddingVertical:10, paddingHorizontal:24, backgroundColor:C.surface, borderRadius:20, borderWidth:0.5, borderColor:C.border },
  retryTxt:     { color:C.white, fontSize:13 },
  pageTitle:    { fontSize:22, fontWeight:'500', color:C.white, paddingTop:12, marginBottom:16 },
  summaryRow:   { flexDirection:'row', backgroundColor:C.surface, borderRadius:12, padding:14, marginBottom:16, borderWidth:0.5, borderColor:C.border },
  summaryItem:  { flex:1, alignItems:'center' },
  summaryLabel: { fontSize:10, color:C.muted, marginBottom:3 },
  summaryVal:   { fontSize:14, fontWeight:'500', color:C.white },
  emptyBox:     { alignItems:'center', paddingVertical:60 },
  emptyIcon:    { fontSize:36, color:C.dim, marginBottom:12 },
  emptyTxt:     { fontSize:16, fontWeight:'500', color:C.muted, marginBottom:6 },
  emptySub:     { fontSize:12, color:C.dim, textAlign:'center', paddingHorizontal:32 },
  card:         { backgroundColor:C.surface, borderRadius:14, padding:16, marginBottom:10, borderWidth:0.5, borderColor:C.border },
  cardHeader:   { flexDirection:'row', justifyContent:'space-between', alignItems:'flex-start', marginBottom:14 },
  symbol:       { fontSize:17, fontWeight:'500', color:C.white, marginBottom:2 },
  qty:          { fontSize:11, color:C.muted },
  pnlBlock:     { alignItems:'flex-end' },
  pnlMain:      { fontSize:16, fontWeight:'500' },
  pnlPct:       { fontSize:11, marginTop:2 },
  priceRow:     { flexDirection:'row', marginBottom:12 },
  priceItem:    { flex:1 },
  priceLabel:   { fontSize:10, color:C.muted, marginBottom:3 },
  priceVal:     { fontSize:12, fontWeight:'500', color:C.white },
  progressWrap: { gap:4 },
  progressBg:   { height:3, backgroundColor:C.dim, borderRadius:2, overflow:'hidden' },
  progressFill: { height:'100%', borderRadius:2 },
  progressLabel:{ fontSize:9, color:C.dim },
  pullHint:     { fontSize:10, color:C.dim, textAlign:'center', paddingVertical:20 },
});
