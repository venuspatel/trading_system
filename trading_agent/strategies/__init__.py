# -*- coding: utf-8 -*-
"""strategies — public API"""

from .base              import BaseStrategy, TradeSignal, TradeAction
from .engine            import StrategyEngine, StrategyReport
from .momentum          import MomentumStrategy
from .mean_reversion    import MeanReversionStrategy
from .breakout          import BreakoutStrategy
from .candle_reversal   import CandleReversalStrategy
from .advanced_strategies import (
    CandleContinuationStrategy,
    DivergenceStrategy,
    FibonacciStrategy,
    VolumeConfirmationStrategy,
    MultiTimeframeStrategy,
    TrendRegimeStrategy,
)

__all__ = [
    "BaseStrategy", "TradeSignal", "TradeAction",
    "StrategyEngine", "StrategyReport",
    "MomentumStrategy", "MeanReversionStrategy", "BreakoutStrategy",
    "CandleReversalStrategy", "CandleContinuationStrategy",
    "DivergenceStrategy", "FibonacciStrategy",
    "VolumeConfirmationStrategy", "MultiTimeframeStrategy",
    "TrendRegimeStrategy",
]

from .trend_strength    import TrendStrengthStrategy
from .earnings_momentum import EarningsMomentumStrategy
