import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Switch, Alert, TextInput, FlatList } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';

const C = { bg:'#0a0a0a', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', green:'#4ade80', red:'#f87171', amber:'#fbbf24', white:'#ffffff', muted:'#555555', dim:'#222222' };

const APPROACHES = ['Profit Maximizer','Balanced','Conservative','Aggressive','Long Term'];
const TABS = ['Strategies','Risk','Watchlist','Safeguards'];

const PRESET_GROUPS = [
  { label:'Big Tech',  syms:['AAPL','MSFT','GOOGL','META','AMZN','NVDA'] },
  { label:'Semis',     syms:['AMD','INTC','MU','AVGO','QCOM','AMAT'] },
  { label:'AI plays',  syms:['NVDA','PLTR','MSFT','GOOGL','AMZN','META'] },
  { label:'Fintech',   syms:['COIN','SOFI','PYPL','MARA','HOOD','SQ'] },
  { label:'ETFs',      syms:['SPY','QQQ','IWM','XLK','SOXX','SMH'] },
];

function SliderRow({ label, value, min, max, step, format, onChange }) {
  const pct = Math.max(0, Math.min(1, (value - min) / (max - min)));
  return (
    <View style={s.sliderWrap}>
      <View style={s.sliderHeader}>
        <Text style={s.rowLabel}>{label}</Text>
        <Text style={s.sliderVal}>{format(value)}</Text>
      </View>
      <View style={s.sliderTrack}>
        <View style={[s.sliderFill, { width: `${pct*100}%` }]} />
      </View>
      <View style={s.sliderBtns}>
        <TouchableOpacity style={s.sliderBtn} onPress={() => onChange(Math.max(min, parseFloat((value-step).toFixed(4))))}>
          <Text style={s.sliderBtnTxt}>−</Text>
        </TouchableOpacity>
        <Text style={s.sliderRange}>{format(min)} → {format(max)}</Text>
        <TouchableOpacity style={s.sliderBtn} onPress={() => onChange(Math.min(max, parseFloat((value+step).toFixed(4))))}>
          <Text style={s.sliderBtnTxt}>+</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

function FlagRow({ label, sub, value, onChange }) {
  return (
    <View style={s.flagRow}>
      <View style={s.flagInfo}>
        <Text style={s.flagLabel}>{label}</Text>
        {sub && <Text style={s.flagSub}>{sub}</Text>}
      </View>
      <Switch value={!!value} onValueChange={onChange} trackColor={{ false:C.dim, true:C.blue }} thumbColor={C.white} />
    </View>
  );
}

export default function ConfigureScreen() {
  const { apiBase } = useApp();
  const [tab, setTab]         = useState('Strategies');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [searchRes, setSearchRes] = useState([]);

  const [approach,    setApproach]    = useState('Profit Maximizer');
  const [minStrats,   setMinStrats]   = useState(2);
  const [confThresh,  setConfThresh]  = useState(65);
  const [stopLoss,    setStopLoss]    = useState(1.0);
  const [takeProfit,  setTakeProfit]  = useState(3.0);
  const [portRisk,    setPortRisk]    = useState(8.0);
  const [maxPos,      setMaxPos]      = useState(10);
  const [dailyLoss,   setDailyLoss]   = useState(4.0);
  const [maxConsec,   setMaxConsec]   = useState(2);
  const [cooldown,    setCooldown]    = useState(120);
  const [watchlist,   setWatchlist]   = useState([]);
  const [flags,       setFlags]       = useState({});
  const [trailing,    setTrailing]    = useState(true);
  const [trailPct,    setTrailPct]    = useState(1.0);
  const [regime,      setRegime]      = useState(true);

  useEffect(() => { fetchConfig(); }, []);

  async function fetchConfig() {
    try {
      const res  = await fetch(`${apiBase}/api/state`);
      const data = await res.json();
      const cfg  = data.config || {};
      setApproach(cfg.approach || 'Profit Maximizer');
      setMinStrats(cfg.min_strategies_agree || 2);
      setConfThresh(Math.round((cfg.confidence_threshold || 0.65) * 100));
      setStopLoss(((cfg.stop_loss_pct || 0.01) * 100).toFixed(2) * 1);
      setTakeProfit(((cfg.take_profit_pct || 0.03) * 100).toFixed(1) * 1);
      setPortRisk(((cfg.max_portfolio_risk_pct || 0.08) * 100).toFixed(1) * 1);
      setMaxPos(cfg.max_open_positions || 10);
      setDailyLoss(((cfg.daily_loss_limit_pct || 0.04) * 100).toFixed(1) * 1);
      setMaxConsec(cfg.consecutive_loss_limit || 2);
      setCooldown((cfg.consecutive_loss_pause_hours || 2) * 60);
      setWatchlist(cfg.watchlist || []);
      setFlags(cfg.feature_flags || {});
      setTrailing(cfg.trailing_stop ?? true);
      setTrailPct(((cfg.trailing_stop_pct || 0.01) * 100).toFixed(2) * 1);
      setRegime(cfg.regime_filter ?? true);
    } catch(e) {}
    finally { setLoading(false); }
  }

  async function searchTickers(q) {
    setSearchQ(q);
    if (q.length < 1) { setSearchRes([]); return; }
    try {
      const res  = await fetch(`${apiBase}/api/tickers/search?q=${encodeURIComponent(q.toUpperCase())}&limit=6`);
      const data = await res.json();
      setSearchRes(data.results || data || []);
    } catch(e) { setSearchRes([]); }
  }

  function addTicker(sym) {
    if (!watchlist.includes(sym)) setWatchlist(w => [...w, sym]);
    setSearchQ(''); setSearchRes([]);
  }

  function removeTicker(sym) {
    setWatchlist(w => w.filter(s => s !== sym));
  }

  async function save() {
    // Safety check — prevent sending obviously wrong values
    if (stopLoss > 15 || stopLoss < 0.1) {
      Alert.alert('Invalid config', 'Stop loss must be between 0.1% and 15%'); return;
    }
    if (takeProfit > 30 || takeProfit < 0.5) {
      Alert.alert('Invalid config', 'Take profit must be between 0.5% and 30%'); return;
    }
    if (takeProfit <= stopLoss) {
      Alert.alert('Invalid config', 'Take profit must be greater than stop loss'); return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${apiBase}/api/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          approach,
          min_strategies_agree:      minStrats,
          confidence_threshold:      confThresh,
          stop_loss_pct:             stopLoss,
          take_profit_pct:           takeProfit,
          max_portfolio_risk_pct:    portRisk,
          max_open_positions:        maxPos,
          daily_loss_limit_pct:      dailyLoss,
          consecutive_loss_limit:    maxConsec,
          consecutive_loss_pause_hours: cooldown / 60,
          watchlist,
          feature_flags:             flags,
          trailing_stop:             trailing,
          trailing_stop_pct:         trailPct,
          regime_filter:             regime,
        }),
      });
      if (res.ok) { setSaved(true); setTimeout(() => setSaved(false), 2000); }
      else Alert.alert('Error', 'Failed to save');
    } catch(e) { Alert.alert('Error', 'Cannot reach agent'); }
    finally { setSaving(false); }
  }

  if (loading) return <View style={s.center}><ActivityIndicator color={C.blue}/></View>;

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <Text style={s.pageTitle}>Configure</Text>
        <TouchableOpacity style={[s.saveBtn, saved && s.saveDone]} onPress={save} disabled={saving}>
          {saving ? <ActivityIndicator color={C.white} size="small"/> : <Text style={s.saveTxt}>{saved ? 'Saved!' : 'Save'}</Text>}
        </TouchableOpacity>
      </View>

      {/* Tab bar */}
      <View style={s.tabBar}>
        {TABS.map(t => (
          <TouchableOpacity key={t} style={[s.tabBtn, tab===t && s.tabActive]} onPress={() => setTab(t)}>
            <Text style={[s.tabTxt, tab===t && s.tabTxtActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={s.scroll} showsVerticalScrollIndicator={false}>

        {/* STRATEGIES TAB */}
        {tab === 'Strategies' && <>
          <Text style={s.secLabel}>Approach</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow}>
            {APPROACHES.map(a => (
              <TouchableOpacity key={a} style={[s.chip, approach===a && s.chipActive]} onPress={() => setApproach(a)}>
                <Text style={[s.chipTxt, approach===a && s.chipTxtActive]}>{a}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          <Text style={s.secLabel}>Signal thresholds</Text>
          <View style={s.card}>
            <SliderRow label="Min strategies agree" value={minStrats}  min={1} max={8}  step={1}   format={v => `${Math.round(v)}`}   onChange={setMinStrats}/>
            <View style={s.divider}/>
            <SliderRow label="Min confidence %"     value={confThresh} min={40} max={95} step={5}  format={v => `${Math.round(v)}%`}  onChange={setConfThresh}/>
          </View>
          <Text style={s.secLabel}>Filters</Text>
          <View style={s.card}>
            <FlagRow label="Regime filter" sub="Only trade in trending markets" value={regime} onChange={v => setRegime(v)}/>
          </View>
        </>}

        {/* RISK TAB */}
        {tab === 'Risk' && <>
          <Text style={s.secLabel}>Position sizing</Text>
          <View style={s.card}>
            <SliderRow label="Stop loss %"        value={stopLoss}   min={0.5} max={5}  step={0.25} format={v => `${v.toFixed(2)}%`} onChange={setStopLoss}/>
            <View style={s.divider}/>
            <SliderRow label="Take profit %"      value={takeProfit} min={1}   max={10} step={0.5}  format={v => `${v.toFixed(1)}%`} onChange={setTakeProfit}/>
            <View style={s.divider}/>
            <SliderRow label="Portfolio risk %"   value={portRisk}   min={1}   max={20} step={1}    format={v => `${Math.round(v)}%`} onChange={setPortRisk}/>
            <View style={s.divider}/>
            <SliderRow label="Max open positions" value={maxPos}     min={1}   max={15} step={1}    format={v => `${Math.round(v)}`}  onChange={setMaxPos}/>
          </View>
          <Text style={s.secLabel}>Loss limits</Text>
          <View style={s.card}>
            <SliderRow label="Daily loss limit %"      value={dailyLoss} min={1} max={10} step={0.5} format={v => `${v.toFixed(1)}%`}    onChange={setDailyLoss}/>
            <View style={s.divider}/>
            <SliderRow label="Max consecutive losses"  value={maxConsec} min={1} max={10} step={1}   format={v => `${Math.round(v)}`}     onChange={setMaxConsec}/>
            <View style={s.divider}/>
            <SliderRow label="Cooldown after losses"   value={cooldown}  min={15} max={480} step={15} format={v => `${Math.round(v)} min`} onChange={setCooldown}/>
          </View>
          <Text style={s.secLabel}>Trailing stop</Text>
          <View style={s.card}>
            <FlagRow label="Trailing stop" sub="Automatically trail winning positions" value={trailing} onChange={setTrailing}/>
            {trailing && <>
              <View style={s.divider}/>
              <SliderRow label="Trail distance %" value={trailPct} min={0.25} max={5} step={0.25} format={v => `${v.toFixed(2)}%`} onChange={setTrailPct}/>
            </>}
          </View>
        </>}

        {/* WATCHLIST TAB */}
        {tab === 'Watchlist' && <>
          <Text style={s.secLabel}>Search & add tickers</Text>
          <View style={s.searchBox}>
            <TextInput
              style={s.searchInput}
              value={searchQ}
              onChangeText={searchTickers}
              placeholder="Search ticker or company..."
              placeholderTextColor={C.muted}
              autoCapitalize="characters"
              autoCorrect={false}
            />
          </View>
          {searchRes.length > 0 && (
            <View style={s.searchResults}>
              {searchRes.map((r, i) => (
                <TouchableOpacity key={i} style={s.searchRow} onPress={() => addTicker(r.symbol || r)}>
                  <View>
                    <Text style={s.searchSym}>{r.symbol || r}</Text>
                    {r.name && <Text style={s.searchName} numberOfLines={1}>{r.name}</Text>}
                  </View>
                  <Text style={[s.addTxt, watchlist.includes(r.symbol||r) && { color:C.muted }]}>
                    {watchlist.includes(r.symbol||r) ? 'Added' : '+ Add'}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          <Text style={s.secLabel}>Quick add groups</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow}>
            {PRESET_GROUPS.map(g => (
              <TouchableOpacity key={g.label} style={s.chip}
                onPress={() => {
                  const toAdd = g.syms.filter(s => !watchlist.includes(s));
                  setWatchlist(w => [...w, ...toAdd]);
                }}>
                <Text style={s.chipTxt}>+ {g.label}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <View style={s.watchlistHeader}>
            <Text style={s.secLabel}>Current watchlist ({watchlist.length})</Text>
            <TouchableOpacity onPress={() => Alert.alert('Clear watchlist', 'Remove all tickers?', [
              { text:'Cancel', style:'cancel' },
              { text:'Clear', style:'destructive', onPress:() => setWatchlist([]) }
            ])}>
              <Text style={s.clearTxt}>Clear all</Text>
            </TouchableOpacity>
          </View>
          <View style={s.tickerGrid}>
            {watchlist.map(sym => (
              <TouchableOpacity key={sym} style={s.tickerChip} onPress={() => removeTicker(sym)}>
                <Text style={s.tickerSym}>{sym}</Text>
                <Text style={s.tickerX}>×</Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={s.hint}>Tap any ticker to remove. All symbols scanned every cycle.</Text>
        </>}

        {/* SAFEGUARDS TAB */}
        {tab === 'Safeguards' && <>
          <Text style={s.secLabel}>Feature flags</Text>
          <View style={s.card}>
            {[
              ['trail_activation',        'Trail activation buffer',    '0.5% buffer before trail starts'],
              ['sector_concentration',    'Sector concentration limit', 'Cap exposure per sector'],
              ['drawdown_circuit_breaker','Drawdown circuit breaker',   'Halt if drawdown > 5%'],
              ['atr_trailing_stops',      'ATR trailing stops',         'Adaptive volatility-based stops'],
              ['news_sentiment',          'News sentiment signal',      'Wire sentiment into conviction'],
            ].map(([key, label, sub], i, arr) => (
              <View key={key}>
                <FlagRow label={label} sub={sub} value={!!flags[key]} onChange={() => setFlags(f => ({...f, [key]:!f[key]}))}/>
                {i < arr.length-1 && <View style={s.divider}/>}
              </View>
            ))}
          </View>
          <Text style={s.hint}>Flags apply immediately on save — no restart needed.</Text>
        </>}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:          { flex:1, backgroundColor:C.bg },
  scroll:        { flex:1, paddingHorizontal:16 },
  center:        { flex:1, backgroundColor:C.bg, alignItems:'center', justifyContent:'center' },
  header:        { flexDirection:'row', justifyContent:'space-between', alignItems:'center', paddingHorizontal:16, paddingTop:12, paddingBottom:8 },
  pageTitle:     { fontSize:22, fontWeight:'500', color:C.white },
  saveBtn:       { backgroundColor:C.blue, paddingVertical:8, paddingHorizontal:20, borderRadius:20 },
  saveDone:      { backgroundColor:'#14532d' },
  saveTxt:       { color:C.white, fontSize:13, fontWeight:'500' },
  tabBar:        { flexDirection:'row', paddingHorizontal:16, gap:8, marginBottom:12 },
  tabBtn:        { paddingVertical:7, paddingHorizontal:14, borderRadius:20, backgroundColor:C.surface, borderWidth:0.5, borderColor:C.border },
  tabActive:     { backgroundColor:C.blue, borderColor:C.blue },
  tabTxt:        { fontSize:12, color:C.muted },
  tabTxtActive:  { color:C.white, fontWeight:'500' },
  secLabel:      { fontSize:10, fontWeight:'500', color:C.muted, letterSpacing:0.6, textTransform:'uppercase', marginBottom:8, marginTop:8 },
  card:          { backgroundColor:C.surface, borderRadius:14, borderWidth:0.5, borderColor:C.border, marginBottom:12, overflow:'hidden' },
  divider:       { height:0.5, backgroundColor:C.border },
  chipRow:       { marginBottom:12 },
  chip:          { paddingVertical:8, paddingHorizontal:14, borderRadius:20, backgroundColor:C.surface, borderWidth:0.5, borderColor:C.border, marginRight:8 },
  chipActive:    { backgroundColor:C.blue, borderColor:C.blue },
  chipTxt:       { fontSize:12, color:C.muted },
  chipTxtActive: { color:C.white, fontWeight:'500' },
  sliderWrap:    { padding:14 },
  sliderHeader:  { flexDirection:'row', justifyContent:'space-between', marginBottom:10 },
  rowLabel:      { fontSize:13, color:C.white },
  sliderVal:     { fontSize:13, fontWeight:'500', color:C.blue },
  sliderTrack:   { height:3, backgroundColor:C.dim, borderRadius:2, marginBottom:8 },
  sliderFill:    { height:'100%', backgroundColor:C.blue, borderRadius:2 },
  sliderBtns:    { flexDirection:'row', alignItems:'center', justifyContent:'space-between' },
  sliderBtn:     { width:32, height:32, backgroundColor:C.dim, borderRadius:8, alignItems:'center', justifyContent:'center' },
  sliderBtnTxt:  { fontSize:18, color:C.white, fontWeight:'500' },
  sliderRange:   { fontSize:11, color:C.dim },
  flagRow:       { flexDirection:'row', alignItems:'center', padding:14, gap:12 },
  flagInfo:      { flex:1 },
  flagLabel:     { fontSize:13, color:C.white, marginBottom:2 },
  flagSub:       { fontSize:11, color:C.muted },
  searchBox:     { backgroundColor:C.surface, borderRadius:12, borderWidth:0.5, borderColor:C.border, marginBottom:8 },
  searchInput:   { padding:14, color:C.white, fontSize:14 },
  searchResults: { backgroundColor:C.surface, borderRadius:12, borderWidth:0.5, borderColor:C.border, marginBottom:12, overflow:'hidden' },
  searchRow:     { flexDirection:'row', justifyContent:'space-between', alignItems:'center', padding:12, borderBottomWidth:0.5, borderBottomColor:C.border },
  searchSym:     { fontSize:14, fontWeight:'500', color:C.white },
  searchName:    { fontSize:11, color:C.muted, maxWidth:200 },
  addTxt:        { fontSize:13, color:C.blue, fontWeight:'500' },
  watchlistHeader:{ flexDirection:'row', justifyContent:'space-between', alignItems:'center' },
  clearTxt:      { fontSize:12, color:C.red },
  tickerGrid:    { flexDirection:'row', flexWrap:'wrap', gap:8, marginBottom:12 },
  tickerChip:    { flexDirection:'row', alignItems:'center', gap:6, paddingVertical:7, paddingHorizontal:12, backgroundColor:C.surface, borderRadius:20, borderWidth:0.5, borderColor:C.border },
  tickerSym:     { fontSize:13, fontWeight:'500', color:C.white },
  tickerX:       { fontSize:16, color:C.muted },
  hint:          { fontSize:11, color:C.dim, textAlign:'center', marginBottom:16 },
});
