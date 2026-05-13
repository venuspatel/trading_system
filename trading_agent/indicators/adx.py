# -*- coding: utf-8 -*-
"""
ADX — Average Directional Index
---------------------------------
Measures trend STRENGTH (not direction). 
  ADX < 20  = no trend, choppy market — avoid entries
  ADX 20-40 = developing trend — good for entries
  ADX > 40  = strong trend — ride it
  ADX > 60  = extremely strong — AMD-style +30% month moves live here

Also returns +DI and -DI for direction:
  +DI > -DI = uptrend
  -DI > +DI = downtrend

Used by TrendStrengthStrategy to catch multi-week momentum moves
that the daily conviction score misses.
"""

import pandas as pd
import numpy as np
class ADXIndicator:
    """Average Directional Index — measures trend strength."""

    def __init__(self, period: int = 14):
        self.period = period

    @property
    def name(self) -> str:
        return f"ADX_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute ADX, +DI, -DI.
        Requires columns: high, low, close.
        Returns df with added columns: adx, plus_di, minus_di, trend_strength
        """
        if len(df) < self.period + 5:
            df["adx"] = 0.0
            df["plus_di"] = 0.0
            df["minus_di"] = 0.0
            df["trend_strength"] = "NONE"
            return df

        high  = df["high"].astype(float)
        low   = df["low"].astype(float)
        close = df["close"].astype(float)

        # True Range
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        # Directional movements
        up_move   = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        # Smoothed ATR, +DM, -DM (Wilder smoothing)
        atr_s      = self._wilder_smooth(pd.Series(tr),       self.period)
        plus_dm_s  = self._wilder_smooth(pd.Series(plus_dm),  self.period)
        minus_dm_s = self._wilder_smooth(pd.Series(minus_dm), self.period)

        plus_di  = 100 * plus_dm_s  / atr_s.replace(0, np.nan)
        minus_di = 100 * minus_dm_s / atr_s.replace(0, np.nan)

        # DX and ADX
        dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = self._wilder_smooth(dx.fillna(0), self.period)

        df = df.copy()
        df["adx"]      = adx.round(2)
        df["plus_di"]  = plus_di.fillna(0).round(2)
        df["minus_di"] = minus_di.fillna(0).round(2)

        # Trend strength label
        last_adx = adx.iloc[-1] if not adx.empty else 0
        if last_adx >= 60:   label = "EXTREME"
        elif last_adx >= 40: label = "STRONG"
        elif last_adx >= 25: label = "MODERATE"
        elif last_adx >= 20: label = "DEVELOPING"
        else:                label = "NONE"

        df["trend_strength"] = label
        return df

    def _wilder_smooth(self, series: pd.Series, period: int) -> pd.Series:
        """Wilder smoothing — used by ADX formula."""
        result = pd.Series(index=series.index, dtype=float)
        result.iloc[:period] = np.nan
        seed = series.iloc[:period].sum()
        result.iloc[period - 1] = seed
        for i in range(period, len(series)):
            result.iloc[i] = result.iloc[i-1] - (result.iloc[i-1] / period) + series.iloc[i]
        return result

    def latest(self, df: pd.DataFrame) -> dict:
        """Return latest ADX values as a dict."""
        df = self.compute(df)
        return {
            "adx":            float(df["adx"].iloc[-1]),
            "plus_di":        float(df["plus_di"].iloc[-1]),
            "minus_di":       float(df["minus_di"].iloc[-1]),
            "trend_strength": df["trend_strength"].iloc[-1],
            "direction":      "UP" if df["plus_di"].iloc[-1] > df["minus_di"].iloc[-1] else "DOWN",
        }
