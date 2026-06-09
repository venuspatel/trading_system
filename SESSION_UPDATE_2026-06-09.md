# TradeAgent — SESSION UPDATE
**Date:** June 9, 2026 | Supersedes the June 5 session update

> Append to PROJECT_HANDOFF.md alongside the May 8 and June 5 updates.
> This session was diagnosis + cleanup. Net result: both agents healthy,
> books honest, credentials rotated, logs bounded. BOUNCE investigated in
> depth — carried into a separate chat for the "make it profitable" decision.

---

## 📊 CURRENT STATE (June 9, 2026, after close)

### V1 — Profit Maximizer (ports 3000/8000)
| Field | Value |
|---|---|
| Equity (Alpaca truth) | **$998,907.76** (flat vs $1M start) |
| Trades on file | 127, realized +$940 net (45% win rate) |
| Open positions | 0 |
| BOUNCE | Active in code, **0 trades ever** — has never fired |
| Status | Running, authenticating on rotated keys, log rotation live |

### V2 — Micro Momentum (ports 3001/8001)
| Field | Value |
|---|---|
| Equity (Alpaca truth) | **$1,009,316.72** (true +$9,316 lifetime) |
| Trades on file | 843, rebuilt clean from Alpaca fills |
| Reconciliation | realized +$9,392 vs equity +$9,317 — agree within $76 |
| Open positions | 0 |
| Status | Running, books reconciled, duplicate-buy guard confirmed live |

---

## ✅ DONE THIS SESSION

### 1. SECURITY — all keys rotated (the one urgent item)
- Anthropic API key, V1 Alpaca pair, V2 Alpaca pair all regenerated and
  updated in both `.env` files. GitHub PAT rotated.
- Verified live: both Alpaca accounts authenticate, Anthropic key works
  **with credits** — so the long-standing AIReviewer HTTP 400 errors are
  now genuinely resolved (was an out-of-credits problem, not a code bug).
- `.env` confirmed gitignored in both agents.
- **Lesson:** keys were exposed repeatedly across docs + chats. Going
  forward, scripts read keys from `.env` via `os.environ` — never hardcoded,
  never pasted into a chat.

### 2. V2 BOOKS — phantom −$233k cleaned, cause confirmed
- **Symptom:** dashboard showed day P&L −$232,999 / realized −$227,631 while
  Alpaca equity was actually +$9.3k. Two GOOGL rows showed "take profit hit"
  with −$67k / −$64k P&L (impossible) — entry ~365 paired against exit ~190.
- **Cause:** stale corrupt rows in the OLD portfolio.json (entry/exit
  mispaired across what looked like a price split — really a duplicate-buy
  desync artifact from before the guard was effective). NOT freshly created.
- **Fix:** rebuilt portfolio.json from Alpaca's 1,618 real fills via FIFO
  matching (`rebuild_v2_portfolio_splitfix.py`, split-aware version). Produced
  843 clean round-trips, reconciled to equity within $76. Corrupt file backed
  up as `portfolio.json.corrupt-backup-20260609-140247`.
- **Duplicate-buy guard verified deployed** in V2 `alpaca_executor.py`:
  fail-closed `_pending_buys` set, checked synchronously at top of BUY branch
  (line ~472), marked before any API call (~479), released on all exit paths.
  Today's 10 trades reconciled with zero phantoms → guard is holding.
- **Conclusion:** one-time cleanup of old damage, not a recurring patch.

### 3. LOG ROTATION — `decisions.jsonl` bounded (real fix, deployed both agents)
- Was 92 MB (V2) / growing unbounded — flagged twice in prior handoffs.
- Manually truncated to ~10-12 MB, THEN added automatic size-based rotation
  to `decision_engine/decision_logger.py`: rotates at 15 MB to `.1`, keeps
  one backup, trims in-memory list to last 5,000. Drop-in, no behavior change.
- V1 and V2 `decision_logger.py` were identical → same patch deployed to both.
  Originals backed up as `~/decision_logger.v{1,2}.bak`.
- Also deleted 13 stale `portfolio.json.bak_*` debug files from May 22.

### 4. PDT CLEANUP — confirmed nothing to do
- Grep found NO live PDT logic (`pattern_day_trader`, `daytrade_count`,
  `daytrading_buying_power` are not checked anywhere). Only explanatory
  comments remain, and they're still accurate (code correctly uses `cash`,
  not `buying_power`). The handoff task was based on a stale assumption.

