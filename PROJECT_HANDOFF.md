# TradeAgent — PROJECT HANDOFF
**Date:** May 11, 2026 | **V1 Equity:** $1,031,060 | **V2 Equity:** ~$998,400

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

## 📊 CURRENT STATE (May 8, 2026)

### V1 — Profit Maximizer ✅ WORKING
| Field | Value |
|---|---|
| Equity | $1,031,060 (+$31k from $1M) |
| Keys | PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q |
| Stop / TP | 1.0% / 3.0% |
| Min conviction | 2.0 (adaptive) |
| Scan interval | 2 min |
| Max positions | 5 |
| Win rate | 76% over 33 trades |
| Grade | B+ |
| Status | Running, all fixes deployed |

**Signals queued for tomorrow open (6:30 AM PST):**
- QCOM conv=+4.93 🔥
- AMZN conv=+3.62
- AMD conv=+3.42
- TSLA conv=+2.18

### V2 — Micro Momentum ⚠️ NEEDS RESTART + RESET
| Field | Value |
|---|---|
| Equity | ~$998,400 (Alpaca ground truth) |
| Keys | PKP3WTGVDUYTDCYW5VDW3Z3CMZ / HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm |
| Stop / TP | 0.25% / 0.50% |
| Min conviction | 1.5 |
| Scan interval | 1 min |
| Max positions | 10 |
| Status | portfolio.json has phantom -$1.4M losses from INTC bug. Needs reset. |

---

## ✅ COMPLETED FIXES (all deployed to V1)

### Fix 1: Duplicate Buy Guard (executor level)
**File:** `execution/alpaca_executor.py` → `_place_order()`
```python
if side == OrderSide.BUY:
    self.update_positions()
    if sym_up in self.open_positions:
        logger.warning(f"[Executor] BLOCKED {sym_up}: already in open positions")
        return failed_order
    open_orders = self._client.get_orders(filter=None)
    pending = {o.symbol.upper() for o in open_orders if o.side=='buy' and o.status in ('new','accepted',...)}
    if sym_up in pending:
        logger.warning(f"[Executor] BLOCKED {sym_up}: already has pending BUY order")
        return failed_order
```

### Fix 2: Full Position Sync Every Cycle
**File:** `decision_engine/trading_agent.py` → scan start
```python
# Fully sync _open_positions from Alpaca every cycle
self._executor.update_positions()
confirmed = set(self._executor.open_positions.keys())
self._pending_buys -= confirmed
self._open_positions = {
    sym: {"symbol": sym, "qty": getattr(pos,"qty",0),
          "entry_price": getattr(pos,"entry_price",0), "max_loss": 0}
    for sym, pos in self._executor.open_positions.items()
}
```

### Fix 3: Import Missing Alpaca Positions
**File:** `execution/alpaca_executor.py` → `update_positions()`
```python
# Import any Alpaca positions not yet tracked locally
for symbol, ap in alpaca_pos_map.items():
    if symbol not in self._positions:
        self._positions[symbol] = Position(
            symbol=symbol, qty=int(ap.qty),
            entry_price=float(ap.avg_entry_price),
            current_price=float(ap.current_price),
        )
        logger.info(f"[Executor] Imported {symbol} from Alpaca (was missing locally)")
```

### Fix 4: Stop-Out Cooldown Enforced Before Buys
**File:** `decision_engine/trading_agent.py` → buy execution block
```python
if d.action == "BUY" and hasattr(self, '_scheduler'):
    if self._scheduler.is_in_stop_cooldown(d.symbol):
        logger.info(f"[Agent] {d.symbol} in stop-out cooldown — skipping")
        continue
```

### Fix 5: Loss-Only Re-entry Cooldown (60 min)
**File:** `decision_engine/trading_agent.py` → after exit recording
```python
# Wins re-enter freely. Only losses get cooldown.
if pnl < 0:
    self._scheduler.mark_stopped_out(symbol, cooldown_minutes=60)
```

### Fix 6: MICRO_MOMENTUM Added to Enum
**File:** `decision_engine/agent_config.py`
```python
class Approach(Enum):
    CONSERVATIVE     = "Conservative"
    BALANCED         = "Balanced"
    AGGRESSIVE       = "Aggressive"
    PROFIT_MAXIMIZER = "Profit Maximizer"
    LONG_TERM        = "Long Term"
    MICRO_MOMENTUM   = "Micro Momentum"   # ← was missing, caused V2 to fall back to Balanced
```

