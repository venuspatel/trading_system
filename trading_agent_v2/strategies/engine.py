# -*- coding: utf-8 -*-
"""
StrategyEngine
--------------
Runs all 10 strategies against a symbol, collects TradeSignals,
and produces a StrategyReport showing which strategies agree,
the combined conviction score, and the final recommendation.

This is what Layer 4 (Decision Engine) reads.

Usage:
    engine   = IndicatorEngine()
    strategy = StrategyEngine()

    summary = engine.analyze("AAPL", df)
    report  = strategy.evaluate("AAPL", df, summary)
    print(report)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole
from .momentum            import MomentumStrategy
from .mean_reversion      import MeanReversionStrategy
from .breakout            import BreakoutStrategy
from .candle_reversal     import CandleReversalStrategy
from .trend_strength    import TrendStrengthStrategy
from .earnings_momentum import EarningsMomentumStrategy
from .intraday_vwap            import IntradayVWAPStrategy
from .opening_range_breakout   import OpeningRangeBreakoutStrategy
from .micro_momentum           import MicroMomentumStrategy
from .advanced_strategies import (
    CandleContinuationStrategy,
    DivergenceStrategy,
    FibonacciStrategy,
    VolumeConfirmationStrategy,
    MultiTimeframeStrategy,
    TrendRegimeStrategy,
)

logger = logging.getLogger(__name__)


@dataclass
class StrategyReport:
    """
    Full strategy evaluation for one symbol.
    Consumed by Layer 4 (Decision Engine).
    """
    symbol:    str
    timestamp: datetime
    signals:   List[TradeSignal]  = field(default_factory=list)
    errors:    Dict[str, str]     = field(default_factory=dict)

    @property
    def buy_signals(self) -> List[TradeSignal]:
        return [s for s in self.signals if s.action == TradeAction.BUY]

    @property
    def sell_signals(self) -> List[TradeSignal]:
        return [s for s in self.signals if s.action == TradeAction.SELL]

    @property
    def buy_count(self) -> int:
        return len(self.buy_signals)

    @property
    def sell_count(self) -> int:
        return len(self.sell_signals)

    @property
    def conviction_score(self) -> float:
        """
        Weighted conviction score: -10 to +10
        Each strategy contributes +/- its confidence score.
        """
        score = 0.0
        for sig in self.signals:
            if sig.action == TradeAction.BUY:
                score += sig.confidence
            elif sig.action == TradeAction.SELL:
                score -= sig.confidence
        return round(score, 3)

    @property
    def recommendation(self) -> str:
        score = self.conviction_score
        buys  = self.buy_count
        sells = self.sell_count

        if score >= 3.0 and buys >= 4:
            return "STRONG BUY"
        elif score >= 1.5 and buys >= 2:
            return "BUY"
        elif score <= -3.0 and sells >= 4:
            return "STRONG SELL"
        elif score <= -1.5 and sells >= 2:
            return "SELL"
        else:
            return "HOLD"

    @property
    def avg_confidence(self) -> float:
        actionable = [s for s in self.signals if s.action != TradeAction.HOLD]
        if not actionable:
            return 0.0
        return round(sum(s.confidence for s in actionable) / len(actionable), 3)

    @property
    def best_stop_loss(self) -> Optional[float]:
        """Most conservative stop loss from all BUY signals."""
        stops = [s.stop_loss for s in self.buy_signals if s.stop_loss]
        return max(stops) if stops else None   # highest stop = closest to price = safest

    @property
    def best_take_profit(self) -> Optional[float]:
        """Most conservative take profit from all BUY signals."""
        tps = [s.take_profit for s in self.buy_signals if s.take_profit]
        return min(tps) if tps else None

    def __str__(self) -> str:
        sep  = "=" * 65
        dash = "-" * 65
        lines = [
            f"\n{sep}",
            f"  STRATEGY REPORT: {self.symbol}  |  {self.timestamp.strftime('%Y-%m-%d %H:%M')}",
            sep,
        ]

        if self.buy_signals:
            lines.append("  BUY signals:")
            for s in sorted(self.buy_signals, key=lambda x: -x.confidence):
                confs = ", ".join(s.confirmations[:3])
                lines.append(f"    ^ [{s.strategy:<20}] {s.confidence*100:.0f}%  {s.reason[:50]}")
                if confs:
                    lines.append(f"       confirmed by: {confs}")

        if self.sell_signals:
            lines.append("  SELL signals:")
            for s in sorted(self.sell_signals, key=lambda x: -x.confidence):
                confs = ", ".join(s.confirmations[:3])
                lines.append(f"    v [{s.strategy:<20}] {s.confidence*100:.0f}%  {s.reason[:50]}")
                if confs:
                    lines.append(f"       confirmed by: {confs}")

        hold_names = [s.strategy for s in self.signals if s.action == TradeAction.HOLD]
        if hold_names:
            lines.append(f"  HOLD: {', '.join(hold_names)}")

        if self.errors:
            for name, err in self.errors.items():
                lines.append(f"  ! [{name}] Error: {err}")

        lines += [
            dash,
            f"  Conviction: {self.conviction_score:+.2f}  |  "
            f"Buys: {self.buy_count}  Sells: {self.sell_count}  |  "
            f"Avg confidence: {self.avg_confidence*100:.0f}%",
        ]

        if self.best_stop_loss:
            lines.append(f"  Stop loss: ${self.best_stop_loss:.2f}  |  "
                         f"Take profit: ${self.best_take_profit:.2f}" if self.best_take_profit
                         else f"  Stop loss: ${self.best_stop_loss:.2f}")

        lines += [
            f"\n  >> RECOMMENDATION: {self.recommendation}",
            sep + "\n",
        ]
        return "\n".join(lines)


class StrategyEngine:
    """
    Runs all 10 strategies and returns a StrategyReport.

    Example:
        from indicators import IndicatorEngine
        from strategies import StrategyEngine

        ind_engine  = IndicatorEngine()
        str_engine  = StrategyEngine()

        summary = ind_engine.analyze("AAPL", df)
        report  = str_engine.evaluate("AAPL", df, summary)
        print(report)
    """

    # Roles allowed per trading mode
    MODE_ROLES = {
        "Conservative":     {StrategyRole.COUNTER_TREND, StrategyRole.NEUTRAL, StrategyRole.TREND},
        "Balanced":         {StrategyRole.COUNTER_TREND, StrategyRole.NEUTRAL, StrategyRole.TREND},
                "Profit Maximizer": {StrategyRole.NEUTRAL, StrategyRole.TREND, StrategyRole.INTRADAY},
        "Micro Momentum":  {StrategyRole.INTRADAY},  # scalp only — fast in/out
        "Aggressive":       {StrategyRole.NEUTRAL, StrategyRole.TREND, StrategyRole.INTRADAY},
        "Long Term":        {StrategyRole.COUNTER_TREND, StrategyRole.NEUTRAL, StrategyRole.TREND},
    }

    def __init__(self, approach: str = "Balanced"):
        self._approach = approach
        self._all_strategies: List[BaseStrategy] = [
            MomentumStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
            CandleReversalStrategy(),
            CandleContinuationStrategy(),
            DivergenceStrategy(),
            FibonacciStrategy(),
            VolumeConfirmationStrategy(),
            MultiTimeframeStrategy(),
            TrendRegimeStrategy(),
            TrendStrengthStrategy(),
            EarningsMomentumStrategy(),
            IntradayVWAPStrategy(),
            OpeningRangeBreakoutStrategy(),
            MicroMomentumStrategy(),
        ]

    @property
    def _strategies(self) -> List[BaseStrategy]:
        """Return only strategies allowed for current mode."""
        allowed = self.MODE_ROLES.get(self._approach,
                  {StrategyRole.NEUTRAL, StrategyRole.TREND, StrategyRole.COUNTER_TREND})
        active = [s for s in self._all_strategies if s.role in allowed]
        return active

    def set_approach(self, approach: str):
        """Update the trading mode — filters strategies accordingly."""
        self._approach = approach
        active = self._strategies
        logger.info(
            f"[StrategyEngine] Mode={approach} | "
            f"Active strategies: {[s.name for s in active]} | "
            f"Filtered out: {[s.name for s in self._all_strategies if s not in active]}"
        )

    @property
    def strategy_names(self) -> List[str]:
        return [s.name for s in self._strategies]

    def evaluate(
        self,
        symbol:  str,
        df:      pd.DataFrame,
        summary: "AnalysisSummary",
    ) -> StrategyReport:
        """
        Run all strategies and return a consolidated StrategyReport.

        Args:
            symbol:  Ticker symbol
            df:      OHLCV DataFrame from DataManager
            summary: IndicatorEngine AnalysisSummary from Layer 2

        Returns:
            StrategyReport with all signals + recommendation
        """
        timestamp = df.index[-1].to_pydatetime() if len(df) > 0 else datetime.utcnow()
        report    = StrategyReport(symbol=symbol, timestamp=timestamp)

        for strategy in self._strategies:
            try:
                signal = strategy.generate_signal(symbol, df, summary)
                report.signals.append(signal)
            except Exception as exc:
                report.errors[strategy.name] = str(exc)
                logger.warning(f"[StrategyEngine] {strategy.name} failed for {symbol}: {exc}")

        logger.info(
            f"[StrategyEngine] {symbol} | "
            f"conviction={report.conviction_score:+.2f} | "
            f"rec={report.recommendation} | "
            f"buys={report.buy_count} sells={report.sell_count}"
        )
        return report
