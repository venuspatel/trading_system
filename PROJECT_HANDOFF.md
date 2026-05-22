# TradeAgent — PROJECT HANDOFF
**Date:** May 15, 2026 | **V1 Equity:** $1,027,097 | **True Total P&L:** +$27,487

---

## PROJECT GOAL
Build an autonomous AI-powered paper trading agent on Alpaca that scans a watchlist every 2 minutes, scores signals using 13 strategies, and executes buy/sell decisions with full risk management — running 24/7 with a React dashboard and React Native mobile app.

---

## CURRENT STATE (May 15, 2026)

### V1 — Profit Maximizer — RUNNING (STABLE — DO NOT MODIFY)
- Equity: $1,027,097 (+$27,487 from $1M start)
- Keys: PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q
- Stop / TP: 1.0% / 3.0%
- Min conviction: 2.0 (adaptive)
- Scan interval: 2 min
- Max positions: 6
- Win rate: 64.2% over 95 trades
- Ports: 3000 (frontend) / 8000 (backend)
- Status: All fixes deployed, running stable

### V2 — Experiment Agent — READY TO START
- Fresh copy of V1 codebase
- Keys: PKP3WTGVDUYTDCYW5VDW3Z3CMZ / HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm
- Starting equity: ~$997,547
- Ports: 3001 (frontend) / 8001 (backend)
- Purpose: Test new candle strategies before promoting to V1
- Enhanced: Pin Bar, Harami, Harami Cross, Gravestone Doji, Dragonfly Doji, Inverted Hammer

### Mobile App
- Framework: React Native + Expo (SDK 54)
- Connection: Cloudflare Tunnel → port 8000
- Start tunnel: `cloudflared tunnel --url http://localhost:8000`
- Update URL in: `trading-agent-mobile/context/AppContext.js` → apiBase
- Permanent URL deferred until iOS App Store submission

---

## ARCHITECTURE

```
trading_system/
├── trading_agent/          ← V1 STABLE (ports 3000/8000)
├── trading_agent_v2/       ← V2 EXPERIMENT (ports 3001/8001)
└── trading-agent-mobile/   ← React Native mobile app
```

V2 differs from V1 only in:
- Alpaca keys (.env)
- Ports (run_dashboard.sh)
- Enhanced candle strategies (strategies/candle_reversal.py + indicators/candlestick.py)
- Fresh portfolio.json (starting $997,547)

---

## ALL FIXES (May 13-15)

### Fix 23: AIReviewer Credits + Model String
- Credits ran out ~May 8 — every BUY auto-approved for 5 days
- Model: claude-sonnet-4-20250514 → claude-sonnet-4-6
- Impact: win rate dropped 82% → 55% while offline

### Fix 24: AIReviewerBadge Dashboard Component
- File: dashboard/frontend/src/components/AIReviewerBadge.jsx
- Green pulsing dot when active, red when credits exhausted
- Direct link to console.anthropic.com/billing

### Fix 25: AIReviewer Status Tracking
- Tracks: status, calls_succeeded, calls_failed, last_error
- Detects credit exhaustion specifically

### Fix 26: AIReviewer Momentum Prompt Fix
- Was vetoing RSI > 70 — blocking good momentum trades
- Updated: high RSI acceptable for momentum strategy

### Fix 27: Trail Activation (FLAG-5)
- Stop doesn't trail until +0.5% gain from entry
- Eliminates same-minute stop-outs from noise

### Fix 28: Max Positions 10 → 6
- Quality over quantity

### Fix 29: AI Confidence-Based Position Sizing
- ≥85% → 100% Kelly, 75-84% → 75%, 65-74% → 50%, 60-64% → 35%

### Fix 30: Self-Healing historical_pnl_offset
- On every restart: pulls Alpaca equity, recalculates offset if gap > $50

### Fix 31: Scan Interval Sync Fix
- scan_frequency_minutes now also sets intraday_interval_min + intraday_mode=True

### Fix 32: Session Ban 3 → 2 Losses
- Symbol banned for rest of session after 2 losses (was 3)

### Fix 33-35: Chart + Display Fixes
- Equity chart line always green
- 1D labels show date + time
- Trade dot filter uses 24h buffer
- toLocaleString("en-US") globally

### Fix 36: Ticker Loss Persistence
- File: decision_engine/discipline.py
- Saves to logs/ticker_cd.json on every loss/win
- Loads on startup — session ban survives restarts

### Fix 37: Alpaca Startup Sync (_sync_today_from_alpaca)
- File: decision_engine/trading_agent.py
- Called on every startup after executor connects
- Injects missing trades + rebuilds ticker loss counts
- Fixes: calendar-based day P&L, session ban after restart

### Fix 38: Dashboard "Trades" Label + Date Visibility
- "Today's trades" → "Trades"
- Date fontSize 8 → 11, fontWeight 500

### V2 Experiment Setup (May 15)
- Wiped old V2 (Micro Momentum with phantom losses)
- Copied V1 entirely into trading_agent_v2/
- Enhanced candle strategies in V2 only

---

## V2 CANDLE STRATEGY ENHANCEMENTS

### New patterns in V2 (not in V1)
| Pattern | Win Rate | Detection |
|---|---|---|
| Pin Bar Bullish/Bearish | 68% | Wick ≥ 2x body |
| Harami | 65% | 2nd candle inside 1st |
| Harami Cross | 72.85% | Harami + doji 2nd |
| Gravestone Doji | 57% | Long upper wick |
| Dragonfly Doji | 55% | Long lower wick |
| Inverted Hammer | 60% | Entry signal (was exit-only) |

