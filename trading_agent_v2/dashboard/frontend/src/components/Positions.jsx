import { useTheme } from "./ThemeContext";
export default function Positions({ state }) {
  const { theme: T, compact } = useTheme();
  const positions = state?.open_positions || state?.positions || {};
  const account   = state?.account||{};
  const fmt$ = v => v!=null?`$${Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`:"—";
  const p = compact?12:16;
  return (
    <div style={{padding:p}}>
      <div style={{fontSize:11,color:T.textMuted,textTransform:"uppercase",letterSpacing:".08em",marginBottom:16}}>Open positions</div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:8,marginBottom:16}}>
        {[{label:"Portfolio value",value:fmt$(account.portfolio_value)},{label:"Cash available",value:fmt$(account.cash)},{label:"Buying power",value:fmt$(account.buying_power)}].map(m=>(
          <div key={m.label} style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,padding:"10px 12px"}}>
            <div style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em",marginBottom:3}}>{m.label}</div>
            <div style={{fontSize:18,fontWeight:500,color:T.textPrimary,fontVariantNumeric:"tabular-nums"}}>{m.value}</div>
          </div>
        ))}
      </div>
      <div style={{background:T.cardBg,border:`1px solid ${T.border}`,borderRadius:8,overflow:"hidden"}}>
        <div style={{display:"grid",gridTemplateColumns:"minmax(60px,80px) 1fr 1fr 1fr 1fr minmax(80px,10%) minmax(80px,10%)",padding:"8px 14px",borderBottom:`1px solid ${T.border}`,background:T.bg3}}>
          {["Symbol","Qty","Entry","Current","P&L","Stop","Target"].map(h=>(
            <div key={h} style={{fontSize:10,color:T.textMuted,textTransform:"uppercase",letterSpacing:".05em"}}>{h}</div>
          ))}
        </div>
        {Object.keys(positions).length===0
          ? <div style={{padding:"24px 14px",fontSize:13,color:T.textMuted,textAlign:"center"}}>No open positions</div>
          : Object.entries(positions).map(([sym,pos])=>(
            <div key={sym} style={{display:"grid",gridTemplateColumns:"minmax(60px,80px) 1fr 1fr 1fr 1fr minmax(80px,10%) minmax(80px,10%)",padding:"10px 14px",borderBottom:`1px solid ${T.borderSub}`,alignItems:"center"}}>
              <div style={{fontSize:13,fontWeight:600,color:T.textPrimary}}>{sym}</div>
              <div style={{fontSize:12,color:T.textSecondary,fontVariantNumeric:"tabular-nums"}}>{pos.qty}</div>
              <div style={{fontSize:12,color:T.textSecondary,fontVariantNumeric:"tabular-nums"}}>{fmt$(pos.entry_price)}</div>
              <div style={{fontSize:12,color:T.textPrimary,fontVariantNumeric:"tabular-nums"}}>{fmt$(pos.current_price)}</div>
              <div style={{fontSize:13,fontWeight:500,color:pos.pnl>=0?T.profit:T.loss,fontVariantNumeric:"tabular-nums"}}>{pos.pnl>=0?"+":""}${pos.pnl?.toFixed(2)}</div>
              <div style={{fontSize:11,color:T.loss,fontVariantNumeric:"tabular-nums"}}>{fmt$(pos.stop_loss)}</div>
              <div style={{fontSize:11,color:T.profit,fontVariantNumeric:"tabular-nums"}}>{fmt$(pos.take_profit)}</div>
            </div>
          ))
        }
      </div>
    </div>
  );
}
