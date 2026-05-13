# -*- coding: utf-8 -*-
"""
Layer 3 quickstart -- Strategy Library
---------------------------------------
Run from inside the trading_agent folder:
    python3 examples/layer3_quickstart.py

What this does:
  1. Fetches 1 year of daily bars for your watchlist
  2. Runs all 6 indicators (Layer 2)
  3. Runs all 10 strategies (Layer 3)
  4. Prints full strategy reports + final ranked recommendations
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timezone, timedelta

from config import cfg
from data_layer import AlpacaProvider, DataManager
from indicators import IndicatorEngine
from strategies import StrategyEngine

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
manager      = DataManager(provider=provider)
manager.connect()

start        = datetime.now(timezone.utc) - timedelta(days=365)
ind_engine   = IndicatorEngine()
str_engine   = StrategyEngine()

print(f"\nRunning all 10 strategies on: {cfg.watchlist}\n")

reports = []
for symbol in cfg.watchlist:
    try:
        df      = manager.get_bars_df(symbol, "1Day", start=start)
        summary = ind_engine.analyze(symbol, df)
        report  = str_engine.evaluate(symbol, df, summary)
        reports.append(report)
        print(report)
    except Exception as e:
        print(f"  [ERROR] {symbol}: {e}\n")

# Final ranked table
print("\n" + "="*65)
print("  FINAL RECOMMENDATIONS  (ranked by conviction)")
print("="*65)
print(f"  {'Symbol':<8} {'Conviction':>10}  {'Rec':<12} {'Buys':>5} {'Sells':>6} {'Conf%':>6}")
print(f"  {'------':<8} {'----------':>10}  {'---':<12} {'----':>5} {'-----':>6} {'-----':>6}")

reports.sort(key=lambda r: r.conviction_score, reverse=True)
for r in reports:
    rec_arrow = "^^" if "BUY" in r.recommendation else \
                "vv" if "SELL" in r.recommendation else "--"
    print(f"  {r.symbol:<8} {r.conviction_score:>+10.2f}  "
          f"{rec_arrow} {r.recommendation:<10} "
          f"{r.buy_count:>5} {r.sell_count:>6} "
          f"{r.avg_confidence*100:>5.0f}%")

print("="*65)
print("\nLayer 3 complete. Ready for Layer 4 (Decision Engine)!\n")

manager.disconnect()
