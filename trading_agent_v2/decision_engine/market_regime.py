# -*- coding: utf-8 -*-
"""
MarketRegimeDetector
---------------------
Reads SPY trend, VIX level, and market breadth every scan cycle
and classifies the current market into one of 4 regimes.

Each regime automatically adjusts the agent's gate thresholds — 
no more single hardcoded numbers blocking trades in bull markets.

Regimes:
  BULL      — SPY trending up, VIX < 20, broad participation
  BEAR      — SPY trending down, VIX > 30, defensive mode
  VOLATILE  — VIX 20-30, choppy price action, reduce size
  RANGING   — Low momentum in both directions, neutral thresholds

Threshold adjustments per regime:
                    BULL    BEAR    VOLATILE  RANGING
  conviction        2.0     3.0     2.8       2.5
  confidence        0.58    0.70    0.68      0.65
  min_strategies    2       3       2         2
  rsi_overbought    85      70      72        75
  position_size     1.0x    0.6x    0.8x      1.0x

AMD example with BULL regime:
  conviction 2.0 → AMD +1.27 passes Gate 2
  confidence 58% → AMD 64% passes Gate 3
  Both gates pass → BUY fires
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RegimeThresholds:
    """Gate thresholds for a specific market regime."""
    regime:             str
    conviction:         float    # min conviction to trade
    confidence:         float    # min avg strategy confidence
    min_strategies:     int      # min strategies agreeing
    rsi_overbought:     float    # RSI level considered overbought
    position_size_mult: float    # multiplier on normal position size
    stop_loss_mult:     float    # multiplier on normal stop loss

    def summary(self) -> str:
        return (f"regime={self.regime} | conv>={self.conviction} | "
                f"conf>={self.confidence:.0%} | rsi_ob={self.rsi_overbought}")


@dataclass
class RegimeReading:
    """Current market regime with full diagnostic data."""
    regime:         str      # BULL / BEAR / VOLATILE / RANGING
    thresholds:     RegimeThresholds
    spy_trend:      str      # UP / DOWN / FLAT
    spy_rsi:        float
    vix_level:      float    # estimated from SPY volatility
    spy_momentum:   float    # % change over 10 days
    confidence:     float    # 0-1 how confident we are in regime
    timestamp:      str      = ""
    reason:         str      = ""


# Regime threshold definitions
REGIMES = {
    "BULL": RegimeThresholds(
        regime             = "BULL",
        conviction         = 2.0,    # easier to get in — trend is your friend
        confidence         = 0.58,   # accept lower confidence in strong trends
        min_strategies     = 2,
        rsi_overbought     = 85,     # stocks can stay overbought for weeks
        position_size_mult = 1.0,
        stop_loss_mult     = 1.0,
    ),
    "BEAR": RegimeThresholds(
        regime             = "BEAR",
        conviction         = 3.0,    # need very strong signal to buy in a downtrend
        confidence         = 0.70,
        min_strategies     = 3,      # require more agreement
        rsi_overbought     = 68,     # overbought happens fast in bear markets
        position_size_mult = 0.6,    # smaller positions
        stop_loss_mult     = 0.8,    # tighter stops
    ),
    "VOLATILE": RegimeThresholds(
        regime             = "VOLATILE",
        conviction         = 2.8,
        confidence         = 0.68,
        min_strategies     = 2,
        rsi_overbought     = 72,
        position_size_mult = 0.8,
        stop_loss_mult     = 0.9,
    ),
    "RANGING": RegimeThresholds(
        regime             = "RANGING",
        conviction         = 2.5,    # default — same as before
        confidence         = 0.65,
        min_strategies     = 2,
        rsi_overbought     = 75,
        position_size_mult = 1.0,
        stop_loss_mult     = 1.0,
    ),
}


class MarketRegimeDetector:
    """
    Detects market regime from SPY price data.
    Called once per scan cycle — result cached until next scan.

    Usage:
        detector = MarketRegimeDetector()
        reading  = detector.detect(spy_df)
        # Now use reading.thresholds instead of hardcoded config values
    """

    def __init__(self):
        self._cached:    Optional[RegimeReading] = None
        self._cache_age: Optional[datetime]      = None
        self._cache_ttl: int = 600   # 10 minutes — same as scan frequency

    def detect(self, spy_df: pd.DataFrame) -> RegimeReading:
        """
        Detect current market regime from SPY daily bars.

        Args:
            spy_df: Daily OHLCV bars for SPY

        Returns:
            RegimeReading with thresholds and diagnostic data
        """
        # Return cached result if fresh
        if self._cached and self._cache_age:
            age = (datetime.now(timezone.utc) - self._cache_age).total_seconds()
            if age < self._cache_ttl:
                return self._cached

        reading = self._analyse(spy_df)
        self._cached    = reading
        self._cache_age = datetime.now(timezone.utc)

        logger.info(
            f"[Regime] {reading.regime} | {reading.reason} | "
            f"Thresholds: conv>={reading.thresholds.conviction} "
            f"conf>={reading.thresholds.confidence:.0%}"
        )
        return reading

    def _analyse(self, df: pd.DataFrame) -> RegimeReading:
        """Core regime detection logic."""
        try:
            if df is None or len(df) < 20:
                return self._default_reading("Insufficient SPY data")

            close = df["close"].astype(float) if "close" in df.columns else df.iloc[:, 3].astype(float)

            # --- SPY trend ---
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(min(50, len(close))).mean().iloc[-1])
            price = float(close.iloc[-1])

            momentum_10d = float((price - close.iloc[-11]) / close.iloc[-11] * 100) if len(close) > 11 else 0

            if price > ma20 > ma50 and momentum_10d > 1:
                spy_trend = "UP"
            elif price < ma20 < ma50 and momentum_10d < -1:
                spy_trend = "DOWN"
            else:
                spy_trend = "FLAT"

            # --- SPY RSI ---
            spy_rsi = self._rsi(close)

            # --- Volatility proxy (VIX estimate from SPY daily returns) ---
            returns     = close.pct_change().dropna()
            recent_vol  = float(returns.iloc[-20:].std() * np.sqrt(252) * 100) if len(returns) >= 20 else 20.0
            # Map annualised vol to rough VIX equivalent
            vix_est = recent_vol * 0.8

            # --- Classify regime ---
            if vix_est > 30:
                regime = "VOLATILE"
                confidence = 0.85
                reason = f"High volatility (VIX~{vix_est:.0f}), reducing thresholds"
            elif spy_trend == "DOWN" and spy_rsi < 45:
                regime = "BEAR"
                confidence = 0.80
                reason = f"SPY downtrend, RSI={spy_rsi:.0f}, tightening gates"
            elif spy_trend == "UP" and spy_rsi > 52 and vix_est < 22:
                regime = "BULL"
                confidence = 0.82
                reason = f"SPY uptrend RSI={spy_rsi:.0f}, VIX~{vix_est:.0f}, easing gates"
            elif abs(momentum_10d) < 1.5 and vix_est < 20:
                regime = "RANGING"
                confidence = 0.70
                reason = f"Low momentum ({momentum_10d:+.1f}%), default thresholds"
            else:
                regime = "RANGING"
                confidence = 0.60
                reason = f"Mixed signals, using default thresholds"

            return RegimeReading(
                regime       = regime,
                thresholds   = REGIMES[regime],
                spy_trend    = spy_trend,
                spy_rsi      = round(spy_rsi, 1),
                vix_level    = round(vix_est, 1),
                spy_momentum = round(momentum_10d, 2),
                confidence   = confidence,
                timestamp    = datetime.now(timezone.utc).isoformat(),
                reason       = reason,
            )

        except Exception as e:
            logger.warning(f"[Regime] Detection error: {e}")
            return self._default_reading(str(e))

    def _default_reading(self, reason: str) -> RegimeReading:
        return RegimeReading(
            regime     = "RANGING",
            thresholds = REGIMES["RANGING"],
            spy_trend  = "FLAT",
            spy_rsi    = 50.0,
            vix_level  = 20.0,
            spy_momentum = 0.0,
            confidence = 0.5,
            timestamp  = datetime.now(timezone.utc).isoformat(),
            reason     = reason,
        )

    def _rsi(self, close: pd.Series, period: int = 14) -> float:
        if len(close) < period + 1:
            return 50.0
        delta = close.diff().dropna()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        v = rsi.iloc[-1]
        return float(v) if not np.isnan(v) else 50.0


# ─────────────────────────────────────────────────────────────
# LAYER 2 — Momentum Strength Override
# ─────────────────────────────────────────────────────────────

@dataclass
class MomentumOverride:
    """
    Per-stock override when a strong price move is detected.
    Gates are relaxed specifically for that symbol — the rally IS the signal.
    """
    symbol:             str
    weekly_return:      float    # % change over 5 days
    monthly_return:     float    # % change over 20 days
    override_active:    bool
    conviction_floor:   float    # threshold drops to this
    confidence_floor:   float    # confidence drops to this
    min_strategies:     int      # can trade with just 1 strong strategy
    reason:             str


class MomentumOverrideDetector:
    """
    Detects when an individual stock has broken out so strongly
    that normal gate thresholds would wrongly block it.

    Trigger rules (any one suffices):
      - Weekly return  > +10%  → mild override
      - Weekly return  > +15%  → strong override
      - Monthly return > +20%  → strong override
      - Weekly + Monthly both positive + ADX > 30 → mild override

    Override threshold reductions:
                    Mild Override   Strong Override
      conviction    2.5 → 1.8      2.5 → 1.5
      confidence    65% → 60%      65% → 55%
      min_strats    2   → 2        2   → 1
    """

    # Trigger thresholds
    WEEKLY_MILD    =  10.0   # %
    WEEKLY_STRONG  =  15.0   # %
    MONTHLY_STRONG =  20.0   # %

    def analyse(self, symbol: str, df: pd.DataFrame) -> MomentumOverride:
        """Detect momentum override for a specific stock."""
        try:
            if df is None or len(df) < 22:
                return MomentumOverride(symbol, 0, 0, False, 2.5, 0.65, 2, "Not enough data")

            close = df["close"].astype(float) if "close" in df.columns else df.iloc[:,3].astype(float)
            price = float(close.iloc[-1])

            # Weekly return (5 trading days)
            weekly_ret  = float((price - close.iloc[-6])  / close.iloc[-6]  * 100) if len(close) > 6  else 0.0
            # Monthly return (20 trading days)
            monthly_ret = float((price - close.iloc[-21]) / close.iloc[-21] * 100) if len(close) > 21 else 0.0

            # Classify override level
            if weekly_ret >= self.WEEKLY_STRONG or monthly_ret >= self.MONTHLY_STRONG:
                level = "STRONG"
                conviction_floor = 1.5
                confidence_floor = 0.55
                min_strats       = 1
                reason = (f"Strong momentum override: "
                          f"weekly={weekly_ret:+.1f}% monthly={monthly_ret:+.1f}%")
            elif weekly_ret >= self.WEEKLY_MILD:
                level = "MILD"
                conviction_floor = 1.8
                confidence_floor = 0.60
                min_strats       = 2
                reason = (f"Mild momentum override: "
                          f"weekly={weekly_ret:+.1f}% monthly={monthly_ret:+.1f}%")
            else:
                return MomentumOverride(
                    symbol, round(weekly_ret, 2), round(monthly_ret, 2),
                    False, 2.5, 0.65, 2,
                    f"No override: weekly={weekly_ret:+.1f}% monthly={monthly_ret:+.1f}%"
                )

            return MomentumOverride(
                symbol           = symbol,
                weekly_return    = round(weekly_ret, 2),
                monthly_return   = round(monthly_ret, 2),
                override_active  = True,
                conviction_floor = conviction_floor,
                confidence_floor = confidence_floor,
                min_strategies   = min_strats,
                reason           = f"[{level}] {reason}",
            )

        except Exception as e:
            return MomentumOverride(symbol, 0, 0, False, 2.5, 0.65, 2, f"Error: {e}")
