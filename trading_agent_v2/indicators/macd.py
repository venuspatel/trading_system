# -*- coding: utf-8 -*-
"""
MACD - Moving Average Convergence Divergence
---------------------------------------------
Tracks the relationship between two EMAs (12 and 26 period by default).
The MACD line minus a 9-period signal line creates the histogram.

Signals:
  BUY  (STRONG)   : MACD crosses ABOVE signal line (bullish crossover)
  BUY  (MODERATE) : MACD above signal, histogram expanding
  SELL (STRONG)   : MACD crosses BELOW signal line (bearish crossover)
  SELL (MODERATE) : MACD below signal, histogram expanding negative
  NEUTRAL         : No crossover, histogram shrinking
"""

import pandas as pd
from .base import Signal, SignalDirection, SignalStrength


def calculate_macd(
    df:          pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> pd.DataFrame:
    """
    Compute MACD, Signal line, and Histogram.

    Returns:
        DataFrame with columns: macd, signal, histogram
    """
    fast_ema = df["close"].ewm(span=fast_period, adjust=False).mean()
    slow_ema = df["close"].ewm(span=slow_period, adjust=False).mean()

    macd_line   = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram   = macd_line - signal_line

    return pd.DataFrame({
        "macd":      macd_line,
        "signal":    signal_line,
        "histogram": histogram,
    }, index=df.index)


def macd_signal(
    symbol:        str,
    df:            pd.DataFrame,
    fast_period:   int = 12,
    slow_period:   int = 26,
    signal_period: int = 9,
) -> Signal:
    """
    Generate a trading signal from MACD crossovers and histogram.

    Args:
        symbol: Ticker symbol
        df:     OHLCV DataFrame from DataManager.get_bars_df()

    Returns:
        Signal with direction BUY / SELL / NEUTRAL
    """
    min_bars = slow_period + signal_period + 5
    if len(df) < min_bars:
        raise ValueError(f"Need at least {min_bars} bars, got {len(df)}")

    macd_df   = calculate_macd(df, fast_period, slow_period, signal_period)
    timestamp = df.index[-1].to_pydatetime()

    curr_macd  = float(macd_df["macd"].iloc[-1])
    curr_sig   = float(macd_df["signal"].iloc[-1])
    curr_hist  = float(macd_df["histogram"].iloc[-1])
    prev_macd  = float(macd_df["macd"].iloc[-2])
    prev_sig   = float(macd_df["signal"].iloc[-2])
    prev_hist  = float(macd_df["histogram"].iloc[-2])

    # Detect crossovers
    bullish_crossover = prev_macd <= prev_sig and curr_macd > curr_sig
    bearish_crossover = prev_macd >= prev_sig and curr_macd < curr_sig

    # Histogram momentum
    hist_expanding_positive = curr_hist > 0 and curr_hist > prev_hist
    hist_expanding_negative = curr_hist < 0 and curr_hist < prev_hist

    if bullish_crossover:
        direction = SignalDirection.BUY
        strength  = SignalStrength.STRONG
        reason    = f"MACD bullish crossover: MACD {curr_macd:.4f} crossed above signal {curr_sig:.4f}"
    elif hist_expanding_positive:
        direction = SignalDirection.BUY
        strength  = SignalStrength.MODERATE
        reason    = f"MACD histogram expanding positive ({curr_hist:.4f})"
    elif bearish_crossover:
        direction = SignalDirection.SELL
        strength  = SignalStrength.STRONG
        reason    = f"MACD bearish crossover: MACD {curr_macd:.4f} crossed below signal {curr_sig:.4f}"
    elif hist_expanding_negative:
        direction = SignalDirection.SELL
        strength  = SignalStrength.MODERATE
        reason    = f"MACD histogram expanding negative ({curr_hist:.4f})"
    else:
        direction = SignalDirection.NEUTRAL
        strength  = SignalStrength.NONE
        reason    = f"MACD no clear signal (hist={curr_hist:.4f})"

    return Signal(
        indicator = "MACD",
        symbol    = symbol,
        timestamp = timestamp,
        direction = direction,
        strength  = strength,
        value     = curr_macd,
        reason    = reason,
        details   = {
            "macd":               curr_macd,
            "signal":             curr_sig,
            "histogram":          curr_hist,
            "prev_histogram":     prev_hist,
            "bullish_crossover":  bullish_crossover,
            "bearish_crossover":  bearish_crossover,
            "above_zero":         curr_macd > 0,
        },
    )
