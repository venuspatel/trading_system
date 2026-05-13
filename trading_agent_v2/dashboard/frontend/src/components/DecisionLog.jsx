import { useState } from "react";
import { useTheme } from "./ThemeContext";

export default function DecisionLog({ state, events }) {
  const { theme: T, compact } = useTheme();
  const [filter,   setFilter]   = useState("ALL");
  const [expanded, setExpanded] = useState(null);

  const decisions = state?.recent_decisions || [];
  const all = [...events.map(e => ({...e, _live:true})), ...decisions].slice(0, 60);
  const filtered = filter === "ALL" ? all : all.filter(d => d.action === filter);

  const SC = { BUY:T.profit, SELL:T.loss, HOLD:T.textMuted, BLOCKED:T.warning };
  const SB = { BUY:T.profit+"15", SELL:T.loss+"15", HOLD:T.bg3, BLOCKED:T.warning+"15" };

  return (
    <div style={{padding:compact?12:16}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
        <span style={{fontSize:11,color:T.textMuted,textTransform:"uppercase",letterSpacing:".08em"}}>Decision log</span>
        <div style={{display:"flex",gap:6}}>
          {["ALL","BUY","SELL","BLOCKED","HOLD"].map(f => (
            <div key={f} onClick={() => setFilter(f)}
              style={{padding:"4px 10px",borderRadius:6,fontSize:11,fontWeight:500,cursor:"pointer",
                border: filter===f ? `1px solid ${SC[f]||T.accent}` : `1px solid ${T.border}`,
                background: filter===f ? (SB[f]||T.accent+"15") : T.bg3,
                color: filter===f ? (SC[f]||T.accent) : T.textMuted}}>
              {f}
            </div>
          ))}
        </div>
      </div>

      <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,overflow:"hidden"}}>
        {/* Header */}
        <div style={{display:"grid",gridTemplateColumns:"48px 56px 68px 72px 1fr 80px",padding:"8px 14px",borderBottom:`1px solid ${T.border}`,background:T.bg3}}>
          {["Time","Symbol","Action","Conviction","Reason","AI"].map(h => (
            <div key={h} style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em"}}>{h}</div>
          ))}
        </div>

        {filtered.length === 0
          ? <div style={{padding:"24px 14px",fontSize:13,color:T.textMuted,textAlign:"center"}}>No decisions yet — hit Scan now</div>
          : filtered.map((d, i) => {
              const col = SC[d.action] || T.textMuted;
              const bg  = SB[d.action] || T.bg3;
              const hasAI = d.ai_used && d.ai_reasoning;
              const isOpen = expanded === i;

              return (
                <div key={i}>
                  <div onClick={() => setExpanded(isOpen ? null : i)}
                    style={{display:"grid",gridTemplateColumns:"48px 56px 68px 72px 1fr 80px",padding:"8px 14px",borderBottom:`1px solid ${T.borderSub}`,alignItems:"center",cursor:"pointer",background:isOpen?T.bg3:d._live?T.bg3:undefined}}>
                    <div style={{fontSize:10,color:T.textMuted,fontVariantNumeric:"tabular-nums"}}>{d.ts||d.timestamp?.slice(11,16)||"—"}</div>
                    <div style={{fontSize:12,fontWeight:600,color:T.textPrimary}}>{d.symbol}</div>
                    <div style={{fontSize:10,fontWeight:700,padding:"2px 6px",borderRadius:4,background:bg,color:col,textAlign:"center"}}>{d.action}</div>
                    <div style={{fontSize:12,color:d.conviction_score>0?T.profit:d.conviction_score<0?T.loss:T.textMuted,fontVariantNumeric:"tabular-nums"}}>
                      {d.conviction_score!=null ? `${d.conviction_score>0?"+":""}${Number(d.conviction_score).toFixed(2)}` : "—"}
                    </div>
                    <div style={{fontSize:11,color:T.textSecondary,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>
                      {(d.top_reasons||[])[0]||d.reason||""}
                    </div>
                    {/* AI badge */}
                    <div style={{fontSize:10,fontWeight:600,padding:"2px 7px",borderRadius:4,textAlign:"center",
                      background: hasAI ? (d.ai_approved!==false ? T.profit+"15" : T.loss+"15") : T.bg3,
                      color: hasAI ? (d.ai_approved!==false ? T.profit : T.loss) : T.textMuted,
                      border: hasAI ? `1px solid ${d.ai_approved!==false ? T.profit : T.loss}33` : `1px solid ${T.border}`}}>
                      {hasAI ? (d.ai_approved!==false ? `AI ${Math.round((d.ai_confidence||0)*100)}%` : "AI VETO") : "—"}
                    </div>
                  </div>

                  {/* Expanded AI reasoning panel */}
                  {isOpen && (
                    <div style={{padding:"12px 14px",background:T.bg1,borderBottom:`1px solid ${T.border}`}}>
                      {hasAI ? (
                        <div>
                          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
                            <div style={{width:6,height:6,borderRadius:"50%",background:d.ai_approved!==false?T.profit:T.loss}}/>
                            <span style={{fontSize:11,fontWeight:500,color:d.ai_approved!==false?T.profit:T.loss}}>
                              {d.ai_approved!==false ? "AI approved" : "AI vetoed"} — {Math.round((d.ai_confidence||0)*100)}% confidence
                            </span>
                          </div>
                          <p style={{fontSize:12,color:T.textPrimary,margin:"0 0 8px",lineHeight:1.6}}>
                            {d.ai_reasoning}
                          </p>
                          {(d.ai_concerns||[]).length > 0 && (
                            <div style={{marginBottom:6}}>
                              <span style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em"}}>Concerns</span>
                              {(d.ai_concerns||[]).map((c,ci) => (
                                <div key={ci} style={{fontSize:11,color:T.warning,marginTop:3}}>· {c}</div>
                              ))}
                            </div>
                          )}
                          {d.ai_suggestion && (
                            <div style={{fontSize:11,color:T.accent,marginTop:4}}>
                              Suggestion: {d.ai_suggestion}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div>
                          <p style={{fontSize:12,color:T.textSecondary,margin:"0 0 6px"}}>
                            {(d.top_reasons||[]).map((r,ri) => <div key={ri} style={{marginBottom:3}}>· {r}</div>)}
                          </p>
                          {d.strategies_fired?.length > 0 && (
                            <div style={{fontSize:11,color:T.textMuted,marginTop:6}}>
                              Strategies: {(d.strategies_fired||[]).join(", ")}
                            </div>
                          )}
                          <div style={{fontSize:11,color:T.textMuted,marginTop:4,padding:"6px 10px",background:T.bg3,borderRadius:6,display:"inline-block"}}>
                            Add ANTHROPIC_API_KEY to .env to enable AI reasoning
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
        }
      </div>

      <div style={{marginTop:8,fontSize:11,color:T.textMuted,textAlign:"right"}}>
        {filtered.length} decisions · Click any row to expand reasoning
      </div>
    </div>
  );
}
