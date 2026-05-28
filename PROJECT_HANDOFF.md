# TradeAgent — PROJECT HANDOFF
**Date:** May 26, 2026 | **V1 Equity:** $1,023,323 | **V2 Equity:** $991,694

---

## 🎯 PROJECT GOAL
Build two autonomous AI-powered paper trading agents on Alpaca that scan a watchlist every 1-2 minutes, score signals using 15 strategies, and execute buy/sell decisions with full risk management — running 24/7 with a React dashboard.

---

## 🏗️ ARCHITECTURE

```
Alpaca API (paper)
     │
     ├── data_layer/providers/alpaca_provider.py   ← fetches 15-min + 1-min OHLCV bars
     │
     ├── indicators/engine.py                       ← RSI, MACD, MA, ATR, Volume
     │
     ├── strategies/engine.py                       ← 15 strategies → StrategyReport + conviction score
     │   ├── momentum.py, breakout.py, micro_momentum.py ...
     │   └── bounce_detector.py                     ← exhaustion bounce signal
     │
     ├── decision_engine/
     │   ├── trading_agent.py                       ← main scan loop, buy/sell execution
     │   │                                             D1+Adaptive bounce state machine
     │   │                                             continuous session-dip pre-activation
     │   ├── engine.py                              ← conviction scoring, MTF, bounce routing
     │   ├── adaptive_thresholds.py                 ← conviction floor (capped 2.5 max)
     │   ├── ai_reviewer.py                         ← Claude reviews BUY decisions
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

## 📊 CURRENT STATE (May 26, 2026)

### V1 — Profit Maximizer ✅ RUNNING
| Field | Value |
|---|---|
| Equity | $1,023,323 |
| Keys | PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q |
| Stop / TP | 1.0% / 3.0% |
| Min conviction | 2.0 (adaptive, capped 2.5 max) |
| Scan interval | 2 min |
| Max positions | 6 |
| Win rate | 60% over 123 trades |
| Strategies | 15 (including BounceDetector) |
| Bounce mode | Live — continuous session-dip pre-activation |
| Status | Running, all fixes deployed |

### V2 — Micro Momentum ✅ RUNNING (first profitable day)
| Field | Value |
|---|---|
| Equity | $991,694 (+$4,455 today) |
| Keys | PKP3WTGVDUYTDCYW5VDW3Z3CMZ / HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm |
| Stop / TP | 0.25% / 0.50% |
| Min conviction | 1.5 |
| Scan interval | 1 min |
| Max positions | 8 |
| Status | Running clean — fresh config, BarSet fix deployed |

---

## ✅ ALL DEPLOYED FIXES (cumulative — May 26 additions)

### Fix 20: bounce_entry flag on TradeDecision (May 26)
**File:** `decision_engine/engine.py`
```python
# Added to TradeDecision dataclass:
bounce_entry: bool = False   # True when decision came from _evaluate_bounce

# In _evaluate_bounce():
_bounce_decision = self._make_decision(...)
_bounce_decision.bounce_entry = True
return _bounce_decision
```
**Impact:** Bounce buy gate `getattr(d, 'bounce_entry', False)` now actually returns True. Without this, bounce buys were blocked at the gate forever.

### Fix 21: _record_bounce_exit wired into SELL block (May 26)
**File:** `decision_engine/trading_agent.py`
```python
# In SELL exit block, after pnl calculated:
if getattr(sig, 'bounce_entry', False):
    self._record_bounce_exit(symbol, pnl)
```
**Impact:** Adaptive stop tightening now actually fires. Previously the method existed but was never called — consec_losses always stayed 0.

### Fix 22: Bounce activates on trailing manager stop-outs (May 26)
**File:** `decision_engine/trading_agent.py`
```python
# In trailing manager exit path, after stop recorded:
if "stop" in (sig.reason or "").lower():
    self._scheduler.mark_stopped_out(sig.symbol, cooldown_minutes=120)
    self._activate_bounce_mode(sig.symbol, reason="PM_LOSS")  # ← NEW
