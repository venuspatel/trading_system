# TradeAgent — PROJECT HANDOFF
**Date:** May 22, 2026 | **V1 Equity:** ~$1,024,384 | **V2 Equity:** ~$989,589

---

## 🎯 PROJECT GOAL
Two autonomous AI-powered paper trading agents on Alpaca scanning a watchlist every 1-2 minutes, scoring signals using 13 strategies, executing buy/sell decisions with full risk management, and autonomously reconfiguring themselves via Claude AI — running 24/7 with a React dashboard.

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
     │   ├── position_sizer.py                      ← Kelly criterion sizing
     │   ├── ai_configurator.py                     ← NEW: autonomous AI self-configuration
     │   ├── ticker_universe.py                     ← NEW: 60+ ticker scoring across 6 domains
     │   └── config_log.py                          ← NEW: append-only AI decision audit log
     │
     ├── execution/
     │   ├── alpaca_executor.py                     ← place orders, sync positions, duplicate guard
     │   │                                             + stale position import guard (>5% drift)
     │   └── portfolio_tracker.py                   ← ClosedTrade objects, P&L stats
     │
     └── dashboard/
         ├── backend/api.py                         ← FastAPI + AI config endpoints
         └── frontend/src/App.jsx                   ← React dashboard
```

**Two independent agents:**
- `trading_agent/` → V1 Profit Maximizer, ports 8000/3000
- `trading_agent_v2/` → V2 Micro Momentum, ports 8001/3001

---

## 📊 CURRENT STATE (May 22, 2026)

### V1 — Profit Maximizer ✅ WORKING
| Field | Value |
|---|---|
| Equity | ~$1,024,384 (+$24k from $1M start) |
| Keys | PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q |
| Stop / TP | 1.0% / 3.0% |
| Min conviction | 2.0 (adaptive) |
| Scan interval | 2 min |
| Max positions | 5 |
| Status | Running, stable |

### V2 — Micro Momentum ⚠️ NEEDS FIXES
| Field | Value |
|---|---|
| Equity | ~$989,589 (down ~$10k from $1M) |
| Keys | PKP3WTGVDUYTDCYW5VDW3Z3CMZ / HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm |
| Stop / TP | 0.40% / 0.80% |
| Min conviction | 1.5 (AI keeps raising to 2.5 — needs fix) |
| Scan interval | 1 min |
| Max positions | 8 |
| Max trades/symbol | 3 per day |
| Status | Running but churning — see open bugs below |

---

## ✅ NEW FEATURES BUILT (May 8–22, 2026)

### AI Self-Configuration System (V2 only)
**Files:** `decision_engine/ai_configurator.py`, `decision_engine/config_log.py`

- Claude autonomously decides expand/defend/hold every scan cycle
- Reads: win_rate, day_pnl, regime, SPY RSI, VIX, streak scores
- Changes: stop_loss, take_profit, conviction, max_positions, scan_interval, watchlist
- Hard bounds on all params — Claude cannot exceed them
- 30-min cooldown between reconfigs, emergency override on -2.5% drawdown
- Full audit log at `logs/ai_config_log.jsonl` — every decision with before/after
- Non-blocking API: `/api/ai_config/latest`, `/api/ai_config/history`
- Revert endpoint: `POST /api/ai_config/revert/{entry_id}`

**Key issue:** Claude reads portfolio.json for performance data. When portfolio.json has phantom/corrupted trades, Claude makes wrong decisions (phantom -$2M losses → 14 DEFEND decisions in a row).

### Ticker Universe (V2 only)
**File:** `decision_engine/ticker_universe.py`

- 68 tickers across 6 domains: tech, finance, energy, biotech, macro, leveraged ETFs
- Scores each ticker: momentum (40%) + volume surge (25%) + win streak (20%) + regime alignment (15%)
- Claude reads top 20 by score and picks the active watchlist dynamically
- Refresh endpoint: `POST /api/universe/refresh`
- Watchlist refresh: `POST /api/universe/watchlist_refresh`

**Key issue:** `_data_manager` is None when TickerUniverse is initialized in `__init__()` because DataManager connects in `start()`. Fix deployed (line ~355 in trading_agent.py wires it after connect) but needs verification.

### AIReviewer (V2)
**File:** `decision_engine/ai_reviewer.py`

- Reviews each individual BUY/SELL before execution
- Currently set to pass-through mode (auto-approves) — was fighting AIConfigurator
- Model: `claude-sonnet-4-6` ✅ correct
- TODO: re-enable with session context from AIConfigurator so they coordinate

### Pre-market AI Brief
- `PREMARKET_GAP_SCAN` fires at 8:30 AM ET (5:30 AM PST)
- Triggers universe refresh + AI evaluation before market open
- News sentiment (NewsFetcher) and earnings calendar wired — only fires at premarket

### Stale Position Import Guard
**File:** `execution/alpaca_executor.py`

- Skips importing Alpaca positions where entry price differs >5% from current price
- Prevents phantom stop-outs from old positions (TSLA bought at $407, current $297 → skipped)
- Critical fix — without this, every restart imported old positions and triggered fake -29% losses

### Minimum Hold Time (60 seconds)
**File:** `decision_engine/trailing_stop.py`

- Stop cannot fire within first 60 seconds of entry
- Prevents META/COIN style immediate stop-outs on volatile fills

### Churn Prevention
**File:** `decision_engine/trading_agent.py`

- `_symbol_trade_count` — tracks trades per symbol per day
- `_symbol_loss_count` — tracks consecutive losses per symbol per day
- Max 3 trades per symbol per day (configurable via `max_trades_per_symbol`)
- After 2 consecutive losses on same ticker → full day block
- **BUG:** Counters NOT initialized in `__init__()` — only in daily reset code
- This means counters are always 0 on startup → guard never fires → churn continues

---

## 🚨 OPEN BUGS (fix before next trading day)

### CRITICAL — Fix immediately

**Bug 1: Churn prevention counters not initialized in `__init__()`**
```python
# trading_agent.py — in __init__() at self._cycle_count = 0, ADD:
self._symbol_trade_count: dict = {}   # trades per symbol today
self._symbol_loss_count:  dict = {}   # consecutive losses per symbol today
```
Without this, getattr(self, '_symbol_trade_count', {}) returns a NEW empty dict every call.
The guard at line ~1576 always sees count=0 and never blocks.
META and MSFT each traded 6 times today despite max_trades_per_symbol=3.

**Bug 2: AI reads corrupted portfolio.json → makes wrong defend decisions**
The portfolio tracker accumulates phantom trades from restarts. Claude reads avg_loss=$17,816
from fake data and DEFEND-loops. Need to either:
- Auto-sync portfolio.json from Alpaca on startup (preferred)
- Add a portfolio validity check before feeding to AIConfigurator

**Bug 3: Universe data_manager wiring — needs verification**
After fix, universe should score 68 tickers at market open.
Currently shows "Scored: 0 tickers | refreshed: None" — wiring may not be taking effect.
Check: after restart, run `curl -s -X POST http://localhost:8001/api/universe/refresh`
If it scores 0, the data_manager is still None when refresh runs.

