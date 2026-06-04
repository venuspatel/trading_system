# TradeAgent — PROJECT HANDOFF
**Date:** June 4, 2026 | **V1 Equity:** $1,008,419 | **V2 Equity:** $1,013,818

---

## 🎯 PROJECT GOAL
Build two autonomous AI-powered paper trading agents on Alpaca that scan a watchlist every 1-2 minutes, score signals using 13 strategies, and execute buy/sell decisions with full risk management — running 24/7 with a React dashboard.

---

## 🏗️ ARCHITECTURE

```
Alpaca API (paper)
     │
     ├── data_layer/providers/alpaca_provider.py   ← fetches 15-min + 1-min OHLCV bars
     │
     ├── indicators/engine.py                       ← RSI, MACD, MA, ATR, Volume
     │
     ├── strategies/engine.py                       ← 13 strategies → StrategyReport + conviction score
     │   ├── momentum.py, breakout.py, micro_momentum.py ...
     │
     ├── decision_engine/
     │   ├── trading_agent.py                       ← main scan loop, buy/sell execution
     │   ├── engine.py                              ← conviction scoring, MTF, position sizing
     │   ├── agent_config.py                        ← apply_profit_maximizer() / apply_micro_momentum()
     │   ├── market_scheduler.py                    ← startup/intraday/EOD scans, cooldowns
     │   ├── risk_guardian.py                       ← position limits, daily loss limits
     │   └── position_sizer.py                      ← Kelly criterion sizing
     │
     ├── execution/
     │   ├── alpaca_executor.py                     ← place orders, sync positions, duplicate guard
     │   └── portfolio_tracker.py                   ← ClosedTrade objects, P&L stats
     │
     └── dashboard/
         ├── backend/api.py                         ← FastAPI: /api/state /api/trades /api/configure
         └── frontend/src/App.jsx                   ← React dashboard
```

**Two independent agents:**
- `trading_agent/` → V1 Profit Maximizer, ports 8000/3000
- `trading_agent_v2/` → V2 Micro Momentum, ports 8001/3001

---

## 📊 CURRENT STATE (June 4, 2026)

### V1 — Profit Maximizer ✅ RUNNING
| Field | Value |
|---|---|
| Equity | $1,008,419 (+$8,419 from $1M) |
| Keys | PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q |
| Stop / TP | 1.0% / 3.0% (trailing) |
| Min conviction | 2.0 (adaptive) |
| Scan interval | 2 min |
| Max positions | 6 |
| Win rate | 52% (100 reconstructed trades from Alpaca — real history lost Jun 4) |
| Grade | C |
| Status | Running, sync fixes deployed, portfolio rebuilt from Alpaca |

### V2 — Micro Momentum ✅ RUNNING
| Field | Value |
|---|---|
| Equity | $1,013,818 (+$13,818 from $1M) |
| Keys | PKP3WTGVDUYTDCYW5VDW3Z3CMZ / HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm |
| Stop / TP | 0.25% / 0.50% |
| Min conviction | 1.5 |
| Scan interval | 1 min |
| Max positions | 8 |
| Win rate | 35% (34 reconstructed trades — real history lost Jun 4) |
| Status | Running, sync fixes deployed, portfolio rebuilt from Alpaca |

---

## 📈 PERFORMANCE HISTORY

| Date | Agent | Day P&L (Alpaca) | Notes | Equity |
|---|---|---|---|---|
| Apr 28 | V1 | +$739 | 3 trades, 100% win | $1,001,010 |
| May 1 | V1 | +$237 | Duplicate buy bug, PDT flagged | $1,005,617 |
| May 4 | V1 | +$13,026 | 82% win rate 🔥 | $1,020,217 |
| May 5 | V1 | +$355 | 23 trades, 82% win, B+ | $1,005,053 |
| May 6 | V1 | +$4,785 | Cooldown bug blocked AM | $1,030,632 |
| May 7 | V1 | $0 | `is_stopped_out` wrong name — 0 trades | $1,031,060 |
| May 8–28 | V1 | various | Multiple debug sessions | ~$1,022,000 |
| May 29 | V2 | +$5,013 | First clean day after P&L fixes | ~$1,014,000 |
| Jun 1 | V1 | +$1,858 | Circuit breaker fired (phantom losses) | $1,022,745 |
| Jun 1 | V2 | +$14,444 | Clean day, accurate P&L | $1,014,444 |
| Jun 2 | V1 | +$1,858 | Stopped at 8:53 AM (weekly circuit) | $1,024,775 |
| Jun 2 | V2 | ~+$350 | 12 trades, mixed | $1,010,348 |
| Jun 4 | V1 | -$6,371 | Bad day — MU/QCOM losses. Sync bugs fixed | $1,008,419 |
| Jun 4 | V2 | +$1,796 | Sync bugs fixed, portfolio rebuilt | $1,013,818 |

