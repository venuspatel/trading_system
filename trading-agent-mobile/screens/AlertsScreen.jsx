import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';

const C = { bg:'#0a0a0a', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', green:'#4ade80', red:'#f87171', amber:'#fbbf24', white:'#ffffff', muted:'#555555', dim:'#222222' };

function timeAgo(dateStr) {
  try {
    const d = new Date(dateStr);
    const diff = Math.floor((Date.now() - d) / 1000);
    if (diff < 60)    return `${diff}s ago`;
    if (diff < 3600)  return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
    return d.toLocaleDateString('en-US', { month:'short', day:'numeric' });
  } catch { return ''; }
}

function getAlertStyle(action) {
  if (action === 'BUY')     return { bg:'#0a2a1a', color:C.green,  icon:'↑' };
  if (action === 'SELL')    return { bg:'#2a0a0a', color:C.red,    icon:'↓' };
  if (action === 'BLOCKED') return { bg:'#1a1200', color:C.amber,  icon:'⊘' };
  return                           { bg:C.surface, color:C.muted,  icon:'○' };
}

function shortReason(reasons) {
  if (!reasons || !reasons.length) return '';
  return reasons[0].slice(0, 50);
}

export default function AlertsScreen() {
  const { apiBase } = useApp();
  const [state, setState]        = useState(null);
  const [loading, setLoading]    = useState(true);
  const [refreshing, setRefresh] = useState(false);

  useEffect(() => {
    fetchState();
    const t = setInterval(fetchState, 15000);
    return () => clearInterval(t);
  }, []);

  async function fetchState(isRefresh = false) {
    if (isRefresh) setRefresh(true);
    try {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 10000);
      const res  = await fetch(`${apiBase}/api/state`, { signal: controller.signal });
      const data = await res.json();
      setState(data);
    } catch (e) {}
    finally { setLoading(false); setRefresh(false); }
  }

  if (loading) return <View style={s.center}><ActivityIndicator color={C.blue}/></View>;

  const decisions   = state?.recent_decisions || [];
  const discipline  = state?.discipline || {};
  const regime      = state?.market_regime || {};

  const buys    = decisions.filter(d => d.action === 'BUY').length;
  const blocked = decisions.filter(d => d.action === 'BLOCKED').length;
  const sells   = decisions.filter(d => d.action === 'SELL').length;

  function renderDecision({ item: d }) {
    const style = getAlertStyle(d.action);
    return (
      <View style={[s.alertCard, { borderLeftColor: style.color }]}>
        <View style={[s.iconBox, { backgroundColor: style.bg }]}>
          <Text style={[s.iconTxt, { color: style.color }]}>{style.icon}</Text>
        </View>
        <View style={s.alertBody}>
          <View style={s.alertTop}>
            <Text style={s.alertSym}>{d.symbol}</Text>
            <View style={[s.actionBadge, { backgroundColor: style.bg }]}>
              <Text style={[s.actionTxt, { color: style.color }]}>{d.action}</Text>
            </View>
          </View>
          <Text style={s.alertReason} numberOfLines={1}>{shortReason(d.top_reasons)}</Text>
          <View style={s.alertBottom}>
            <Text style={s.alertConv}>conv {d.conviction_score > 0 ? '+' : ''}{d.conviction_score?.toFixed(2)}</Text>
            <Text style={s.alertTime}>{timeAgo(d.timestamp)}</Text>
          </View>
        </View>
      </View>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <Text style={s.pageTitle}>Alerts</Text>
        <View style={[s.regimeBadge, { borderColor: regime.regime === 'BULL' ? C.green : C.amber }]}>
          <Text style={[s.regimeTxt, { color: regime.regime === 'BULL' ? C.green : C.amber }]}>
            {regime.regime || 'UNKNOWN'} market
          </Text>
        </View>
      </View>

      {/* Summary */}
      <View style={s.summaryRow}>
        <View style={s.summaryItem}>
          <Text style={s.summaryLabel}>Buys</Text>
          <Text style={[s.summaryVal, { color: C.green }]}>{buys}</Text>
        </View>
        <View style={s.summaryItem}>
          <Text style={s.summaryLabel}>Sells</Text>
          <Text style={[s.summaryVal, { color: C.red }]}>{sells}</Text>
        </View>
        <View style={s.summaryItem}>
          <Text style={s.summaryLabel}>Blocked</Text>
          <Text style={[s.summaryVal, { color: C.amber }]}>{blocked}</Text>
        </View>
        <View style={s.summaryItem}>
          <Text style={s.summaryLabel}>SPY RSI</Text>
          <Text style={s.summaryVal}>{regime.spy_rsi?.toFixed(0) || '--'}</Text>
        </View>
      </View>

      {/* Discipline status */}
      {discipline.cooldown_active && (
        <View style={s.cooldownBanner}>
          <Text style={s.cooldownTxt}>
            Cooldown active — {discipline.cooldown_remaining_min} min remaining
          </Text>
        </View>
      )}

      {discipline.profit_lock_active && (
        <View style={[s.cooldownBanner, { borderColor: C.green }]}>
          <Text style={[s.cooldownTxt, { color: C.green }]}>
            Profit lock active — protecting gains
          </Text>
        </View>
      )}

      <FlatList
        data={decisions}
        keyExtractor={(_, i) => i.toString()}
        renderItem={renderDecision}
        contentContainerStyle={s.list}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => fetchState(true)} tintColor={C.blue}/>}
        ListEmptyComponent={
          <View style={s.empty}>
            <Text style={s.emptyTxt}>No recent decisions</Text>
            <Text style={s.emptySub}>Decisions will appear here during market hours</Text>
          </View>
        }
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:          { flex:1, backgroundColor:C.bg },
  center:        { flex:1, backgroundColor:C.bg, alignItems:'center', justifyContent:'center' },
  header:        { flexDirection:'row', justifyContent:'space-between', alignItems:'center', paddingHorizontal:16, paddingTop:12, paddingBottom:8 },
  pageTitle:     { fontSize:22, fontWeight:'500', color:C.white },
  regimeBadge:   { paddingVertical:4, paddingHorizontal:10, borderRadius:20, borderWidth:0.5 },
  regimeTxt:     { fontSize:11, fontWeight:'500' },
  summaryRow:    { flexDirection:'row', marginHorizontal:16, marginBottom:10, backgroundColor:C.surface, borderRadius:12, padding:14, borderWidth:0.5, borderColor:C.border },
  summaryItem:   { flex:1, alignItems:'center' },
  summaryLabel:  { fontSize:10, color:C.muted, marginBottom:3 },
  summaryVal:    { fontSize:14, fontWeight:'500', color:C.white },
  cooldownBanner:{ marginHorizontal:16, marginBottom:8, padding:10, borderRadius:10, borderWidth:0.5, borderColor:C.amber, backgroundColor:'#1a1200' },
  cooldownTxt:   { fontSize:12, color:C.amber, textAlign:'center' },
  list:          { paddingHorizontal:16, paddingBottom:20 },
  alertCard:     { flexDirection:'row', backgroundColor:C.surface, borderRadius:12, marginBottom:8, borderWidth:0.5, borderColor:C.border, borderLeftWidth:3, overflow:'hidden', gap:12, padding:12 },
  iconBox:       { width:32, height:32, borderRadius:8, alignItems:'center', justifyContent:'center', flexShrink:0 },
  iconTxt:       { fontSize:16, fontWeight:'500' },
  alertBody:     { flex:1 },
  alertTop:      { flexDirection:'row', justifyContent:'space-between', alignItems:'center', marginBottom:3 },
  alertSym:      { fontSize:14, fontWeight:'500', color:C.white },
  actionBadge:   { paddingVertical:2, paddingHorizontal:8, borderRadius:10 },
  actionTxt:     { fontSize:10, fontWeight:'500' },
  alertReason:   { fontSize:11, color:C.muted, marginBottom:4 },
  alertBottom:   { flexDirection:'row', justifyContent:'space-between' },
  alertConv:     { fontSize:11, color:C.dim },
  alertTime:     { fontSize:11, color:C.dim },
  empty:         { alignItems:'center', paddingTop:60, paddingHorizontal:32 },
  emptyTxt:      { fontSize:15, color:C.muted, marginBottom:6 },
  emptySub:      { fontSize:12, color:C.dim, textAlign:'center' },
});