**Bug 4: AI keeps raising conviction to 2.5**
Claude sees 0% win rate (from phantom data) and raises conviction.
Fix Bug 2 first — clean data will give Claude correct win rate → stops over-defending.
Also add conviction floor: never let AI set conviction > 2.0 for Micro Momentum.

### MEDIUM

**Bug 5: Portfolio.json accumulates phantom trades across restarts**
Every restart, the portfolio tracker's `sync_eod_from_alpaca()` may reimport old trades.
Need to add a session boundary — only sync trades from current day.

**Bug 6: AI watchlist too small after defend**
Claude trims to 5 tickers when defending. With only 5 tickers and conviction 2.5,
no trades fire for hours. Add minimum watchlist size (8 tickers) even in defend mode.

---

## ✅ FIXES FROM ORIGINAL HANDOFF (all deployed)

All 14 original fixes (Fix 1–14) from May 8 handoff are deployed to V1 and V2:
- Duplicate buy guard ✅
- Full position sync every cycle ✅
- Import missing Alpaca positions ✅ (+ stale guard added)
- Stop-out cooldown enforced ✅
- Loss-only re-entry cooldown 60min ✅
- MICRO_MOMENTUM enum ✅
- _is_micro enum check ✅
- Momentum strategy price= removed ✅
- BarSet KeyError fix ✅
- SIGALRM removed ✅
- get_open_positions() property fix ✅
- V2 saved_config.json corrected ✅
- V2 all 13 strategies active (MODE_ROLES expanded) ✅
- MicroMomentum thresholds lowered ✅

---

## 📈 PERFORMANCE HISTORY

| Date | Agent | Day P&L | Notes | Equity |
|---|---|---|---|---|
| Apr 28 | V1 | +$739 | 3 trades, 100% win | $1,001,010 |
| May 1 | V1 | +$237 | Duplicate buy bug, PDT flagged | $1,005,617 |
| May 4 | V1 | +$13,026 | 82% win rate 🔥 | $1,020,217 |
| May 5 | V1 | +$355 | 23 trades, B+ | $1,005,053 |
| May 6 | V1 | +$4,785 | Cooldown bug blocked AM | $1,030,632 |
| May 7 | V1 | $0 | is_stopped_out wrong name | $1,031,060 |
| May 8–16 | V1 | mixed | Stable, running | ~$1,024,384 |
| May 18 | V2 | -$414 | Phantom imports + MSFT churn | $997,133 |
| May 19 | V2 | +$158 | AAPL +$186, META -$28 | $997,308 |
| May 20 | V2 | -$837 | COIN/MSFT churn (10 trades each) | $990,095 |
| May 21 | V2 | -$10 | AI over-defending, few trades | $990,078 |
| May 22 | V2 | -$489 | META/MSFT churn (6 each), churn guard not firing | $989,589 |

