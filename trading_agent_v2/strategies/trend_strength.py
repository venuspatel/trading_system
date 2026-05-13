# -*- coding: utf-8 -*-
"""
TrendStrengthStrategy — catches multi-week momentum moves like AMD +31%
------------------------------------------------------------------------
Combines ADX trend strength + MA alignment + weekly momentum.
Would have caught AMD's 31% month run and TSLA's big moves.
"""

import pandas as pd
import numpy as np
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole
from indicators.adx import ADXIndicator


class TrendStrengthStrategy(BaseStrategy):

    def __init__(self, adx_threshold=25.0, ma_fast=20, ma_slow=50,
                 momentum_bars=10, momentum_min=0.05):
        self.adx_threshold  = adx_threshold
        self.ma_fast        = ma_fast
        self.ma_slow        = ma_slow
        self.momentum_bars  = momentum_bars
        self.momentum_min   = momentum_min
        self._adx           = ADXIndicator(period=14)

    @property
    def name(self) -> str:
        return "TrendStrength"

    @property
    def description(self) -> str:
        return "Catches multi-week momentum moves via ADX + MA alignment + 10-bar momentum"

    @property
    def role(self) -> str:
        return StrategyRole.TREND

    def generate_signal(self, symbol: str, df: pd.DataFrame, summary) -> TradeSignal:
        min_bars = self.ma_slow + self.momentum_bars + 5
        if len(df) < min_bars:
            return self._hold(symbol, df, "Insufficient data for trend analysis")

        close = df["close"].astype(float)
        price = float(close.iloc[-1])

        # ADX trend strength
        adx_data = self._adx.latest(df)
        adx_val  = adx_data["adx"]
        adx_dir  = adx_data["direction"]

        # Moving averages
        ma_fast_val = float(close.rolling(self.ma_fast).mean().iloc[-1])
        ma_slow_val = float(close.rolling(self.ma_slow).mean().iloc[-1])
        above_fast  = price > ma_fast_val
        above_slow  = price > ma_slow_val
        ma_aligned  = ma_fast_val > ma_slow_val

        # 10-bar (2-week) momentum
        momentum_pct = (price - float(close.iloc[-self.momentum_bars])) / float(close.iloc[-self.momentum_bars])

        # BUY: strong trend + price above both MAs + solid momentum
        if (adx_val >= self.adx_threshold and adx_dir == "UP"
                and above_fast and above_slow and ma_aligned
                and momentum_pct >= self.momentum_min):

            confidence = min(0.93, 0.62 + (adx_val - self.adx_threshold) / 60)
            if adx_val >= 40 and momentum_pct >= 0.10:
                # AMD-style strong trend
                reason = (f"STRONG TREND: ADX={adx_val:.0f} · "
                          f"{momentum_pct*100:.1f}% gain over {self.momentum_bars} bars · "
                          f"Price {((price/ma_slow_val-1)*100):.1f}% above 50MA")
                confidence = min(0.95, confidence + 0.08)
            else:
                reason = (f"Trend: ADX={adx_val:.0f} · MA aligned · "
                          f"{momentum_pct*100:.1f}% momentum")

            return TradeSignal(
                symbol=symbol, strategy=self.name,
                action=TradeAction.BUY,
                confidence=confidence,
                price=price,
                timestamp=df.index[-1].to_pydatetime(),
                reason=reason,
                details={"adx": adx_val, "momentum_pct": round(momentum_pct*100,2),
                         "trend_strength": adx_data["trend_strength"]},
            )

        # SELL: trend turning down
        if adx_val >= 20 and adx_dir == "DOWN" and not above_fast:
            return TradeSignal(
                symbol=symbol, strategy=self.name,
                action=TradeAction.SELL,
                confidence=0.65,
                price=price,
                timestamp=df.index[-1].to_pydatetime(),
                reason=f"Trend weakening: ADX={adx_val:.0f} turned DOWN · below fast MA",
            )

        reasons = []
        if adx_val < self.adx_threshold:
            reasons.append(f"ADX={adx_val:.0f} < {self.adx_threshold}")
        if not (above_fast and above_slow):
            reasons.append("Price below MAs")
        if momentum_pct < self.momentum_min:
            reasons.append(f"Momentum {momentum_pct*100:.1f}% < {self.momentum_min*100:.0f}%")

        return self._hold(symbol, df, " · ".join(reasons) or "No strong trend")