### Files modified in V2 only
- `trading_agent_v2/indicators/candlestick.py` — 13 patterns (V1 has 8)
- `trading_agent_v2/strategies/candle_reversal.py` — all 13 patterns

### Experiment hypothesis
V2 win rate > V1 win rate after 2 weeks → promote candle strategies to V1

---

## OPEN TASKS (priority order)

### IMMEDIATE
1. Start V2 and verify it connects to correct Alpaca account
2. Run V1 and V2 side by side for 2 weeks
3. Compare win rates

### SHORT TERM
4. EOD auto-recovery scan — auto-inject Alpaca EOD batch closes
5. force_scan() EOD scan type bug — pass "INTRADAY" explicitly
6. PDT cleanup — FINRA abolished PDT June 4, 2026

### FUTURE
7. More V2 candle patterns: Three Outside Up/Down, Marubozu, Tweezer
8. Strategy backtester — 3-5 years historical data
9. IBKR live integration
10. Binance crypto integration
11. ML strategy weight optimizer
12. iOS App Store submission

---

## KNOWN ISSUES

| Issue | Status |
|---|---|
| EOD batch closes not auto-recorded | Workaround: self-healing offset corrects P&L |
| force_scan triggers EOD type | Open — cosmetic |
| Cloudflare tunnel URL changes on restart | Update AppContext.js apiBase |
| Position display 0 for ~3 cycles after restart | Resolves itself |

---

## KEY DECISIONS (finalized)

1. V1 is STABLE — never experiment on V1 directly
2. V2 is the experiment sandbox — promote to V1 after 2 weeks outperformance
3. Trail activation ON — stop only trails after +0.5% gain
4. Max positions 6 — quality over quantity
5. Session ban after 2 losses on same symbol
6. AI confidence scales position size
7. AIReviewer prompt: high RSI OK for momentum strategy
8. Alpaca sync on every startup — rebuilds loss counts + injects missing trades
9. Ticker loss counts persist to logs/ticker_cd.json
10. historical_pnl_offset auto-heals against Alpaca on every restart
11. Mobile app permanent URL deferred until iOS App Store submission

---

## LAUNCH COMMANDS

```bash
# V1 (stable)
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh 2>&1 | tee /tmp/agent_log.txt

# V2 (experiment)
lsof -ti:8001,3001 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent_v2 && bash run_dashboard.sh 2>&1 | tee /tmp/v2_log.txt

# Mobile tunnel
cloudflared tunnel --url http://localhost:8000
# Then update AppContext.js apiBase with new URL
cd ~/Desktop/trading_system/trading-agent-mobile && npx expo start --lan

# Emergency close V1
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKUPVN2TBTLKAUHOQLIMWGK4BM' \
  -H 'APCA-API-SECRET-KEY: 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'

# Emergency close V2
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKP3WTGVDUYTDCYW5VDW3Z3CMZ' \
  -H 'APCA-API-SECRET-KEY: HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'

# Backup
~/Desktop/trading_system/backup.sh
```

---

## HEALTH CHECK

```bash
# Both agents
for port in 8000 8001; do
  name="V1" && [ $port -eq 8001 ] && name="V2"
  curl -s http://localhost:$port/api/state | python3 -c "
import sys,json
d=json.load(sys.stdin)
perf=d.get('performance',{})
rep=d.get('reporting',{})
print(f'$name: {d.get(\"agent_status\")} | equity=\${d.get(\"account\",{}).get(\"portfolio_value\",0):,.0f} | pnl=\${perf.get(\"total_pnl\",0):+,.0f} | wr={perf.get(\"win_rate\",0)*100:.0f}% | day=\${rep.get(\"day_pnl\",0):+,.0f}')
" 2>/dev/null || echo "$name: DOWN"
done

# Alpaca ground truth
python3 -c "
import urllib.request,json
for name,k,s in [
    ('V1','PKUPVN2TBTLKAUHOQLIMWGK4BM','3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'),
    ('V2','PKP3WTGVDUYTDCYW5VDW3Z3CMZ','HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'),
]:
    req=urllib.request.Request('https://paper-api.alpaca.markets/v2/account',
        headers={'APCA-API-KEY-ID':k,'APCA-API-SECRET-KEY':s})
    a=json.loads(urllib.request.urlopen(req,timeout=8).read())
    print(f'{name}: \${float(a[\"equity\"]):,.2f} (P&L: \${float(a[\"equity\"])-1000000:+,.2f})')
"
```

---

## PERFORMANCE HISTORY

| Date | Day P&L | Win Rate | Notes | Equity |
|---|---|---|---|---|
| Apr 28 | +$739 | 100% | 3 trades | $1,001,010 |
| May 1 | +$237 | 100% | PDT flagged | $1,005,617 |
| May 4 | +$13,026 | 82% | Peak day | $1,020,217 |
| May 5 | +$355 | 82% | 23 trades | $1,005,053 |
| May 6 | +$4,785 | 75% | Cooldown bug | $1,030,632 |
| May 7 | $0 | — | is_stopped_out bug | $1,031,060 |
| May 12 | +$3,881 | 75% | Dashboard overhaul | $1,030,574 |
| May 13 | -$3,882 | 43% | RKLB/MARA losses | $1,026,688 |
| May 14 | +$1,314 | 86% | All fixes live | $1,028,000 |
| May 15 | -$844 | 50% | RKLB/MARA/AMD | $1,027,097 |

---

## GIT + BACKUP

- Repo: github.com/venuspatel/trading_system (public)
- Auto-backup: cron at 11 PM via backup.sh
- Manual: ~/Desktop/trading_system/backup.sh
- GitHub token: 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

---

*TradeAgent Project Handoff | May 15, 2026 | Confidential*
