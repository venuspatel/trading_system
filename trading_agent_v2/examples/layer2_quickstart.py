# -*- coding: utf-8 -*-
"""
Layer 2 quickstart -- Pattern Recognition & Technical Indicators
----------------------------------------------------------------
Run from inside the trading_agent folder:
    python3 examples/layer2_quickstart.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timezone, timedelta

from config import cfg
from data_layer import AlpacaProvider, DataManager
from indicators import IndicatorEngine

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# Connect
provider = AlpacaProvider(
    api_key    = cfg.alpaca_api_key,
    secret_key = cfg.alpaca_secret_key,
    paper      = cfg.alpaca_paper,
)
manager = DataManager(provider=provider)
manager.connect()

start  = datetime.now(timezone.utc) - timedelta(days=365)
engine = IndicatorEngine()

print(f"\nFetching 1 year of daily bars for: {cfg.watchlist}")
print("Running all indicators...\n")

# Analyze each symbol
results = []
for symbol in cfg.watchlist:
    try:
        df      = manager.get_bars_df(symbol, "1Day", start=start)
        summary = engine.analyze(symbol, df)
        results.append(summary)
        print(summary)
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}\n")

# Ranked summary table
print("\n" + "="*60)
print("  WATCHLIST SUMMARY  (ranked by signal strength)")
print("="*60)
print(f"  {'Symbol':<8} {'Score':>6}  {'Signal':<10} {'Buys':>5} {'Sells':>6}")
print(f"  {'------':<8} {'-----':>6}  {'------':<10} {'----':>5} {'-----':>6}")

results.sort(key=lambda r: r.score, reverse=True)
for r in results:
    arrow = "^^" if r.score >= 2 else "vv" if r.score <= -2 else "--"
    print(f"  {r.symbol:<8} {r.score:>+6.1f}  "
          f"{arrow} {r.combined_signal.value:<8} "
          f"{r.buy_count:>5} {r.sell_count:>6}")

print("="*60)
print("\nLayer 2 complete. Ready for Layer 3 (Strategy Engine)!\n")

manager.disconnect()
