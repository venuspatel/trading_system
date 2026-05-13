import { useEffect, useRef } from 'react';
import { sendLocalNotification } from './notifications';

export function useTradeNotifications(apiBase) {
  const lastTradeCount = useRef(0);
  const lastPositions  = useRef({});

  useEffect(() => {
    if (!apiBase || apiBase.includes('localhost')) return;

    const interval = setInterval(async () => {
      try {
        const res  = await fetch(`${apiBase}/api/state`, { signal: AbortSignal.timeout(8000) });
        const data = await res.json();

        // Check for new closed trades
        const trades = data?.recent_trades || [];
        if (lastTradeCount.current > 0 && trades.length > lastTradeCount.current) {
          const newTrades = trades.slice(trades.length - (trades.length - lastTradeCount.current));
          for (const t of newTrades) {
            const isWin = t.pnl >= 0;
            const emoji = isWin ? '✅' : '🔴';
            const sign  = isWin ? '+' : '';
            await sendLocalNotification(
              `${emoji} ${t.symbol} ${isWin ? 'WIN' : 'LOSS'}`,
              `${sign}$${Math.abs(t.pnl).toFixed(0)} · ${t.exit_reason?.slice(0,40) || 'Trade closed'}`
            );
          }
        }
        lastTradeCount.current = trades.length;

        // Check for new positions opened
        const positions = data?.positions || {};
        const newSymbols = Object.keys(positions).filter(s => !lastPositions.current[s]);
        for (const sym of newSymbols) {
          const pos = positions[sym];
          await sendLocalNotification(
            `🟢 Bought ${sym}`,
            `${pos.qty} shares @ $${parseFloat(pos.entry_price || 0).toFixed(2)}`
          );
        }
        lastPositions.current = positions;

      } catch(e) {
        // Silent fail — don't spam console
      }
    }, 30000); // check every 30 seconds

    return () => clearInterval(interval);
  }, [apiBase]);
}