**Combined P&L from $1M start: +$22,237**

---

## ✅ THE THREE-SYNC BUG (Fixed June 4, 2026 — commit 42370b2)

### Root Cause
Three competing sync functions all ran on every startup and fought each other:

| | Sync 1 (Block 1 in `_connect`) | Sync 2 (`_sync_today_from_alpaca`) | Sync 3 (`sync_eod_from_alpaca` in portfolio_tracker) |
|---|---|---|---|
| Status | **DISABLED** | **KEPT + FIXED** | **DISABLED** |
| Problem | Per-order injection, no ET filter | Symbol-only dedup, no `after=` filter | One trade per symbol per day — wrong for multi-trade symbols |

Additionally `clean_bad_trades(max_single_pnl=500.0)` was deleting all trades with P&L > $500 on every startup, wiping legitimate large trades.

### Fix Applied (both V1 and V2)
1. **Disabled Sync 1** — `raise Exception("Sync1Disabled")` in Block 1
2. **Disabled Sync 3** — `pass` replacing `sync_eod_from_alpaca()` call
3. **Fixed Sync 2** — added ET midnight `after=` filter + `(symbol, exit_time[:16])` dedup
4. **Raised `clean_bad_trades`** threshold from `$500` to `$50,000`
5. **Added `portfolio_value`** to `/api/state` response (was showing $0.00)

### The One Sync to Rule Them All: Sync 2 (`_sync_today_from_alpaca`)
- Fetches only TODAY's orders using `after=` ET midnight UTC filter
- Aggregates multi-trade symbols correctly (weighted avg buy/sell)
- Deduplicates on `(symbol, exit_time[:16])` — not symbol-only
- Rebuilds ticker cooldown counts so session bans survive restarts
- V2 also has sentinel file check (EOD reset → skip sync same day)

---

## ✅ ALL FIXES DEPLOYED (both V1 and V2)

### Fix A: Three-Sync Bug (June 4)
See above — commit 42370b2.

### Fix B: portfolio_value in API state (June 4)
**File:** `dashboard/backend/api.py`
```python
"portfolio_value": round(
    float(account.get("equity", 0))
    or float(account.get("portfolio_value", 0))
    or float(getattr(_agent, "_portfolio_value", 0))
    or float((live_portfolio._starting_value or 0) + (live_portfolio._historical_pnl_offset or 0)),
    2),
```
Previously showed $0.00 until executor connected. Now falls back through chain.

### Fix C: V2 EOD Force-Close + Sentinel (pre-June 4)
**File:** `trading_agent_v2/decision_engine/trading_agent.py`
- At 3:30 PM ET: closes ALL V2 positions, resets P&L counters, preserves trade history
- Writes `logs/eod_reset_done.flag` — Sync 2 skips on same-day restart
- Next morning: flag cleared, Sync 2 runs normally

### Fix D: V2 Exit P&L Drift Guard (pre-June 4)
**File:** `trading_agent_v2/decision_engine/trading_agent.py`
- Discards stale fill prices drifting >5% from exit trigger price
- Prevents phantom -$163k losses from stale Alpaca avg_entry_price

### Fix E: clean_bad_trades Threshold (June 4)
**Both agents** — raised from $500 to $50,000.

---

## ⚠️ KNOWN ISSUES / OPEN TASKS

### HIGH PRIORITY — Next Session
1. **Win rate/grade inaccurate** — portfolio history was lost on June 4 when portfolio.json
   was rebuilt from Alpaca (Alpaca only keeps 500 orders, covering ~May 1–19 for V1).
   Win rates will recover as agents trade going forward. No action needed.

2. **Equity curve flat on 1D/1M views** — snapshots wiped when portfolio.json rebuilt.
   Will self-heal as scan cycles record new snapshots. No action needed.

3. **Weekly circuit breaker uses accumulated trade P&L, not Alpaca equity** — can fire
   falsely if trades are missed. Fix: recalculate `pnl_week_pct` from Alpaca account
   `equity - last_equity` at start of each week.

4. **V1 EOD reset + sentinel** — V2 has it, V1 doesn't. V1 positions CAN hold overnight
   (Profit Maximizer strategy) but the portfolio.json reset + sentinel prevents sync
   contamination. Should be applied to V1 as well.