```
**Impact:** All stop-outs now activate bounce mode. Previously only stops in the main SELL block triggered bounce — trailing manager stops (90%+ of all stops) were missed entirely.

### Fix 23: bounce_tickers exposed in /api/state (May 26)
**File:** `dashboard/backend/api.py`
```python
"bounce_tickers": {
    sym: {"active": bt.get("active"), "consec_losses": bt.get("consec_losses"),
          "next_sl_pct": round(bt.get("next_sl", 0.003)*100, 3)}
    for sym, bt in (getattr(_agent, "_bounce_tickers", {}) or {}).items()
} if _agent else {},
```

### Fix 24: Continuous session-dip bounce pre-activation (May 26)
**File:** `decision_engine/trading_agent.py`
```python
# Runs EVERY scan cycle (was STARTUP only, cycle <= 2)
# Trigger: ticker dropped >=1% from session high AND RSI < 45
# Cap: max 4 tickers pre-activated at once
# Skips: tickers already in open positions or bounce mode
# Reason tag: "session_dip" (preserved across new-day reset)

if _drop >= 0.010 and _rsi < 45:
    self._bounce_tickers[_sym] = {
        "active": True, "consec_losses": 0,
        "next_sl": 0.003, "reason": "session_dip"
    }
```
**Impact:** Catches mid-session weakness at any time, not just at open. On May 26 today: QCOM dropped 3.9% from session high at 6:44 AM — would have pre-activated at first scan instead of taking PM stop-out.

### Fix 25: New-day reset preserves pre-activated tickers (May 26)
**File:** `decision_engine/trading_agent.py`
```python
# Preserves both bar2_preactivate AND session_dip entries
keep = {sym: bt for sym, bt in self._bounce_tickers.items()
        if bt.get("reason") in ("bar2_preactivate", "session_dip")}
```
**Impact:** Bounce tickers set during STARTUP cycle are no longer immediately cleared by the new-day reset that fires at end of cycle 1.

### Fix 26: AIReviewer gets MTF-boosted conviction (May 26)
**File:** `decision_engine/engine.py`
```python
# BEFORE (wrong — raw strategy score):
conviction_score = report.conviction_score  # e.g. +1.09 for AMAT

# AFTER (correct — final boosted score):
conviction_score = _enhanced_score  # e.g. +3.12 for AMAT after MTF boost
```
**Impact:** AIReviewer was vetoing AVGO (+2.96 final), AMAT (+3.12 final), AMD (+3.58 final) because it saw raw strategy scores (+1.30, +1.09, +1.70). After fix all three approved.

### Fix 27: Adaptive threshold floor capped at 2.5 (May 26)
**File:** `decision_engine/adaptive_thresholds.py`
```python
# BEFORE: 50-60% win rate → floor 3.0 (blocked nearly all trades)
# AFTER:  floor never exceeds 2.5 regardless of win rate
if win_rate >= 0.55:    rec.conviction_floor = 2.0
elif win_rate >= 0.45:  rec.conviction_floor = 2.5
else:                   rec.conviction_floor = 2.5  # cap at 2.5 even when losing
```

### Fix 28: V2 BarSet KeyError fix (May 26)
**File:** `trading_agent_v2/data_layer/providers/alpaca_provider.py`
```python
try:
    raw = data[symbol]
except (KeyError, TypeError):
    raw = []
bars = [self._alpaca_bar_to_bar(symbol, b) for b in (raw or [])]
```
**Impact:** `get_bars` errors on all 15 symbols eliminated. V2 was running blind on 1-min bars.

### Fix 29: V2 startup close guard (May 26)
**File:** `trading_agent_v2/decision_engine/trading_agent.py`
```python
# On startup, if stale Alpaca positions exist → close all before first buy
if self._open_positions:
    # DELETE https://paper-api.alpaca.markets/v2/positions
    self._open_positions = {}