### Fix 7: _is_micro Enum Check
**File:** `decision_engine/trading_agent.py` → bar fetch section
```python
_approach_val = getattr(self.config, 'approach', '')
_approach_str = _approach_val.value if hasattr(_approach_val, 'value') else str(_approach_val)
_is_micro = _approach_str.lower() in ('micro momentum', 'micro_momentum')
```

### Fix 8: Momentum Strategy price= Argument Removed
**File:** `strategies/momentum.py`
```python
# WRONG (caused Momentum failed for QCOM every cycle):
return TradeSignal(..., price=price)
# FIXED:
return TradeSignal(...)  # price= arg doesn't exist on TradeSignal
```
**Impact:** QCOM conviction jumped 1.44 → 2.04 after fix.

### Fix 9: BarSet .get() → [] with KeyError
**File:** `data_layer/providers/alpaca_provider.py`
```python
try:
    raw = data[symbol]
except (KeyError, TypeError):
    raw = []
bars = [self._alpaca_bar_to_bar(symbol, b) for b in (raw or [])]
```

### Fix 10: SIGALRM Removed (thread-unsafe)
**File:** `data_layer/providers/alpaca_provider.py`
- Removed all `signal.alarm()` / `SIGALRM` code
- SIGALRM only works on main thread; agent scans run in background threads

### Fix 11: get_open_positions() → open_positions property
**File:** `dashboard/backend/api.py`
```python
# WRONG: agent._executor.get_open_positions()
# FIXED: agent._executor.open_positions
```

### Fix 12: V2 saved_config.json Corrected
```json
{
  "approach": "Micro Momentum",
  "stop_loss_pct": 0.0025,
  "take_profit_pct": 0.005,
  "min_conviction_score": 1.5,
  "min_strategies_agree": 1,
  "trading_timeframe": "15Min",
  "intraday_mode": true,
  "intraday_interval_min": 1,
  "min_risk_reward": 2.0
}
```

### Fix 13: V2 Strategies — All 13 Active
**File:** `strategies/engine.py` → MODE_ROLES
```python
"Micro Momentum": {StrategyRole.INTRADAY, StrategyRole.NEUTRAL, StrategyRole.TREND}
# was: {StrategyRole.INTRADAY}  ← only 3 strategies, conviction always 0
```

### Fix 14: MicroMomentum Thresholds Lowered
**File:** `strategies/micro_momentum.py`
```python
min_vol_spike      = 1.3   # was 2.0 — too strict for normal trading
min_price_move_pct = 0.0003  # was 0.002 — 0.2% in 2 min is extreme
max_spread_pct     = 0.005   # was 0.003
accel_ok = move_1bar > -self.min_price_move_pct  # was: move_1bar > 0
```

---

## 🚨 OPEN TASKS (in priority order)

### IMMEDIATE (before next trading day)
1. **Reset V2 portfolio.json** — phantom INTC losses showing -$1.4M
   ```bash
   python3 -c "
   import json
   path = '/Users/venuspatel/Desktop/trading_system/trading_agent_v2/logs/portfolio.json'
   with open(path, 'w') as f:
       json.dump({'trades':[],'snapshots':[],'session_start_pnl':0.0,'total_pnl':0.0,'version':2}, f)
   print('V2 portfolio cleared')
   "
   ```

2. **Apply V2 targeted patches** (do NOT blindly copy V1 files):
   - `is_in_stop_cooldown` check before buys (Fix 4)
   - Loss cooldown 60 min (Fix 5)
   - Check what V2 already has: `grep -n "stop-out cooldown\|is_in_stop_cooldown" ~/Desktop/trading_system/trading_agent_v2/decision_engine/trading_agent.py`

3. **Fix AIReviewer 400 errors** — update Anthropic API key or model string in `.env` files
   - Error: `[AIReviewer] API call failed: HTTP Error 400`
   - Check `.env` for `ANTHROPIC_API_KEY` and model string (should be `claude-sonnet-4-20250514`)

### SHORT TERM
4. **Trade sync robustness** — `GetOrdersRequest` SDK call fails intermittently
   - Fallback already in place using `requests` library
   - Verify log shows `[Agent] Synced X missing trades` or `Trade sync: X sells checked`

5. **Smart close wash trade fix** — positions bought same cycle shouldn't be immediately closed
   - Happens when restarting during 3:30-4:00 PM ET window
   - Need to track `_session_buys` set and exclude from smart close

6. **PDT cleanup** — FINRA abolished PDT June 4, 2026
   - Remove `pattern_day_trader`, `daytrade_count`, `daytrading_buying_power` references
   - Replace with plain `buying_power` check

