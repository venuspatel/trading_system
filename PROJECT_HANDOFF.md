# TradeAgent — PROJECT HANDOFF
**Date:** May 14, 2026 | **V1 Equity:** ~$1,027,500 | **True Total P&L:** +$27,500

---

## PROJECT GOAL
Build an autonomous AI-powered paper trading agent on Alpaca that scans a watchlist every 2 minutes, scores signals using 13 strategies, and executes buy/sell decisions with full risk management — running 24/7 with a React dashboard and React Native mobile app.

---

## CURRENT STATE (May 14, 2026)

### V1 — Profit Maximizer — RUNNING
- Equity: ~$1,027,500 (+$27,500 from $1M start)
- Keys: PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q
- Stop / TP: 1.0% / 3.0%
- Min conviction: 2.0 (adaptive — raises to 2.5 when win rate < 65%)
- Scan interval: 2 min
- Max positions: 6 (reduced from 10 on May 14)
- Win rate: ~63% overall, 75% in first 4 post-fix trades
- Grade: B-
- Ports: 3000 (frontend) / 8000 (backend)

### V2 — OFF
V2 is disabled. Focus is 100% on V1.

### Mobile App — RUNNING (Expo Go)
- React Native app via Expo Go
- Connected via Cloudflare Tunnel (temporary URL — changes on restart)
- Tunnel command: `cloudflared tunnel --url http://localhost:8000`
- After restart: update URL in AppContext.js → apiBase fallback
- Permanent URL solution deferred until iOS App Store submission

---

## FIXES — May 13-14, 2026

### Fix 15-22: (See May 12 handoff — dashboard overhaul, synthetic curve, mobile)

### Fix 23: AIReviewer Credits + Model String
- Credits ran out ~May 8 — every BUY auto-approved for 5 days
- Model string updated: claude-sonnet-4-20250514 → claude-sonnet-4-6
- Credits topped up at console.anthropic.com
- Impact: win rate dropped 82% → 55% while offline

### Fix 24: AIReviewerBadge Dashboard Component
- File: dashboard/frontend/src/components/AIReviewerBadge.jsx
- Green pulsing dot when active, red dot when credits exhausted
- Shows model, calls succeeded/failed, last error
- Direct link to console.anthropic.com/billing when credits low
- Wired to _agent._dec_engine.reviewer.status_dict via api.py

### Fix 25: AIReviewer Status Tracking
- File: decision_engine/ai_reviewer.py
- Added status field: enabled / no_credits / bad_model / bad_key / error
- Added calls_succeeded / calls_failed / last_error tracking
- Added status_dict property for dashboard
- Detects credit exhaustion specifically (vs generic errors)

### Fix 26: AIReviewer Momentum Prompt Fix
- Was vetoing RSI > 70 as "overbought" — blocking good momentum trades
- Updated prompt: high RSI is acceptable for momentum strategy
- Veto only on: R:R < 1:1, conviction < 1.5, more sells than buys
- Result: RKLB/AMD approved instead of vetoed

### Fix 27: Trail Activation (FLAG-5)
- File: decision_engine/trailing_stop.py
- Enabled trail_activation feature flag in saved_config.json
- Stop doesn't trail until price moves +0.5% from entry
- Eliminates same-minute stop-outs from bid/ask noise
- Was causing 20+ unnecessary losses per week

### Fix 28: Max Positions 10 → 6
- Slots 7-10 were filling with borderline 2.0-2.5 conviction signals
- With 6 slots only top signals trade — quality over quantity
- Win rate improvement expected: 60% → 68-75%

### Fix 29: AI Confidence-Based Position Sizing
- File: decision_engine/engine.py
- After AI review, scales position size by confidence:
  - ≥ 85% confidence → 100% Kelly size
  - 75-84% → 75% size
  - 65-74% → 50% size
  - 60-64% → 35% size
- Log: [Engine] GOOGL AI confidence 72% → size scaled 50%: 222 → 111 shares

