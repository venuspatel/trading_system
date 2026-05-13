# -*- coding: utf-8 -*-
"""
StrategyRanker
--------------
Analyses real trade history to re-rank strategies by performance.
Updates the DecisionEngine's confidence weights so better-performing
strategies carry more weight in future decisions.

This is the "learning" part of the feedback loop — the agent
gets smarter over time based on what actually worked.

Re-ranking logic:
  - Strategies with win rate > 60% and profit factor > 1.5 → PROMOTED
  - Strategies with win rate < 40% or profit factor < 1.0 → DEMOTED
  - Strategies with < 5 trades → INSUFFICIENT DATA (keep default weight)

Weight range: 0.5 (demoted) to 2.0 (promoted), default 1.0
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum trades before we trust the stats
MIN_TRADES_FOR_RANKING = 5

# Weight bounds
WEIGHT_MIN     = 0.5
WEIGHT_DEFAULT = 1.0
WEIGHT_MAX     = 2.0


@dataclass
class StrategyRank:
    """Performance rank for one strategy."""
    name:          str
    trades:        int
    win_rate:      float
    profit_factor: float
    total_pnl:     float
    avg_pnl:       float
    weight:        float      # applied to confidence score in DecisionEngine
    status:        str        # PROMOTED | DEMOTED | NEUTRAL | INSUFFICIENT
    note:          str        = ""


class StrategyRanker:
    """
    Re-ranks all 10 strategies based on real trade history.
    Weights are saved to a JSON file and loaded by DecisionEngine
    at the start of each cycle.

    Usage:
        ranker  = StrategyRanker()
        ranks   = ranker.rank(trades)
        weights = ranker.get_weights()   # pass to DecisionEngine
    """

    def __init__(self, weights_path: str = "config/strategy_weights.json"):
        self.weights_path = weights_path
        self._weights: Dict[str, float] = {}
        self._ranks:   List[StrategyRank] = []
        os.makedirs(os.path.dirname(weights_path), exist_ok=True)
        self._load_weights()

    def rank(self, trades: List) -> List[StrategyRank]:
        """
        Analyse trade history and compute new strategy weights.
        Called by the feedback loop after each trading day.
        """
        # Group trades by strategy
        by_strategy: Dict[str, List] = {}
        for t in trades:
            strat = getattr(t, "strategy", "unknown") or "unknown"
            by_strategy.setdefault(strat, []).append(t)

        ranks = []
        for strat, strat_trades in by_strategy.items():
            winners  = [t for t in strat_trades if t.pnl > 0]
            losers   = [t for t in strat_trades if t.pnl <= 0]

            win_rate = len(winners) / len(strat_trades) if strat_trades else 0
            gross_p  = sum(t.pnl for t in winners)
            gross_l  = abs(sum(t.pnl for t in losers))
            pf       = gross_p / gross_l if gross_l > 0 else 0.0
            total    = sum(t.pnl for t in strat_trades)
            avg      = total / len(strat_trades)

            if len(strat_trades) < MIN_TRADES_FOR_RANKING:
                weight = WEIGHT_DEFAULT
                status = "INSUFFICIENT"
                note   = f"Only {len(strat_trades)} trades — need {MIN_TRADES_FOR_RANKING}"
            elif win_rate >= 0.60 and pf >= 1.5:
                weight = min(WEIGHT_DEFAULT + (win_rate - 0.5) * 2, WEIGHT_MAX)
                status = "PROMOTED"
                note   = f"Win rate {win_rate:.0%}, PF {pf:.1f} — increasing weight"
            elif win_rate < 0.40 or pf < 1.0:
                weight = max(WEIGHT_DEFAULT - (0.5 - win_rate) * 2, WEIGHT_MIN)
                status = "DEMOTED"
                note   = f"Win rate {win_rate:.0%}, PF {pf:.1f} — reducing weight"
            else:
                weight = WEIGHT_DEFAULT
                status = "NEUTRAL"
                note   = f"Win rate {win_rate:.0%}, PF {pf:.1f} — keeping default weight"

            weight = round(weight, 2)
            ranks.append(StrategyRank(
                name          = strat,
                trades        = len(strat_trades),
                win_rate      = round(win_rate, 3),
                profit_factor = round(pf, 2),
                total_pnl     = round(total, 2),
                avg_pnl       = round(avg, 2),
                weight        = weight,
                status        = status,
                note          = note,
            ))

        ranks.sort(key=lambda r: -r.total_pnl)
        self._ranks = ranks
        self._update_weights(ranks)

        logger.info(
            f"[StrategyRanker] Ranked {len(ranks)} strategies — "
            f"promoted: {sum(1 for r in ranks if r.status=='PROMOTED')} | "
            f"demoted: {sum(1 for r in ranks if r.status=='DEMOTED')}"
        )
        return ranks

    def get_weights(self) -> Dict[str, float]:
        """Return current strategy weights for the DecisionEngine."""
        return dict(self._weights)

    def print_rankings(self):
        """Print a formatted strategy ranking table."""
        if not self._ranks:
            print("No rankings yet — need trade history.")
            return

        print(f"\n{'='*65}")
        print(f"  STRATEGY RANKINGS")
        print(f"{'='*65}")
        print(f"  {'Strategy':<22} {'Trades':>6} {'Win%':>6} {'PF':>5} "
              f"{'P&L':>8} {'Weight':>7} Status")
        print(f"  {'-'*22} {'-'*6} {'-'*6} {'-'*5} {'-'*8} {'-'*7} ------")

        for r in self._ranks:
            status_icon = "^" if r.status == "PROMOTED" else \
                          "v" if r.status == "DEMOTED"  else \
                          "?" if r.status == "INSUFFICIENT" else "-"
            print(
                f"  {r.name:<22} {r.trades:>6} "
                f"{r.win_rate:>5.0%} {r.profit_factor:>5.1f} "
                f"${r.total_pnl:>7.0f} {r.weight:>7.2f}  "
                f"{status_icon} {r.status}"
            )
        print(f"{'='*65}\n")

    # ------------------------------------------------------------------

    def _update_weights(self, ranks: List[StrategyRank]):
        for r in ranks:
            self._weights[r.name] = r.weight
        self._save_weights()

    def _save_weights(self):
        try:
            data = {
                "updated_at": datetime.utcnow().isoformat(),
                "weights":    self._weights,
            }
            with open(self.weights_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.error(f"[StrategyRanker] Save failed: {exc}")

    def _load_weights(self):
        if not os.path.exists(self.weights_path):
            return
        try:
            with open(self.weights_path) as f:
                data = json.load(f)
            self._weights = data.get("weights", {})
            logger.info(f"[StrategyRanker] Loaded weights for {len(self._weights)} strategies")
        except Exception as exc:
            logger.warning(f"[StrategyRanker] Load failed: {exc}")