5. **AIReviewer model string** — currently `claude-sonnet-4-20250514`, should be
   `claude-sonnet-4-6`. Shows "Reviewer error" badge. Trades still execute (approves
   by default on error).

### LOW PRIORITY / FUTURE
6. V2 learns from V1 trades (StrategyRanker cross-feed)
7. PDT rule cleanup (abolished June 4, 2026 — remove `pattern_day_trader` references)
8. Strategy backtester (3–5 years historical data)
9. IBKR live integration
10. Binance crypto integration
11. ML-based strategy weight optimizer
12. News & sentiment analysis layer
13. Options strategies

---

## 🔑 KEY DECISIONS (finalized)

1. **Sync 2 is the single source of truth** — Sync 1 and Sync 3 are disabled
2. **Dedup key is `(symbol, exit_time[:16])`** — never symbol-only (blocks multi-trade symbols)
3. **after= filter uses ET midnight** — not UTC midnight (different by 4-5 hours)
4. **clean_bad_trades threshold = $50,000** — $500 was deleting legitimate trades
5. **portfolio_value falls back through 4-level chain** — never shows $0
6. **Alpaca is ground truth** — always verify P&L from Alpaca API, not dashboard
7. **Never blindly copy between agents** — V1 and V2 have diverged
8. **ast.parse() every file before deploying** — syntax errors killed trading days
9. **portfolio.json is NOT in git** — must rebuild from Alpaca if lost
10. **Alpaca only keeps ~500 orders** — covers ~3 weeks of history for V1

---

## 🚀 LAUNCH COMMANDS

```bash
# V1
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh

# V2
lsof -ti:8001,3001 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent_v2 && bash run_dashboard.sh

# Both
lsof -ti:8000,3000,8001,3001 | xargs kill -9 2>/dev/null
sleep 2
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh > /tmp/v1.log 2>&1 &
sleep 6
cd ~/Desktop/trading_system/trading_agent_v2 && bash run_dashboard.sh > /tmp/v2.log 2>&1 &

# Emergency close all V1 positions
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKUPVN2TBTLKAUHOQLIMWGK4BM' \
  -H 'APCA-API-SECRET-KEY: 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'

# Emergency close all V2 positions
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKP3WTGVDUYTDCYW5VDW3Z3CMZ' \
  -H 'APCA-API-SECRET-KEY: HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'
```

---

## 🩺 HEALTH CHECK COMMANDS

```bash
# Quick status both agents
python3 - << 'EOF'
import urllib.request, json
from datetime import datetime; import zoneinfo
PST = zoneinfo.ZoneInfo('America/Los_Angeles')
print(datetime.now(PST).strftime('%I:%M:%S %p PST'))
for name, port in [('V1',8000),('V2',8001)]:
    try:
        with urllib.request.urlopen(f'http://localhost:{port}/api/state', timeout=5) as r:
            d = json.loads(r.read())
        rep = d.get('reporting',{}); perf = d.get('performance',{})
        print(f"{name}: {d.get('agent_status')} cycle={d.get('cycle_count')} "
              f"equity=${d.get('portfolio_value',0):,.2f} "
              f"day_pnl=${rep.get('day_pnl',0):+,.2f} "
              f"total_pnl=${perf.get('total_pnl',0):+,.2f}")
    except Exception as e:
        print(f"{name}: DOWN — {e}")
EOF

# Ground truth from Alpaca
python3 - << 'EOF'
import urllib.request, json
V1_KEY='PKUPVN2TBTLKAUHOQLIMWGK4BM'; V1_SEC='3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'
V2_KEY='PKP3WTGVDUYTDCYW5VDW3Z3CMZ'; V2_SEC='HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'
for name,k,s in [('V1',V1_KEY,V1_SEC),('V2',V2_KEY,V2_SEC)]:
    req=urllib.request.Request('https://paper-api.alpaca.markets/v2/account',
        headers={'APCA-API-KEY-ID':k,'APCA-API-SECRET-KEY':s})
    acct=json.loads(urllib.request.urlopen(req,timeout=8).read())
    day_pnl = float(acct['equity']) - float(acct.get('last_equity',0))
    print(f"{name}: equity=${float(acct['equity']):,.2f} "
          f"total_pnl=${float(acct['equity'])-1000000:+,.2f} "
          f"day_pnl=${day_pnl:+,.2f}")
EOF

# Rebuild portfolio from Alpaca (use if portfolio.json corrupted)
# python3 /tmp/reconstruct_history_v2.py  ← V1
# python3 /tmp/rebuild_v2.py              ← V2
```

