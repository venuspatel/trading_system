import { useState, useEffect, useCallback } from "react";
import { useTheme } from "./ThemeContext";

const GRADE_CONFIG = {
  STRONGLY_POSITIVE: { label: "Strongly positive", short: "++" },
  POSITIVE:          { label: "Positive",           short: "+"  },
  NEUTRAL:           { label: "Neutral",            short: "~"  },
  NEGATIVE:          { label: "Negative",           short: "-"  },
  STRONGLY_NEGATIVE: { label: "Strongly negative",  short: "--" },
};

function sentimentColors(score, scheme, T) {
  const schemes = {
    "Red → Green": {
      sp: { bg:"#052210", border:"#22c55e44", text:"#22c55e", bar:"#22c55e" },
      p:  { bg:"#0a1a0a", border:"#4ade8044", text:"#4ade80", bar:"#4ade80" },
      n:  { bg:"#111",    border:"#33333344", text:"#666",    bar:"#444"    },
      ng: { bg:"#1a1200", border:"#f59e0b44", text:"#f59e0b", bar:"#f59e0b" },
      sn: { bg:"#1f0505", border:"#ef444444", text:"#ef4444", bar:"#ef4444" },
    },
    "Blue → Amber": {
      sp: { bg:"#020e1f", border:"#4d9cf844", text:"#4d9cf8", bar:"#4d9cf8" },
      p:  { bg:"#071525", border:"#60a5fa44", text:"#60a5fa", bar:"#60a5fa" },
      n:  { bg:"#111",    border:"#33333344", text:"#666",    bar:"#444"    },
      ng: { bg:"#1a1200", border:"#f59e0b44", text:"#f59e0b", bar:"#f59e0b" },
      sn: { bg:"#1a0e00", border:"#fb923c44", text:"#fb923c", bar:"#fb923c" },
    },
    "Purple → Teal": {
      sp: { bg:"#04201a", border:"#2dd4bf44", text:"#2dd4bf", bar:"#2dd4bf" },
      p:  { bg:"#082018", border:"#34d39944", text:"#34d399", bar:"#34d399" },
      n:  { bg:"#111",    border:"#33333344", text:"#666",    bar:"#444"    },
      ng: { bg:"#140820", border:"#a78bfa44", text:"#a78bfa", bar:"#a78bfa" },
      sn: { bg:"#1e0a30", border:"#c084fc44", text:"#c084fc", bar:"#c084fc" },
    },
    "Monochrome": {
      sp: { bg:"#1a1a1a", border:"#e0e0e044", text:"#e0e0e0", bar:"#e0e0e0" },
      p:  { bg:"#141414", border:"#aaaaaa44", text:"#aaaaaa", bar:"#aaaaaa" },
      n:  { bg:"#111",    border:"#55555544", text:"#555",    bar:"#444"    },
      ng: { bg:"#111",    border:"#77777744", text:"#777",    bar:"#666"    },
      sn: { bg:"#0a0a0a", border:"#99999944", text:"#999",    bar:"#888"    },
    },
  };

  const palette = schemes[scheme] || schemes["Red → Green"];
  if (score >= 0.6)  return palette.sp;
  if (score >= 0.25) return palette.p;
  if (score >= -0.25)return palette.n;
  if (score >= -0.6) return palette.ng;
  return palette.sn;
}

function TickerChip({ sym, data, active, onClick, scheme, T }) {
  const score = data?.score ?? 0;
  const c = sentimentColors(score, scheme, T);
  return (
    <div onClick={() => onClick(sym)}
      style={{padding:"6px 12px",borderRadius:7,border:active?`2px solid ${c.text}`:`1px solid ${c.border}`,
        background:active?c.bg+"cc":c.bg,cursor:"pointer",textAlign:"center",minWidth:62,transition:"all .15s"}}>
      <div style={{fontSize:12,fontWeight:700,color:c.text}}>{sym}</div>
      <div style={{fontSize:9,color:c.text,opacity:.8,fontVariantNumeric:"tabular-nums"}}>
        {score>0?"+":""}{score.toFixed(2)}
      </div>
    </div>
  );
}

