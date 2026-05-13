# -*- coding: utf-8 -*-
"""
Support & Resistance Levels
-----------------------------
Identifies key price zones by finding swing highs and lows over a
rolling window. Price approaching these zones generates signals.

Signals:
  BUY  (STRONG)   : Price bouncing off a strong support level
  BUY  (MODERATE) : Price approaching support from above
  SELL (STRONG)   : Price rejected at a strong resistance level
  SELL (MODERATE) : Price approaching resistance from below
  NEUTRAL         : Price in open space between levels
"""

import pandas as pd
import numpy as np
from typing import List, Tuple
from .base import Signal, SignalDirection, SignalStrength


def find_support_resistance(
    df:          pd.DataFrame,
    window:      int   = 10,    # bars on each side to confirm swing
    n_levels:    int   = 5,     # how many levels to return
    tolerance:   float = 0.01,  # 1% price tolerance for clustering
) -> Tuple[List[float], List[float]]:
    """
    Find significant support and resistance price levels.

    Args:
        df:        OHLCV DataFrame
        window:    Number of bars on each side to confirm a swing point
        n_levels:  Maximum number of levels to return
        tolerance: % tolerance for merging nearby levels into one

    Returns:
        (support_levels, resistance_levels) — sorted ascending
    """
    highs = df["high"].values
    lows  = df["low"].values

    swing_highs = []
    swing_lows  = []

    for i in range(window, len(df) - window):
        # Swing high: highest point in the window
        if highs[i] == max(highs[i - window: i + window + 1]):
            swing_highs.append(highs[i])
        # Swing low: lowest point in the window
        if lows[i] == min(lows[i - window: i + window + 1]):
            swing_lows.append(lows[i])

    def cluster_levels(levels: List[float]) -> List[float]:
        """Merge levels within tolerance% of each other."""
        if not levels:
            return []
        levels = sorted(levels)
        clustered = [levels[0]]
        for lvl in levels[1:]:
            if abs(lvl - clustered[-1]) / clustered[-1] > tolerance:
                clustered.append(lvl)
            else:
                clustered[-1] = (clustered[-1] + lvl) / 2  # average
        return clustered

    support    = cluster_levels(swing_lows)[-n_levels:]
    resistance = cluster_levels(swing_highs)[-n_levels:]

    return sorted(support), sorted(resistance)


def support_resistance_signal(
    symbol:    str,
    df:        pd.DataFrame,
    window:    int   = 10,
    proximity: float = 0.02,   # within 2% of a level counts as "near"
) -> Signal:
    """
    Generate a signal based on price proximity to support/resistance.

    Args:
        symbol:    Ticker symbol
        df:        OHLCV DataFrame from DataManager.get_bars_df()
        window:    Swing point detection window
        proximity: How close (%) price must be to a level to trigger

    Returns:
        Signal with direction BUY / SELL / NEUTRAL
    """
    min_bars = window * 3
    if len(df) < min_bars:
        raise ValueError(f"Need at least {min_bars} bars for S/R, got {len(df)}")

    timestamp  = df.index[-1].to_pydatetime()
    price      = float(df["close"].iloc[-1])
    prev_price = float(df["close"].iloc[-2])

    supports, resistances = find_support_resistance(df, window)

    # Find nearest levels
    nearest_support    = max([s for s in supports    if s <= price * 1.02], default=None)
    nearest_resistance = min([r for r in resistances if r >= price * 0.98], default=None)

    direction = SignalDirection.NEUTRAL
    strength  = SignalStrength.NONE
    reason    = f"Price {price:.2f} in open range"
    near_level = None

    if nearest_support:
        dist_to_support = (price - nearest_support) / price
        if dist_to_support < proximity:
            near_level = nearest_support
            if price > prev_price:       # bouncing up from support
                direction = SignalDirection.BUY
                strength  = SignalStrength.STRONG
                reason    = f"Price bouncing off support at {nearest_support:.2f} (dist={dist_to_support:.1%})"
            else:                        # approaching support
                direction = SignalDirection.BUY
                strength  = SignalStrength.MODERATE
                reason    = f"Price approaching support at {nearest_support:.2f} (dist={dist_to_support:.1%})"

    if nearest_resistance and direction == SignalDirection.NEUTRAL:
        dist_to_resistance = (nearest_resistance - price) / price
        if dist_to_resistance < proximity:
            near_level = nearest_resistance
            if price < prev_price:       # being rejected at resistance
                direction = SignalDirection.SELL
                strength  = SignalStrength.STRONG
                reason    = f"Price rejected at resistance {nearest_resistance:.2f} (dist={dist_to_resistance:.1%})"
            else:                        # approaching resistance
                direction = SignalDirection.SELL
                strength  = SignalStrength.MODERATE
                reason    = f"Price approaching resistance at {nearest_resistance:.2f} (dist={dist_to_resistance:.1%})"

    return Signal(
        indicator = "SR",
        symbol    = symbol,
        timestamp = timestamp,
        direction = direction,
        strength  = strength,
        value     = price,
        reason    = reason,
        details   = {
            "price":               price,
            "support_levels":      supports,
            "resistance_levels":   resistances,
            "nearest_support":     nearest_support,
            "nearest_resistance":  nearest_resistance,
            "near_level":          near_level,
        },
    )
