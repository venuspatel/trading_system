# -*- coding: utf-8 -*-
"""
Base Strategy Interface
-----------------------
Every strategy must implement this contract.
The Strategy Engine runs all strategies and collects their TradeSignals.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
import pandas as pd


class TradeAction(Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeSignal:
    """Output of every strategy — consumed by Layer 4 Decision Engine."""
    strategy:    str
    symbol:      str
    timestamp:   datetime
    action:      TradeAction
    confidence:  float          # 0.0 to 1.0
    reason:      str
    confirmations: List[str]    = field(default_factory=list)  # what confirmed it
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None
    details:     Dict           = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.action != TradeAction.HOLD and self.confidence >= 0.5

    def __str__(self):
        conf_pct = f"{self.confidence*100:.0f}%"
        confs    = ", ".join(self.confirmations) if self.confirmations else "none"
        return (f"[{self.strategy}] {self.symbol} {self.action.value} "
                f"confidence={conf_pct} | {self.reason} | confirmed by: {confs}")


class StrategyRole:
    """
    Strategy roles — used to filter strategies per trading mode.
    
    TREND:         Buys rising trends, rides momentum.
                   Examples: Momentum, Breakout, TrendStrength, EarningsMomentum
                   Best modes: Profit Maximizer, Aggressive
    
    COUNTER_TREND: Buys dips, sells overbought conditions.
                   Examples: Mean Reversion, Fibonacci
                   Best modes: Balanced, Conservative, Long Term
                   BAD for: Profit Maximizer (cancels trend signals)
    
    NEUTRAL:       Works in any market condition.
                   Examples: Candlestick patterns, Volume, Divergence, MultiTimeframe
                   All modes: always active
    """
    TREND         = "Trend"
    COUNTER_TREND = "Counter-trend"
    NEUTRAL       = "Neutral"
    INTRADAY      = "Intraday"
    BOUNCE        = "Bounce"   # bounce setups within confirmed downtrends


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Each strategy takes a price DataFrame + indicator summary
    and returns a TradeSignal.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name, e.g. 'Momentum'"""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of what this strategy does."""

    @property
    def role(self) -> str:
        """
        Strategy role — controls which modes activate this strategy.
        Override in subclasses. Defaults to NEUTRAL (always active).
        """
        return StrategyRole.NEUTRAL

    @abstractmethod
    def generate_signal(
        self,
        symbol:  str,
        df:      pd.DataFrame,
        summary: "AnalysisSummary",        # from indicators.IndicatorEngine
    ) -> TradeSignal:
        """
        Analyse the DataFrame + indicator summary and return a TradeSignal.

        Args:
            symbol:  Ticker symbol
            df:      OHLCV DataFrame (from DataManager)
            summary: IndicatorEngine analysis summary (from Layer 2)

        Returns:
            TradeSignal with action BUY / SELL / HOLD
        """

    def _hold(self, symbol: str, df: pd.DataFrame, reason: str) -> TradeSignal:
        """Convenience: return a HOLD signal."""
        return TradeSignal(
            strategy  = self.name,
            symbol    = symbol,
            timestamp = df.index[-1].to_pydatetime(),
            action    = TradeAction.HOLD,
            confidence= 0.0,
            reason    = reason,
        )
