# -*- coding: utf-8 -*-
"""
MultiTimeframeConviction
--------------------------
Analyses a symbol across 4 timeframes and produces a conviction bonus
that gets added on top of the base strategy score.

Timeframes:
  Daily   → already handled by strategies (no bonus here)
  Weekly  → looks at last 4 weekly bars  (+0 to +1.0 bonus)
  Monthly → looks at last 3 monthly bars (+0 to +0.8 bonus)
  Yearly  → looks at full year context   (+0 to +0.5 bonus, used as multiplier)

How it works for each timeframe:
  1. Resample daily OHLCV bars into weekly/monthly/yearly bars
  2. Check: price above MA, RSI in trend zone, momentum positive
  3. Score 0.0 to 1.0 per timeframe, apply weight

AMD example (April 2026):
  Weekly:  Price > 20-week MA, RSI 68, momentum +12% = +0.9 bonus
  Monthly: March bar +18%, price > 3-month MA = +0.8 bonus  
  Yearly:  +21% YTD, long-term uptrend = +0.5 bonus
  Total bonus: +2.2 → AMD daily +0.53 + 2.2 = +2.73 → TRADE FIRES
"""

import logging
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TimeframeScore:
    """Score for one timeframe."""
    timeframe:     str
    score:         float = 0.0   # 0.0 to 1.0
    bonus:         float = 0.0   # conviction points added
    direction:     str   = "NEUTRAL"   # UP / DOWN / NEUTRAL
    rsi:           float = 50.0
    momentum_pct:  float = 0.0
    above_ma:      bool  = False
    reason:        str   = ""


@dataclass
class MultiTimeframeResult:
    """Combined result across all timeframes."""
    symbol:         str
    daily:          TimeframeScore = field(default_factory=lambda: TimeframeScore("1D"))
    weekly:         TimeframeScore = field(default_factory=lambda: TimeframeScore("1W"))
    monthly:        TimeframeScore = field(default_factory=lambda: TimeframeScore("1M"))
    yearly:         TimeframeScore = field(default_factory=lambda: TimeframeScore("1Y"))
    total_bonus:    float = 0.0
    alignment:      str   = "NEUTRAL"  # ALL_UP / MOSTLY_UP / MIXED / MOSTLY_DOWN

    def summary(self) -> str:
        parts = []
        for tf in [self.weekly, self.monthly, self.yearly]:
            if tf.bonus != 0:
                parts.append(f"{tf.timeframe}={tf.bonus:+.2f}({tf.direction})")
        return " | ".join(parts) if parts else "no bonus"


