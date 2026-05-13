# -*- coding: utf-8 -*-
"""
Layer 5 quickstart — Trade Execution
--------------------------------------
Run from inside the trading_agent folder:
    python3 examples/layer5_quickstart.py

What this does:
  1. Connects to Alpaca (paper trading)
  2. Shows your current account balance and positions
  3. Runs one full decision cycle
  4. Executes any approved trades on paper account
  5. Shows updated positions and portfolio state

IMPORTANT: This runs in PAPER TRADING mode by default.
No real money is used. Set ALPACA_PAPER=false in .env only
when you are ready to go live after full testing.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timezone, timedelta

from config import cfg as app_cfg
from data_layer import AlpacaProvider, DataManager
from indicators import IndicatorEngine
from strategies import StrategyEngine
from decision_engine import AgentConfig, Approach, DecisionEngine
from execution import AlpacaExecutor, PortfolioTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

print("\n" + "="*60)
print("  TRADING AGENT — Layer 5: Trade Execution")
print("  MODE: PAPER TRADING (no real money)")
print("="*60)

# ── Configure ─────────────────────────────────────────────────
config = AgentConfig()
config.apply_balanced()
config.paper_trading = True    # always True for this quickstart

# ── Connect executor ──────────────────────────────────────────
executor = AlpacaExecutor(
    api_key    = app_cfg.alpaca_api_key,
    secret_key = app_cfg.alpaca_secret_key,
    paper      = True,
)
executor.connect()

# ── Show account state ────────────────────────────────────────
acct = executor.get_account()
print(f"\nAccount state:")
print(f"  Portfolio value: ${acct.get('portfolio_value', 0):,.2f}")
print(f"  Cash:            ${acct.get('cash', 0):,.2f}")
print(f"  Buying power:    ${acct.get('buying_power', 0):,.2f}")
print(f"  Daily P&L:       ${acct.get('daily_pnl', 0):+,.2f}")
print(f"  Mode:            {'PAPER' if acct.get('paper') else 'LIVE'}")

portfolio_value = acct.get("portfolio_value", 10000)

# ── Show existing positions ───────────────────────────────────
positions = executor.update_positions()
if positions:
    print(f"\nOpen positions ({len(positions)}):")
    for sym, pos in positions.items():
        print(f"  {pos}")
else:
    print("\nNo open positions.")

# ── Connect data + run pipeline ───────────────────────────────
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

print(f"\nRunning decision cycle on: {config.watchlist}")

portfolio = PortfolioTracker()
orders_placed = []

for symbol in config.watchlist:
    try:
        df       = manager.get_bars_df(symbol, "1Day", start=start)
        summary  = ind_engine.analyze(symbol, df)
        report   = str_engine.evaluate(symbol, df, summary)
        decision = dec_engine.decide(symbol, df, report, portfolio_value)

        if decision.approved and decision.action in ("BUY", "SELL"):
            print(f"\n  Executing: {decision}")
            order = executor.execute(decision)
            if order:
                orders_placed.append(order)
                print(f"  Order result: {order}")
        else:
            action_str = f"{decision.action}"
            reason = decision.top_reasons[0] if decision.top_reasons else "no signal"
            print(f"  {symbol}: {action_str} — {reason}")

    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}")

# ── Final state ───────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  EXECUTION SUMMARY")
print(f"{'='*60}")
print(f"  Orders placed: {len(orders_placed)}")
for o in orders_placed:
    print(f"    {o}")

# Updated positions
positions = executor.update_positions()
if positions:
    print(f"\n  Open positions after cycle ({len(positions)}):")
    for sym, pos in positions.items():
        print(f"    {pos}")

# Updated account
acct = executor.get_account()
print(f"\n  Portfolio value: ${acct.get('portfolio_value', 0):,.2f}")
print(f"  Daily P&L:       ${acct.get('daily_pnl', 0):+,.2f}")
print(f"\n  Decision log:    {config.log_path}")
print(f"  Portfolio data:  logs/portfolio.json")
print(f"{'='*60}")
print("\nLayer 5 complete. Ready for Layer 6 (Performance Loop)!\n")

manager.disconnect()
executor.disconnect()
