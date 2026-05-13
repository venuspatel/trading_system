# -*- coding: utf-8 -*-
"""
StrategyRanker — weights each strategy by its historical accuracy
------------------------------------------------------------------
Instead of all 12 strategies voting equally, each strategy's
conviction vote is multiplied by its win-rate accuracy on that symbol.

Example:
  EarningsMomentum: 80% accuracy on MARA → vote weight 1.6x
  Divergence:       35% accuracy on MARA → vote weight 0.7x

The weighted conviction score gives higher quality entries.
Recalculated after every 5 new completed trades.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

NEUTRAL_WEIGHT = 1.0   # default before any history exists
MIN_TRADES     = 3     # minimum trades to trust a strategy's weight


@dataclass
class StrategyWeight:
    strategy:    str
    symbol:      str
    trades:      int   = 0
    wins:        int   = 0
    weight:      float = NEUTRAL_WEIGHT
    win_rate:    float = 0.5

    def update(self, is_win: bool):
        self.trades += 1
        if is_win:
            self.wins += 1
        self.win_rate = self.wins / self.trades if self.trades else 0.5
        # Weight: 0.5 (bad) to 2.0 (excellent), neutral at 1.0 (50% win rate)
        # Formula: 2 * win_rate scales linearly: 0%→0.0, 50%→1.0, 100%→2.0
        if self.trades >= MIN_TRADES:
            self.weight = round(min(2.0, max(0.5, self.win_rate * 2)), 3)


class StrategyRanker:
    """
    Tracks per-strategy, per-symbol win rates from completed trades.
    Provides conviction vote multipliers for the decision engine.

    Usage:
        ranker = StrategyRanker()
        ranker.record_trade("MARA", "EarningsMomentum", is_win=True)
        weight = ranker.get_weight("MARA", "EarningsMomentum")  # 1.4 after wins
    """

    def __init__(self):
        # {(symbol, strategy): StrategyWeight}
        self._weights: Dict[tuple, StrategyWeight] = {}
        # Global strategy weights (across all symbols)
        self._global: Dict[str, StrategyWeight]    = {}

    def record_trade(self, symbol: str, strategy: str, is_win: bool):
        """Record the outcome of a trade for a strategy+symbol combination."""
        if not strategy:
            return
        key = (symbol.upper(), strategy)
        if key not in self._weights:
            self._weights[key] = StrategyWeight(strategy=strategy, symbol=symbol)
        self._weights[key].update(is_win)

        # Also update global weight for this strategy
        if strategy not in self._global:
            self._global[strategy] = StrategyWeight(strategy=strategy, symbol="*")
        self._global[strategy].update(is_win)

    def get_weight(self, symbol: str, strategy: str) -> float:
        """
        Return conviction multiplier for this strategy on this symbol.
        Falls back to global weight, then neutral 1.0.
        """
        key = (symbol.upper(), strategy)
        # Per-symbol weight takes priority if enough data
        if key in self._weights and self._weights[key].trades >= MIN_TRADES:
            return self._weights[key].weight
        # Fall back to global weight
        if strategy in self._global and self._global[strategy].trades >= MIN_TRADES:
            return self._global[strategy].weight
        return NEUTRAL_WEIGHT

    def learn_from_trades(self, trades: list):
        """
        Bulk-learn from completed trade history.
        trades: list of ClosedTrade objects
        """
        self._weights.clear()
        self._global.clear()
        for t in trades:
            if t.strategy:
                self.record_trade(t.symbol, t.strategy, t.pnl >= 0)
        logger.info(
            f"[StrategyRanker] Learned from {len(trades)} trades | "
            f"{len(self._global)} strategies tracked"
        )

    def top_strategies(self, n: int = 5) -> List[StrategyWeight]:
        """Return the top N strategies by global win rate."""
        ranked = sorted(
            [w for w in self._global.values() if w.trades >= MIN_TRADES],
            key=lambda w: w.win_rate, reverse=True
        )
        return ranked[:n]

    def bottom_strategies(self, n: int = 3) -> List[StrategyWeight]:
        """Return the worst N strategies by global win rate."""
        ranked = sorted(
            [w for w in self._global.values() if w.trades >= MIN_TRADES],
            key=lambda w: w.win_rate
        )
        return ranked[:n]

    def summary(self) -> dict:
        """Return a dict for dashboard display."""
        return {
            "total_tracked":  len(self._global),
            "top_strategies": [
                {"strategy": w.strategy, "win_rate": round(w.win_rate, 3),
                 "trades": w.trades, "weight": w.weight}
                for w in self.top_strategies()
            ],
            "bottom_strategies": [
                {"strategy": w.strategy, "win_rate": round(w.win_rate, 3),
                 "trades": w.trades, "weight": w.weight}
                for w in self.bottom_strategies()
            ],
        }
