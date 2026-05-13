# -*- coding: utf-8 -*-
"""
PositionSizer
-------------
Calculates the exact dollar amount and share quantity for each trade.
Three methods: Kelly Criterion, Fixed Fractional, Confidence-Scaled.
All methods respect the hard position and portfolio risk limits in AgentConfig.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

from .agent_config import AgentConfig, SizingMethod

logger = logging.getLogger(__name__)


@dataclass
class PositionSize:
    """Result of position sizing calculation."""
    symbol:          str
    price:           float
    shares:          int
    dollar_amount:   float
    pct_of_portfolio: float
    stop_loss:       float
    take_profit:     float
    max_loss:        float       # dollar loss if stop hit
    max_gain:        float       # dollar gain if TP hit
    risk_reward:     float
    sizing_method:   str
    reasoning:       str

    @property
    def is_valid(self) -> bool:
        return self.shares > 0 and self.risk_reward >= 1.5


class PositionSizer:
    """
    Calculates optimal position size for a trade given:
      - Current portfolio value
      - Entry price
      - Strategy confidence score
      - AgentConfig risk limits
    """

    def __init__(self, config: AgentConfig):
        self.config = config

    def calculate(
        self,
        symbol:         str,
        price:          float,
        confidence:     float,      # 0.0 to 1.0 from StrategyReport
        portfolio_value: float,
        current_risk:   float = 0.0, # existing portfolio risk already committed
        win_rate:       float = 0.55, # historical win rate for Kelly
        avg_win:        float = 0.06, # avg win % for Kelly
        avg_loss:       float = 0.03, # avg loss % for Kelly
    ) -> PositionSize:
        """
        Calculate position size using the configured method.

        Args:
            symbol:          Ticker
            price:           Current price per share
            confidence:      Strategy confidence (0-1)
            portfolio_value: Total portfolio value in dollars
            current_risk:    Dollars already at risk in open positions
            win_rate:        Historical win rate (for Kelly)
            avg_win:         Average win % (for Kelly)
            avg_loss:        Average loss % (for Kelly)

        Returns:
            PositionSize with shares, stops, and reasoning
        """
        cfg = self.config

        # Hard caps
        max_dollar    = portfolio_value * cfg.max_position_pct
        remaining_risk = (portfolio_value * cfg.max_portfolio_risk_pct) - current_risk
        stop_price    = round(price * (1 - cfg.stop_loss_pct), 2)
        tp_price      = round(price * (1 + cfg.take_profit_pct), 2)
        risk_per_share = price - stop_price
        rr             = (tp_price - price) / risk_per_share if risk_per_share > 0 else 0

        # Choose sizing method
        if cfg.sizing_method == SizingMethod.KELLY:
            dollar_amount, reasoning = self._kelly(
                portfolio_value, win_rate, avg_win, avg_loss,
                cfg.kelly_fraction, max_dollar
            )
        elif cfg.sizing_method == SizingMethod.CONFIDENCE:
            dollar_amount, reasoning = self._confidence_scaled(
                portfolio_value, confidence, max_dollar
            )
        else:
            dollar_amount, reasoning = self._fixed_fractional(
                portfolio_value, max_dollar
            )

        # Never risk more than remaining portfolio risk budget
        max_by_risk   = (remaining_risk / cfg.stop_loss_pct) if cfg.stop_loss_pct > 0 else dollar_amount
        dollar_amount  = min(dollar_amount, max_by_risk, max_dollar)
        dollar_amount  = max(dollar_amount, 0)

        shares        = math.floor(dollar_amount / price) if price > 0 else 0
        actual_dollars = shares * price
        pct_portfolio  = actual_dollars / portfolio_value if portfolio_value > 0 else 0
        max_loss       = shares * risk_per_share
        max_gain       = shares * (tp_price - price)

        if shares == 0:
            reasoning += " | Position too small after risk limits applied — skipping"

        logger.info(
            f"[PositionSizer] {symbol}: {shares} shares @ ${price:.2f} = "
            f"${actual_dollars:,.0f} ({pct_portfolio:.1%} of portfolio) | "
            f"stop=${stop_price:.2f} tp=${tp_price:.2f} | {reasoning}"
        )

        return PositionSize(
            symbol           = symbol,
            price            = price,
            shares           = shares,
            dollar_amount    = round(actual_dollars, 2),
            pct_of_portfolio = round(pct_portfolio, 4),
            stop_loss        = stop_price,
            take_profit      = tp_price,
            max_loss         = round(max_loss, 2),
            max_gain         = round(max_gain, 2),
            risk_reward      = round(rr, 2),
            sizing_method    = (cfg.sizing_method.value if hasattr(cfg.sizing_method, "value") else cfg.sizing_method),
            reasoning        = reasoning,
        )

    def _kelly(self, portfolio, win_rate, avg_win, avg_loss,
               fraction, max_dollar):
        """Half-Kelly criterion: f = fraction * (p*b - q) / b"""
        b = avg_win / avg_loss if avg_loss > 0 else 1
        q = 1 - win_rate
        f = fraction * (win_rate * b - q) / b
        f = max(0.0, min(f, 0.25))    # cap at 25% of portfolio
        dollar = min(portfolio * f, max_dollar)
        return dollar, f"Kelly f={f:.2%} (win={win_rate:.0%} b={b:.1f})"

    def _confidence_scaled(self, portfolio, confidence, max_dollar):
        """Scale position size linearly with strategy confidence."""
        scale  = max(0.0, min(confidence, 1.0))
        dollar = min(portfolio * self.config.max_position_pct * scale, max_dollar)
        return dollar, f"Confidence-scaled: {scale:.0%} of max position"

    def _fixed_fractional(self, portfolio, max_dollar):
        """Always use the same fixed % of portfolio."""
        dollar = min(portfolio * self.config.max_position_pct, max_dollar)
        return dollar, f"Fixed fractional: {self.config.max_position_pct:.0%} of portfolio"