### FUTURE
7. **V2 learns from V1 trades** — `StrategyRanker.learn_from_trades(v1_portfolio.json)`
8. **Performance tab accuracy** — portfolio.json sync for stop/TP exits missed offline

---

## ⚠️ KNOWN ISSUES

| Issue | Cause | Status |
|---|---|---|
| V2 phantom -$1.4M P&L | INTC bought 7,158 shares (2x duplicate), stop recorded twice | Fix: clear portfolio.json |
| AIReviewer 400 errors | Anthropic API key expired or wrong model string | Workaround: approves by default |
| get_bars errors after hours | Alpaca returns empty BarSet after 4PM ET | Expected, resolves at open |
| Smart close wash trades | Restart during 3:45 PM ET fires close on just-bought positions | Workaround: don't restart then |
| V2 stop_loss was 0.0 | saved_config.json had wrong values | FIXED: corrected config deployed |

---

## 🔑 KEY DECISIONS (finalized — don't revisit)

1. **Two separate agents** (`trading_agent/` + `trading_agent_v2/`) — do NOT share files blindly, apply targeted patches
2. **Executor-level duplicate guard** is the gold standard — checks both open positions AND pending orders at `_place_order()` time
3. **Loss-only cooldown** (60 min) — wins can re-enter freely to capture momentum, losses are blocked
4. **Kelly sizer uses `cash` not `buying_power`** — avoids PDT $0 buying_power trap
5. **`update_positions()` does full two-way sync** — adds missing from Alpaca AND removes closed locally
6. **`_open_positions` fully replaced each cycle** — never merge, always rebuild from executor
7. **BarSet uses `[]` with KeyError, never `.get()`** — Alpaca SDK BarSet doesn't support dict API
8. **SIGALRM forbidden** — only works on main thread; use threading.Event or simple timeout instead
9. **V2 uses all 13 strategies** (MODE_ROLES expanded) — not just 3 INTRADAY strategies
10. **Enum comparisons require `.value`** — `Approach.MICRO_MOMENTUM == 'Micro Momentum'` always False

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
```

---

## 📐 PLANNING PHASE — STRATEGY DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                  TRADING AGENT ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  LAYER 1: DATA                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Alpaca SDK → 15-min bars (main) + 1-min bars (V2) │   │
│  │  BarSet → OHLCV DataFrame per symbol               │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  LAYER 2: INDICATORS                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  RSI · MACD · SMA20/50 · Volume · ATR · VWAP      │   │
│  │  → AnalysisSummary (per symbol)                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  LAYER 3: STRATEGIES (13 total)                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Momentum · Breakout · CandleReversal               │   │
│  │  CandleContinuation · Divergence · VolumeConfirm   │   │
│  │  MultiTimeframe · TrendRegime · TrendStrength       │   │
│  │  EarningsMomentum · IntradayVWAP · ORBreakout      │   │
│  │  MicroMomentum (V2 only, uses 1-min bars)          │   │
│  │  → StrategyReport (conviction score -10 to +10)    │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  LAYER 4: DECISION ENGINE                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ConvictionScorer → MTF boost → RegimeFilter        │   │
│  │  RiskGuardian (max positions, daily loss limit)     │   │
│  │  KellySizer (position size based on conviction)    │   │
│  │  → TradeDecision (BUY/SELL/HOLD + shares + stops) │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  LAYER 5: EXECUTION                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Duplicate Buy Guard (checks positions + orders)   │   │
│  │  AlpacaExecutor → submit order → track fills       │   │
│  │  PortfolioTracker → record ClosedTrade + P&L       │   │
│  │  TrailingStopManager → monitor open positions      │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  LAYER 6: DASHBOARD                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FastAPI /api/state · /api/trades · /api/configure │   │
│  │  React frontend → live equity curve, positions     │   │
│  │  Performance tab · Trade history · Grade display   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

V1 FLOW (Profit Maximizer):
6:30 AM PST → startup scan → buy top 5 signals (conv≥2.0)
Every 2 min → intraday scan → exit losers, hold winners
Trailing stop 1% · Take profit 3% · Max hold 2 days
Loss exit → 60 min cooldown · Win exit → re-enter freely

V2 FLOW (Micro Momentum):  
6:30 AM PST → startup scan → buy top 10 signals (conv≥1.5)
Every 1 min → scan with 1-min bars → scalp momentum
Stop 0.25% · TP 0.50% · R/R ≥ 2.0 · Fast in/out
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
| May 7 | V1 | $0 | `is_stopped_out` wrong name — 0 trades | $1,031,060 |
| May 8 | V1 | Ready | All fixes deployed | $1,031,060 |

---

## 🔧 TECHNICAL CONSTRAINTS

- **Python 3.11** on macOS (venuspatel's MacBook)
- **Alpaca Paper Trading** — base URL `https://paper-api.alpaca.markets/v2`
- **Alpaca SDK** — `alpaca-trade-api` + `alpaca-py`. BarSet uses `[]` not `.get()`
- **FastAPI** with `uvicorn --reload` (hot-reloads on file save)
- **React** frontend on npm
- **No margin** — Kelly sizer uses `cash` only, `max_position_pct=10%`
- **PDT rule abolished June 4, 2026** — clean up references after that date
- **Market hours** — 6:30 AM – 1:00 PM PST (PST timezone, NOT ET)
- **Early close days** — market closes 10:00 AM PST (e.g. May 1)
- **ast.parse() every file** before deploying — syntax errors killed multiple trading days
- **Targeted patches for V2** — never blindly copy V1 files, agents have diverged

