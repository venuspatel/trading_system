# -*- coding: utf-8 -*-
"""
Strategy 4: Candle Reversal
-----------------------------
Trades high-confidence reversal candlestick patterns
that appear at key support/resistance levels.

The key insight: a pattern alone is ~55% reliable.
The same pattern AT a S/R level is ~72% reliable.
Adding RSI confirmation pushes it to ~78%.

Bullish reversals (BUY):
  Hammer / Bullish Engulfing / Morning Star
  -- must appear near a support level
  -- RSI < 50 preferred (not already overbought)

Bearish reversals (SELL):
  Shooting Star / Bearish Engulfing / Evening Star
  -- must appear near a resistance level
  -- RSI > 50 preferred
"""

import pandas as pd
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole
from indicators.base import SignalDirection


BULLISH_PATTERNS = {"Hammer", "Bullish Engulfing", "Morning Star"}
BEARISH_PATTERNS = {"Shooting Star", "Bearish Engulfing", "Evening Star"}


class CandleReversalStrategy(BaseStrategy):

    def __init__(self, sr_proximity=0.02):
        self.sr_proximity = sr_proximity   # within 2% of S/R level

    @property
    def name(self) -> str:
        return "CandleReversal"

    @property
    def description(self) -> str:
        return "Trades reversal candle patterns confirmed at support/resistance levels"

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        if len(df) < 10:
            return self._hold(symbol, df, "Not enough bars")

        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        candle_sig = summary.signals.get("CANDLE")
        sr_sig     = summary.signals.get("SR")
        rsi_sig    = summary.signals.get("RSI")

        if not candle_sig:
            return self._hold(symbol, df, "No candle data")

        pattern  = candle_sig.details.get("pattern")
        if not pattern or pattern == "Doji":
            return self._hold(symbol, df, "No strong reversal pattern")

        rsi_val  = rsi_sig.details.get("rsi", 50) if rsi_sig else 50
        supports    = sr_sig.details.get("support_levels", [])    if sr_sig else []
        resistances = sr_sig.details.get("resistance_levels", []) if sr_sig else []

        confirmations = [f"{pattern} pattern detected"]
        confidence    = 0.55    # base: pattern alone

        # BUY: bullish pattern
        if pattern in BULLISH_PATTERNS:
            # Check if near support
            near_support = any(
                abs(price - s) / price < self.sr_proximity
                for s in supports
            )
            if near_support:
                confirmations.append("at support level")
                confidence += 0.12

            if rsi_val < 50:
                confirmations.append(f"RSI not overbought ({rsi_val:.1f})")
                confidence += 0.08

            if rsi_val < 35:
                confirmations.append(f"RSI oversold ({rsi_val:.1f}) -- strong confirmation")
                confidence += 0.07

            # Strong patterns get extra weight
            if pattern in {"Bullish Engulfing", "Morning Star"}:
                confirmations.append(f"strong pattern ({pattern})")
                confidence += 0.05

            stop = float(df["low"].iloc[-1]) * 0.99
            tp   = price + (price - stop) * 2.0

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.BUY,
                confidence    = min(confidence, 0.93),
                reason        = f"{pattern} at key level (RSI={rsi_val:.1f})",
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {"pattern": pattern, "rsi": rsi_val, "near_support": near_support if supports else False},
            )

        # SELL: bearish pattern
        if pattern in BEARISH_PATTERNS:
            near_resistance = any(
                abs(price - r) / price < self.sr_proximity
                for r in resistances
            )
            if near_resistance:
                confirmations.append("at resistance level")
                confidence += 0.12

            if rsi_val > 50:
                confirmations.append(f"RSI elevated ({rsi_val:.1f})")
                confidence += 0.08

            if rsi_val > 65:
                confirmations.append(f"RSI overbought ({rsi_val:.1f}) -- strong confirmation")
                confidence += 0.07

            if pattern in {"Bearish Engulfing", "Evening Star"}:
                confirmations.append(f"strong pattern ({pattern})")
                confidence += 0.05

            stop = float(df["high"].iloc[-1]) * 1.01
            tp   = price - (stop - price) * 2.0

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.SELL,
                confidence    = min(confidence, 0.93),
                reason        = f"{pattern} at key level (RSI={rsi_val:.1f})",
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {"pattern": pattern, "rsi": rsi_val},
            )

        return self._hold(symbol, df, f"Pattern {pattern} not a reversal signal")
