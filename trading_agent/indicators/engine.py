# -*- coding: utf-8 -*-
"""
IndicatorEngine
----------------
Runs all indicators on a symbol's DataFrame and returns a combined
summary that the Strategy Engine (Layer 3) consumes.

Usage:
    engine = IndicatorEngine()
    summary = engine.analyze("AAPL", df)
    print(summary)                   # human-readable
    print(summary.combined_signal)   # BUY / SELL / NEUTRAL
    print(summary.score)             # -6 to +6
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from .base import Signal, SignalDirection, SignalStrength
from .rsi               import rsi_signal
from .macd              import macd_signal
from .bollinger         import bollinger_signal
from .moving_averages   import moving_average_signal
from .candlestick       import candlestick_signal
from .support_resistance import support_resistance_signal

logger = logging.getLogger(__name__)


@dataclass
class AnalysisSummary:
    """
    Full indicator analysis result for one symbol at one moment.
    This is what Layer 3 (Strategy Engine) reads.
    """
    symbol:    str
    timestamp: datetime
    signals:   Dict[str, Signal]   = field(default_factory=dict)
    errors:    Dict[str, str]      = field(default_factory=dict)

    @property
    def score(self) -> float:
        """
        Aggregate signal score from -6 (strong sell) to +6 (strong buy).
        Each indicator contributes based on direction and strength:
          STRONG  = +/-2
          MODERATE = +/-1
          WEAK    = +/-0.5
        """
        weights = {
            SignalStrength.STRONG:   2.0,
            SignalStrength.MODERATE: 1.0,
            SignalStrength.WEAK:     0.5,
            SignalStrength.NONE:     0.0,
        }
        total = 0.0
        for sig in self.signals.values():
            w = weights[sig.strength]
            if sig.direction == SignalDirection.BUY:
                total += w
            elif sig.direction == SignalDirection.SELL:
                total -= w
        return round(total, 2)

    @property
    def combined_signal(self) -> SignalDirection:
        """Overall direction based on score threshold."""
        s = self.score
        if s >= 2.0:
            return SignalDirection.BUY
        elif s <= -2.0:
            return SignalDirection.SELL
        return SignalDirection.NEUTRAL

    @property
    def combined_strength(self) -> SignalStrength:
        s = abs(self.score)
        if s >= 4.0:
            return SignalStrength.STRONG
        elif s >= 2.0:
            return SignalStrength.MODERATE
        elif s >= 1.0:
            return SignalStrength.WEAK
        return SignalStrength.NONE

    @property
    def buy_count(self) -> int:
        return sum(1 for s in self.signals.values()
                   if s.direction == SignalDirection.BUY)

    @property
    def sell_count(self) -> int:
        return sum(1 for s in self.signals.values()
                   if s.direction == SignalDirection.SELL)

    def __str__(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"  ANALYSIS: {self.symbol}  |  {self.timestamp.strftime('%Y-%m-%d %H:%M')}",
            f"{'='*60}",
        ]
        for name, sig in self.signals.items():
            arrow = "^" if sig.direction == SignalDirection.BUY else \
                    "v" if sig.direction == SignalDirection.SELL else "-"
            lines.append(f"  {arrow} [{sig.indicator:6s}] {sig.reason}")
        if self.errors:
            for name, err in self.errors.items():
                lines.append(f"  ! [{name:6s}] Error: {err}")
        lines += [
            f"{'─'*60}",
            f"  Score: {self.score:+.1f}  |  "
            f"Buys: {self.buy_count}  Sells: {self.sell_count}  |  "
            f"Signal: {self.combined_signal.value} ({self.combined_strength.name})",
            f"{'='*60}\n",
        ]
        return "\n".join(lines)


class IndicatorEngine:
    """
    Runs all indicators against a price DataFrame and returns an AnalysisSummary.

    Example:
        from data_layer import AlpacaProvider, DataManager
        from indicators import IndicatorEngine

        manager = DataManager(AlpacaProvider(...))
        manager.connect()
        df = manager.get_bars_df("AAPL", "1Day",
                                 start=datetime(2023, 1, 1, tzinfo=timezone.utc))

        engine  = IndicatorEngine()
        summary = engine.analyze("AAPL", df)
        print(summary)
    """

    def __init__(
        self,
        use_rsi:    bool = True,
        use_macd:   bool = True,
        use_bb:     bool = True,
        use_ma:     bool = True,
        use_candle: bool = True,
        use_sr:     bool = True,
    ):
        self._use = {
            "RSI":    use_rsi,
            "MACD":   use_macd,
            "BB":     use_bb,
            "MA":     use_ma,
            "CANDLE": use_candle,
            "SR":     use_sr,
        }

    def analyze(self, symbol: str, df: pd.DataFrame) -> AnalysisSummary:
        """
        Run all enabled indicators on df and return an AnalysisSummary.

        Args:
            symbol: Ticker symbol (used for labelling)
            df:     OHLCV DataFrame from DataManager.get_bars_df()

        Returns:
            AnalysisSummary with all signals and combined score
        """
        timestamp = df.index[-1].to_pydatetime() if len(df) > 0 else datetime.utcnow()
        summary   = AnalysisSummary(symbol=symbol, timestamp=timestamp)

        runners = {
            "RSI":    lambda: rsi_signal(symbol, df),
            "MACD":   lambda: macd_signal(symbol, df),
            "BB":     lambda: bollinger_signal(symbol, df),
            "MA":     lambda: moving_average_signal(symbol, df),
            "CANDLE": lambda: candlestick_signal(symbol, df),
            "SR":     lambda: support_resistance_signal(symbol, df),
        }

        for name, fn in runners.items():
            if not self._use.get(name, True):
                continue
            try:
                summary.signals[name] = fn()
            except Exception as exc:
                summary.errors[name] = str(exc)
                logger.warning(f"[IndicatorEngine] {name} failed for {symbol}: {exc}")

        logger.debug(f"[IndicatorEngine] {symbol} score={summary.score:+.1f} "
                     f"signal={summary.combined_signal.value}")
        return summary
