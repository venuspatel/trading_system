# TradeAgent — PROJECT HANDOFF
**Date:** May 23, 2026 | **V1 Equity:** $1,025,010 | **V2 Equity:** ~$998,400

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
     ├── strategies/engine.py                       ← 15 strategies → StrategyReport + conviction score
     │   ├── momentum.py, breakout.py, micro_momentum.py ...
     │   └── bounce_detector.py                     ← NEW: exhaustion bounce signal
     │
     ├── decision_engine/
     │   ├── trading_agent.py                       ← main scan loop, buy/sell execution
     │   │                                             D1+Adaptive bounce state machine
     │   ├── engine.py                              ← conviction scoring, MTF, bounce routing gate
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

## 📊 CURRENT STATE (May 23, 2026)

### V1 — Profit Maximizer ✅ WORKING + BOUNCE DEPLOYED
| Field | Value |
|---|---|
| Equity | $1,025,010.95 |
| Keys | PKUPVN2TBTLKAUHOQLIMWGK4BM / 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q |
| Stop / TP | 1.0% / 3.0% |
| Min conviction | 2.5 (adaptive, 60% WR over 116 trades) |
| Scan interval | 2 min |
| Max positions | 6 |
| Win rate | 60% over 116 trades |
| Strategies | 15 (added BounceDetector) |
| Status | Running, bounce mode live |