```
**Impact:** Prevents duplicate buys when V2 restarts with stale positions from previous sessions. Fixed the AAPL/PLTR/AMZN doubling issue.

### Fix 30: V2 AIConfigurator reset (May 26)
- Cleared `logs/ai_config_log.jsonl` — Claude was defending based on 0% win rate from broken agent history
- Reset `saved_config.json` to proper Micro Momentum values
- Removed `config/agent_config.json` — regenerated fresh on restart
- V2's first profitable day: +$4,455

---

## 🚨 OPEN TASKS (priority order)

### IMMEDIATE (before Monday open)
- None — both agents running, all fixes live

### SHORT TERM
1. **PDT cleanup** — FINRA abolished PDT June 4, 2026 (9 days away)
   - Remove `pattern_day_trader`, `daytrade_count`, `daytrading_buying_power` references
   - Replace with plain `buying_power` check

2. **Daily bar fetch for trend classifier** — 15-min MA20 misclassifies stocks. Add 1Day bars for proper trend direction. QCOM was called DOWNTREND despite +60% monthly.

3. **V2 learns from V1 trades** — feed V1 portfolio.json into V2's StrategyRanker

4. **Performance tab accuracy** — portfolio.json trade sync for missed stop/TP exits

### FUTURE
5. ML-based strategy weight optimizer
6. News & sentiment analysis layer
7. IBKR live integration
8. Options strategies

---

## ⚠️ KNOWN ISSUES

| Issue | Cause | Status |
|---|---|---|
| V1 AIReviewer 400 errors | None — working now with correct Anthropic API key | ✅ Fixed |
| V2 phantom -$1.4M P&L | INTC duplicate bug — old history | ✅ Cleared |
| get_bars errors after hours | Alpaca returns empty BarSet after 4PM ET | Expected |
| AMD entry price wrong in V2 | Old Alpaca lifetime basis averaging | Monitor — EOD close clears it |

---

## 🔑 KEY DECISIONS (finalized — don't revisit)

1. **Continuous session-dip bounce** beats startup-only bar-2 check — catches weakness at any point in session
2. **Loss-triggered > cooldown** — active bounce mode turns losses into recovery trades
3. **Adaptive threshold capped at 2.5** — never lock out trading entirely even in a losing streak
4. **AIReviewer must receive MTF-boosted score** — raw strategy score causes false vetoes
5. **V2 startup guard** — always close stale Alpaca positions before first buy cycle
6. **V2 AIConfigurator** reads `saved_config.json` on boot — agent_config.json is runtime output, do NOT commit it
7. All previous key decisions from May 8 + May 23 handoffs remain valid

---

## 🚀 LAUNCH COMMANDS

```bash
# V1
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh

# V2
lsof -ti:8001,3001 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent_v2 && bash run_dashboard.sh

# Health check both agents
python3 - << 'EOF'
import urllib.request, json
from datetime import datetime
import zoneinfo
PST = zoneinfo.ZoneInfo('America/Los_Angeles')
print(datetime.now(PST).strftime('%I:%M:%S %p PST'))
for name, port in [('V1',8000),('V2',8001)]:
    try:
        with urllib.request.urlopen(f'http://localhost:{port}/api/state', timeout=5) as r:
            d = json.loads(r.read())
        rep = d.get('reporting',{}); cfg = d.get('config',{})
        bt  = d.get('bounce_tickers',{})
        print(f"{name}: {d.get('agent_status')} cycle={d.get('cycle_count')} "
              f"pnl=${rep.get('day_pnl',0):+.2f} approach={cfg.get('approach')} "
              f"bounce={list(bt.keys()) or 'none'}")
    except Exception as e:
        print(f"{name}: DOWN — {e}")
EOF

# Ground truth from Alpaca
python3 - << 'EOF'
import urllib.request, json
for name, k, s in [
    ('V1','PKUPVN2TBTLKAUHOQLIMWGK4BM','3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'),
    ('V2','PKP3WTGVDUYTDCYW5VDW3Z3CMZ','HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'),
]:
    hdrs={'APCA-API-KEY-ID':k,'APCA-API-SECRET-KEY':s}
    acct=json.loads(urllib.request.urlopen(urllib.request.Request(
        'https://paper-api.alpaca.markets/v2/account',headers=hdrs),timeout=8).read())
    pos=json.loads(urllib.request.urlopen(urllib.request.Request(
        'https://paper-api.alpaca.markets/v2/positions',headers=hdrs),timeout=8).read())
    print(f"{name}: equity=${float(acct['equity']):,.2f} cash=${float(acct['cash']):,.2f} "
          f"positions={[p['symbol'] for p in pos]}")
EOF

# Check bounce state
curl -s http://localhost:8000/api/state | python3 -c "
import sys,json
d=json.load(sys.stdin)
bt=d.get('bounce_tickers',{})
print('bounce_tickers:', bt if bt else 'none')
"

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

## 📈 PERFORMANCE HISTORY

| Date | Agent | Day P&L | Notes | Equity |
|---|---|---|---|---|
| Apr 28 | V1 | +$739 | 3 trades, 100% win | $1,001,010 |
| May 1 | V1 | +$237 | Duplicate buy bug, PDT flagged | $1,005,617 |
| May 4 | V1 | +$13,026 | 82% win rate 🔥 | $1,020,217 |
| May 5 | V1 | +$355 | 23 trades, 82% win, B+ | $1,005,053 |
| May 6 | V1 | +$4,785 | Cooldown bug blocked AM | $1,030,632 |
| May 7 | V1 | $0 | is_stopped_out wrong name | $1,031,060 |
| May 8-21 | V1 | -$6,049 | Various losses, 60% WR | $1,025,010 |
| May 22 | V1 | -$544 | 50% win, 6 trades | $1,025,010 |
| May 26 | V1 | -$1,686 | Morning stop-outs before fixes, 48%→75% after | $1,023,323 |
| May 26 | V2 | +$4,455 | First profitable session 🔥 AMD+3963 META+350 | $991,694 |