### 5. Sync1Disabled — confirmed NOT a bug
- The log warning comes from an intentional `raise Exception("Sync1Disabled")`
  in V1 `trading_agent.py` (~line 436), placed June 4 to disable the flaky
  `GetOrdersRequest` trade-sync path in favor of rebuilding from Alpaca.
- It is expected output, not an error. Leave as-is. (Optional: downgrade to a
  quiet skip if the log noise is annoying — purely cosmetic.)

---

## 🔍 BOUNCE INVESTIGATION — findings (carry into next chat)

The original question: "why didn't BOUNCE fire on June 5?" Resolved through
code reading + a 25-name × 33-day backtest. Summary:

- **BOUNCE is wired in and active** (Profit Maximizer MODE_ROLES includes it;
  `engine.py` routes downtrend stocks to `_evaluate_bounce`). It is NOT
  disabled. But it has **never produced a single trade** (0 of 127) — its
  3-of-4 conditions have never aligned live. Functionally dormant.
- **Three real (but currently harmless) defects found:**
  1. *Gate placement* — `_evaluate_bounce` sits inside the `if recommendation
     in (BUY, STRONG_BUY)` block (engine.py ~line 202), so in a true downtrend
     where trend strategies vote sell, bounce can be vetoed before it's asked.
  2. *Broken RSI* — `bounce_detector._rsi` has no warmup guard + a 50.0
     fallback; the correct `indicators/rsi.py` (min_periods guard) exists but
     bounce doesn't call it. Inert today, but wrong.
  3. *Weak entry* — leg-drop + oversold RSI alone is a falling-knife magnet.
- **On June 5 specifically:** BOUNCE correctly bought nothing on MSFT/AVGO/MU
  — they kept falling, no real reversal. The −$9,756 that day was the
  PROFIT MAXIMIZER going 0/10, NOT bounce.

### Research results (backtest harness in `research/`)
- Premise is real: up-swings inside declines exist and are catchable
  (validated across 825 symbol-days, clean train/test split).
- Best variant: **HL_strict** = higher-low entry + trailing exit + real-time
  market-breadth regime filter. Positive on recovery/uptrend days, contained
  on selloffs, survives the held-out test set.
- **But thin:** gross edge ~+$4/trade, break-even ~2 bps slippage. The strict
  variant pushes break-even past ~3 bps and is net-positive on the test set,
  but only roughly break-even across a full regime cycle.
- **Verdict: conditionally viable → tiny PAPER trial only, NOT real capital,
  and only after 60–90 day validation.** No urgency: bounce idle is harmless.

### Behavior contrast (intent-aligned summary)
- June-5-type day (broad selloff): regime filter blocks all entries → does
  nothing → correct.
- Recovery/uptrend day: participates, ~2 small trades/name, ~41% win, trailing
  exit lets winners run → small net positive.

### Tools produced (in `research/`, NOT wired into live agents)
- `fetch_bounce_data.py` — pulls N days of 1-min OHLCV for a ticker basket.
- `bounce_backtest.py` — multi-day, regime-split, train/test, slippage sweep,
  5 variants incl. HL_strict.
- `rebuild_v2_portfolio_splitfix.py` — the split-aware Alpaca rebuild.

---

## 🚦 NEXT STEPS (for the BOUNCE chat)
1. Decide: shelve / validate / wire. Recommended: **validate first** —
   pull 60–90 days, re-run `bounce_backtest.py --sweep`, see if HL_strict
   holds its shape across more regimes.
2. If it holds AND survives 2–3 bps slippage: implement HL_strict in the live
   bounce path (fix RSI to use `indicators/rsi.py`, add regime filter, KEEP the
   working 1%/3% exit — do NOT use the tiny scalp exit), behind a flag, min size.
3. If it doesn't hold: leave bounce disabled. It costs nothing idle.

## 🩹 STILL OPEN (non-urgent, unchanged)
- Automatic log rotation now DONE; remaining: none critical.
- V2 `learn_from_trades` cross-feed from V1 (future enhancement).
- Strategy backtester for the other 12 strategies (only bounce studied so far).

## 🔐 HOUSEKEEPING
- Delete `~/decision_logger.v{1,2}.bak` after a few days of stable rotation.
- Keep `portfolio.json.corrupt-backup-20260609-*` as rollback safety.

---

*Session update | June 9, 2026 | append to PROJECT_HANDOFF.md*