---

## 🔧 CORRECT V2 CONFIG (saved_config.json)

```json
{
  "approach": "Micro Momentum",
  "stop_loss_pct": 0.004,
  "take_profit_pct": 0.008,
  "min_conviction_score": 1.5,
  "min_strategies_agree": 1,
  "max_open_positions": 8,
  "max_trades_per_symbol": 3,
  "intraday_mode": true,
  "intraday_interval_min": 1,
  "scan_interval_minutes": 1,
  "trading_timeframe": "15Min",
  "min_risk_reward": 2.0,
  "paper_trading": true,
  "market_hours_only": true
}
```

---

## 🚀 LAUNCH COMMANDS

```bash
# V1
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh

# V2
lsof -ti:8001,3001 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent_v2 && bash run_dashboard.sh

# Emergency close all V1 positions
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKUPVN2TBTLKAUHOQLIMWGK4BM' \
  -H 'APCA-API-SECRET-KEY: 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'

# Emergency close all V2 positions
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKP3WTGVDUYTDCYW5VDW3Z3CMZ' \
  -H 'APCA-API-SECRET-KEY: HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'

# Check both agents
bash ~/Downloads/quick_check.sh

# V2 full health check
bash ~/Downloads/v2_health_check.sh
```

---

## 🩺 AI CONFIG API ENDPOINTS (V2 only)

```bash
# Latest AI decision (instant, never blocks)
curl -s http://localhost:8001/api/ai_config/latest | python3 -m json.tool

# Full decision history
curl -s http://localhost:8001/api/ai_config/history | python3 -m json.tool

# Trigger force evaluation (sets flag, fires next scan cycle)
curl -s -X POST http://localhost:8001/api/ai_config/evaluate | python3 -m json.tool

# Universe scores
curl -s http://localhost:8001/api/universe/scores | python3 -m json.tool

# Force universe refresh
curl -s -X POST http://localhost:8001/api/universe/refresh | python3 -m json.tool

# Force Claude to pick new watchlist
curl -s -X POST http://localhost:8001/api/universe/watchlist_refresh | python3 -m json.tool

# Revert to config before entry_id
curl -s -X POST http://localhost:8001/api/ai_config/revert/{entry_id} | python3 -m json.tool
```

---

## ⚠️ KEY LESSONS LEARNED (May 8–22)

1. **portfolio.json is the single source of truth for AI decisions** — if it has phantom data, Claude makes wrong decisions. Always verify against Alpaca before trusting dashboard P&L.
2. **Churn = tight stop + 30min cooldown + re-entry** — when a ticker moves against, 0.4% stop fires, 30min passes, agent re-buys, repeat. Fix: max_trades_per_symbol + consecutive loss block.
3. **Stale Alpaca positions cause phantom stop-outs** — positions from previous weeks get imported on restart with old entry prices, immediately stop out showing -29% losses. Stale guard (>5% drift) prevents this.
4. **AIReviewer and AIConfigurator fight each other** — AIConfigurator says EXPAND, AIReviewer says VETO. They need session context sharing. AIReviewer currently in pass-through mode.
5. **Universe scoring needs data_manager** — TickerUniverse initialized before DataManager connects. Wire data_manager into universe after connect() in start().
6. **Claude's DEFEND loop** — once Claude sees consecutive losses (even phantom), it raises conviction → fewer signals → fewer trades → losses continue → more defend. Break the loop with clean portfolio data.
7. **ast.parse() every file before restart** — syntax errors killed multiple trading days.
8. **MODE_ROLES must include NEUTRAL+TREND for Micro Momentum** — INTRADAY only = 3 strategies = conviction always 0.

---

## 📁 NEW FILES ADDED (May 8–22)

```
trading_agent_v2/
├── decision_engine/
│   ├── ai_configurator.py     ← autonomous config engine
│   ├── ticker_universe.py     ← 68-ticker scoring system
│   └── config_log.py          ← append-only AI decision log
└── logs/
    └── ai_config_log.jsonl    ← AI decision history
```

---

## 🔑 KEY DECISIONS (finalized — don't revisit)

1. **Fully autonomous AI** — no human approval, Claude decides everything about config
2. **Hard bounds** — PARAM_BOUNDS in ai_configurator.py, Claude cannot exceed them
3. **Non-blocking evaluate()** — lock.acquire(blocking=force, timeout) prevents API hang
4. **Stale import guard** — >5% price drift = skip import, prevents phantom stop-outs
5. **60s minimum hold** — stops cannot fire within first 60 seconds of entry
6. **Pass-through AIReviewer** — disabled until coordinated with AIConfigurator
7. **Portfolio.json = AI's brain** — keep it clean and synced with Alpaca reality
8. **Loss-only cooldown** — wins re-enter freely, only losses blocked for 60min

---

*TradeAgent Project Handoff | May 22, 2026 | Confidential*
