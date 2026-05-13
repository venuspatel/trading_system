# -*- coding: utf-8 -*-
"""
Layer 6 quickstart — Performance & Feedback Loop
--------------------------------------------------
Run from inside the trading_agent folder:
    python3 examples/layer6_quickstart.py

What this does:
  1. Loads your trade history from logs/portfolio.json
  2. Calculates all performance metrics (Sharpe, win rate, drawdown etc)
  3. Re-ranks all 10 strategies based on real results
  4. Generates a full daily report with recommendations
  5. Saves updated strategy weights to config/strategy_weights.json

If you have no trades yet (paper trading just started), it will
show placeholder metrics and explain what to expect.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timezone

from config import cfg as app_cfg
from decision_engine import AgentConfig
from execution import AlpacaExecutor, PortfolioTracker
from performance import PerformanceAnalyzer, StrategyRanker, DailyReportGenerator
from decision_engine.decision_logger import DecisionLogger

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

print("\n" + "="*60)
print("  TRADING AGENT — Layer 6: Performance & Feedback Loop")
print("="*60)

# ── Load config ───────────────────────────────────────────────
config = AgentConfig()
config.apply_balanced()

# ── Connect executor for live account data ────────────────────
executor = AlpacaExecutor(
    api_key    = app_cfg.alpaca_api_key,
    secret_key = app_cfg.alpaca_secret_key,
    paper      = True,
)
executor.connect()
acct = executor.get_account()

print(f"\nAccount: ${acct.get('portfolio_value', 0):,.2f} | "
      f"Daily P&L: ${acct.get('daily_pnl', 0):+,.2f}")

# ── Load historical data ──────────────────────────────────────
portfolio = PortfolioTracker()
d_logger  = DecisionLogger(config.log_path)
trades    = portfolio._trades
snaps     = portfolio._snapshots

print(f"Trades loaded:    {len(trades)}")
print(f"Snapshots loaded: {len(snaps)}")

# ── Performance analysis ──────────────────────────────────────
analyzer = PerformanceAnalyzer()
report   = analyzer.analyze(
    trades, snaps,
    starting_value = portfolio._starting_value or 100000
)
print(report)

# ── Strategy ranking ──────────────────────────────────────────
ranker = StrategyRanker()
if trades:
    ranks = ranker.rank(trades)
    ranker.print_rankings()
    print(f"Strategy weights saved to: config/strategy_weights.json\n")
else:
    print("No trades yet — strategy rankings will appear after first completed trades.")
    print("Weights remain at default (1.0) for all strategies.\n")

# ── Daily report ──────────────────────────────────────────────
reporter = DailyReportGenerator()
daily    = reporter.generate(
    decision_logger      = d_logger,
    portfolio_tracker    = portfolio,
    performance_analyzer = analyzer,
    strategy_ranker      = ranker,
    executor             = executor,
    config               = config,
)
print(daily.to_text())

today = datetime.now(timezone.utc).date().isoformat()
print(f"Report saved to:")
print(f"  logs/reports/{today}.json")
print(f"  logs/reports/{today}.txt")
print(f"\nLayer 6 complete. Ready for Layer 7 (Web Dashboard)!\n")

executor.disconnect()
