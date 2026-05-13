# -*- coding: utf-8 -*-
"""
Strategy 3: Breakout
---------------------
Detects when price breaks through key support/resistance
with volume confirmation — signals the start of a new move.

Entry BUY:
  - Price breaks above resistance level
  - Volume >= 1.5x average (confirms institutional participation)
  - Bollinger squeeze was detected (energy buildup before break)

Entry SELL:
  - Price breaks below support level
  - Volume confirms the breakdown
"""

import pandas as pd
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole


class BreakoutStrategy(BaseStrategy):

    def __init__(self, volume_factor=1.5, proximity=0.015):
        self.volume_factor = volume_factor
        self.proximity     = proximity     # within 1.5% of level = near it

    @property
    def name(self) -> str:
        return "Breakout"

    @property
    def description(self) -> str:
        return "Trades price breakouts above resistance or below support with volume"

    @property
    def role(self) -> str:
        return StrategyRole.TREND

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        if len(df) < 30:
            return self._hold(symbol, df, "Not enough bars")

        price     = float(df["close"].iloc[-1])
        prev      = float(df["close"].iloc[-2])
        timestamp = df.index[-1].to_pydatetime()

        sr_sig = summary.signals.get("SR")
        bb_sig = summary.signals.get("BB")

        if not sr_sig:
            return self._hold(symbol, df, "No S/R data")

        resistances = sr_sig.details.get("resistance_levels", [])
        supports    = sr_sig.details.get("support_levels", [])
        squeeze     = bb_sig.details.get("squeeze", False) if bb_sig else False

        avg_vol  = df["volume"].rolling(20).mean().iloc[-1]
        curr_vol = float(df["volume"].iloc[-1])
        vol_ok   = curr_vol >= avg_vol * self.volume_factor

        confirmations = []

        # BUY breakout: current price above resistance, previous was below
        broken_resistance = [r for r in resistances
                             if prev <= r * (1 + self.proximity) and price > r]

        if broken_resistance:
            level = broken_resistance[-1]
            confirmations.append(f"broke resistance at ${level:.2f}")
            if vol_ok:   confirmations.append(f"volume {curr_vol/avg_vol:.1f}x average")
            if squeeze:  confirmations.append("Bollinger squeeze released")

            confidence = 0.55 + (0.12 if vol_ok else 0) + (0.08 if squeeze else 0)

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.BUY,
                confidence    = min(confidence, 0.92),
                reason        = f"Breakout above resistance ${level:.2f}",
                confirmations = confirmations,
                stop_loss     = round(level * 0.985, 2),   # just below broken resistance
                take_profit   = round(price + (price - level) * 2, 2),
                details       = {"broken_level": level, "volume_ratio": round(curr_vol/avg_vol, 2)},
            )

        # SELL breakdown: current price below support, previous was above
        broken_support = [s for s in supports
                         if prev >= s * (1 - self.proximity) and price < s]

        if broken_support:
            level = broken_support[0]
            confirmations.append(f"broke support at ${level:.2f}")
            if vol_ok: confirmations.append(f"volume {curr_vol/avg_vol:.1f}x average")

            confidence = 0.55 + (0.12 if vol_ok else 0)

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.SELL,
                confidence    = min(confidence, 0.88),
                reason        = f"Breakdown below support ${level:.2f}",
                confirmations = confirmations,
                stop_loss     = round(level * 1.015, 2),
                take_profit   = round(price - (level - price) * 2, 2),
                details       = {"broken_level": level, "volume_ratio": round(curr_vol/avg_vol, 2)},
            )

        return self._hold(symbol, df, "No breakout detected")
