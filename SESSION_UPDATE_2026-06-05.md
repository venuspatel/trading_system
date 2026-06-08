# TradeAgent — SESSION UPDATE
**Date:** June 5, 2026 (post-close) | Supersedes status as of May 8 handoff

> Drop this into the project root alongside PROJECT_HANDOFF.md. It captures
> everything done on June 5 and the one open investigation (BOUNCE) to carry
> into the next chat.

---

## 📊 CURRENT STATE (June 5, 2026, after close)

### V1 — Profit Maximizer (ports 3000/8000)
| Field | Value |
|---|---|
| Equity (Alpaca truth) | **$1,001,934** (down from $1,031,060 on May 8) |
| Trades on file | 118, self-healed offset OK ($+246 offset, books honest) |
| Today's result | **0 wins / 10 losses / −$9,756** — bad day in RANGING/selloff market |
| Adaptive thresholds | conviction 2.5 / min_strats 2 (legitimate — V1 trades are real & attributed) |
| Config | Profit Maximizer, 2-min scan, max 6 positions |
| Status | Running, patched, books clean |

### V2 — Micro Momentum (ports 3001/8001)
| Field | Value |
|---|---|
| Equity (Alpaca truth) | **$1,005,294** (true +$5,294 lifetime) |
| Trades on file | 833 (rebuilt from Alpaca fills — see below) |
| Adaptive thresholds | baseline 1.5 / 1 (fixed — was poisoned to 3.5) |
| Config | Micro Momentum, 1-min scan, max 8 positions |
| Status | Running, all June 5 fixes deployed |

---

## ✅ FIXED & COMMITTED ON JUNE 5

All committed to `master`. Key commit: **`f7536a9`** + a follow-up V1 sentiment commit.

### 1. V2 portfolio.json was corrupt (−$157k phantom) → REBUILT
- **Cause:** the duplicate-buy bug (below) desynced the position map, so the
  tracker paired exits against WRONG entry prices (e.g. GOOGL entry=368 exit=195
  on a "−0.4% stop"). Every price field in portfolio.json was unreliable.
- **Fix:** rebuilt portfolio.json from Alpaca fill history via FIFO matching
  (`rebuild_v2_portfolio.py`). Reconstructed 833 real round-trips, true P&L
  +$5,368 realized / +$5,294 equity-based (agree within $74). Reconstructed
  trades tagged `exit_reason = "Reconstructed from Alpaca fills"`.
- **Note:** portfolio.json is gitignored (local only). Backups of the corrupt
  file saved as `portfolio.json.corrupt-backup-*`.

### 2. V2 duplicate-buy bug (ROOT CAUSE of the whole cascade) → GUARDED
- **Symptom:** same symbol bought 2-3× in consecutive scans before the first
  fill synced (e.g. GOOGL 405+405+405 = 1,215 shares, 76s apart). The existing
  guard checked open_positions (set only after a 2s fill poll) and Alpaca
  pending orders (propagation delay) — both populated too late, and both had
  fail-open `except...proceeding` fallbacks.
- **Fix:** added a **fail-closed `_pending_buys` set** in `alpaca_executor.py`.
  Marked synchronously at the top of the BUY branch in `_place_order` (before
  any API call), held until the position is RECORDED in `_open_position`,
  released on every failure path. Closes the same-cycle race.
- **File:** `trading_agent_v2/execution/alpaca_executor.py`

### 3. V2 adaptive thresholds poisoned to 3.5 → FIXED
- **Cause:** the adaptive-learning exclusion filter in `trading_agent.py` checked
  for tag `'Recovered from Alpaca'` but the rebuilt trades are tagged
  `'Reconstructed from Alpaca fills'` — mismatch meant all 833 reconstructed
  trades fed the AdaptiveThresholdEngine, which saw 42% win rate → floor 3.5.
- **Fix:** aligned the filter string. (Note: for Micro Momentum the floor was
  already clamped to 1.5 downstream, so the 3.5 was mostly a misleading
  display, but the fix makes the intended exclusion real.)
- **File:** `trading_agent_v2/decision_engine/trading_agent.py`

### 4. AIConfig / AIReviewer HTTP 400 → DIAGNOSED (not a code bug)
- **Cause:** the Anthropic **account is out of API credits.** The API returns
  this as a 400 ("credit balance is too low"). Key is valid, model string valid.