---

## 📁 FILE STRUCTURE

```
~/Desktop/trading_system/
├── trading_agent/              ← V1 (ports 3000/8000)
│   ├── run_dashboard.sh
│   ├── saved_config.json       ← Profit Maximizer config
│   ├── logs/portfolio.json     ← trade history
│   ├── decision_engine/
│   │   ├── trading_agent.py    ← MAIN — most changes here
│   │   ├── engine.py
│   │   ├── agent_config.py
│   │   ├── market_scheduler.py
│   │   ├── risk_guardian.py
│   │   └── position_sizer.py
│   ├── execution/
│   │   ├── alpaca_executor.py  ← duplicate buy guard here
│   │   └── portfolio_tracker.py
│   ├── strategies/
│   │   ├── engine.py           ← MODE_ROLES
│   │   ├── momentum.py         ← fixed price= bug
│   │   └── micro_momentum.py   ← V2 1-min scalping
│   ├── data_layer/providers/
│   │   └── alpaca_provider.py  ← BarSet fix, no SIGALRM
│   └── dashboard/backend/
│       └── api.py              ← open_positions property fix
│
└── trading_agent_v2/           ← V2 (ports 3001/8001)
    ├── run_dashboard.sh
    ├── saved_config.json       ← Micro Momentum config (FIXED)
    ├── logs/portfolio.json     ← NEEDS RESET (phantom losses)
    └── [same structure as V1 — apply patches carefully]
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
        rep = d.get('reporting',{}); cfg = d.get('config',{})
        print(f"{name}: {d.get('agent_status')} cycle={d.get('cycle_count')} "
              f"pnl=${rep.get('day_pnl',0):+.2f} approach={cfg.get('approach')}")
    except Exception as e:
        print(f"{name}: DOWN — {e}")
EOF

# Ground truth from Alpaca
python3 - << 'EOF'
import urllib.request, json
V1_KEY='PKUPVN2TBTLKAUHOQLIMWGK4BM'; V1_SEC='3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'
V2_KEY='PKP3WTGVDUYTDCYW5VDW3Z3CMZ'; V2_SEC='HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm'
for name,k,s in [('V1',V1_KEY,V1_SEC),('V2',V2_KEY,V2_SEC)]:
    req=urllib.request.Request(f'https://paper-api.alpaca.markets/v2/account',
        headers={'APCA-API-KEY-ID':k,'APCA-API-SECRET-KEY':s})
    acct=json.loads(urllib.request.urlopen(req,timeout=8).read())
    req2=urllib.request.Request(f'https://paper-api.alpaca.markets/v2/positions',
        headers={'APCA-API-KEY-ID':k,'APCA-API-SECRET-KEY':s})
    pos=json.loads(urllib.request.urlopen(req2,timeout=8).read())
    print(f"{name}: equity=${float(acct['equity']):,.2f} cash=${float(acct['cash']):,.2f} "
          f"positions={[p['symbol'] for p in pos]}")
EOF
```

---

*TradeAgent Project Handoff | May 8, 2026 | Confidential*

---

## 🗺️ ORIGINAL PLANNING PHASE — VISUAL ROADMAP

This was created on April 14, 2026 before any code was written. It governed the entire build sequence.

