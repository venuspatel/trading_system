import React, { useState, useMemo, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { GestureDetector, Gesture } from 'react-native-gesture-handler';
import Svg, { Polyline, Path, Line, Circle, Text as SvgText, Defs, LinearGradient, Stop } from 'react-native-svg';

const C = { green:'#4ade80', red:'#f87171', muted:'#555555', dim:'#333333', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', white:'#ffffff' };
const RANGES = [
  { label:'1H',   minutes:60 },
  { label:'3H',   minutes:180 },
  { label:'1D',   minutes:1440 },
  { label:'1W',   minutes:10080 },
  { label:'1M',   minutes:43200 },
  { label:'3M',   minutes:129600 },
  { label:'YTD',  minutes:-1 },
  { label:'1Y',   minutes:525600 },
  { label:'All',  minutes:99999 },
];

function fmtMoney(v) {
  return (v >= 0 ? '+$' : '-$') + Math.abs(v).toLocaleString('en-US', { maximumFractionDigits:0 });
}
function fmtMoneyK(v) {
  if (Math.abs(v) >= 1000) return (v >= 0 ? '+$' : '-$') + (Math.abs(v)/1000).toFixed(1) + 'k';
  return fmtMoney(v);
}
function fmtTime(dateStr, showDate=false) {
  try {
    const d = new Date(dateStr);
    if (showDate) return d.toLocaleDateString('en-US', { month:'short', day:'numeric' });
    return d.toLocaleTimeString('en-US', { hour:'numeric', minute:'2-digit', hour12:true });
  } catch { return ''; }
}
function shortReason(r) {
  if (!r) return '';
  if (r.includes('Trailing stop')) return 'Trailing stop';
  if (r.includes('Take profit'))   return 'Take profit';
  if (r.includes('Momentum'))      return 'Momentum exit';
  if (r.includes('partial'))       return 'Partial profit';
  if (r.includes('Max hold'))      return 'Max hold';
  return r.slice(0, 22);
}

export default function EquityChart({ equityCurve, syntheticCurve, recentTrades, onDragStart, onDragEnd }) {
  const [rangeLabel, setRangeLabel]       = useState('1D');
  const [hoverIdx, setHoverIdx]           = useState(null);
  const [hoveredTrades, setHoveredTrades] = useState([]);
  const [svgWidth, setSvgWidth]           = useState(320);
  const [zoomStart, setZoomStart]         = useState(0);
  const [zoomEnd, setZoomEnd]             = useState(1);
  const zoomRef = useRef({ start:0, end:1 });

  const W = svgWidth, H = 260;
  const PAD = { top:16, bottom:24, left:4, right:4 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const isAllView = rangeLabel === 'All';

  const fullCurve = useMemo(() => {
    const longRange = ['All','1Y','YTD','3M'].includes(rangeLabel);
    const src = (longRange && syntheticCurve && syntheticCurve.length >= 2)
      ? syntheticCurve : equityCurve;
    if (!src || src.length < 2) return [];
    const sel = RANGES.find(r => r.label === rangeLabel);
    if (longRange) return src;
    let cutoff;
    if (sel.minutes === -1) {
      cutoff = new Date(new Date().getFullYear(), 0, 1);
    } else if (sel.minutes === 99999) {
      return src;
    } else {
      cutoff = new Date(Date.now() - sel.minutes * 60 * 1000);
    }
    const filtered = src.filter(p => new Date(p.t) >= cutoff);
    return filtered.length >= 2 ? filtered : src.slice(-20);
  }, [equityCurve, syntheticCurve, rangeLabel]);

  const curve = useMemo(() => {
    if (!fullCurve.length) return [];
    const s = Math.floor(zoomStart * (fullCurve.length - 1));
    const e = Math.ceil(zoomEnd   * (fullCurve.length - 1));
    return fullCurve.slice(s, e + 1);
  }, [fullCurve, zoomStart, zoomEnd]);

  const baseline   = curve.length ? curve[0].v : 0;
  const pnlVals    = curve.map(p => p.v - baseline);
  const maxPnl     = pnlVals.length ? Math.max(...pnlVals) : 1;
  const minPnl     = pnlVals.length ? Math.min(...pnlVals) : -1;
  const scale      = Math.max(Math.abs(maxPnl), Math.abs(minPnl), 100);
  const midY       = PAD.top + innerH / 2;
  const currentPnl = pnlVals.length ? pnlVals[pnlVals.length-1] : 0;
  const liveEquity = curve.length ? curve[curve.length-1].v : 0;
  const isUp       = currentPnl >= 0;
  const color      = C.green;
  const changePct  = baseline > 0 ? (currentPnl / baseline * 100) : 0;

  function pnlToY(pnl) {
    return midY - (pnl / scale) * (innerH / 2);
  }

  const points = pnlVals.map((pnl, i) => ({
    x: PAD.left + (i / Math.max(pnlVals.length-1, 1)) * innerW,
    y: pnlToY(pnl),
    pnl, v: curve[i]?.v, t: curve[i]?.t,
  }));

  const polyPoints = points.map(p => `${p.x},${p.y}`).join(' ');

  const greenPath = (() => {
    if (points.length < 2) return '';
    let d = `M${points[0].x},${midY} `;
    points.forEach(p => { d += `L${p.x},${Math.min(p.y, midY)} `; });
    d += `L${points[points.length-1].x},${midY} Z`;
    return d;
  })();

  const redPath = (() => {
    if (points.length < 2) return '';
    let d = `M${points[0].x},${midY} `;
    points.forEach(p => { d += `L${p.x},${Math.max(p.y, midY)} `; });
    d += `L${points[points.length-1].x},${midY} Z`;
    return d;
  })();

  const { tradeDots, tradeMap } = useMemo(() => {
    const dots = [], map = {};
    if (!recentTrades || !curve.length || points.length < 2) return { tradeDots:[], tradeMap:{} };
    const toMs = (s) => {
      if (!s) return 0;
      const n = s.includes("+") || s.endsWith("Z") ? s : s + "Z";
      return new Date(n).getTime();
    };
    const start = toMs(curve[0]?.t);
    const end   = toMs(curve[curve.length-1]?.t);
    for (const t of (recentTrades || [])) {
      const te = toMs(t.exit_time || t.entry_time);
      if (te < start || te > end) continue;
      let nearIdx = 0, nearDiff = Infinity;
      curve.forEach((pt, i) => {
        const d = Math.abs(toMs(pt.t) - te);
        if (d < nearDiff) { nearDiff = d; nearIdx = i; }
      });
      // No distance limit — snap to nearest point within slice
      const pt = points[nearIdx];
      if (!pt) continue;
      dots.push({ x:pt.x, y:pt.y, isWin:t.pnl>=0, pnl:t.pnl, symbol:t.symbol });
      [-1,0,1].forEach(off => {
        const k = nearIdx + off;
        if (!map[k]) map[k] = [];
        map[k].push(t);
      });
    }
    return { tradeDots:dots, tradeMap:map };
  }, [recentTrades, curve, points]);

  function handleHover(x) {
    if (points.length < 2) return;
    const idx = Math.round((x - PAD.left) / innerW * (points.length - 1));
    const c = Math.max(0, Math.min(points.length-1, idx));
    setHoverIdx(c);
    setHoveredTrades(tradeMap[c] || []);
  }

  const panGesture = useMemo(() => Gesture.Pan()
    .runOnJS(true).minDistance(0)
    .onBegin(e  => { onDragStart?.(); handleHover(e.x); })
    .onUpdate(e => handleHover(e.x))
    .onEnd(     () => { onDragEnd?.(); setHoverIdx(null); setHoveredTrades([]); })
    .onFinalize(() => { onDragEnd?.(); setHoverIdx(null); setHoveredTrades([]); }),
  [points, tradeMap]);

  const pinchGesture = useMemo(() => Gesture.Pinch()
    .runOnJS(true)
    .onBegin(() => { zoomRef.current = { start:zoomStart, end:zoomEnd }; })
    .onUpdate(e => {
      const prev = zoomRef.current;
      const newSpan = Math.max(0.05, Math.min(1, (prev.end - prev.start) / e.scale));
      const center  = (prev.start + prev.end) / 2;
      setZoomStart(Math.max(0, center - newSpan/2));
      setZoomEnd(Math.min(1, center + newSpan/2));
    }),
  [zoomStart, zoomEnd]);

  const composed = Gesture.Simultaneous(panGesture, pinchGesture);
  const hoverPt  = hoverIdx !== null ? points[hoverIdx] : null;
  const isZoomed = zoomStart > 0.01 || zoomEnd < 0.99;
  const showDate = isAllView;
  const displayEquity = hoverPt ? hoverPt.v : liveEquity;
  const displayPnl    = hoverPt ? hoverPt.pnl : currentPnl;
  const displayColor  = displayPnl >= 0 ? C.green : C.red;

  if (curve.length < 2) return null;

  return (
    <View style={s.wrap}>

      {/* ── HERO HEADER — always visible, updates on hover ── */}
      <View style={s.heroRow}>
        <View style={{ flex:1 }}>
          <Text style={s.heroLabel}>
            {isAllView ? 'Total since start' : "Today's session"}{isZoomed ? ' · zoomed' : ''}
          </Text>
          <Text style={s.heroEquity}>
            ${Math.round(displayEquity).toLocaleString()}
          </Text>
          <Text style={[s.heroPnl, { color: displayColor }]}>
            {displayPnl >= 0 ? '▲' : '▼'} {fmtMoney(displayPnl)}
            {'  '}{displayPnl >= 0 ? '+' : ''}{(displayPnl / (displayEquity - displayPnl || 1) * 100).toFixed(2)}%
            {hoverPt ? '  ·  ' + fmtTime(hoverPt.t, showDate) : ''}
          </Text>
          {hoveredTrades.length > 0 && hoveredTrades.slice(0,2).map((t, i) => (
            <View key={i} style={s.tradeHint}>
              <View style={[s.tradeDotSmall, { backgroundColor: t.pnl>=0 ? C.green : C.red }]}/>
              <Text style={s.tradeHintSym}>{t.symbol}</Text>
              <Text style={[s.tradeHintPnl, { color: t.pnl>=0 ? C.green : C.red }]}> {fmtMoney(t.pnl)}</Text>
              <Text style={s.tradeHintReason}> · {shortReason(t.exit_reason)}</Text>
            </View>
          ))}
        </View>

  
      </View>

      {/* ── CHART ── */}
      <GestureDetector gesture={composed}>
        <View onLayout={e => setSvgWidth(Math.floor(e.nativeEvent.layout.width))}>
          <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
            <Defs>
              <LinearGradient id="greenGrad" x1="0" y1="0" x2="0" y2="1">
                <Stop offset="0%" stopColor={C.green} stopOpacity="0.35"/>
                <Stop offset="100%" stopColor={C.green} stopOpacity="0.02"/>
              </LinearGradient>
              <LinearGradient id="redGrad" x1="0" y1="0" x2="0" y2="1">
                <Stop offset="0%" stopColor={C.red} stopOpacity="0.02"/>
                <Stop offset="100%" stopColor={C.red} stopOpacity="0.35"/>
              </LinearGradient>
            </Defs>

            {/* Grid */}
            <Line x1={PAD.left} y1={PAD.top}         x2={W-PAD.right} y2={PAD.top}         stroke={C.dim} strokeWidth="0.5" strokeDasharray="4,4"/>
            <Line x1={PAD.left} y1={midY}             x2={W-PAD.right} y2={midY}             stroke="#ffffff" strokeWidth="1" strokeDasharray="4,3" strokeOpacity="0.4"/>
            <Line x1={PAD.left} y1={PAD.top+innerH}   x2={W-PAD.right} y2={PAD.top+innerH}   stroke={C.dim} strokeWidth="0.5" strokeDasharray="4,4"/>

            {/* Y labels */}
            <SvgText x={W-PAD.right} y={PAD.top+9}        fontSize="8" fill={C.green} textAnchor="end">{fmtMoneyK(scale)}</SvgText>
            <SvgText x={PAD.left+2}  y={midY-3}            fontSize="8" fill="#555">{isAllView ? '$1M start' : 'open'}</SvgText>
            <SvgText x={W-PAD.right} y={PAD.top+innerH-2}  fontSize="8" fill={C.red}   textAnchor="end">{fmtMoneyK(-scale)}</SvgText>

            {/* Areas */}
            <Path d={greenPath} fill="url(#greenGrad)"/>
            <Path d={redPath}   fill="url(#redGrad)"/>

            {/* Zero line */}
            <Line x1={PAD.left} y1={midY} x2={W-PAD.right} y2={midY} stroke="#ffffff" strokeWidth="1" strokeDasharray="4,3" strokeOpacity="0.4"/>

            {/* Main line */}
            <Polyline points={polyPoints} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/>

            {/* Trade dots */}
            {tradeDots.map((td, i) => (
              <React.Fragment key={i}>
                <Circle cx={td.x} cy={td.y} r="8"  fill={td.isWin ? C.green : C.red} fillOpacity="0.15"/>
                <Circle cx={td.x} cy={td.y} r="4"  fill={td.isWin ? C.green : C.red} stroke="#0a0a0a" strokeWidth="1.5"/>
              </React.Fragment>
            ))}

            {/* Hover crosshair */}
            {hoverPt && (
              <React.Fragment>
                <Line x1={hoverPt.x} y1={PAD.top} x2={hoverPt.x} y2={PAD.top+innerH} stroke={C.blue} strokeWidth="1" strokeDasharray="3,2"/>
                <Circle cx={hoverPt.x} cy={hoverPt.y} r="9"  fill={C.blue} fillOpacity="0.2"/>
                <Circle cx={hoverPt.x} cy={hoverPt.y} r="4"  fill={C.blue} stroke="#0a0a0a" strokeWidth="1.5"/>
              </React.Fragment>
            )}

            {/* X labels */}
            <SvgText x={PAD.left}    y={H-4} fontSize="8" fill={C.muted}>{fmtTime(curve[0]?.t, showDate)}</SvgText>
            <SvgText x={W-PAD.right} y={H-4} fontSize="8" fill={C.muted} textAnchor="end">{fmtTime(curve[curve.length-1]?.t, showDate)}</SvgText>
            {curve.length > 4 && (
              <SvgText x={W/2} y={H-4} fontSize="8" fill={C.dim} textAnchor="middle">
                {fmtTime(curve[Math.floor(curve.length/2)]?.t, showDate)}
              </SvgText>
            )}
          </Svg>
        </View>
      </GestureDetector>

      {/* Scrollable range tabs at bottom */}
      <View style={s.rangeScroll}>
        {RANGES.map(r => (
          <TouchableOpacity key={r.label}
            style={[s.rangeBtn, rangeLabel===r.label && s.rangeBtnActive]}
            onPress={() => { setRangeLabel(r.label); setZoomStart(0); setZoomEnd(1); }}
          >
            <Text style={[s.rangeTxt, rangeLabel===r.label && s.rangeTxtActive]}>{r.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Scrollable range tabs at bottom */}
      {/* Stats footer */}
      <View style={s.footer}>
        <View style={s.stat}><Text style={s.statLabel}>Peak gain</Text><Text style={[s.statVal,{color:C.green}]}>{fmtMoneyK(Math.max(...pnlVals,0))}</Text></View>
        <View style={s.stat}><Text style={s.statLabel}>Peak loss</Text><Text style={[s.statVal,{color:C.red}]}>{fmtMoneyK(Math.min(...pnlVals,0))}</Text></View>
        <View style={s.stat}><Text style={s.statLabel}>Trades</Text><Text style={s.statVal}>{tradeDots.length}</Text></View>
        <View style={s.stat}><Text style={s.statLabel}>Net P&L</Text><Text style={[s.statVal,{color}]}>{fmtMoneyK(currentPnl)}</Text></View>
      </View>

      <View style={s.legend}>
        <View style={[s.ldot,{backgroundColor:C.green}]}/><Text style={s.ltxt}>Win</Text>
        <View style={[s.ldot,{backgroundColor:C.red,marginLeft:10}]}/><Text style={s.ltxt}>Loss</Text>
        <Text style={s.lhint}>  Drag · Pinch to zoom</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap:           { backgroundColor:'#1a1a1a', borderRadius:14, padding:14, marginBottom:12, borderWidth:0.5, borderColor:'#2a2a2a' },
  heroRow:        { flexDirection:'row', justifyContent:'space-between', alignItems:'flex-start', marginBottom:12 },
  heroLabel:      { fontSize:10, color:'#555', textTransform:'uppercase', letterSpacing:0.6, marginBottom:4 },
  heroEquity:     { fontSize:30, fontWeight:'500', color:'#fff', marginBottom:3 },
  heroPnl:        { fontSize:13, fontWeight:'500', marginBottom:3 },
  tradeHint:      { flexDirection:'row', alignItems:'center', gap:4, marginTop:3 },
  tradeDotSmall:  { width:6, height:6, borderRadius:3 },
  tradeHintSym:   { fontSize:11, fontWeight:'500', color:'#fff' },
  tradeHintPnl:   { fontSize:11, fontWeight:'500' },
  tradeHintReason:{ fontSize:10, color:'#555' },
  rangeRow:       { flexDirection:'row', gap:4 },
  rangeScroll:    { flexDirection:'row', gap:6, marginTop:10, marginBottom:4, flexWrap:'wrap', justifyContent:'center' },
  rangeBtn:       { paddingVertical:4, paddingHorizontal:8, borderRadius:12, backgroundColor:'#222', borderWidth:0.5, borderColor:'#333' },
  rangeBtnActive: { backgroundColor:'#378ADD', borderColor:'#378ADD' },
  rangeTxt:       { fontSize:10, color:'#555' },
  rangeTxtActive: { color:'#fff', fontWeight:'500' },
  resetTxt:       { fontSize:10, color:'#378ADD', textAlign:'right' },
  footer:         { flexDirection:'row', marginTop:10, paddingTop:10, borderTopWidth:0.5, borderTopColor:'#222' },
  stat:           { flex:1, alignItems:'center' },
  statLabel:      { fontSize:9, color:'#555', marginBottom:2 },
  statVal:        { fontSize:11, fontWeight:'500', color:'#fff' },
  legend:         { flexDirection:'row', alignItems:'center', marginTop:8 },
  ldot:           { width:7, height:7, borderRadius:4 },
  ltxt:           { fontSize:10, color:'#555', marginLeft:4 },
  lhint:          { fontSize:10, color:'#333', marginLeft:'auto' },
});
