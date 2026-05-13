import { useState } from "react";
import { useTheme } from "./ThemeContext";

export default function ThemeSettings({ onClose }) {
  const { theme, themeName, setThemeName, accentName, setAccentName, fontSize, setFontSize, compact, setCompact, newsColorScheme, setNewsColorScheme, NEWS_COLOR_SCHEMES, THEMES, ACCENT_COLORS, FONT_SIZES } = useTheme();
  const [tab, setTab] = useState("theme");

  const T = theme;

  const tabStyle = (t) => ({
    padding: "6px 14px", borderRadius: 6, fontSize: 12, fontWeight: 500,
    cursor: "pointer", border: "none",
    background: tab === t ? T.accent : T.bg3,
    color: tab === t ? "#000" : T.textSecondary,
  });

  return (
    <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,.7)", zIndex:1000, display:"flex", alignItems:"center", justifyContent:"center" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ background:T.bg1, border:`1px solid ${T.border}`, borderRadius:12, width:520, maxHeight:"80vh", overflow:"auto" }}>

        {/* Header */}
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"14px 18px", borderBottom:`1px solid ${T.border}` }}>
          <span style={{ fontSize:14, fontWeight:500, color:T.textPrimary }}>Dashboard settings</span>
          <div onClick={onClose} style={{ width:28, height:28, borderRadius:6, display:"flex", alignItems:"center", justifyContent:"center", cursor:"pointer", background:T.bg3, color:T.textSecondary, fontSize:16 }}>×</div>
        </div>

        {/* Tabs */}
        <div style={{ display:"flex", gap:6, padding:"12px 18px", borderBottom:`1px solid ${T.border}` }}>
          {["theme","accent","display"].map(t => <button key={t} style={tabStyle(t)} onClick={()=>setTab(t)}>{t.charAt(0).toUpperCase()+t.slice(1)}</button>)}
        </div>

        <div style={{ padding:"16px 18px" }}>

          {/* THEME TAB */}
          {tab === "theme" && (
            <div>
              <p style={{ fontSize:11, color:T.textMuted, textTransform:"uppercase", letterSpacing:".06em", marginBottom:12 }}>Background theme</p>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                {Object.entries(THEMES).map(([name, t]) => (
                  <div key={name} onClick={() => setThemeName(name)}
                    style={{ border: themeName===name ? `2px solid ${T.accent}` : `1px solid ${t.border}`, borderRadius:10, overflow:"hidden", cursor:"pointer", transition:"border .15s" }}>
                    {/* Mini preview */}
                    <div style={{ background:t.bg0, padding:"10px 12px" }}>
                      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:8 }}>
                        <span style={{ fontSize:11, fontWeight:600, color:t.accent }}>TradeAgent</span>
                        <span style={{ fontSize:9, padding:"1px 6px", borderRadius:3, background:t.bg2, color:t.profit }}>PAPER</span>
                      </div>
                      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:4, marginBottom:6 }}>
                        {[{l:"Portfolio",v:"$100K",c:t.textPrimary},{l:"P&L",v:"+$420",c:t.profit},{l:"Win",v:"67%",c:t.accent}].map(m=>(
                          <div key={m.l} style={{ background:t.bg1, borderRadius:4, padding:"4px 6px" }}>
                            <div style={{ fontSize:8, color:t.textMuted, marginBottom:1 }}>{m.l}</div>
                            <div style={{ fontSize:11, fontWeight:500, color:m.c }}>{m.v}</div>
                          </div>
                        ))}
                      </div>
                      <div style={{ display:"flex", gap:4 }}>
                        {["NVDA","AAPL","TSLA"].map((s,i)=>(
                          <div key={s} style={{ flex:1, background:[t.bg2,"#0a1a0a","#1a0a0a"][i]||t.bg2, borderRadius:4, padding:"3px 0", textAlign:"center" }}>
                            <div style={{ fontSize:8, fontWeight:600, color:[t.textSecondary,t.profit,t.loss][i] }}>{s}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div style={{ background:t.bg1, padding:"6px 12px", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
                      <span style={{ fontSize:11, fontWeight:500, color:t.textPrimary }}>{name}</span>
                      {themeName===name && <span style={{ fontSize:9, padding:"1px 6px", borderRadius:3, background:t.accent+"22", color:t.accent }}>Active</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ACCENT TAB */}
          {tab === "accent" && (
            <div>
              <p style={{ fontSize:11, color:T.textMuted, textTransform:"uppercase", letterSpacing:".06em", marginBottom:12 }}>Accent color</p>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:8, marginBottom:20 }}>
                {Object.entries(ACCENT_COLORS).map(([name, color]) => (
                  <div key={name} onClick={() => setAccentName(name)}
                    style={{ border: accentName===name ? `2px solid ${color}` : `1px solid ${T.border}`, borderRadius:8, padding:"12px 10px", cursor:"pointer", textAlign:"center", background: accentName===name ? color+"15" : T.bg2 }}>
                    <div style={{ width:28, height:28, borderRadius:"50%", background:color, margin:"0 auto 8px" }}/>
                    <div style={{ fontSize:12, color:accentName===name ? color : T.textSecondary, fontWeight:accentName===name?500:400 }}>{name}</div>
                  </div>
                ))}
              </div>

              <p style={{ fontSize:11, color:T.textMuted, textTransform:"uppercase", letterSpacing:".06em", marginBottom:12 }}>Preview</p>
              <div style={{ background:T.bg2, borderRadius:8, padding:"12px 14px", display:"flex", gap:8, alignItems:"center" }}>
                <button style={{ padding:"6px 14px", borderRadius:6, fontSize:12, fontWeight:500, background:T.accent, color:"#000", border:"none", cursor:"pointer" }}>Start</button>
                <button style={{ padding:"6px 14px", borderRadius:6, fontSize:12, fontWeight:500, background:"transparent", color:T.accent, border:`1px solid ${T.accent}`, cursor:"pointer" }}>Scan now</button>
                <span style={{ fontSize:12, color:T.accent, marginLeft:4 }}>● Running</span>
              </div>
            </div>
          )}

          {/* DISPLAY TAB */}
          {tab === "display" && (
            <div>
              <p style={{ fontSize:11, color:T.textMuted, textTransform:"uppercase", letterSpacing:".06em", marginBottom:12 }}>Font size</p>
              <div style={{ display:"flex", gap:8, marginBottom:20 }}>
                {Object.keys(FONT_SIZES).map(name => (
                  <div key={name} onClick={() => setFontSize(name)}
                    style={{ flex:1, padding:"10px 0", borderRadius:8, textAlign:"center", cursor:"pointer", border: fontSize===name ? `2px solid ${T.accent}` : `1px solid ${T.border}`, background: fontSize===name ? T.accent+"15" : T.bg2 }}>
                    <div style={{ fontSize: FONT_SIZES[name], color: fontSize===name ? T.accent : T.textSecondary, fontWeight:500 }}>Aa</div>
                    <div style={{ fontSize:11, color: fontSize===name ? T.accent : T.textMuted, marginTop:4 }}>{name}</div>
                  </div>
                ))}
              </div>

              <p style={{ fontSize:11, color:T.textMuted, textTransform:"uppercase", letterSpacing:".06em", marginBottom:12 }}>Layout</p>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 0", borderBottom:`1px solid ${T.borderSub}` }}>
                <div>
                  <div style={{ fontSize:13, color:T.textPrimary }}>Compact mode</div>
                  <div style={{ fontSize:11, color:T.textMuted, marginTop:2 }}>Reduce padding and card sizes for more data density</div>
                </div>
                <div onClick={() => setCompact(!compact)}
                  style={{ position:"relative", width:36, height:20, borderRadius:10, background:compact?T.accent:T.bg3, cursor:"pointer", flexShrink:0, transition:"background .2s" }}>
                  <div style={{ position:"absolute", top:3, left:compact?17:3, width:14, height:14, borderRadius:"50%", background:"#fff", transition:"left .2s" }}/>
                </div>
              </div>

              <p style={{ fontSize:11, color:T.textMuted, textTransform:"uppercase", letterSpacing:".06em", margin:"16px 0 10px" }}>News sentiment colors</p>
              <div style={{ display:"flex", flexWrap:"wrap", gap:8, marginBottom:16 }}>
                {NEWS_COLOR_SCHEMES.map(s => (
                  <div key={s} onClick={() => setNewsColorScheme(s)}
                    style={{ padding:"7px 14px", borderRadius:8, fontSize:12, cursor:"pointer",
                      border: newsColorScheme===s ? `2px solid ${T.accent}` : `1px solid ${T.border}`,
                      background: newsColorScheme===s ? T.accent+"15" : T.bg2,
                      color: newsColorScheme===s ? T.accent : T.textSecondary }}>
                    {s}
                  </div>
                ))}
              </div>
              <div style={{ marginTop:8, padding:"12px 14px", background:T.bg2, borderRadius:8, fontSize:12, color:T.textMuted }}>
                Changes apply immediately — no restart needed.
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding:"12px 18px", borderTop:`1px solid ${T.border}`, display:"flex", justifyContent:"flex-end" }}>
          <button onClick={onClose} style={{ padding:"7px 20px", borderRadius:7, fontSize:13, fontWeight:500, background:T.accent, color:"#000", border:"none", cursor:"pointer" }}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