### Original 6-layer plan (now all complete ✅)
```
Layer 1: Market Data Ingestion      ✅ Complete — Alpaca SDK, OHLCV bars
Layer 2: Pattern Recognition        ✅ Complete — RSI, MACD, MA, Volume, ATR
Layer 3: Strategy Library           ✅ Complete — 13 strategies deployed
Layer 4: Decision Engine            ✅ Complete — Conviction, MTF, Risk, Kelly
Layer 5: Trade Execution            ✅ Complete — AlpacaExecutor, stops, fills
Layer 6: Performance Loop           ✅ Complete — P&L, StrategyRanker, adaptive
Layer 7: Dashboard + AI Config UI   ✅ Complete — React + FastAPI
```

### Phase 2 — Paper trading gate (IN PROGRESS)
- Run both agents minimum 4 weeks
- Target: 70%+ win rate, <10% max drawdown, both agents stable
- V1 currently at 76% win rate ✅
- V2 needs stabilization first ⚠️

### Phase 2b — V1 Feature Flag Rollout (in progress)
5-week plan, one flag per week:
- Week 1: Flag 5 — trailing stop activation buffer (0.5%) ✅ ON
- Week 2: Flag 4 — sector concentration limiter (NOT BUILT YET — next up)
- Week 3: Flag 3 — drawdown circuit breaker (NOT BUILT)
- Week 4: Flag 2 — ATR-based adaptive trailing stops (NOT BUILT)
- Week 5: Flag 1 — news sentiment → conviction wiring (NOT BUILT)

### Phase 3 — Non-trade roadmap (ranked by impact vs effort)
Discussed and prioritized May 11, 2026. DO NOT start until paper trading gate passes.

#### Quick wins — code exists, just needs wiring (days)
1. **News/sentiment → conviction modifier** ⭐ HIGHEST LEVERAGE
   - `news/sentiment.py` (333 lines) + `news/fetcher.py` (276 lines) fully built but DEAD CODE
   - Wire as ±0.5–1.0 conviction modifier on every buy signal
   - Effort: 1 day. Impact: immediate alpha improvement.

2. **Risk-adjusted performance metrics**
   - Add Sharpe ratio, Sortino ratio, max drawdown to `performance/daily_report.py`
   - Surface on dashboard Performance tab alongside win rate + P&L
   - Effort: 1 day. Formula: `Sharpe = (avg_daily_return / std_daily_return) × √252`
   - Critical credibility signal before live trading.

3. **Transaction cost modeling**
   - Paper trading hides slippage, spread, commission. Add `TxCostModel` that deducts
     estimated transaction costs from P&L on every trade simulation.
   - Effort: 1–2 days. Critical before any live trading decision.

#### Medium effort — 1–2 weeks each
4. **Backtesting engine** ⭐ CRITICAL GAP
   - Zero historical validation right now. All win rates tuned purely on live paper data.
   - Run all 13 strategies against 3–5 years of Alpaca historical bars.
   - The only true architectural gap vs institutional systems.
   - Effort: 2 weeks. Impact: validates (or invalidates) every strategy before live money.

5. **Drawdown circuit breaker (Flag 3)**
   - Halt new positions when drawdown exceeds 5% from portfolio peak.
   - Prevents spiral losses in adverse market regimes.
   - Effort: 3–5 days.

6. **ATR-based adaptive trailing stops (Flag 2)**
   - Replace fixed 1% trail with `stop = price − 2×ATR14`.
   - Adapts automatically — tight stops on calm stocks, wider on volatile ones.
   - Effort: 3–5 days.

7. **V2 learns from V1 trades**
   - Feed `trading_agent/logs/portfolio.json` into V2's `StrategyRanker.learn_from_trades()`
   - V2 inherits V1's winning signal weights. Agents become collaborative.
   - Effort: 1 week.

#### Bigger builds — Phase 3 proper (post paper trading gate)
8. **ML-based strategy weight optimizer** (4–6 weeks)
   - Auto-upweight strategies performing well recently, downweight losers.
   - Moves beyond static conviction scoring toward adaptive alpha.

9. **IBKR live integration** (3–4 weeks)
   - IBKR stub (96 lines) exists. Replace with real `ib_insync` calls.
   - Professional-grade execution, real commissions, extended hours.
   - Gateway to live trading — do NOT start until paper trading gate passes.

10. **Options strategies** (6–8 weeks)
    - Covered calls on winning positions, protective puts as hedges, spreads.
    - Significant complexity — needs separate strategy engine layer.

11. **Binance crypto integration** (2–3 weeks)
    - Binance stub (137 lines) exists. Replace with `python-binance`.
    - 24/7 crypto trading on same decision engine.

