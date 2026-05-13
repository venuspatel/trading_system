# -*- coding: utf-8 -*-
"""
Candlestick Pattern Detector
------------------------------
Detects key single and multi-candle reversal/continuation patterns.

Patterns detected:
  Bullish: Hammer, Bullish Engulfing, Morning Star, Dragonfly Doji
  Bearish: Shooting Star, Bearish Engulfing, Evening Star, Gravestone Doji
  Neutral: Doji (indecision)
"""

import pandas as pd
from .base import Signal, SignalDirection, SignalStrength


def _body(o, c):
    return abs(c - o)

def _upper_shadow(o, c, h):
    return h - max(o, c)

def _lower_shadow(o, c, l):
    return min(o, c) - l

def _is_doji(o, c, h, l, threshold=0.1):
    total_range = h - l
    if total_range == 0:
        return False
    return _body(o, c) / total_range < threshold

def _is_hammer(o, c, h, l):
    body   = _body(o, c)
    lower  = _lower_shadow(o, c, l)
    upper  = _upper_shadow(o, c, h)
    total  = h - l
    if total == 0 or body == 0:
        return False
    return lower >= 2 * body and upper <= 0.1 * total

def _is_shooting_star(o, c, h, l):
    body   = _body(o, c)
    upper  = _upper_shadow(o, c, h)
    lower  = _lower_shadow(o, c, l)
    total  = h - l
    if total == 0 or body == 0:
        return False
    return upper >= 2 * body and lower <= 0.1 * total

def _is_bullish_engulfing(prev_o, prev_c, curr_o, curr_c):
    prev_bearish = prev_c < prev_o
    curr_bullish = curr_c > curr_o
    engulfs      = curr_o <= prev_c and curr_c >= prev_o
    return prev_bearish and curr_bullish and engulfs

def _is_bearish_engulfing(prev_o, prev_c, curr_o, curr_c):
    prev_bullish = prev_c > prev_o
    curr_bearish = curr_c < curr_o
    engulfs      = curr_o >= prev_c and curr_c <= prev_o
    return prev_bullish and curr_bearish and engulfs


def candlestick_signal(
    symbol: str,
    df:     pd.DataFrame,
) -> Signal:
    """
    Detect candlestick patterns on the last 3 candles.

    Args:
        symbol: Ticker symbol
        df:     OHLCV DataFrame from DataManager.get_bars_df()

    Returns:
        Signal with the detected pattern (or NEUTRAL if none found)
    """
    if len(df) < 3:
        raise ValueError(f"Need at least 3 bars for candlestick patterns, got {len(df)}")

    timestamp = df.index[-1].to_pydatetime()

    # Current candle
    o  = float(df["open"].iloc[-1])
    h  = float(df["high"].iloc[-1])
    l  = float(df["low"].iloc[-1])
    c  = float(df["close"].iloc[-1])

    # Previous candle
    po = float(df["open"].iloc[-2])
    ph = float(df["high"].iloc[-2])
    pl = float(df["low"].iloc[-2])
    pc = float(df["close"].iloc[-2])

    # Two candles ago
    ppo = float(df["open"].iloc[-3])
    ppc = float(df["close"].iloc[-3])

    pattern   = None
    direction = SignalDirection.NEUTRAL
    strength  = SignalStrength.NONE
    reason    = "No significant candlestick pattern"

    # --- Single candle patterns ---
    if _is_doji(o, c, h, l):
        pattern   = "Doji"
        direction = SignalDirection.NEUTRAL
        strength  = SignalStrength.WEAK
        reason    = "Doji candle -- market indecision, watch for breakout"

    elif _is_hammer(o, c, h, l) and pc < po:     # hammer after downtrend
        pattern   = "Hammer"
        direction = SignalDirection.BUY
        strength  = SignalStrength.MODERATE
        reason    = "Hammer pattern after bearish candle -- potential reversal up"

    elif _is_shooting_star(o, c, h, l) and pc > po:  # shooting star after uptrend
        pattern   = "Shooting Star"
        direction = SignalDirection.SELL
        strength  = SignalStrength.MODERATE
        reason    = "Shooting Star after bullish candle -- potential reversal down"

    # --- Two candle patterns ---
    elif _is_bullish_engulfing(po, pc, o, c):
        pattern   = "Bullish Engulfing"
        direction = SignalDirection.BUY
        strength  = SignalStrength.STRONG
        reason    = f"Bullish Engulfing: current candle ({o:.2f}-{c:.2f}) engulfs prior ({po:.2f}-{pc:.2f})"

    elif _is_bearish_engulfing(po, pc, o, c):
        pattern   = "Bearish Engulfing"
        direction = SignalDirection.SELL
        strength  = SignalStrength.STRONG
        reason    = f"Bearish Engulfing: current candle ({o:.2f}-{c:.2f}) engulfs prior ({po:.2f}-{pc:.2f})"

    # --- Three candle patterns ---
    # Morning Star: bearish, small doji/indecision, bullish
    elif (ppo > ppc and                        # first: bearish
          _is_doji(po, pc, ph, pl) and         # second: doji/small
          c > o and c > (ppo + ppc) / 2):      # third: bullish, closes above midpoint
        pattern   = "Morning Star"
        direction = SignalDirection.BUY
        strength  = SignalStrength.STRONG
        reason    = "Morning Star: 3-candle bullish reversal pattern"

    # Evening Star: bullish, small doji/indecision, bearish
    elif (ppc > ppo and                        # first: bullish
          _is_doji(po, pc, ph, pl) and         # second: doji/small
          c < o and c < (ppo + ppc) / 2):      # third: bearish, closes below midpoint
        pattern   = "Evening Star"
        direction = SignalDirection.SELL
        strength  = SignalStrength.STRONG
        reason    = "Evening Star: 3-candle bearish reversal pattern"

    return Signal(
        indicator = "CANDLE",
        symbol    = symbol,
        timestamp = timestamp,
        direction = direction,
        strength  = strength,
        value     = c,
        reason    = reason,
        details   = {
            "pattern":       pattern,
            "open":          o,
            "high":          h,
            "low":           l,
            "close":         c,
            "body_size":     _body(o, c),
            "upper_shadow":  _upper_shadow(o, c, h),
            "lower_shadow":  _lower_shadow(o, c, l),
            "is_bullish":    c > o,
        },
    )
