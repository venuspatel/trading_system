import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';

const C = { bg:'#0a0a0a', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', green:'#4ade80', red:'#f87171', amber:'#fbbf24', white:'#ffffff', muted:'#555555', dim:'#222222' };

function fmtTime(dateStr) {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr).toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', hour12:true });
  } catch { return '—'; }
}

function fmtDate(dateStr) {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr).toLocaleDateString('en-US', { month:'short', day:'numeric' });
  } catch { return '—'; }
}

function shortReason(r) {
  if (!r) return '—';
  return r.replace(/\s*at\s+\$[\d.]+[^).]*\([^)]*\)?/i,'')
          .replace(/\s*\([^)]*\)/g,'')
          .trim()
          .slice(0, 24) || r.slice(0, 24);
}

function isToday(dateStr) {
  if (!dateStr) return false;
  try {
    const d = new Date(dateStr);
    const n = new Date();
    return d.getDate()===n.getDate() && d.getMonth()===n.getMonth() && d.getFullYear()===n.getFullYear();
  } catch { return false; }
}

export default function TradesScreen() {
  const { apiBase } = useApp();
  const [state, setState]        = useState(null);
  const [loading, setLoading]    = useState(true);
  const [refreshing, setRefresh] = useState(false);
  const [filter, setFilter]      = useState('today');

  useEffect(() => { fetchState(); }, []);

  async function fetchState(isRefresh=false) {
    if (isRefresh) setRefresh(true);
    try {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 10000);
      const res  = await fetch(`${apiBase}/api/state`, { signal:controller.signal });
      const data = await res.json();
      setState(data);
    } catch(e) {}
    finally { setLoading(false); setRefresh(false); }
  }

  if (loading) return <View style={s.center}><ActivityIndicator color={C.blue}/></View>;

  const allTrades = (state?.all_trades || []).slice().reverse();
  const port      = state?.portfolio || {};
  const rep       = state?.reporting || {};

  const todayTrades = allTrades.filter(t => isToday(t.exit_time || t.entry_time));

  const filtered = filter === 'today'  ? todayTrades
                 : filter === 'wins'   ? allTrades.filter(t => t.pnl >= 0)
                 : filter === 'losses' ? allTrades.filter(t => t.pnl < 0)
                 : allTrades;

  const wins   = filtered.filter(t => t.pnl >= 0).length;
  const losses = filtered.filter(t => t.pnl < 0).length;
  const totalPnl = filtered.reduce((s,t) => s + (t.pnl||0), 0);

  function renderTrade({ item:t, index }) {
    const isWin = t.pnl >= 0;
    const col   = isWin ? C.green : C.red;
    const entryP = parseFloat(t.entry_price||0).toFixed(2);
    const exitP  = parseFloat(t.exit_price||0).toFixed(2);
    const entryT = fmtTime(t.entry_time);
    const exitT  = fmtTime(t.exit_time);
    const dateStr = fmtDate(t.exit_time || t.entry_time);
    const todayTrade = isToday(t.exit_time || t.entry_time);

    return (
      <View style={[s.tradeRow, { borderLeftColor: col }]}>
        <View style={[s.badge, { backgroundColor: isWin ? '#14532d' : '#7f1d1d' }]}>
          <Text style={[s.badgeTxt, { color: col }]}>{isWin ? 'WIN' : 'LOSS'}</Text>
        </View>
        <View style={s.symBlock}>
          <Text style={s.tradeSym}>{t.symbol}</Text>
          <Text style={s.tradeDate}>{dateStr}</Text>
        </View>
        <View style={s.tradeMid}>
          <Text style={s.tradeReason} numberOfLines={1}>{shortReason(t.exit_reason)}</Text>
          <Text style={s.tradePriceTime} numberOfLines={1}>${entryP}→${exitP} · {entryT}→{exitT}</Text>
        </View>
        <Text style={[s.tradePnl, { color: col }]}>{isWin?'+':''}{(t.pnl||0).toFixed(2)}</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      {/* Stats bar */}
      <View style={s.statsBar}>
        <View style={s.statItem}>
          <Text style={s.statLabel}>P&L</Text>
          <Text style={[s.statVal, { color: totalPnl>=0 ? C.green : C.red }]}>
            {totalPnl>=0?'+':''}{totalPnl>=0?'$'+totalPnl.toFixed(0):'-$'+Math.abs(totalPnl).toFixed(0)}
          </Text>
        </View>
        <View style={s.statItem}>
          <Text style={s.statLabel}>Win rate</Text>
          <Text style={s.statVal}>{filtered.length ? Math.round(wins/filtered.length*100) : 0}%</Text>
        </View>
        <View style={s.statItem}>
          <Text style={s.statLabel}>Trades</Text>
          <Text style={s.statVal}>{filtered.length}</Text>
        </View>
        <View style={s.statItem}>
          <Text style={s.statLabel}>W / L</Text>
          <Text style={s.statVal}>{wins}W · {losses}L</Text>
        </View>
        <View style={s.statItem}>
          <Text style={s.statLabel}>Grade</Text>
          <Text style={[s.statVal, { color: C.amber }]}>{state?.performance?.grade || 'B'}</Text>
        </View>
      </View>

      {/* Filter pills */}
      <View style={s.filterRow}>
        {[['today','Today'], ['all','All'], ['wins','Wins'], ['losses','Losses']].map(([key,label]) => (
          <TouchableOpacity key={key} style={[s.pill, filter===key && s.pillActive]} onPress={() => setFilter(key)}>
            <Text style={[s.pillTxt, filter===key && s.pillTxtActive]}>
              {label}{key==='today' ? ` (${todayTrades.length})` : key==='wins' ? ` (${allTrades.filter(t=>t.pnl>=0).length})` : key==='losses' ? ` (${allTrades.filter(t=>t.pnl<0).length})` : ` (${allTrades.length})`}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Column headers */}
      <View style={s.colHeaders}>
        <View style={{ width:36 }}/>
        <Text style={[s.colHdr, { flex:1.2 }]}>Symbol</Text>
        <Text style={[s.colHdr, { flex:2 }]}>Reason</Text>
        <Text style={[s.colHdr, { flex:1.5, textAlign:'right' }]}>P&L</Text>
      </View>

      <FlatList
        data={filtered}
        keyExtractor={(_,i) => i.toString()}
        renderItem={renderTrade}
        contentContainerStyle={s.list}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => fetchState(true)} tintColor={C.blue}/>}
        ListEmptyComponent={<View style={s.empty}><Text style={s.emptyTxt}>No trades</Text></View>}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:        { flex:1, backgroundColor:C.bg },
  center:      { flex:1, backgroundColor:C.bg, alignItems:'center', justifyContent:'center' },
  statsBar:    { flexDirection:'row', marginHorizontal:16, marginTop:12, marginBottom:8, backgroundColor:C.surface, borderRadius:12, padding:12, borderWidth:0.5, borderColor:C.border },
  statItem:    { flex:1, alignItems:'center' },
  statLabel:   { fontSize:9, color:C.muted, marginBottom:2 },
  statVal:     { fontSize:12, fontWeight:'500', color:C.white },
  filterRow:   { flexDirection:'row', paddingHorizontal:16, gap:6, marginBottom:8 },
  pill:        { paddingVertical:5, paddingHorizontal:10, borderRadius:20, backgroundColor:C.surface, borderWidth:0.5, borderColor:C.border },
  pillActive:  { backgroundColor:C.blue, borderColor:C.blue },
  pillTxt:     { fontSize:11, color:C.muted },
  pillTxtActive:{ color:C.white, fontWeight:'500' },
  colHeaders:  { flexDirection:'row', paddingHorizontal:16, paddingBottom:6, borderBottomWidth:0.5, borderBottomColor:C.border, marginHorizontal:16, marginBottom:4 },
  colHdr:      { fontSize:8, color:C.muted, textTransform:'uppercase', letterSpacing:0.5 },
  list:        { paddingHorizontal:16, paddingBottom:20 },
  tradeRow:    { flexDirection:'row', alignItems:'center', gap:6, paddingVertical:9, borderBottomWidth:0.5, borderBottomColor:C.dim, borderLeftWidth:2, paddingLeft:8, marginBottom:2 },
  symBlock:    { width:46, flexShrink:0 },
  tradeMid:    { flex:1, minWidth:0 },
  tradePriceTime: { fontSize:10, color:'#cccccc', marginTop:2 },
  badge:       { paddingVertical:2, paddingHorizontal:5, borderRadius:4 },
  badgeTxt:    { fontSize:9, fontWeight:'600' },
  tradeSym:    { fontSize:13, fontWeight:'600', color:C.white },
  tradeReason: { fontSize:11, color:'#aaaaaa' },
  tradePnl:    { fontSize:13, fontWeight:'600', minWidth:55, textAlign:'right' },
  tradeDate:   { fontSize:10, color:'#aaaaaa', marginTop:1 },
  empty:       { alignItems:'center', paddingTop:60 },
  emptyTxt:    { color:C.muted, fontSize:14 },
});