12. **Mobile app — React Native** (discussed May 11, 2026)
    - Full native iOS/Android app via Expo + React Native
    - 7 screens: Login (PIN + Face ID), Home, Positions, Trades, Configure, Alerts, Accounts
    - Remote access via Cloudflare Tunnel or ngrok (HTTPS)
    - Push notifications via Expo Notifications + new `/api/notify` FastAPI endpoint
    - Configure screen mirrors existing ConfigPanel — same `/api/configure` endpoint
    - Strategy profiles: save named configs (e.g. "Profit Maximizer") — pure strategy
      settings, zero broker credentials. Reusable across any future broker.
    - Dark theme. No app store needed during development (Expo Go).
    - Estimated effort: 10–12 days. All mockups designed and approved May 11.

    KEY ARCHITECTURE DECISION (May 11):
    - App built against Alpaca NOW. Works fully today.
    - App uses AppContext.js — broker URL + auth token come from context, never hardcoded.
    - The 4 FastAPI endpoints the app uses (/api/state, /api/trades, /api/configure,
      /api/notify) never change regardless of broker underneath.
    - When backend broker abstraction is built later → app automatically supports new
      brokers. Zero app code changes needed. Just add entry to Accounts screen.

    TWO INDEPENDENT WORKSTREAMS:
    Workstream 1 (now)  → Mobile app, Alpaca only, fully working
    Workstream 2 (later) → Backend generic broker layer refactor
    Result              → App works with all brokers automatically

13. **Backend broker abstraction layer** (prerequisite for live trading)
    - Current state: Alpaca-specific code baked into 3 files:
        alpaca_executor.py  — imports alpaca-py SDK directly, Alpaca types hardcoded
        alpaca_provider.py  — Alpaca BarSet quirks, Alpaca-specific error handling
        trading_agent.py    — references Alpaca account field names (cash, buying_power)
    - Stub files exist but empty: ibkr_provider.py, binance_provider.py
    - What to build: BrokerProvider base class with 4 normalized methods:
        get_account()   → cash, buying_power, equity (normalized across brokers)
        get_positions() → symbol, qty, avg_entry, current_price
        place_order()   → symbol, side, qty, order_type
        get_bars()      → OHLCV in standard Bar format
    - Then implement per broker:
        AlpacaProvider  — refactor existing code behind interface (~1 week)
        IBKRProvider    — fill existing stub with ib_insync (~2–3 weeks)
        ETradeProvider  — new subclass + OAuth flow (~3 weeks)
        Robinhood       — unofficial API only, risk of ban. Low priority.
    - DO NOT start until: paper trading gate passes + mobile app stable.
    - Nothing above the broker layer changes: strategies, conviction engine,
      risk guardian, Kelly sizer, dashboard, mobile app — all untouched.

14. **PDT rule cleanup**
    - FINRA abolished PDT June 4, 2026.
    - Remove `pattern_day_trader`, `daytrade_count`, `daytrading_buying_power` references.
    - Replace with plain `buying_power` check.

#### NOT in scope (discussed and deferred)
- Mobile / app integration — discussed May 11, to be evaluated separately
- Multi-timeframe hourly bars — nice to have, low urgency vs above items
- Order flow / microstructure (dark pool, options flow) — institutional complexity, Phase 4

### Design principle (from day 1, unchanged)
"Each layer produces working, runnable code before we move to the next. No skipping ahead."

---

## MOBILE APP — SESSION 2 UPDATE (May 12, 2026)

### Chart improvements completed
- Normalized P&L chart — line starts at midpoint, moves up/down based on P&L not absolute equity
- 1D view: zero = today open. All view: zero = $1M account start with dates on x-axis
- Green line always (neutral), win/loss dots handle color coding
- White dotted midline as neutral baseline
- 9 time range tabs at bottom: 1H, 3H, 1D, 1W, 1M, 3M, YTD, 1Y, All
- Pinch to zoom + drag crosshair (GestureHandler — no ScrollView conflict)
- Hero equity header: always shows live equity, updates live while dragging
- Trade dots on line with P&L info inline in header when near dot
- Peak gain / Peak loss / Trades / Net P&L footer stats

### Configure screen — full dashboard parity
- 4 tabs: Strategies, Risk, Watchlist, Safeguards
- Ticker search + quick add groups (Big Tech, Semis, AI, Fintech, ETFs)
- All sliders match dashboard: stop, TP, portfolio risk, max pos, daily loss, cooldown
- Feature flags with Switch toggles
- Save validation prevents bad values reaching agent

### Known issue fixed
- Mobile configure was sending stop_loss_pct as percentage (1.0) but API divides by 100
  so agent was getting 0.0001. Fixed. Original config restored via curl.

