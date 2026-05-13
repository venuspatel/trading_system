# TradeAgent — PROJECT HANDOFF
**Date:** May 12, 2026 | **V1 Equity:** $1,030,574 | **True Total P&L:** +$30,574

---

## PROJECT GOAL
Build an autonomous AI-powered paper trading agent on Alpaca that scans a watchlist every 2 minutes, scores signals using 13 strategies, and executes buy/sell decisions with full risk management — running 24/7 with a React dashboard and React Native mobile app.

---

## CURRENT STATE (May 12, 2026)

### V1 — Profit Maximizer — RUNNING
- Equity: $1,030,574 (+$30,574 from $1M start)
- Keys: PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q
- Stop / TP: 1.0% / 3.0%
- Min conviction: 2.0 (adaptive)
- Scan interval: 2 min
- Max positions: 10
- Win rate: 60% over 67 trades (76% peak on May 4)
- Grade: C (today GOOGL/ORCL/QCOM losses)
- Ports: 3000 (frontend) / 8000 (backend)

### V2 — OFF
V2 is disabled. Focus is 100% on V1.

---

## NEW FIXES — May 12, 2026

### Fix 15: Synthetic Equity Curve
- File: execution/portfolio_tracker.py
- Added _rebuild_synthetic_curve() — builds curve from all trades starting at $1M
- Added synthetic_curve property — exposed in /api/state
- Rebuilt after every trade and on load
- Dashboard + mobile use synthetic curve for ALL/1Y/YTD/3M views
- Short-range views (1D/1W/1M) use live snapshot curve

### Fix 16: Historical P&L Offset
- File: execution/portfolio_tracker.py, logs/portfolio.json
- Added _historical_pnl_offset field — stores $28,164.41 of pre-recording P&L
- Loaded from portfolio.json key: historical_pnl_offset
- Added to total_closed_pnl in stats computation
- Survives restarts — persisted in JSON
- Total P&L now shows true +$30,574 matching Alpaca

### Fix 17: Performance Tab Datetime Fix
- File: performance/analyzer.py → _parse_dt()
- Was returning naive datetime for strings without timezone
- Fix: always attach timezone.utc if tzinfo is None
- Performance tab now loads all 67 trades correctly

### Fix 18: Trade Dots Timezone Fix
- Files: dashboard/frontend/src/components/EquityChart.jsx
         trading-agent-mobile/components/EquityChart.jsx
- Curve timestamps are UTC-aware (+00:00), trade exit_times are naive
- Fix: toMs() helper normalizes both — appends Z if no timezone info
- Removed 900,000ms distance limit — snaps to nearest point within slice

### Fix 19: Dashboard Zone 2 Redesign
- File: dashboard/frontend/src/components/Dashboard.jsx
- Open Positions: column headers (SYMBOL, QTY@ENTRY, CURRENT, STOP, P&L)
- Today's Trades: full columns (WIN/LOSS, SYMBOL+DATE, REASON, IN→OUT, TIME, P&L)
- Trades per page: 6
- Date shown under symbol for all trades

### Fix 20: EquityChart Full Rewrite (Dashboard)
- File: dashboard/frontend/src/components/EquityChart.jsx
- Mobile-style normalized P&L chart
- No Y axis — value shows in header on hover only
- Dashed baseline with $1M start label
- Green fill above baseline, red fill below
- Stats row: Peak gain / Peak loss / Trades / Net P&L
- 9 range buttons: 1H 3H 1D 1W 1M 3M YTD 1Y ALL
- Zoom in/out + click-drag pan
- Bold crosshair with time label pill on hover
- Default range: 1D

### Fix 21: Mobile Trade Row Redesign
- File: trading-agent-mobile/screens/TradesScreen.jsx
- Single-line layout: badge + symbol+date + reason+price/time + P&L
- Date shown under symbol for all trades
- Price and time on same line separated by dot
- Larger fonts: 13px symbol, 11px reason, 10px price/time
- Brighter colors: #cccccc prices/times, #aaaaaa dates

### Fix 22: Mobile EquityChart Synthetic Curve
- File: trading-agent-mobile/components/EquityChart.jsx
- Added syntheticCurve prop
- ALL/1Y/YTD/3M use synthetic curve (full history from $1M)
- Short ranges use live snapshot curve

---

## OPEN TASKS (priority order)

### IMMEDIATE — before next trading day
1. AIReviewer 400 errors
   - Error: [AIReviewer] API call failed: HTTP Error 400
   - Find model string: grep -rn "claude\|model" ~/Desktop/trading_system/trading_agent/decision_engine/
   - Fix: update to claude-sonnet-4-20250514
   - API key is in .env: ANTHROPIC_API_KEY=sk-ant-...

