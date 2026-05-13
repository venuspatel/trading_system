# -*- coding: utf-8 -*-
"""
Layer 4 quickstart — Decision Engine
--------------------------------------
Run from inside the trading_agent folder:
    python3 examples/layer4_quickstart.py

What this does:
  1. Configures the agent (you choose the approach)
  2. Fetches 1 year of data for all watchlist symbols
  3. Runs all 10 strategies
  4. Makes fully autonomous decisions with position sizing + risk checks
  5. Prints a complete decision report showing exactly what the agent would do
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timezone, timedelta

from config import cfg as app_cfg
from data_layer import AlpacaProvider, DataManager
from indicators import IndicatorEngine
from strategies import StrategyEngine
from decision_engine import AgentConfig, Approach, DecisionEngine, next_scan_times

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ── 1. Configure the agent ────────────────────────────────────
print("\n" + "="*60)
print("  TRADING AGENT — Layer 4: Decision Engine")
print("="*60)
print("\nChoose your approach:")
print("  1. Conservative  (5+ strategies, 2% risk, quality only)")
print("  2. Balanced      (3+ strategies, 5% risk, solid signals)")
print("  3. Aggressive    (2+ strategies, 10% risk, more trades)")

choice = input("\nEnter 1, 2, or 3 [default: 2]: ").strip() or "2"

config = AgentConfig()
if choice == "1":
    config.apply_conservative()
elif choice == "3":
    config.apply_aggressive()
else:
    config.apply_balanced()

portfolio_value = float(input("Enter portfolio value in $ [default: 10000]: ").strip() or "10000")
print(f"\nConfig: {config}")
print(f"Portfolio: ${portfolio_value:,.0f}")

# Show when agent will scan
scans = next_scan_times(config.approach)
print(f"\nScan schedule ({config.approach.value}):")
for s in scans:
    print(f"  {s.strftime('%I:%M %p ET')} — {('EOD scan (daily bar closed)' if s.hour >= 16 else 'Pre-market confirmation' if s.hour < 9 else 'Intraday scan')}")
print()

# ── 2. Connect and fetch data ─────────────────────────────────
provider = AlpacaProvider(
    api_key    = app_cfg.alpaca_api_key,
    secret_key = app_cfg.alpaca_secret_key,
    paper      = True,
)
manager    = DataManager(provider=provider)
manager.connect()

start      = datetime.now(timezone.utc) - timedelta(days=365)
ind_engine = IndicatorEngine()
str_engine = StrategyEngine()
dec_engine = DecisionEngine(config)

print(f"Scanning watchlist: {config.watchlist}\n")

# ── 3. Run full pipeline ──────────────────────────────────────
decisions = []
for symbol in config.watchlist:
    try:
        df      = manager.get_bars_df(symbol, "1Day", start=start)
        summary = ind_engine.analyze(symbol, df)
        report  = str_engine.evaluate(symbol, df, summary)
        decision = dec_engine.decide(symbol, df, report, portfolio_value)
        decisions.append(decision)
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")

# ── 4. Print decision report ──────────────────────────────────
print("\n" + "="*60)
print("  AUTONOMOUS DECISION REPORT")
print("="*60)

actionable = [d for d in decisions if d.action in ("BUY", "SELL")]
holds      = [d for d in decisions if d.action == "HOLD"]
blocked    = [d for d in decisions if d.action == "BLOCKED"]

if actionable:
    print("\n  TRADE SIGNALS:")
    for d in sorted(actionable, key=lambda x: -x.conviction_score):
        print(f"\n  [{d.action}] {d.symbol}")
        print(f"    Conviction:   {d.conviction_score:+.2f}  |  Confidence: {d.avg_confidence:.0%}")
        print(f"    Strategies:   {d.buy_signals} buy, {d.sell_signals} sell signals")
        print(f"    Position:     {d.shares} shares = ${d.dollar_amount:,.0f}")
        print(f"    Stop loss:    ${d.stop_loss:.2f}  |  Take profit: ${d.take_profit:.2f}")
        print(f"    Risk/reward:  {d.risk_reward:.1f}:1")
        print(f"    Top reasons:")
        for r in d.top_reasons[:3]:
            print(f"      - {r}")
        print(f"    Strategies:   {', '.join(d.strategies_fired[:4])}")
else:
    print("\n  No actionable signals this cycle.")

if blocked:
    print(f"\n  BLOCKED ({len(blocked)}):")
    for d in blocked:
        print(f"    {d.symbol}: {d.block_reasons[0] if d.block_reasons else 'risk rule'}")

if holds:
    print(f"\n  HOLD ({len(holds)}): {', '.join(d.symbol for d in holds)}")

print(f"\n{'='*60}")
print(f"  Summary: {len(actionable)} trades | {len(blocked)} blocked | {len(holds)} hold")
print(f"  Mode: {'PAPER (simulated)' if config.paper_trading else 'LIVE'}")
print(f"  Approach: {config.approach.value}")
print(f"  Decision log: {config.log_path}")
print(f"{'='*60}\n")
print("Layer 4 complete. Ready for Layer 5 (Trade Execution)!\n")

manager.disconnect()