### Tab icons
- Using @expo/vector-icons Ionicons
- Home=home, Positions=bar-chart, Trades=list, Configure=settings, Alerts=notifications, Accounts=wallet

### Next session
- Push notifications (Expo Notifications + /api/notify endpoint)
- Permanent Cloudflare tunnel so URL does not change on restart
- Stop/TP display fix on metrics grid

---

## MOBILE APP — INFRASTRUCTURE ROADMAP (May 12, 2026)

### Item 1 — Different network support
Solved by permanent Cloudflare tunnel (item 2).
Once permanent URL is set, app works on any network — WiFi, cellular, anywhere.
No app reconfiguration needed ever again.

### Item 2 — Permanent Cloudflare tunnel (DO NEXT)
Replace throwaway quick tunnel with named tunnel + permanent subdomain.
e.g. https://agent.yourdomain.com — never changes.
Free via Cloudflare. One-time 20-min setup.
Commands:
  cloudflared tunnel create tradeagent
  cloudflared tunnel route dns tradeagent agent.yourdomain.com
  cloudflared tunnel run tradeagent
Unblocks: items 1, 4, and makes item 3 possible.

### Item 3 — Official iPhone app via TestFlight
Apple Developer Program: $99/year.
Build: npx eas build --platform ios
Distribute via TestFlight — no App Store review, installs like real app.
Expo Go no longer needed after this.
Prereq: permanent tunnel must be set up first.
Estimated effort: 2-3 hours.

### Item 4 — PIN lock on app launch (30 min fix)
LoginScreen.jsx already built with PIN + Face ID.
Bug: first launch skips PIN because none is set yet.
Fix: force PIN setup screen before anything loads on first launch.
Small change to AppContext.js — check if PIN exists, if not show setup flow.

### Item 5 — What needs to run on Mac
Two processes must always run:
  1. Trading agent:   cd trading_agent && bash run_dashboard.sh
  2. Cloudflare tunnel: cloudflared tunnel run tradeagent (after item 2)
Expo dev server (npx expo start) only needed during development.
After TestFlight build (item 3) — Expo no longer needed at all.

### Item 6 — Cloud deployment (Phase 3, after paper trading gate)
Move agent + tunnel off Mac entirely. Mac can be off.
Architecture:
  Cloud VPS runs: FastAPI agent + Cloudflare tunnel
  Phone connects to same permanent URL
  No Mac dependency
Options (easiest to hardest):
  Railway / Render  — $7/mo, deploy from GitHub, easiest
  DigitalOcean      — $6/mo, more control, good docs
  AWS EC2           — most powerful, most setup
Prereqs: paper trading gate passed + live trading approved + item 3 done.
Estimated effort: 1-2 days.

### Recommended sequence
  Step 1 (now)          Permanent Cloudflare tunnel
  Step 2 (soon)         Force PIN on first launch
  Step 3 (paper gate)   TestFlight build — real iPhone app
  Step 4 (live trading) Cloud deployment — full Mac independence

---

## MOBILE APP — SESSION 3 UPDATE (May 12, 2026 — late night)

### Permanent tunnel set up ✅
- Using ngrok free static domain — never changes
- URL: https://crispy-recycled-blemish.ngrok-free.dev
- Works from ANY network — WiFi, cellular, anywhere in the world
- Auth token saved to ngrok config
- Startup script: ~/Desktop/trading_system/start_tunnel.sh

### To start tunnel each session
```bash
ngrok http 8000 --domain=crispy-recycled-blemish.ngrok-free.dev
```

### Chart fixes ✅
- Duplicate timing tabs removed — single row at bottom now
- 9 tabs: 1H, 3H, 1D, 1W, 1M, 3M, YTD, 1Y, All
- Centered with justifyContent center

### What needs to run on Mac at all times
1. Trading agent:  cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh
2. ngrok tunnel:   ngrok http 8000 --domain=crispy-recycled-blemish.ngrok-free.dev

### Next session TODO (in order)
1. Force PIN on first launch — 30 min fix in AppContext.js
2. Auto-start ngrok with agent (one command to rule them all)
3. TestFlight build — real iPhone app, no Expo Go needed
4. Cloud deployment planning

---

## SESSION 4 UPDATE (May 12, 2026 — morning)

### Web dashboard fixes
- Open positions table redesigned to match trades table style
- New columns: Symbol | Qty @ Entry (with TP below) | Current | Stop | P&L + %
- WIN/LOSS style coloring on P&L
- Overnight gap badge preserved