### Fix 30: Self-Healing historical_pnl_offset
- File: execution/portfolio_tracker.py
- Added set_alpaca_credentials() + _heal_offset() methods
- On every restart: pulls Alpaca ground truth, recalculates offset
- If gap > $50 → auto-corrects and saves
- Called from trading_agent.py after PortfolioTracker init
- Eliminates manual P&L reconciliation after crashes

### Fix 31: Scan Interval Sync Fix
- File: dashboard/backend/api.py line 298
- scan_frequency_minutes now also sets intraday_interval_min + intraday_mode=True
- ConfigPanel saves no longer produce null scan interval

### Fix 32: Session Ban 3 → 2 Losses
- File: decision_engine/trading_agent.py
- Symbol banned for rest of session after 2 losses (was 3)
- Prevents RKLB/MARA triple-loss days (-$2,471 + -$1,852 on May 13)

### Fix 33: Position Sync Debug
- File: decision_engine/trading_agent.py
- Changed position sync exception from logger.debug → logger.warning
- Now shows actual error if sync fails silently

### Fix 34: Equity Chart Line Color
- File: dashboard/frontend/src/components/EquityChart.jsx
- Line always green regardless of liveDiff at build time
- Was getting stuck red after restart during down period

### Fix 35: Trade Dots + Date Labels on 1D Chart
- File: dashboard/frontend/src/components/EquityChart.jsx
- 1D labels now show "May 12 05:30 PM" format (date + time)
- Trade dot filter uses 24h buffer — yesterday's dots show on 1D
- toLocaleString() → toLocaleString("en-US") globally to fix en-IN formatting

---

## OPEN TASKS (priority order)

### IMMEDIATE
1. Reconcile today's missing trades against Alpaca on next restart
   - Self-healing offset handles P&L but trade records still need injection
   - Check: `python3 -c "import urllib.request,json; ..."`  (see health check)

2. Position display bug after restart
   - _open_positions shows empty for ~3-4 cycles after restart
   - RiskGuardian correctly sees positions via executor (blocks new buys)
   - Display-only issue — resolves itself within 10 minutes
   - Root cause: _open_positions rebuild at cycle start may have timing issue

### SHORT TERM
3. Permanent tunnel URL for mobile app
   - Currently using Cloudflare quick tunnel (temporary, changes on restart)
   - Deferred until iOS App Store submission decision
   - Options: ngrok paid ($8/mo) OR Cloudflare named tunnel (free + own domain)

4. PDT cleanup — FINRA abolished PDT June 4, 2026
   - Remove pattern_day_trader, daytrade_count, daytrading_buying_power
   - Replace with plain buying_power check

5. Smart close wash trade fix
   - Positions bought in same session should not be closed on restart
   - Track _session_buys set and exclude from smart close logic

6. force_scan() EOD scan type bug
   - "Scan now" button triggers EOD scan type instead of INTRADAY
   - Need to pass "INTRADAY" explicitly in force_scan()

### FUTURE — after 4-week paper trading gate
7. Strategy backtester — 3-5 years historical data
8. IBKR live integration (stub exists)
9. Binance crypto integration (stub exists)
10. ML strategy weight optimizer
11. News and sentiment layer
12. Options strategies
13. iOS App Store submission
    - Requires: permanent tunnel URL, TestFlight build, App Store review
    - Tunnel options: ngrok paid OR Cloudflare named tunnel (needs domain)
    - Build: `npx expo build:ios` or EAS Build
    - Estimated effort: 1-2 weeks after paper trading gate passes

---

## KNOWN ISSUES

| Issue | Status |
|---|---|
| Position display shows 0 for ~3-4 cycles after restart | Open — display only, resolves itself |
| force_scan triggers EOD type | Open — cosmetic, scans correctly |
| Missing trades on fast open/close | Workaround: self-healing offset corrects P&L |
| Cloudflare tunnel URL changes on restart | Workaround: update AppContext.js apiBase |
| historical_pnl_offset | Auto-healed on restart via Fix 30 |

---

## KEY DECISIONS (finalized — do not revisit)