function SentimentBar({ score, scheme, T }) {
  const c = sentimentColors(score, scheme, T);
  const pct = Math.abs(score) * 50;
  return (
    <div style={{display:"flex",alignItems:"center",gap:10,padding:"8px 14px",background:"#080808",borderBottom:"1px solid #1c1c1c"}}>
      <span style={{fontSize:10,color:"#ef4444",minWidth:24,textAlign:"right",fontVariantNumeric:"tabular-nums"}}>-1</span>
      <div style={{flex:1,height:5,background:"#1c1c1c",borderRadius:3,position:"relative"}}>
        <div style={{position:"absolute",left:"50%",top:0,width:1,height:"100%",background:"#333"}}/>
        {score >= 0
          ? <div style={{position:"absolute",left:"50%",width:`${pct}%`,height:"100%",background:c.bar,borderRadius:"0 3px 3px 0"}}/>
          : <div style={{position:"absolute",right:"50%",width:`${pct}%`,height:"100%",background:c.bar,borderRadius:"3px 0 0 3px"}}/>
        }
      </div>
      <span style={{fontSize:10,color:c.text,minWidth:36,fontVariantNumeric:"tabular-nums",fontWeight:500}}>
        {score>0?"+":""}{score.toFixed(2)}
      </span>
      <span style={{fontSize:10,color:"#555"}}>
        {data => data?.sources_count || 0} sources · {data => data?.article_count || 0} articles
      </span>
    </div>
  );
}

function ArticleRow({ article, scheme, T }) {
  const score = article.score ?? 0;
  const c = sentimentColors(score, scheme, T);
  const grade = GRADE_CONFIG[article.grade] || GRADE_CONFIG.NEUTRAL;
  return (
    <div style={{display:"flex",gap:10,padding:"10px 14px",borderBottom:"1px solid #111",alignItems:"flex-start"}}>
      <div style={{width:3,alignSelf:"stretch",borderRadius:2,background:c.bar,flexShrink:0,minHeight:30}}/>
      <div style={{flex:1}}>
        <div style={{fontSize:12,color:"#d0d0d0",marginBottom:4,lineHeight:1.5}}>{article.headline}</div>
        <div style={{display:"flex",alignItems:"center",gap:6}}>
          <span style={{fontSize:10,color:"#666"}}>{article.source}</span>
          <span style={{fontSize:9,padding:"1px 6px",borderRadius:4,fontWeight:600,background:c.bg,color:c.text,border:`1px solid ${c.border}`}}>
            {grade.label}
          </span>
          {article.method === "claude" && (
            <span style={{fontSize:9,padding:"1px 6px",borderRadius:4,background:"#0d1a30",color:"#4d9cf8",border:"1px solid #4d9cf833"}}>AI</span>
          )}
        </div>
      </div>
      <div style={{fontSize:11,fontWeight:500,color:c.text,fontVariantNumeric:"tabular-nums",flexShrink:0}}>
        {score>0?"+":""}{score.toFixed(2)}
      </div>
    </div>
  );
}

