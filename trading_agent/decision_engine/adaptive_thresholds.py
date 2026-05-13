# -*- coding: utf-8 -*-
"""
AdaptiveThresholdEngine — Phase 3 intelligence
------------------------------------------------
Analyses completed trade history to learn which conviction levels,
strategies and market conditions actually predict wins vs losses.
Auto-adjusts entry thresholds toward what the market proved works.

Called after every 5 completed trades to update thresholds.

Key outputs:
  - conviction_floor:  minimum conviction score to enter (replaces fixed config value)
  - strategy_weights:  multipliers per strategy based on historical accuracy
  - regime_bias:       which regimes produce the best outcomes for this portfolio
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ThresholdRecommendation:
    """Output of adaptive analysis — new recommended thresholds."""
    conviction_floor:   float          = 2.5    # min conviction to enter
    min_strategies:     int            = 2      # min strategies to agree
    strategy_weights:   Dict[str, float] = field(default_factory=dict)
    regime_bias:        Dict[str, float] = field(default_factory=dict)
    confidence:         float          = 0.0    # 0-1 how confident in recommendation
    based_on_trades:    int            = 0
    summary:            str            = ""


class AdaptiveThresholdEngine:
    """
    Learns from completed trades to improve entry quality over time.

    Usage:
        engine = AdaptiveThresholdEngine()
        rec = engine.analyse(completed_trades)
        if rec.confidence > 0.5:
            config.min_conviction_score = rec.conviction_floor
    """

    MIN_TRADES_FOR_LEARNING = 10    # need at least 10 trades to make recommendations
    UPDATE_EVERY_N_TRADES   = 5     # re-analyse every 5 new trades

    def __init__(self):
        self._last_analysed_count = 0
        self._current_rec: Optional[ThresholdRecommendation] = None

    def should_update(self, trade_count: int) -> bool:
        """Return True if we have enough new trades to re-analyse."""
        return (
            trade_count >= self.MIN_TRADES_FOR_LEARNING and
            trade_count - self._last_analysed_count >= self.UPDATE_EVERY_N_TRADES
        )

    def analyse(self, trades: list) -> ThresholdRecommendation:
        """
        Analyse completed trades and return recommended thresholds.
        trades: list of ClosedTrade objects
        """
        if len(trades) < self.MIN_TRADES_FOR_LEARNING:
            return ThresholdRecommendation(
                summary=f"Need {self.MIN_TRADES_FOR_LEARNING - len(trades)} more trades to learn"
            )

        self._last_analysed_count = len(trades)
        rec = ThresholdRecommendation(based_on_trades=len(trades))

        wins   = [t for t in trades if t.pnl >= 0]
        losses = [t for t in trades if t.pnl <  0]
        win_rate = len(wins) / len(trades)

        # ── 1. Conviction floor analysis ─────────────────────────────
        # What's the average P&L at each conviction bucket?
        # Group trades into conviction buckets and find the floor where wins dominate
        # Since we don't store entry conviction per trade yet, we use exit_reason
        # as a proxy: "Take profit" = high conviction worked, "Trailing stop" = conviction wrong

        tp_exits   = [t for t in trades if "Take profit" in (t.exit_reason or "")]
        stop_exits = [t for t in trades if "stop" in (t.exit_reason or "").lower()]
        mom_exits  = [t for t in trades if "Momentum" in (t.exit_reason or "")]

        # Take profit exits are the cleanest wins — these are conviction working
        # If TP rate is high, conviction threshold is well calibrated
        tp_rate = len(tp_exits) / len(trades) if trades else 0

        # Adjust conviction floor based on win rate
        if win_rate >= 0.70:
            # Winning well — can slightly relax conviction to get more trades
            rec.conviction_floor = 2.0
            rec.min_strategies   = 2
        elif win_rate >= 0.60:
            # Doing well — keep current threshold
            rec.conviction_floor = 2.5
            rec.min_strategies   = 2
        elif win_rate >= 0.50:
            # Break-even — tighten slightly
            rec.conviction_floor = 3.0
            rec.min_strategies   = 3
        else:
            # Losing — tighten significantly
            rec.conviction_floor = 3.5
            rec.min_strategies   = 3

        # ── 2. Exit reason performance breakdown ─────────────────────
        exit_stats = {}
        for exit_type, trade_group in [
            ("take_profit", tp_exits),
            ("trailing_stop", stop_exits),
            ("momentum_exit", mom_exits),
        ]:
            if trade_group:
                group_wins = [t for t in trade_group if t.pnl >= 0]
                exit_stats[exit_type] = {
                    "count":    len(trade_group),
                    "win_rate": len(group_wins) / len(trade_group),
                    "avg_pnl":  sum(t.pnl for t in trade_group) / len(trade_group),
                }

        # ── 3. Per-symbol performance ─────────────────────────────────
        symbol_stats: Dict[str, dict] = {}
        for t in trades:
            sym = t.symbol
            if sym not in symbol_stats:
                symbol_stats[sym] = {"wins": 0, "losses": 0, "pnl": 0.0}
            if t.pnl >= 0:
                symbol_stats[sym]["wins"] += 1
            else:
                symbol_stats[sym]["losses"] += 1
            symbol_stats[sym]["pnl"] += t.pnl

        # Symbols with 100% win rate get a boost, consistent losers get penalised
        rec.strategy_weights = {}
        for sym, stats in symbol_stats.items():
            total = stats["wins"] + stats["losses"]
            if total >= 2:
                sym_win_rate = stats["wins"] / total
                if sym_win_rate >= 0.75:
                    rec.strategy_weights[sym] = 1.2   # boost
                elif sym_win_rate <= 0.33:
                    rec.strategy_weights[sym] = 0.7   # penalise

        # ── 4. Confidence score ───────────────────────────────────────
        # More trades = higher confidence. Cap at 1.0 at 50 trades.
        rec.confidence = min(1.0, len(trades) / 50)

        # ── 5. Summary message ────────────────────────────────────────
        best_exit = max(exit_stats.items(), key=lambda x: x[1]["win_rate"], default=None)
        worst_sym = min(symbol_stats.items(),
                        key=lambda x: x[1]["pnl"] if (x[1]["wins"]+x[1]["losses"])>=2 else 0,
                        default=None)
        rec.summary = (
            f"Win rate {win_rate:.0%} over {len(trades)} trades → "
            f"conviction floor {rec.conviction_floor} | "
            f"min strategies {rec.min_strategies}"
        )
        if best_exit:
            rec.summary += f" | Best exit: {best_exit[0]} ({best_exit[1]['win_rate']:.0%})"
        if worst_sym and worst_sym[1]["pnl"] < -5:
            rec.summary += f" | Watch: {worst_sym[0]} ({worst_sym[1]['pnl']:+.2f})"

        self._current_rec = rec
        logger.info(f"[Adaptive] {rec.summary}")
        return rec

    def get_current(self) -> Optional[ThresholdRecommendation]:
        return self._current_rec