1. V2 is OFF — 100% focus on V1 Profit Maximizer
2. Synthetic curve built from trades, starts at $1M April 14
3. historical_pnl_offset auto-heals against Alpaca on every restart
4. toMs() normalization — all timestamps treated as UTC
5. No Y axis on chart — value shows on hover only
6. Executor-level duplicate guard — checks positions AND pending orders
7. Loss-only cooldown 60 min — wins re-enter freely
8. Kelly sizer uses cash not buying_power
9. All 13 strategies active for Profit Maximizer
10. Trail activation ON — stop only trails after +0.5% gain
11. Max positions 6 — quality over quantity
12. Session ban after 2 losses on same symbol (not 3)
13. AI confidence scales position size — 85%+=full, 65-74%=50%
14. AIReviewer prompt: high RSI is OK for momentum strategy
15. Mobile app permanent URL deferred until iOS App Store submission

---

## LAUNCH COMMANDS

```bash
# Start V1 agent + dashboard
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh 2>&1 | tee /tmp/agent_log.txt

# Start mobile tunnel (new terminal — URL changes each time)
cloudflared tunnel --url http://localhost:8000
# Update AppContext.js apiBase with new URL, Metro hot-reloads

# Start mobile app
cd ~/Desktop/trading_system/trading-agent-mobile && npx expo start --lan

# Emergency close all positions
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKUPVN2TBTLKAUHOQLIMWGK4BM' \
  -H 'APCA-API-SECRET-KEY: 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'

# Backup to GitHub + Google Drive
~/Desktop/trading_system/backup.sh
```

---

## HEALTH CHECK

```bash
# Quick status
curl -s http://localhost:8000/api/state > /tmp/state.json && python3 << 'EOF'
import json
with open('/tmp/state.json') as f:
    d = json.load(f)
perf = d.get('performance', {})
rev  = d.get('ai_reviewer', {})
print(f'Status:    {d.get("agent_status")}  Cycle: {d.get("cycle_count")}')
print(f'Equity:    ${d.get("account",{}).get("portfolio_value",0):,.2f}')
print(f'Total P&L: ${perf.get("total_pnl",0):+,.2f}')
print(f'Win rate:  {perf.get("win_rate",0)*100:.1f}%  ({perf.get("total_trades",0)} trades)')
print(f'Reviewer:  {rev.get("status")} ({rev.get("calls_succeeded",0)} reviewed)')
print(f'Positions: {list(d.get("open_positions",{}).keys()) or "none"}')
EOF

# Ground truth from Alpaca
python3 -c "
import urllib.request,json
KEY='PKUPVN2TBTLKAUHOQLIMWGK4BM'; SEC='3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'
req=urllib.request.Request('https://paper-api.alpaca.markets/v2/account',
    headers={'APCA-API-KEY-ID':KEY,'APCA-API-SECRET-KEY':SEC})
acct=json.loads(urllib.request.urlopen(req,timeout=8).read())
print(f'Equity: \${float(acct[\"equity\"]):,.2f}')
print(f'True P&L: \${float(acct[\"equity\"])-1000000:+,.2f}')
"
```

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
| May 13 | -$3,882 | RKLB -$2,471 + MARA -$1,852 multiple re-entries | $1,026,688 |
| May 14 | TBD | All fixes live, trail activation, AI reviewer restored | ~$1,027,500 |

---

## GIT + BACKUP

- Repo: github.com/venuspatel/trading_system (private)
- Auto-backup: cron job at 11 PM every night via backup.sh
- backup.sh: git commit + push (logs excluded via .gitignore)
- Manual backup: ~/Desktop/trading_system/backup.sh
- GitHub token for Claude: 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
- Raw file URLs in project instructions for Claude to fetch

---

## MOBILE APP STATE

- Framework: React Native + Expo (SDK 54)
- Location: ~/Desktop/trading_system/trading-agent-mobile/
- Screens: Login, Home, Positions, Trades, Configure, Alerts
- Connection: Cloudflare Tunnel → FastAPI on port 8000
- Start: `npx expo start --lan` then scan QR with Expo Go
- URL management: AppContext.js → apiBase → update after each tunnel restart
- Push notifications: local only (Expo Go limitation — needs dev build for remote)
- Permanent URL plan: deferred until iOS App Store submission

---

*TradeAgent Project Handoff | May 14, 2026 | Confidential*