- **Also fixed:** `ai_configurator.py` had a stale model string
  `claude-sonnet-4-20250514` → changed to `claude-sonnet-4-6` (would 400 on
  model once credits are added). Committed.
- **Action needed:** add credits in Anthropic Console if the AI layer is wanted.
  Both modules fail SAFE (reviewer approves by default; configurator skips).

### 5. Sentiment API cost cut ~80% (both agents)
- **Cause:** `sentiment.py._score_article` called Claude once PER HEADLINE.
- **Fix:** switched individual headline scoring to the free keyword scorer;
  kept the per-symbol AI summary (`_get_ai_summary`). Aggregate score unchanged.
- **Cost:** both agents dropped from ~$8-10/day to ~$2-3/day (~$60-90/mo).
- **Files:** `trading_agent_v2/news/sentiment.py` AND `trading_agent/news/sentiment.py`
  (V1 patch also fixed V1's stale model string in the same file).

---

## 🔭 OPEN INVESTIGATION — BOUNCE not firing (START HERE NEXT CHAT)

**Question:** BOUNCE is designed to buy oversold dips on down days. On June 5
(a selloff: V1 went 0/10, −$9,756), BOUNCE PRE-ACTIVATED 3 oversold names
(MSFT RSI 25, AVGO RSI 25, MU RSI 30, all down 1.6-5.2%) but never bought.

**Leading hypothesis (from reading `decision_engine/engine.py`):**
The decision engine has a hard **DOWNTREND block** in Gate 2 — any stock below
its MAs / down 5%+ over 10 days is classified DOWNTREND and "always blocked
regardless of conviction." It ALSO blocks NEUTRAL-trend stocks in a RANGING
market. A stock dipped enough to trigger BOUNCE is, by definition, DOWNTREND —
so the trend filter vetoes the exact setups BOUNCE exists to catch.

The engine has a `MomentumOverrideDetector` that LOWERS thresholds for *rallying*
stocks, but there appears to be **NO symmetric bounce-override hook** — i.e.
BOUNCE's pre-activation flag is likely never read by `engine.py`, so the
DOWNTREND filter blocks bounce candidates before bounce logic is consulted.
Two systems not talking: BOUNCE pre-activates in the strategy layer; the
decision engine independently HOLDs the same stock.

**Alternative possibility to rule out:** BOUNCE may be CORRECTLY declining a
falling-knife day (names dipped and kept dipping; buying them would have added
to the −$9,756). Need to check whether BOUNCE requires a confirming reversal
signal before buying.

**Files needed to confirm (paste as raw GitHub URLs in the new chat):**
- `trading_agent/strategies/bounce_detector.py` (core logic — what pre-activation enables)
- `trading_agent/strategies/engine.py` (strategy-layer wiring)
- `trading_agent/decision_engine/engine.py` (already analyzed — DOWNTREND block at Gate 2)
- `trading_agent/decision_engine/trading_agent.py` (where pre-activation meets the buy gate)

**Likely fix direction:** add a bounce-override hook in `engine.py`, symmetric
to the momentum override — "if symbol is bounce-pre-activated, skip DOWNTREND
block and apply bounce entry criteria." Confirm wiring is missing before
prescribing.

---

## 🔐 SECURITY — DO THIS (credentials exposed in chat)
Revoke and regenerate:
- 3 GitHub personal access tokens (pasted during the session)
- **Anthropic API key** `sk-ant-api03-0xT71...` (in BOTH agents' `.env`) — regenerate, update both `.env` files
- (Alpaca paper keys are throughout the docs — lower risk since paper, but rotate before any live trading)

---

## 🩹 RELATED — worth a future session
- **V1 underperformance in selloffs.** June 5 was 0/10 / −$9,756. Stops/TP may not
  always place (earlier: TSLA exited −3%, PLTR +5% against 0.25% stops). The
  BOUNCE gap is part of a bigger "why does V1 bleed on down days" question.
- **`Sync1Disabled`** warning on both agents — Alpaca trade-sync path partly disabled.
- **`decisions.jsonl` is 84 MB and growing** — V2 logs every decision every cycle.
  Consider rotation/pruning.
- **Both agents share ONE Anthropic key** — can't split cost per-agent in the
  Console without a second key; both draw from the same balance.

---

*Session update | June 5, 2026 | append to PROJECT_HANDOFF.md*