---

## 🩺 WHAT TO WATCH ON MONDAY MORNING

```
# Bounce session-dip firing correctly (6:30-7:00 AM):
[BounceMode] QCOM PRE-ACTIVATED (session dip) drop=2.1% RSI=38.5 high=$248 now=$242 — PM blocked, bounce enabled
[BounceMode] Session-dip pre-activation: 2 tickers (total: 2/4)

# PM trading blocked for pre-activated tickers:
[Decision] - QCOM HOLD | conviction=+3.03 | bounce_mode=active

# Bounce entry firing:
[Agent] ACTION: [BUY] QCOM | bounce entry @ $242 stop=0.30% tp=0.60%

# Adaptive stop tightening after loss:
[BounceMode] QCOM loss #1 — stop → 0.20%

# Clean day (no dips):
# No [BounceMode] lines at all — pure PM trading
```

---

## 🔧 TECHNICAL CONSTRAINTS

- **Python 3.11** on macOS (venuspatel's MacBook)
- **Alpaca Paper Trading** — base URL `https://paper-api.alpaca.markets/v2`
- **15 strategies** active in V1 Profit Maximizer
- **PDT rule abolished June 4, 2026** — clean up references after that date
- **Market hours** — 6:30 AM – 1:00 PM PST
- **ast.parse() every file** before deploying — syntax errors killed multiple trading days
- **Targeted patches for V2** — never blindly copy V1 files, agents have diverged
- **V2 agent_config.json is runtime** — never commit it, gitignored
- **Bounce tickers persist across new-day reset** if reason is session_dip or bar2_preactivate

---

## 📁 FILE STRUCTURE

```
~/Desktop/trading_system/
├── trading_agent/              ← V1 (ports 3000/8000)
│   ├── run_dashboard.sh
│   ├── saved_config.json
│   ├── logs/portfolio.json
│   ├── decision_engine/
│   │   ├── trading_agent.py         ← 1988 lines — bounce state machine + session-dip
│   │   ├── engine.py                ← MTF conviction, bounce routing, _enhanced_score to AI
│   │   ├── adaptive_thresholds.py   ← conviction floor capped 2.5
│   │   ├── ai_reviewer.py           ← Claude vets BUY decisions
│   │   ├── agent_config.py
│   │   ├── market_scheduler.py
│   │   ├── risk_guardian.py
│   │   └── position_sizer.py
│   ├── execution/
│   │   ├── alpaca_executor.py
│   │   └── portfolio_tracker.py
│   ├── strategies/
│   │   ├── bounce_detector.py       ← 15th strategy
│   │   ├── engine.py                ← MODE_ROLES with BOUNCE
│   │   └── [12 other strategies]
│   ├── data_layer/providers/
│   │   └── alpaca_provider.py
│   └── dashboard/backend/
│       └── api.py                   ← bounce_tickers in /api/state
│
└── trading_agent_v2/           ← V2 (ports 3001/8001)
    ├── run_dashboard.sh
    ├── saved_config.json            ← stop 0.25% / TP 0.50% (correct)
    ├── decision_engine/
    │   └── trading_agent.py         ← startup close guard
    ├── data_layer/providers/
    │   └── alpaca_provider.py       ← BarSet KeyError fix
    └── logs/portfolio.json          ← 10 real trades, clean
```

---

*TradeAgent Project Handoff | May 26, 2026 | Confidential*

---

## 🔥 MAY 27-28 SESSION — V2 FILL CACHE BUG (UNSOLVED)

**Date:** May 27-28, 2026 | **V1:** $1,020,737 | **V2:** ~$988,000 (declining from restarts)

### Root Cause (Fully Diagnosed)
V2 positions are imported with wrong entry prices → stops fire immediately → -15% to -54% losses.

**The chain:**
1. Alpaca's `avg_entry_price` is a **lifetime blended cost basis** (e.g. AAPL=$310 from months ago, not today's $213)
2. A `_today_fills` cache was built to use actual fill prices instead
3. The cache uses `after=UTC_midnight` to fetch today's fills — but PST sessions from 6:30 AM-1 PM PST fall **before** UTC midnight of the next day, so yesterday's fills get included
4. Startup guard sets `_today_fills = {}` to force a re-fetch — but `{}` vs `None` sentinel broke: `if self._today_fills is None` is False for `{}`, so the fetch is **skipped**
5. New buys come in, fallback fetch runs — but it finds yesterday's fills because the time window is wrong