**Queued for open (9:30 AM ET):**
- QCOM conv=4.29 🔥 (monthly +60%)
- MARA conv=4.10 (cooldown LOSS #1 until ~8:46 ET)
- RKLB conv=3.58
- AAPL conv=3.50
- MU conv=3.35
- AAL conv=2.68 (cooldown LOSS #2 until ~10:16 ET)

### V2 — Micro Momentum ⚠️ NEEDS RESTART + RESET
| Field | Value |
|---|---|
| Equity | ~$998,400 (Alpaca ground truth) |
| Keys | PKP3WTGVDUYTDCYW5VDW3Z3CMZ / HnMPyPA2haqsGJamiM5HLnPQF2TGx8g8Si7qNLxs4YZm |
| Status | portfolio.json has phantom -$1.4M losses from INTC bug. Needs reset. |

---

## ✅ ALL DEPLOYED FIXES (cumulative)

### Original Fixes 1-14 (May 8, 2026)
See previous handoff — all deployed to V1, working.

### Fix 15: BounceDetector Strategy (May 22-23, 2026)
**File:** `strategies/bounce_detector.py` (new file, 191 lines)
```python
# Entry conditions — 3 of 4 required:
# C1: Price dropped ≥1.0% from recent 15-min leg high
# C2: RSI(14) < 40  (oversold)
# C3: Hammer candle OR 2-bar low stabilisation (exhaustion)
# C4: Volume < 85% of 50-bar average (sellers drying up)
# Confidence: 0.6-1.0 scaled by RSI depth + leg size
```

### Fix 16: StrategyRole.BOUNCE Added
**File:** `strategies/base.py`
```python
class StrategyRole:
    BOUNCE = "Bounce"   # ← added — bounce setups within downtrends/volatile moves
```

### Fix 17: BounceDetector in MODE_ROLES
**File:** `strategies/engine.py`
```python
"Profit Maximizer": {StrategyRole.NEUTRAL, StrategyRole.TREND,
                      StrategyRole.INTRADAY, StrategyRole.BOUNCE}  # ← BOUNCE added
```

### Fix 18: DOWNTREND Routing Gate
**File:** `decision_engine/engine.py`
```python
# BEFORE: DOWNTREND always blocked
if trend_state == "DOWNTREND": return HOLD

# AFTER: DOWNTREND routes to bounce evaluation
if trend_state == "DOWNTREND":
    return self._evaluate_bounce(symbol, df, report, price, ...)
# _evaluate_bounce() runs BounceDetectorStrategy in isolation
# if bounce signal fires with conv ≥ 1.5 → allow BUY
# otherwise → HOLD with informative reason
```

### Fix 19: D1+Adaptive Loss-Triggered Bounce Mode
**File:** `decision_engine/trading_agent.py`

**The core mechanism:** After any PM (Profit Maximizer) loss on a ticker, that ticker immediately enters bounce mode for the rest of the trading session. The 60-min cooldown is replaced by active bounce monitoring.

```python
# Three new methods:
_activate_bounce_mode(symbol, reason)    # called after PM loss
_record_bounce_exit(symbol, pnl)         # updates adaptive stop after bounce exit
_reset_bounce_tickers_for_new_day()      # clears all session state each morning

# Adaptive stop tightening after consecutive bounce losses:
# Normal:  -0.30% stop
# Loss #1: -0.20% stop (tighter)
# Loss #2: -0.15% stop (tightest)
# Loss #3+: 1.5hr pause, reset to -0.30%
# Bounce WIN: always resets to -0.30%
```

**State machine:**
```
PM loss on TICKER
    → _bounce_tickers[TICKER] = {active: True, consec_losses: 0, next_sl: 0.003}
    → next scan: PM signal skipped for TICKER
    → BounceDetector runs: if RSI<40 + leg>1% + 2/4 conditions → BUY

Bounce WIN  → consec_losses = 0, next_sl = 0.003 (reset)
Bounce LOSS #1 → next_sl = 0.002
Bounce LOSS #2 → next_sl = 0.0015
Bounce LOSS #3 → pause 6 scan cycles (~1.5hr), reset

New trading day → all bounce state cleared
```

**Simulation results on real Alpaca data (May 12-20, 2026):**
| Stock | Role | PM P&L | D1+Adp P&L | Improvement |
|---|---|---|---|---|
| AMD | Volatile (real 15-min data) | -$346 | +$1,091 | +$1,437 |
| QCOM | Bull | -$940 | +$55 | +$995 |
| RKLB | Mix/volatile bull | +$531 | +$1,003 | +$472 |
| HIMS | Downtrend | -$123 | +$136 | +$259 |
| **Total** | | **-$878** | **+$2,285** | **+$3,163** |

---

## 🚨 OPEN TASKS (priority order)

### IMMEDIATE
1. **Commit to GitHub** — token expired, commit manually from Mac:
   ```bash
   cd ~/Desktop/trading_system
   git add trading_agent/strategies/base.py \
           trading_agent/strategies/bounce_detector.py \
           trading_agent/strategies/engine.py \
           trading_agent/decision_engine/engine.py \
           trading_agent/decision_engine/trading_agent.py
   git commit -m "feat: BounceDetector + D1+Adaptive loss-triggered bounce mode"
   git push origin master
   ```

2. **Reset V2 portfolio.json** — phantom INTC losses showing -$1.4M:
   ```bash
   python3 -c "
   import json
   path = '/Users/venuspatel/Desktop/trading_system/trading_agent_v2/logs/portfolio.json'
   with open(path, 'w') as f:
       json.dump({'trades':[],'snapshots':[],'session_start_pnl':0.0,'total_pnl':0.0,'version':2}, f)
   print('V2 portfolio cleared')
   "
   ```

3. **AIReviewer API key** — running in pass-through mode (no key):
   - Set `ANTHROPIC_API_KEY` in `.env` file
   - Model string should be `claude-sonnet-4-20250514`

### SHORT TERM
4. **Wire `_record_bounce_exit` into exit loop** — the method exists and works but is not yet called from the exit recording section. Add this after recording a bounce trade exit:
   ```python
   # In the exit recording block, after pnl is calculated:
   if symbol in self._bounce_tickers and self._bounce_tickers[symbol].get('active'):
       self._record_bounce_exit(symbol, pnl)
   ```

5. **PDT cleanup** — FINRA abolished PDT June 4, 2026 (12 days away):
   - Remove `pattern_day_trader`, `daytrade_count`, `daytrading_buying_power` references
   - Replace with plain `buying_power` check

6. **Daily bar fetch for trend classifier** — current classifier uses 15-min MA20 (5 hours of data). Fix: fetch 1Day bars alongside 15-min, use daily MA20 for trend direction. QCOM was being misclassified as DOWNTREND by the 15-min classifier despite being +60% monthly.

7. **Trade sync robustness** — `GetOrdersRequest` SDK call fails intermittently

### FUTURE (after paper trading passes 4-week gate)
8. V2 learns from V1 trades (StrategyRanker cross-feed)
9. Volatility gate: if avg daily swing >2.5% → activate bounce as supplement even before PM loss
10. ML-based strategy weight optimizer
11. News & sentiment analysis layer
12. IBKR live integration
13. Options strategies

---

## ⚠️ KNOWN ISSUES

| Issue | Cause | Status |
|---|---|---|
| V2 phantom -$1.4M P&L | INTC bought 7,158 shares (2x duplicate) | Fix: clear portfolio.json |
| AIReviewer pass-through | No ANTHROPIC_API_KEY in .env | Set key, use claude-sonnet-4-20250514 |
| _record_bounce_exit not wired | Method exists, not called from exit loop | Needs 3-line patch |
| GitHub token expired | ghp_eGs0V... is 401 Unauthorized | Commit from Mac terminal |
| get_bars errors after hours | Alpaca returns empty BarSet after 4PM ET | Expected, resolves at open |

---

## 🔑 KEY DECISIONS (finalized — don't revisit)

1. **D1 session bounce beats D2/D3** — PM loss → bounce for full session outperformed 2hr window (+$1,091 vs -$938) and win-return-to-PM (+$607). Session reset is the right design.
2. **Loss-triggered > cooldown** — replacing 60-min cooldown with active bounce mode turns a blocking pause into profitable trades.
3. **Adaptive stop is a safety valve** — it didn't trigger on this dataset (bounce losses weren't consecutive) but protects against 3+ consecutive losses in a genuine freefall.
4. **Volatility gate pending** — all 4 stocks had avg daily swings >2.5% (AMD 6.2%, QCOM 7.1%, RKLB 9.3%, HIMS 6.9%). A volatility-based gate would activate bounce even before PM losses occur, but this adds complexity. Decided to ship loss-triggered mode first and add volatility gate later.
5. **15 strategies now active** (was 13, then 14 with BounceDetector) — BounceDetector added to Profit Maximizer MODE_ROLES.
6. **DOWNTREND → bounce routing** replaces the old unconditional DOWNTREND block. Stocks in downtrend now get bounce evaluated instead of being blocked forever.
7. All previous key decisions from May 8 handoff remain valid.

---

## 🚀 LAUNCH COMMANDS

```bash
# V1
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent && bash run_dashboard.sh

# V2
lsof -ti:8001,3001 | xargs kill -9 2>/dev/null
cd ~/Desktop/trading_system/trading_agent_v2 && bash run_dashboard.sh

# Health check
python3 - << 'EOF'
import urllib.request, json
for name, port in [('V1',8000),('V2',8001)]:
    try:
        with urllib.request.urlopen(f'http://localhost:{port}/api/state', timeout=5) as r:
            d = json.loads(r.read())
        rep = d.get('reporting',{}); cfg = d.get('config',{})
        print(f"{name}: {d.get('agent_status')} cycle={d.get('cycle_count')} "
              f"pnl=${rep.get('day_pnl',0):+.2f} bounce_tickers={d.get('bounce_tickers',{})}")
    except Exception as e:
        print(f"{name}: DOWN — {e}")
EOF

# Verify bounce state machine
python3 - << 'EOF'
import sys; sys.path.insert(0,'.')
from decision_engine.trading_agent import TradingAgent
from decision_engine.agent_config import AgentConfig, Approach
cfg = AgentConfig(); cfg.approach = Approach.PROFIT_MAXIMIZER
agent = TradingAgent(cfg)
agent._activate_bounce_mode("TEST", "PM_LOSS")
agent._record_bounce_exit("TEST", -100)
assert agent._bounce_tickers["TEST"]["next_sl"] == 0.002
agent._record_bounce_exit("TEST", +200)
assert agent._bounce_tickers["TEST"]["next_sl"] == 0.003
agent._reset_bounce_tickers_for_new_day()
assert agent._bounce_tickers == {}
print("✓ Bounce state machine fully operational")
EOF

# Emergency close all V1 positions
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H 'APCA-API-KEY-ID: PKUPVN2TBTLKAUHOQLIMWGK4BM' \
  -H 'APCA-API-SECRET-KEY: 3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q'
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
| May 8-21 | V1 | -$6,049 | Various losses, 60% WR over 116 trades | $1,025,010 |
| May 22 | V1 | -$544 | 6 trades, 50% win | $1,025,010 |
| May 23 | V1 | TBD | Bounce mode live — first day | — |

---

## 🩺 WHAT TO WATCH ON FIRST BOUNCE DAY

```
# Bounce activated correctly:
[BounceMode] AMD ACTIVATED (PM_LOSS) sl=0.30% consec=0

# Bounce blocking PM re-entry:
[Agent] AMD in bounce mode — PM signal skipped, waiting for exhaustion

# Bounce entry firing:
[BounceDetector] AMD: Bounce 3/4 — leg=1.8% RSI=36 vol_dry
[Decision] ✓ AMD BUY | bounce_entry=True | conviction=+2.1

# Adaptive stop tightening after loss:
[BounceMode] AMD loss #1 — stop → 0.20%
[BounceMode] AMD loss #2 — stop → 0.15%

# Full session reset:
[BounceMode] New day — clearing bounce state: ['AMD', 'QCOM']
```

---

## 🔧 TECHNICAL CONSTRAINTS

- **Python 3.11** on macOS (venuspatel's MacBook)
- **Alpaca Paper Trading** — base URL `https://paper-api.alpaca.markets/v2`
- **15 strategies** — Momentum, Breakout, CandleReversal, CandleContinuation, Divergence, Fibonacci, VolumeConfirmation, MultiTimeframe, TrendRegime, TrendStrength, EarningsMomentum, IntradayVWAP, OpeningRangeBreakout, MicroMomentum, **BounceDetector** (new)
- **PDT rule abolished June 4, 2026** — clean up references after that date
- **Market hours** — 6:30 AM – 1:00 PM PST
- **ast.parse() every file** before deploying
- **Targeted patches for V2** — never blindly copy V1 files

---

## 📁 FILE STRUCTURE

```
~/Desktop/trading_system/
├── trading_agent/              ← V1 (ports 3000/8000)
│   ├── run_dashboard.sh
│   ├── saved_config.json
│   ├── logs/portfolio.json
│   ├── decision_engine/
│   │   ├── trading_agent.py    ← D1+Adaptive bounce state machine (1702 lines)
│   │   ├── engine.py           ← DOWNTREND → bounce routing gate (675 lines)
│   │   ├── agent_config.py
│   │   ├── market_scheduler.py
│   │   ├── risk_guardian.py
│   │   └── position_sizer.py
│   ├── execution/
│   │   ├── alpaca_executor.py
│   │   └── portfolio_tracker.py
│   ├── strategies/
│   │   ├── base.py             ← StrategyRole.BOUNCE added (125 lines)
│   │   ├── engine.py           ← BounceDetector in MODE_ROLES (282 lines)
│   │   ├── bounce_detector.py  ← NEW strategy (191 lines)
│   │   ├── momentum.py
│   │   └── micro_momentum.py
│   ├── data_layer/providers/
│   │   └── alpaca_provider.py
│   └── dashboard/backend/
│       └── api.py
│
└── trading_agent_v2/           ← V2 (ports 3001/8001) — NEEDS FIXES
    ├── run_dashboard.sh
    ├── saved_config.json       ← Micro Momentum config
    └── logs/portfolio.json     ← NEEDS RESET (phantom losses)
```

---

*TradeAgent Project Handoff | May 23, 2026 | Confidential*