2. Smart close wash trade fix
   - Positions bought in same session should not be closed on restart
   - Track _session_buys set and exclude from smart close logic

### SHORT TERM
3. PDT cleanup — FINRA abolished PDT June 4, 2026 (3 weeks away)
   - Remove pattern_day_trader, daytrade_count, daytrading_buying_power
   - Replace with plain buying_power check

4. Win rate improvement — currently 60%, target 70%+
   - Today losses: GOOGL -$934, ORCL -$926, QCOM -$936, TSLA -$390
   - Look at conviction threshold tuning
   - Consider sector concentration limits

### FUTURE — after 4-week paper trading gate
5. Strategy backtester — 3-5 years historical data
6. IBKR live integration (stub exists)
7. Binance crypto integration (stub exists)
8. ML strategy weight optimizer
9. News and sentiment layer
10. Options strategies

---

## KNOWN ISSUES

| Issue | Status |
|---|---|
| AIReviewer 400 errors | OPEN — fix tomorrow |
| Trade history loss on crash | Workaround: Alpaca recovery script |
| Smart close wash trades | OPEN |
| historical_pnl_offset is static | Manual update needed after Alpaca recovery |

---

## KEY DECISIONS (finalized — do not revisit)

1. V2 is OFF — 100% focus on V1 Profit Maximizer
2. Synthetic curve built from trades, starts at $1M April 14
3. historical_pnl_offset persists in portfolio.json across restarts
4. toMs() normalization — all timestamps treated as UTC
5. No Y axis on chart — value shows on hover only
6. Executor-level duplicate guard — checks positions AND pending orders
7. Loss-only cooldown 60 min — wins re-enter freely
8. Kelly sizer uses cash not buying_power
9. All 13 strategies active for Profit Maximizer

---

## LAUNCH COMMANDS

# Start V1
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh

# Emergency close all positions
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKUPVN2TBTLKAUHOQLIMWGK4BM' \
  -H 'APCA-API-SECRET-KEY: 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'

# Manual backup to GitHub
~/Desktop/trading_system/backup.sh

---

## HEALTH CHECK

# Quick status
curl -s http://localhost:8000/api/state | python3 -c "
import sys,json; d=json.load(sys.stdin)
perf=d.get('performance',{})
print(f'Status: {d.get("agent_status")}')
print(f'Equity: \${d.get("account",{}).get("portfolio_value",0):,.2f}')
print(f'Total P&L: \${perf.get("total_pnl",0):+,.2f}')
print(f'Win rate: {perf.get("win_rate",0)*100:.1f}%')
print(f'Trades: {perf.get("total_trades",0)}')
"

# Ground truth from Alpaca
python3 -c "
import urllib.request,json
KEY='PKUPVN2TBTLKAUHOQLIMWGK4BM'; SEC='3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'
req=urllib.request.Request('https://paper-api.alpaca.markets/v2/account',
    headers={'APCA-API-KEY-ID':KEY,'APCA-API-SECRET-KEY':SEC})
acct=json.loads(urllib.request.urlopen(req,timeout=8).read())
print(f'Equity: \${float(acct["equity"]):,.2f}')
print(f'True P&L: \${float(acct["equity"])-1000000:+,.2f}')
"

---

## PERFORMANCE HISTORY

| Date | Day P&L | Notes | Equity |
|---|---|---|---|
| Apr 28 | +$739 | 3 trades, 100% win | $1,001,010 |
| May 1 | +$237 | Duplicate buy bug, PDT flagged | $1,005,617 |
| May 4 | +$13,026 | 82% win rate | $1,020,217 |
| May 5 | +$355 | 23 trades, 82% win, B+ | $1,005,053 |
| May 6 | +$4,785 | Cooldown bug blocked AM | $1,030,632 |
| May 7 | $0 | is_stopped_out wrong name — 0 trades | $1,031,060 |
| May 8 | Ready | All fixes deployed | $1,031,060 |
| May 12 | +$3,881 | Dashboard overhaul, synthetic curve, git backup | $1,030,574 |

---

## GIT BACKUP

- Repo: github.com/venuspatel/trading_system (private)
- Auto-backup: cron job at 11 PM every night
- Manual backup: ~/Desktop/trading_system/backup.sh
- SSH key configured on this Mac

---

*TradeAgent Project Handoff | May 12, 2026 | Confidential*