### What Was Fixed (Committed to GitHub — commit 35dc49c + subsequent)
All in `trading_agent_v2/`:

| Fix | File | Status |
|---|---|---|
| Startup guard: poll until Alpaca empty | trading_agent.py | ✅ Working |
| TickerCooldown skips Recovered trades | trading_agent.py | ✅ Working |
| Adaptive threshold skips Recovered trades | trading_agent.py | ✅ Working |
| Regime cap for Micro Momentum (2.5→1.8) | engine.py | ✅ Working |
| ADX floor lowered (20→12) | engine.py | ✅ Working |
| NEUTRAL bypass for Micro Momentum | engine.py | ✅ Working |
| Fill poll after buy (1s→2s) | alpaca_executor.py | ✅ Working |
| Fallback fill fetch when cache miss | alpaca_executor.py | ✅ Working |
| Fill cache after buy confirmed | alpaca_executor.py | ✅ Working |

### What Is Still Broken
**`_today_fills` sentinel + time window** — the two-part fix needed:

**Part 1 — `trading_agent.py` L484:**
```python
# WRONG (currently in file):
self._executor._today_fills = {}

# CORRECT (sets to None so fetch re-runs):
self._executor._today_fills = None
```

**Part 2 — `alpaca_executor.py` date cutoff (both in initial fetch L328 and fallback fetch L~400):**
```python
# WRONG (currently): UTC midnight — includes yesterday's PST fills
_utc_midnight = datetime.now(timezone.utc).replace(hour=0, ...).strftime(...)

# CORRECT: PST market open = 6:30 AM PST = 13:30 UTC
import zoneinfo
_pst = zoneinfo.ZoneInfo('America/Los_Angeles')
_now_pst = datetime.now(_pst)
_market_open_pst = _now_pst.replace(hour=6, minute=30, second=0, microsecond=0)
_utc_cutoff = _market_open_pst.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

### Verify Fixes Are In Files
```bash
# Check Part 1 — should show None not {}
grep -n "_today_fills" \
  ~/Desktop/trading_system/trading_agent_v2/decision_engine/trading_agent.py

# Check Part 2 — should show 'PST market open' or 'hour=6'
grep -n "PST market open\|hour=6\|zoneinfo" \
  ~/Desktop/trading_system/trading_agent_v2/execution/alpaca_executor.py
```

### Correct Startup Log (when fixed)
```
[Executor] Today's fill prices loaded: []          ← empty, no stale yesterday fills
[Agent] STARTUP: closing N positions — starting fresh
[Agent] STARTUP: positions confirmed empty after Xs
[Agent] STARTUP: fill cache cleared — fresh prices for new buys
[Executor] Imported AVGO from Alpaca: 300sh @ $280.xx (today fill price)  ← correct price
[TrailingStop] Registered AVGO @ $280.xx | stop=$279.xx                   ← correct stop
```

### V2 Current State
- Equity: ~$988,000 (losses entirely from restart chaos, not bad trades)
- All fixes committed EXCEPT the two-part sentinel+time fix above
- Stop V2, apply both parts, restart clean

### Emergency Commands
```bash
# Stop V2 + close all positions
lsof -ti:8001,3001 | xargs kill -9 2>/dev/null
curl -s -X DELETE "https://paper-api.alpaca.markets/v2/positions" \
  -H 'APCA-API-KEY-ID: PKP3WTGVDUYTDCYW5VDW3Z3CMZ' \
  -H 'APCA-API-SECRET-KEY: HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'

# Reset portfolio
python3 -c "
import json, datetime
path = '/Users/venuspatel/Desktop/trading_system/trading_agent_v2/logs/portfolio.json'
with open(path, 'w') as f:
    json.dump({'starting_value': 988000.0, 'historical_pnl_offset': 0.0,
               'peak_value': 988000.0, 'day_date': datetime.date.today().strftime('%Y-%m-%d'),
               'day_start_pnl': 0.0, 'trades': [], 'snapshots': []}, f, indent=2)
print('Reset done')
"
```

### V1 Status
Running cleanly — $1,020,737 (+$20,737). No changes needed.
