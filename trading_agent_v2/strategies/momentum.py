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

        rsi_val     = rsi_sig.details.get("rsi", 50)
        above_sma20 = ma_sig.details.get("above_sma20", False)
        above_sma50 = ma_sig.details.get("above_sma50", False)
        macd_above  = macd_sig.details.get("above_zero", False)
        hist        = macd_sig.details.get("histogram", 0)
        prev_hist   = macd_sig.details.get("prev_histogram", 0)

        # Volume check
        avg_vol   = df["volume"].rolling(20).mean().iloc[-1]
        curr_vol  = float(df["volume"].iloc[-1])
        vol_ok    = curr_vol >= avg_vol * self.volume_factor
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        # ── Fix 2a: ADX filter — only trade stocks that are actually trending ──
        # ADX < 20 = choppy/ranging market — RSI 50+ in ranging stocks is noise
        try:
            high  = df["high"]
            low   = df["low"]
            close = df["close"]
            tr    = pd.concat([
                high - low,
                (high - close.shift(1)).abs(),
                (low  - close.shift(1)).abs()
            ], axis=1).max(axis=1)
            atr14     = tr.rolling(14).mean()
            plus_dm   = (high.diff()).clip(lower=0)
            minus_dm  = (-low.diff()).clip(lower=0)
            plus_di   = 100 * plus_dm.rolling(14).mean() / atr14.replace(0, float("nan"))
            minus_di  = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, float("nan"))
            dx        = (100 * (plus_di - minus_di).abs()
                         / (plus_di + minus_di).replace(0, float("nan")))
            adx_val   = float(dx.rolling(14).mean().iloc[-1])
            atr_val   = float(atr14.iloc[-1])
        except Exception:
            adx_val = 25.0   # assume trending if calculation fails
            atr_val = price * 0.01

        if adx_val < 20:
            return self._hold(symbol, df,
                f"Momentum blocked: ADX={adx_val:.1f} < 20 — not trending (choppy stock)")

        # ── Fix 2b: Relative strength vs SPY ────────────────────────────────
        # Stock must outperform SPY over last 10 bars — eliminates laggards
        spy_df = getattr(summary, "spy_df", None)
        rs_ok  = True   # default pass if no SPY data available
        rs_val = 0.0
        if spy_df is not None and len(spy_df) >= 11 and len(df) >= 11:
            try:
                stock_chg = (float(df["close"].iloc[-1]) -
                             float(df["close"].iloc[-11])) / float(df["close"].iloc[-11])
                spy_chg   = (float(spy_df["close"].iloc[-1]) -
                             float(spy_df["close"].iloc[-11])) / float(spy_df["close"].iloc[-11])
                rs_val    = stock_chg - spy_chg   # positive = outperforming SPY
                rs_ok     = rs_val > -0.01        # allow slight underperformance (-1%)
            except Exception:
                rs_ok = True

        confirmations = []
        confidence    = 0.0

        # ── Rally override: RSI 80-95 + volume ──────────────────────────────
        rally_override = (
            80 < rsi_val <= 95 and
            above_sma20 and above_sma50 and
            vol_ratio >= 0.8 and
            adx_val >= 20   # must still be trending
        )

        if rally_override:
            conf = min(0.65 + (adx_val - 20) / 100, 0.85)
            rs_note = f" RS={rs_val:+.1%}" if spy_df is not None else ""
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = round(conf, 3),
                reason     = (f"Rally override: RSI={rsi_val:.1f} "
                              f"ADX={adx_val:.1f} vol={vol_ratio:.1f}x{rs_note}"),
                strategy   = self.name,
                details    = {"rsi": rsi_val, "adx": round(adx_val,1),
                              "volume_ratio": round(vol_ratio,2), "rs_vs_spy": round(rs_val,4)},
            )

        # ── Main BUY logic ───────────────────────────────────────────────────
        if (above_sma20 and above_sma50 and
                self.rsi_min <= rsi_val <= self.rsi_max and
                macd_above and hist > 0):

            if above_sma20:        confirmations.append("above SMA20")
            if above_sma50:        confirmations.append("above SMA50")
            if macd_above:         confirmations.append("MACD positive")
            if hist > prev_hist:   confirmations.append("histogram expanding")
            if vol_ok:             confirmations.append("volume confirmed")
            if adx_val >= 25:      confirmations.append(f"ADX={adx_val:.1f} strong trend")
            if rs_ok and rs_val > 0: confirmations.append(f"RS vs SPY +{rs_val:.1%}")

            # RS penalty — if underperforming SPY, reduce confidence
            rs_adj     = max(0.0, min(0.1, rs_val * 2)) if spy_df is not None else 0.0
            # ADX boost — stronger trend = higher confidence
            adx_boost  = min(0.05, (adx_val - 20) / 200) if adx_val > 20 else 0.0
            confidence = min(0.5 + len(confirmations) * 0.08 + rs_adj + adx_boost, 0.95)

            # ── Fix 2c: ATR-based stop instead of SMA20×0.98 ────────────────
            # 1.5×ATR14 below entry adapts to actual volatility
            stop = price - (1.5 * atr_val)
            tp   = price + (3.0 * atr_val)   # 2:1 R:R using ATR

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.BUY,
                confidence    = round(confidence, 3),
                reason        = (f"Momentum: RSI={rsi_val:.1f} "
                                 f"ADX={adx_val:.1f} "
                                 f"RS={rs_val:+.1%} vol={vol_ratio:.1f}x"),
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {
                    "rsi":          rsi_val,
                    "adx":          round(adx_val, 1),
                    "volume_ratio": round(vol_ratio, 2),
                    "rs_vs_spy":    round(rs_val, 4),
                    "atr":          round(atr_val, 3),
                },
            )

        # ── SELL logic ───────────────────────────────────────────────────────
        bearish_cross = macd_sig.details.get("bearish_crossover", False)
        if bearish_cross or (not above_sma20) or rsi_val < 45:
            reasons = []
            if bearish_cross:   reasons.append("MACD bearish crossover")
            if not above_sma20: reasons.append("price below SMA20")
            if rsi_val < 45:    reasons.append(f"RSI fading ({rsi_val:.1f})")

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.SELL,
                confidence    = 0.6,
                reason        = "Momentum fading: " + ", ".join(reasons),
                confirmations = reasons,
                details       = {"rsi": rsi_val, "adx": round(adx_val, 1)},
            )

        return self._hold(symbol, df,
            f"Momentum neutral: RSI={rsi_val:.1f} ADX={adx_val:.1f} RS={rs_val:+.1%}")
