# -*- coding: utf-8 -*-
"""
Strategy 2: Mean Reversion
---------------------------
Buys oversold dips expecting price to revert to the mean.
Sells overbought spikes expecting price to pull back.

Entry BUY:
  - RSI < 35 (oversold)
  - Price at or below lower Bollinger Band
  - Price above SMA200 (still in long-term uptrend)

Entry SELL:
  - RSI > 65 (overbought)
  - Price at or above upper Bollinger Band
"""

import pandas as pd
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole


class MeanReversionStrategy(BaseStrategy):

    def __init__(self, rsi_oversold=35, rsi_overbought=65):
        self.rsi_oversold   = rsi_oversold
        self.rsi_overbought = rsi_overbought

    @property
    def name(self) -> str:
        return "MeanReversion"

    @property
    def description(self) -> str:
        return "Buys oversold dips and sells overbought spikes using RSI + Bollinger Bands"

    @property
    def role(self) -> str:
        return StrategyRole.COUNTER_TREND

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # MeanReversion is a counter-trend strategy — it fights the tape in
        # trend-following modes. Auto-disable for PM, Aggressive, Momentum modes.
        _approach = str(getattr(summary, "approach", "") or "").lower()
        if any(x in _approach for x in ("profit maximizer", "aggressive", "micro momentum")):
            return self._hold(symbol, df,
                f"MeanReversion disabled in {_approach} mode — counter-trend vs trend-following conflict")

        if len(df) < 25:
            return self._hold(symbol, df, "Not enough bars")

        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        rsi_sig  = summary.signals.get("RSI")
        bb_sig   = summary.signals.get("BB")
        ma_sig   = summary.signals.get("MA")

        if not all([rsi_sig, bb_sig]):
            return self._hold(symbol, df, "Missing indicator data")

        rsi_val  = rsi_sig.details.get("rsi", 50)
        pct_b    = bb_sig.details.get("pct_b", 0.5)
        upper    = bb_sig.details.get("upper", price * 1.02)
        lower    = bb_sig.details.get("lower", price * 0.98)
        middle   = bb_sig.details.get("middle", price)
        squeeze  = bb_sig.details.get("squeeze", False)

        above_sma200 = ma_sig.details.get("above_sma200", True) if ma_sig else True

        confirmations = []
        confidence    = 0.0

        # BUY: oversold + at lower band
        if rsi_val < self.rsi_oversold and pct_b < 0.2:
            if rsi_val < self.rsi_oversold:  confirmations.append(f"RSI oversold ({rsi_val:.1f})")
            if pct_b < 0.2:                  confirmations.append(f"at lower Bollinger band")
            if above_sma200:                 confirmations.append("above SMA200 (uptrend intact)")
            if squeeze:                      confirmations.append("Bollinger squeeze releasing")

            confidence = min(0.5 + len(confirmations) * 0.12, 0.92)
            stop       = lower * 0.99
            tp         = middle              # target: revert to mean

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.BUY,
                confidence    = confidence,
                reason        = f"Oversold dip: RSI={rsi_val:.1f}, pct_b={pct_b:.2f}",
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {"rsi": rsi_val, "pct_b": pct_b, "target": middle},
            )

        # SELL: overbought + at upper band
        if rsi_val > self.rsi_overbought and pct_b > 0.8:
            confirmations = [
                f"RSI overbought ({rsi_val:.1f})",
                f"at upper Bollinger band (pct_b={pct_b:.2f})",
            ]
            confidence = min(0.5 + len(confirmations) * 0.12, 0.88)

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.SELL,
                confidence    = confidence,
                reason        = f"Overbought spike: RSI={rsi_val:.1f}, pct_b={pct_b:.2f}",
                confirmations = confirmations,
                stop_loss     = round(upper * 1.01, 2),
                take_profit   = round(middle, 2),
                details       = {"rsi": rsi_val, "pct_b": pct_b},
            )

        return self._hold(symbol, df, f"Price in normal range: RSI={rsi_val:.1f}, pct_b={pct_b:.2f}")