### Mobile home screen fixes  
- Positions table showing correctly with entry price fix
- entry_price=0 bug fixed in alpaca_executor.py
- 4 stat panels added below chart: Day P&L, Total P&L, Win Rate, Max Drawdown
- Panels sized down for compact display

### Permanent tunnel
- ngrok static domain: https://crispy-recycled-blemish.ngrok-free.dev
- Works from any network — WiFi or cellular
- Start command: ngrok http 8000 --domain=crispy-recycled-blemish.ngrok-free.dev

### Agent status 8:06 AM PST
- Equity: $1,025,658
- Day P&L: +$604 (7 trades, 57% win)
- Total P&L: +$2,800 (66 trades)
- Open: GOOGL 238 @ $387.50
- Grade: B | Market: BULL

---

## SESSION 5 UPDATE (May 12, 2026 — afternoon)

### Push notifications WORKING ✅
- Local notifications via expo-notifications
- Polls every 30 seconds for new trades
- Fires notification on: new trade closed (WIN/LOSS) + new position opened
- Works in Expo Go — no push token server needed
- utils/useTradeNotifications.js — polling hook wired into App.js
- utils/notifications.js — sendLocalNotification helper

### Notification format
- WIN:  ✅ SYMBOL WIN  |  +$537 · Trailing stop hit
- LOSS: 🔴 SYMBOL LOSS |  -$265 · Stop loss hit
- BUY:  🟢 Bought SYMBOL | 238 shares @ $387.50

### PIN system fixed ✅
- First launch: Set PIN → Confirm PIN → logged in
- Normal launch: Enter PIN → logged in
- Forgot PIN: Face ID verify → reset → set new PIN
- Face ID works properly after TestFlight build (Expo Go limitation)

### One-command startup script
- ~/Desktop/trading_system/start_all.sh
- Starts: agent + ngrok tunnel together
- Usage: bash ~/Desktop/trading_system/start_all.sh

---

## SESSION 6 UPDATE (May 12, 2026 — afternoon/evening)

### Dashboard.jsx CORRUPTED — needs restore
- File lost its main Dashboard export function during failed edit attempt
- Dashboard_final.jsx was uploaded to chat — copy it to restore:
  cp ~/Downloads/Dashboard_final.jsx ~/Desktop/trading_system/trading_agent/dashboard/frontend/src/components/Dashboard.jsx
- After restore, add new sections CAREFULLY below Strategy Votes section

### New dashboard sections to add (DO IN NEW CHAT)
Add these 4 sections below Strategy Votes in Dashboard.jsx:
1. Trade bar chart — horizontal bars per trade, green=win red=loss, centered on zero
2. Win streak + stats — current streak, best streak ring, avg win/loss, expectancy, profit factor
3. Velocity — trades/hr today, avg P&L/trade, all-time trades, day win rate
4. Candlestick — price chart for open position with entry/stop/target lines
Layout: Row 1 = trade bar chart + win streak (2 cols), Row 2 = velocity + candlestick (1fr + 2fr)
IMPORTANT: Insert INSIDE the main Dashboard function, before the last 2 closing </div> tags

### Mobile app completed this session
- Push notifications working via local notifications (expo-notifications)
- useTradeNotifications.js polls every 30s, fires on new trades/positions
- Notification format: WIN/LOSS badge + symbol + P&L + exit reason
- PIN system fixed: set/confirm on first launch, forgot PIN via Face ID
- Trade bar chart on mobile Trades screen — WIN/LOSS badge, price range, time, P&L
- Positions table on Home screen — entry price bug fixed in alpaca_executor.py
- 4 stat panels on Home screen: Day P&L, Total P&L, Win Rate, Max Drawdown

### Files changed this session
- trading-agent-mobile/screens/TradesScreen.jsx — rebuilt with table view
- trading-agent-mobile/screens/HomeScreen.jsx — positions table + stat panels
- trading-agent-mobile/context/AppContext.js — notifications + clearPin
- trading-agent-mobile/utils/notifications.js — local notifications helper
- trading-agent-mobile/utils/useTradeNotifications.js — polling hook
- trading_agent/execution/alpaca_executor.py — entry_price=0 fix
- trading_agent/dashboard/backend/api.py — /api/notify/register + /api/notify/send
- trading_agent/dashboard/frontend/src/components/Dashboard.jsx — CORRUPTED, needs restore

### Start of next chat
1. Restore Dashboard.jsx from Dashboard_final.jsx
2. Add 4 new sections to Dashboard carefully
3. Continue mobile improvements
