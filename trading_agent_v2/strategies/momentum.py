# -*- coding: utf-8 -*-
"""
Strategy 1: Momentum
---------------------
Buys when price is in a strong confirmed uptrend.
Sells when momentum begins to fade.

Entry conditions (BUY):
  - Price above SMA20 > SMA50
  - MACD above signal line
  - RSI between 50-70 (trending, not overbought)
  - Volume above 20-day average

Exit conditions (SELL):
  - MACD bearish crossover, OR
  - Price drops below SMA20, OR
  - RSI drops below 45
"""

import pandas as pd
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole
from indicators.base import SignalDirection


class MomentumStrategy(BaseStrategy):

    def __init__(self, rsi_min=50, rsi_max=80, volume_factor=1.0):
        self.rsi_min      = rsi_min
        self.rsi_max      = rsi_max
        self.volume_factor = volume_factor

    @property
    def name(self) -> str:
        return "Momentum"

    @property
    def description(self) -> str:
        return "Buys strong uptrends confirmed by MA, MACD, RSI and volume"

    @property
    def role(self) -> str:
        return StrategyRole.TREND

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        if len(df) < 52:
            return self._hold(symbol, df, "Not enough bars")

        price      = float(df["close"].iloc[-1])
        prev_price = float(df["close"].iloc[-2])
        timestamp  = df.index[-1].to_pydatetime()

        # Pull values from indicator summary
        ma_sig     = summary.signals.get("MA")
        macd_sig   = summary.signals.get("MACD")
        rsi_sig    = summary.signals.get("RSI")

        if not all([ma_sig, macd_sig, rsi_sig]):
            return self._hold(symbol, df, "Missing indicator data")

        rsi_val    = rsi_sig.details.get("rsi", 50)
        above_sma20 = ma_sig.details.get("above_sma20", False)
        above_sma50 = ma_sig.details.get("above_sma50", False)
        macd_above  = macd_sig.details.get("above_zero", False)
        hist        = macd_sig.details.get("histogram", 0)
        prev_hist   = macd_sig.details.get("prev_histogram", 0)

        # Volume check
        avg_vol    = df["volume"].rolling(20).mean().iloc[-1]
        curr_vol   = float(df["volume"].iloc[-1])
        vol_ok     = curr_vol >= avg_vol * self.volume_factor

        confirmations = []
        confidence    = 0.0

        # BUY logic — includes rally override for RSI 80-88 with volume confirmation
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
        rally_override = (80 < rsi_val <= 95 and above_sma20 and above_sma50 and vol_ratio >= 1.3)

        if rally_override:
            # Strong rally — RSI overbought but volume confirms institutional buying
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = 0.6,  # lower confidence — momentum is stretched
                reason     = f"Rally override: RSI={rsi_val:.1f} but vol={vol_ratio:.1f}x avg — momentum breakout",
                strategy   = self.name,
                price      = price,
            )

        if (above_sma20 and above_sma50 and
                self.rsi_min <= rsi_val <= self.rsi_max and
                macd_above and hist > 0):

            if above_sma20:   confirmations.append("above SMA20")
            if above_sma50:   confirmations.append("above SMA50")
            if macd_above:    confirmations.append("MACD positive")
            if hist > prev_hist: confirmations.append("histogram expanding")
            if vol_ok:        confirmations.append("volume confirmed")

            confidence = min(0.5 + len(confirmations) * 0.1, 0.95)

            sma20 = ma_sig.details.get("sma_20", price)
            stop  = sma20 * 0.98
            tp    = price * (1 + (price - stop) / price * 2)   # 2:1 R:R

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.BUY,
                confidence    = confidence,
                reason        = f"Momentum confirmed: RSI={rsi_val:.1f}, price above MAs, MACD positive",
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {"rsi": rsi_val, "volume_ratio": round(curr_vol/avg_vol, 2)},
            )

        # SELL logic
        bearish_cross = macd_sig.details.get("bearish_crossover", False)
        if bearish_cross or (not above_sma20) or rsi_val < 45:
            reasons = []
            if bearish_cross:    reasons.append("MACD bearish crossover")
            if not above_sma20:  reasons.append("price below SMA20")
            if rsi_val < 45:     reasons.append(f"RSI fading ({rsi_val:.1f})")

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.SELL,
                confidence    = 0.6,
                reason        = "Momentum fading: " + ", ".join(reasons),
                confirmations = reasons,
                details       = {"rsi": rsi_val},
            )

        return self._hold(symbol, df, f"Momentum neutral: RSI={rsi_val:.1f}")
