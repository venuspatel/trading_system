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
        # Fix 6: Lower momentum threshold + weekly ADX check + ATR stops + scaled confidence
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

        # Fix 6a: Lower momentum threshold 5% → 3%
        # 5% in 10 bars = ~65% annualized — too strict, misses steady grinders
        # 3% in 10 bars = ~39% annualized — still a strong move
        effective_min = max(0.03, self.momentum_min * 0.6)
        momentum_pct  = (price - float(close.iloc[-self.momentum_bars])) / float(close.iloc[-self.momentum_bars])

        # Fix 6b: Weekly ADX check — prevent false trend signals from single-day spikes
        # Resample to weekly and check ADX is also elevated on weekly bars
        weekly_adx_ok = True   # default pass
        try:
            weekly = df.resample("W").agg({
                "open":"first","high":"max","low":"min","close":"last","volume":"sum"
            }).dropna()
            if len(weekly) >= 16:
                w_high, w_low, w_close = weekly["high"], weekly["low"], weekly["close"]
                w_tr  = pd.concat([
                    w_high - w_low,
                    (w_high - w_close.shift(1)).abs(),
                    (w_low  - w_close.shift(1)).abs()
                ], axis=1).max(axis=1)
                w_atr = w_tr.rolling(14).mean()
                w_pdm = (w_high.diff()).clip(lower=0)
                w_mdm = (-w_low.diff()).clip(lower=0)
                w_pdi = 100 * w_pdm.rolling(14).mean() / w_atr.replace(0, float("nan"))
                w_mdi = 100 * w_mdm.rolling(14).mean() / w_atr.replace(0, float("nan"))
                w_dx  = (100 * (w_pdi - w_mdi).abs() / (w_pdi + w_mdi).replace(0, float("nan")))
                w_adx = float(w_dx.rolling(14).mean().iloc[-1])
                weekly_adx_ok = w_adx >= 20   # weekly ADX must also show trend
        except Exception:
            weekly_adx_ok = True   # if calc fails, don't block

        # Fix 6c: ATR for adaptive stops
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── BUY: strong trend + price above both MAs + momentum ──────────
        if (adx_val >= self.adx_threshold and adx_dir == "UP"
                and above_fast and above_slow and ma_aligned
                and momentum_pct >= effective_min
                and weekly_adx_ok):

            # Fix 6d: Scale confidence by ADX strength tier
            # ADX 25-35 = developing trend, 35-45 = strong, 45+ = very strong
            if adx_val >= 45:
                base_conf = 0.85
            elif adx_val >= 35:
                base_conf = 0.78
            else:
                base_conf = 0.70

            # Momentum boost
            mom_boost = min(0.08, momentum_pct * 0.8)
            # Weekly ADX confirmation boost
            w_boost   = 0.04 if weekly_adx_ok else 0.0
            confidence = min(0.95, base_conf + mom_boost + w_boost)

            if adx_val >= 40 and momentum_pct >= 0.08:
                reason = (f"STRONG TREND: ADX={adx_val:.0f} · "
                          f"{momentum_pct*100:.1f}% gain/{self.momentum_bars}bars · "
                          f"{((price/ma_slow_val-1)*100):.1f}% above 50MA · "
                          f"weekly ADX ok={weekly_adx_ok}")
            else:
                reason = (f"TrendStrength: ADX={adx_val:.0f} · "
                          f"MA aligned · {momentum_pct*100:.1f}% mom · "
                          f"weekly={weekly_adx_ok}")

            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)

            return TradeSignal(
                symbol=symbol, strategy=self.name,
                action=TradeAction.BUY,
                confidence=round(confidence, 3),
                timestamp=df.index[-1].to_pydatetime(),
                reason=reason,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={
                    "adx":           adx_val,
                    "momentum_pct":  round(momentum_pct*100, 2),
                    "trend_strength":adx_data["trend_strength"],
                    "weekly_adx_ok": weekly_adx_ok,
                    "atr14":         round(atr14, 3),
                    "effective_min": round(effective_min*100, 1),
                },
            )

        # ── SELL: trend turning down ──────────────────────────────────────
        if adx_val >= 20 and adx_dir == "DOWN" and not above_fast:
            stop = price + (1.5 * atr14)
            tp   = price - (2.0 * atr14)
            return TradeSignal(
                symbol=symbol, strategy=self.name,
                action=TradeAction.SELL,
                confidence=0.65,
                timestamp=df.index[-1].to_pydatetime(),
                reason=f"Trend weakening: ADX={adx_val:.0f} DOWN · below fast MA",
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
            )

        reasons = []
        if adx_val < self.adx_threshold:
            reasons.append(f"ADX={adx_val:.0f}<{self.adx_threshold}")
        if not (above_fast and above_slow):
            reasons.append("below MAs")
        if momentum_pct < effective_min:
            reasons.append(f"mom={momentum_pct*100:.1f}%<{effective_min*100:.0f}%")
        if not weekly_adx_ok:
            reasons.append("weekly ADX weak")

        return self._hold(symbol, df, " · ".join(reasons) or "No strong trend")