---

## 🔧 TECHNICAL CONSTRAINTS

- **Python 3.11** on macOS (venuspatel's MacBook)
- **Alpaca Paper Trading** — base URL `https://paper-api.alpaca.markets/v2`
- **Alpaca SDK** — `alpaca-trade-api` + `alpaca-py`. BarSet uses `[]` not `.get()`
- **FastAPI** with `uvicorn --reload` (hot-reloads on file save — can cause double-sync)
- **React** frontend on npm
- **No margin** — Kelly sizer uses `cash` only, `max_position_pct=10%`
- **PDT rule abolished June 4, 2026** — clean up references after that date
- **Market hours** — 6:30 AM – 1:00 PM PST (PST timezone, NOT ET)
- **ast.parse() every file** before deploying — syntax errors killed multiple trading days
- **Targeted patches** — never blindly copy V1 files to V2 or vice versa, agents have diverged
- **GitHub repo** — venuspatel/trading_system, branch: master
- **portfolio.json NOT in git** — if lost, rebuild using Alpaca order history script
- **Alpaca order history limit** — ~500 orders, covers ~3 weeks. Older history is gone.

---

## 📁 FILE STRUCTURE

```
~/Desktop/trading_system/
├── trading_agent/              ← V1 (ports 3000/8000)
│   ├── run_dashboard.sh
│   ├── saved_config.json       ← Profit Maximizer config
│   ├── logs/
│   │   ├── portfolio.json      ← 100 reconstructed trades (May 1–19 + Jun 4)
│   │   └── ticker_cd.json      ← ticker cooldown state
│   ├── decision_engine/
│   │   ├── trading_agent.py    ← Sync 1+3 disabled, Sync 2 fixed
│   │   ├── engine.py
│   │   ├── agent_config.py
│   │   ├── market_scheduler.py
│   │   ├── risk_guardian.py
│   │   ├── discipline.py       ← weekly circuit breaker
│   │   └── position_sizer.py
│   ├── execution/
│   │   ├── alpaca_executor.py
│   │   └── portfolio_tracker.py ← clean_bad_trades = $50k
│   └── dashboard/backend/api.py ← portfolio_value fix deployed
│
└── trading_agent_v2/           ← V2 (ports 3001/8001)
    ├── run_dashboard.sh
    ├── saved_config.json       ← Micro Momentum config
    ├── logs/
    │   ├── portfolio.json      ← 34 reconstructed trades
    │   ├── ticker_cd.json
    │   └── eod_reset_done.flag ← sentinel (V2 only)
    ├── decision_engine/
    │   └── trading_agent.py    ← Sync 1+3 disabled, Sync 2 fixed, EOD close + sentinel
    ├── execution/
    │   └── portfolio_tracker.py ← clean_bad_trades = $50k
    └── dashboard/backend/api.py ← portfolio_value fix deployed
```

---

## 💡 LESSONS LEARNED

- **Three syncs = chaos** — having Block 1, `_sync_today_from_alpaca`, and `sync_eod_from_alpaca` all run on startup creates duplicate injection. Keep only one.
- **Dedup must use (symbol, exit_time[:16])** — symbol-only blocks second trade for same symbol same day (V2 scalps same symbol multiple times)
- **after= filter must use ET midnight, not UTC midnight** — UTC midnight at 6PM PST = yesterday 5PM PST, pulls previous session
- **clean_bad_trades(500)** deletes legitimate large trades — use $50k threshold
- **portfolio.json is not in git** — add it or accept losing history on corruption
- **Alpaca only keeps ~500 orders** — ~3 weeks of V1 history maximum
- **uvicorn --reload re-runs __init__** — syncs run twice on hot-reload if no sentinel
- **Alpaca is ground truth** — always verify from Alpaca API, never trust dashboard alone
- **ast.parse() before every deploy** — syntax errors killed multiple trading days
- **Never copy between agents** — V1 and V2 have diverged significantly

---

## 🗓️ NEXT SESSION CHECKLIST

When starting next session, first run health check to verify:
1. Both agents still running after overnight
2. Morning sync injected correct trades (not phantoms)
3. Day P&L matches Alpaca ground truth
4. No stale "Alpaca EOD close (recovered)" phantom trades

Then address:
- Weekly circuit breaker Alpaca ground truth fix
- V1 EOD sentinel (same as V2)
- AIReviewer model string fix (`claude-sonnet-4-6`)

---

*TradeAgent Project Handoff | June 4, 2026 | Confidential | Commit: 42370b2*