class MultiTimeframeConviction:
    """
    Resamples daily bars into higher timeframes and scores trend alignment.
    
    Usage:
        mtf = MultiTimeframeConviction()
        result = mtf.analyse("AMD", df_daily)
        conviction += result.total_bonus
    """

    # Weights per timeframe (max bonus each can contribute)
    WEEKLY_MAX  = 1.0
    MONTHLY_MAX = 0.8
    YEARLY_MAX  = 0.5   # context multiplier — adds less but contextualises all

    # RSI zones
    RSI_BULL = (55, 75)   # trending up without being too overbought
    RSI_BEAR = (25, 45)   # trending down

    def analyse(self, symbol: str, df: pd.DataFrame) -> MultiTimeframeResult:
        """
        Analyse symbol across weekly, monthly, yearly timeframes.
        
        Args:
            symbol: Ticker
            df:     Daily OHLCV DataFrame with DatetimeIndex
            
        Returns:
            MultiTimeframeResult with bonus breakdown
        """
        result = MultiTimeframeResult(symbol=symbol)

        if len(df) < 30:
            return result

        try:
            # Ensure datetime index
            df = df.copy()
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)

            # Score each timeframe
            result.weekly  = self._score_timeframe(df, "W",  self.WEEKLY_MAX,  min_bars=4)
            result.monthly = self._score_timeframe(df, "ME", self.MONTHLY_MAX, min_bars=3)
            result.yearly  = self._score_timeframe(df, "YE", self.YEARLY_MAX,  min_bars=1)

            # Total bonus
            result.total_bonus = round(
                result.weekly.bonus + result.monthly.bonus + result.yearly.bonus, 3
            )

            # Overall alignment
            directions = [result.weekly.direction, result.monthly.direction, result.yearly.direction]
            up_count   = directions.count("UP")
            down_count = directions.count("DOWN")
            if up_count == 3:   result.alignment = "ALL_UP"
            elif up_count == 2: result.alignment = "MOSTLY_UP"
            elif down_count >= 2: result.alignment = "MOSTLY_DOWN"
            else:               result.alignment = "MIXED"

            logger.info(
                f"[MTF] {symbol} | "
                f"W={result.weekly.bonus:+.2f} M={result.monthly.bonus:+.2f} "
                f"Y={result.yearly.bonus:+.2f} | "
                f"total={result.total_bonus:+.2f} | {result.alignment}"
            )

        except Exception as e:
            logger.debug(f"[MTF] {symbol} error: {e}")

        return result

    def _score_timeframe(
        self,
        df: pd.DataFrame,
        freq: str,
        max_bonus: float,
        min_bars: int = 3,
    ) -> TimeframeScore:
        """Resample to frequency and score the trend."""
        ts = TimeframeScore(timeframe=freq)

        try:
            # Resample OHLCV
            agg = {
                "open":   "first",
                "high":   "max",
                "low":    "min",
                "close":  "last",
            }
            if "volume" in df.columns:
                agg["volume"] = "sum"

            # Normalise column names
            df_norm = df.rename(columns={c: c.lower() for c in df.columns})
            resampled = df_norm.resample(freq).agg(agg).dropna()

            if len(resampled) < min_bars:
                ts.reason = f"Not enough {freq} bars ({len(resampled)} < {min_bars})"
                return ts

            close     = resampled["close"].astype(float)
            price     = float(close.iloc[-1])
            prev      = float(close.iloc[-2]) if len(close) > 1 else price

            # Momentum: % change over available bars
            lookback      = min(len(close) - 1, 6)
            ts.momentum_pct = float((price - close.iloc[-lookback-1]) / close.iloc[-lookback-1] * 100)

            # Moving average alignment
            ma_period   = min(len(close), max(3, len(close) // 2))
            ma_val      = float(close.rolling(ma_period).mean().iloc[-1])
            ts.above_ma = price > ma_val

            # RSI on resampled bars
            ts.rsi = self._rsi(close, min(14, len(close) - 1))

            # Direction
            if ts.momentum_pct > 2 and ts.above_ma:
                ts.direction = "UP"
            elif ts.momentum_pct < -2 and not ts.above_ma:
                ts.direction = "DOWN"
            else:
                ts.direction = "NEUTRAL"

            # Score 0.0 → 1.0
            score = 0.0
            if ts.direction == "UP":
                # Base score from momentum strength
                score += min(0.5, abs(ts.momentum_pct) / 20)
                # RSI in bull zone
                if self.RSI_BULL[0] <= ts.rsi <= self.RSI_BULL[1]:
                    score += 0.3
                elif ts.rsi > self.RSI_BULL[1]:
                    score += 0.15   # overbought — still positive but less
                # Above MA
                if ts.above_ma:
                    score += 0.2
                score = min(1.0, score)
                ts.bonus = round(score * max_bonus, 3)
            elif ts.direction == "DOWN":
                # Negative bonus — penalise bullish trades in downtrend
                score = min(0.5, abs(ts.momentum_pct) / 20)
                if not ts.above_ma:
                    score += 0.2
                ts.bonus = round(-score * max_bonus * 0.7, 3)   # smaller penalty than reward

            ts.score = round(score, 3)
            ts.reason = (
                f"mom={ts.momentum_pct:+.1f}% rsi={ts.rsi:.0f} "
                f"{'above' if ts.above_ma else 'below'} MA"
            )

        except Exception as e:
            ts.reason = f"Error: {e}"
            logger.debug(f"[MTF] {freq} score error: {e}")

        return ts

    def _rsi(self, close: pd.Series, period: int = 14) -> float:
        """Simple RSI calculation."""
        if len(close) < period + 1:
            return 50.0
        delta = close.diff().dropna()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty else 50.0