export default function NewsTab({ state, api }) {
  const { theme: T, newsColorScheme = "Red → Green" } = useTheme();
  const [selected,    setSelected]    = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const newsData  = state?.news_sentiment || {};
  const watchlist = state?.watchlist || [];

  // Auto-select first symbol
  useEffect(() => {
    if (!selected && watchlist.length > 0) setSelected(watchlist[0]);
  }, [watchlist, selected]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      await fetch(`${api}/api/news/refresh`, { method: "POST" });
      setLastUpdated(new Date().toLocaleTimeString());
      setTimeout(() => setLoading(false), 3000);
    } catch(e) { setLoading(false); }
  }, [api]);

  const selectedData = selected ? newsData[selected] : null;

  // Sort watchlist by sentiment score
  const sortedWatchlist = [...watchlist].sort((a, b) => {
    const sa = newsData[a]?.score ?? 0;
    const sb = newsData[b]?.score ?? 0;
    return sb - sa;
  });

  const sc = sentimentColors(selectedData?.score ?? 0, newsColorScheme, T);

  return (
    <div style={{padding:16}}>
      {/* Header */}
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
        <div>
          <span style={{fontSize:11,color:"#666",textTransform:"uppercase",letterSpacing:".08em"}}>News & sentiment</span>
          {lastUpdated && <span style={{fontSize:10,color:"#444",marginLeft:8}}>Updated {lastUpdated}</span>}
        </div>
        <button onClick={refresh} disabled={loading}
          style={{padding:"5px 14px",borderRadius:6,fontSize:11,fontWeight:500,border:"1px solid #1a2a4a",background:"#0d1a30",color:loading?"#444":"#4d9cf8",cursor:"pointer"}}>
          {loading ? "Fetching..." : "Refresh news"}
        </button>
      </div>

      {/* Ticker chips — sorted by sentiment */}
      <div style={{marginBottom:14}}>
        <div style={{fontSize:10,color:"#444",textTransform:"uppercase",letterSpacing:".05em",marginBottom:8}}>
          Watchlist sentiment — sorted by score
        </div>
        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
          {sortedWatchlist.map(sym => (
            <TickerChip key={sym} sym={sym} data={newsData[sym]} active={selected===sym}
              onClick={setSelected} scheme={newsColorScheme} T={T}/>
          ))}
        </div>
      </div>

      {/* Empty state */}
      {Object.keys(newsData).length === 0 && (
        <div style={{background:"#0a0a0a",border:"1px solid #1c1c1c",borderRadius:8,padding:"24px 14px",textAlign:"center"}}>
          <div style={{fontSize:13,color:"#444",marginBottom:8}}>No news loaded yet</div>
          <div style={{fontSize:11,color:"#333"}}>Click "Refresh news" to fetch the latest headlines for your watchlist</div>
        </div>
      )}

      {/* Detail panel */}
      {selected && selectedData && (
        <div style={{background:"#050505",border:"1px solid #252525",borderRadius:10,overflow:"hidden"}}>

          {/* Symbol header */}
          <div style={{padding:"12px 14px",borderBottom:"1px solid #1c1c1c",background:"#0a0a0a",display:"flex",alignItems:"center",gap:10}}>
            <div style={{flex:1}}>
              <div style={{display:"flex",alignItems:"center",gap:8}}>
                <span style={{fontSize:18,fontWeight:700,color:"#f0f0f0"}}>{selected}</span>
                <span style={{fontSize:11,color:"#666"}}>
                  {selectedData.article_count} articles · {selectedData.sources_count} sources
                </span>
              </div>
              <div style={{fontSize:11,color:"#444",marginTop:2}}>{GRADE_CONFIG[selectedData.grade]?.label || "Neutral"}</div>
            </div>
            <div style={{padding:"5px 14px",borderRadius:6,fontSize:13,fontWeight:600,background:sc.bg,color:sc.text,border:`1px solid ${sc.border}`}}>
              {selectedData.score>0?"+":""}{selectedData.score.toFixed(2)}
            </div>
            <div style={{padding:"5px 12px",borderRadius:6,fontSize:11,background:"#111",color:selectedData.signal==="BUY_BOOST"?"#22c55e":selectedData.signal==="SELL_SIGNAL"?"#ef4444":"#666",border:"1px solid #222"}}>
              {selectedData.signal}
            </div>
          </div>

          {/* Sentiment bar */}
          <div style={{display:"flex",alignItems:"center",gap:10,padding:"8px 14px",background:"#080808",borderBottom:"1px solid #1c1c1c"}}>
            <span style={{fontSize:10,color:"#ef4444",minWidth:24,textAlign:"right"}}>-1.0</span>
            <div style={{flex:1,height:5,background:"#1c1c1c",borderRadius:3,position:"relative"}}>
              <div style={{position:"absolute",left:"50%",top:0,width:1,height:"100%",background:"#333"}}/>
              {selectedData.score >= 0
                ? <div style={{position:"absolute",left:"50%",width:`${Math.abs(selectedData.score)*50}%`,height:"100%",background:sc.bar,borderRadius:"0 3px 3px 0"}}/>
                : <div style={{position:"absolute",right:"50%",width:`${Math.abs(selectedData.score)*50}%`,height:"100%",background:sc.bar,borderRadius:"3px 0 0 3px"}}/>
              }
            </div>
            <span style={{fontSize:10,color:sc.text,minWidth:40,fontWeight:500,fontVariantNumeric:"tabular-nums"}}>
              {selectedData.score>0?"+":""}{selectedData.score.toFixed(2)}
            </span>
            <span style={{fontSize:10,color:"#555"}}>
              confidence {Math.round((selectedData.confidence||0)*100)}%
            </span>
          </div>

          {/* Articles */}
          {(selectedData.articles || []).length > 0 ? (
            <div>
              {(selectedData.articles || []).map((a, i) => (
                <ArticleRow key={i} article={a} scheme={newsColorScheme} T={T}/>
              ))}
            </div>
          ) : (
            <div style={{padding:"16px 14px",fontSize:12,color:"#444",textAlign:"center"}}>
              No articles found — click Refresh news
            </div>
          )}

          {/* AI summary */}
          {selectedData.ai_summary && (
            <div style={{padding:"12px 14px",background:"#080808",borderTop:"1px solid #1c1c1c"}}>
              <div style={{fontSize:10,color:"#4d9cf8",textTransform:"uppercase",letterSpacing:".05em",marginBottom:5,display:"flex",alignItems:"center",gap:5}}>
                <div style={{width:5,height:5,borderRadius:"50%",background:"#4d9cf8"}}/>
                AI summary
              </div>
              <div style={{fontSize:12,color:"#aaa",lineHeight:1.7}}>{selectedData.ai_summary}</div>
            </div>
          )}
        </div>
      )}

      {/* Selected but no data yet */}
      {selected && !selectedData && Object.keys(newsData).length === 0 && (
        <div style={{background:"#0a0a0a",border:"1px solid #1c1c1c",borderRadius:8,padding:"16px 14px",textAlign:"center",fontSize:12,color:"#444"}}>
          Click "Refresh news" to load headlines for {selected}
        </div>
      )}
    </div>
  );
}
