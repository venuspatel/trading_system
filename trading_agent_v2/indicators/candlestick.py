# -*- coding: utf-8 -*-
"""
Candlestick Pattern Detector (V2 Enhanced)
-------------------------------------------
V1 patterns: Hammer, Shooting Star, Bullish/Bearish Engulfing,
             Morning Star, Evening Star, Doji

V2 adds:     Inverted Hammer, Pin Bar (bull/bear), Harami,
             Harami Cross, Gravestone Doji, Dragonfly Doji
"""

import pandas as pd
from .base import Signal, SignalDirection, SignalStrength


def _body(o, c):         return abs(c - o)
def _upper_shadow(o,c,h): return h - max(o, c)
def _lower_shadow(o,c,l): return min(o, c) - l

def _is_doji(o, c, h, l, threshold=0.1):
    total_range = h - l
    if total_range == 0: return False
    return _body(o, c) / total_range < threshold

def _is_hammer(o, c, h, l):
    body  = _body(o, c)
    lower = _lower_shadow(o, c, l)
    upper = _upper_shadow(o, c, h)
    total = h - l
    if total == 0 or body == 0: return False
    return lower >= 2 * body and upper <= 0.1 * total

def _is_inverted_hammer(o, c, h, l):
    body  = _body(o, c)
    upper = _upper_shadow(o, c, h)
    lower = _lower_shadow(o, c, l)
    total = h - l
    if total == 0 or body == 0: return False
    return upper >= 2 * body and lower <= 0.1 * total and c >= o  # bullish close

def _is_shooting_star(o, c, h, l):
    body  = _body(o, c)
    upper = _upper_shadow(o, c, h)
    lower = _lower_shadow(o, c, l)
    total = h - l
    if total == 0 or body == 0: return False
    return upper >= 2 * body and lower <= 0.1 * total and c < o  # bearish close

def _is_pin_bar_bull(o, c, h, l):
    """Long lower wick >= 2x body, upper wick <= 0.5x body"""
    body  = _body(o, c)
    lower = _lower_shadow(o, c, l)
    upper = _upper_shadow(o, c, h)
    if body == 0: return False, 0
    ratio = lower / body
    return ratio >= 2.0 and upper <= body * 0.5, round(ratio, 1)

def _is_pin_bar_bear(o, c, h, l):
    """Long upper wick >= 2x body, lower wick <= 0.5x body"""
    body  = _body(o, c)
    upper = _upper_shadow(o, c, h)
    lower = _lower_shadow(o, c, l)
    if body == 0: return False, 0
    ratio = upper / body
    return ratio >= 2.0 and lower <= body * 0.5, round(ratio, 1)

def _is_bullish_engulfing(po, pc, o, c):
    return pc < po and c > o and o <= pc and c >= po

def _is_bearish_engulfing(po, pc, o, c):
    return pc > po and c < o and o >= pc and c <= po

def _is_harami(po, pc, o, c):
    """Second candle body inside first candle body"""
    body1 = _body(po, pc)
    if body1 == 0: return False, None, None
    inside = max(o,c) < max(po,pc) and min(o,c) > min(po,pc)
    if not inside: return False, None, None
    body2 = _body(o, c)
    is_cross = body2 / body1 < 0.10
    pattern = "Harami Cross" if is_cross else "Harami"
    direction = "bullish" if pc < po else "bearish"
    return True, pattern, direction

def _is_gravestone_doji(o, c, h, l):
    full_range = h - l
    if full_range == 0: return False
    body = _body(o, c)
    if body / full_range > 0.10: return False
    upper = _upper_shadow(o, c, h)
    lower = _lower_shadow(o, c, l)
    return upper > full_range * 0.7 and lower < full_range * 0.1

def _is_dragonfly_doji(o, c, h, l):
    full_range = h - l
    if full_range == 0: return False
    body = _body(o, c)
    if body / full_range > 0.10: return False
    upper = _upper_shadow(o, c, h)
    lower = _lower_shadow(o, c, l)
    return lower > full_range * 0.7 and upper < full_range * 0.1


def candlestick_signal(symbol: str, df: pd.DataFrame) -> Signal:
    if len(df) < 3:
        raise ValueError(f"Need at least 3 bars, got {len(df)}")

    timestamp = df.index[-1].to_pydatetime()

    o   = float(df["open"].iloc[-1])
    h   = float(df["high"].iloc[-1])
    l   = float(df["low"].iloc[-1])
    c   = float(df["close"].iloc[-1])
    po  = float(df["open"].iloc[-2])
    ph  = float(df["high"].iloc[-2])
    pl  = float(df["low"].iloc[-2])
    pc  = float(df["close"].iloc[-2])
    ppo = float(df["open"].iloc[-3])
    ppc = float(df["close"].iloc[-3])

    pattern   = None
    direction = SignalDirection.NEUTRAL
    strength  = SignalStrength.NONE
    reason    = "No significant candlestick pattern"

    # ── Single candle ────────────────────────────────────────

    if _is_gravestone_doji(o, c, h, l):
        pattern, direction, strength = "Gravestone Doji", SignalDirection.SELL, SignalStrength.MODERATE
        reason = "Gravestone Doji — bearish rejection at highs"

    elif _is_dragonfly_doji(o, c, h, l):
        pattern, direction, strength = "Dragonfly Doji", SignalDirection.BUY, SignalStrength.MODERATE
        reason = "Dragonfly Doji — bullish rejection at lows"

    elif _is_doji(o, c, h, l):
        pattern, direction, strength = "Doji", SignalDirection.NEUTRAL, SignalStrength.WEAK
        reason = "Doji — market indecision"

    elif _is_hammer(o, c, h, l) and pc < po:
        pattern, direction, strength = "Hammer", SignalDirection.BUY, SignalStrength.MODERATE
        reason = "Hammer after bearish candle — potential reversal up"

    elif _is_inverted_hammer(o, c, h, l) and pc < po:
        pattern, direction, strength = "Inverted Hammer", SignalDirection.BUY, SignalStrength.MODERATE
        reason = "Inverted Hammer after bearish candle — potential reversal up"

    elif _is_shooting_star(o, c, h, l) and pc > po:
        pattern, direction, strength = "Shooting Star", SignalDirection.SELL, SignalStrength.MODERATE
        reason = "Shooting Star after bullish candle — potential reversal down"

    else:
        # Check pin bars
        bull_pin, bull_ratio = _is_pin_bar_bull(o, c, h, l)
        bear_pin, bear_ratio = _is_pin_bar_bear(o, c, h, l)

        if bull_pin and pc < po:
            pattern   = f"Pin Bar Bullish"
            direction = SignalDirection.BUY
            strength  = SignalStrength.STRONG
            reason    = f"Bullish Pin Bar — lower wick {bull_ratio}x body, rejection of lows"

        elif bear_pin and pc > po:
            pattern   = f"Pin Bar Bearish"
            direction = SignalDirection.SELL
            strength  = SignalStrength.STRONG
            reason    = f"Bearish Pin Bar — upper wick {bear_ratio}x body, rejection of highs"

        # ── Two candle patterns ───────────────────────────────
        elif _is_bullish_engulfing(po, pc, o, c):
            pattern, direction, strength = "Bullish Engulfing", SignalDirection.BUY, SignalStrength.STRONG
            reason = f"Bullish Engulfing: ({o:.2f}-{c:.2f}) engulfs ({po:.2f}-{pc:.2f})"

        elif _is_bearish_engulfing(po, pc, o, c):
            pattern, direction, strength = "Bearish Engulfing", SignalDirection.SELL, SignalStrength.STRONG
            reason = f"Bearish Engulfing: ({o:.2f}-{c:.2f}) engulfs ({po:.2f}-{pc:.2f})"

        else:
            harami, h_pattern, h_dir = _is_harami(po, pc, o, c)
            if harami:
                pattern   = h_pattern
                direction = SignalDirection.BUY if h_dir == "bullish" else SignalDirection.SELL
                strength  = SignalStrength.STRONG
                reason    = f"{h_pattern} — {h_dir} reversal signal"

            # ── Three candle patterns ─────────────────────────
            elif (ppo > ppc and _is_doji(po, pc, ph, pl) and
                  c > o and c > (ppo + ppc) / 2):
                pattern, direction, strength = "Morning Star", SignalDirection.BUY, SignalStrength.STRONG
                reason = "Morning Star — 3-candle bullish reversal"

            elif (ppc > ppo and _is_doji(po, pc, ph, pl) and
                  c < o and c < (ppo + ppc) / 2):
                pattern, direction, strength = "Evening Star", SignalDirection.SELL, SignalStrength.STRONG
                reason = "Evening Star — 3-candle bearish reversal"

    return Signal(
        indicator = "CANDLE",
        symbol    = symbol,
        timestamp = timestamp,
        direction = direction,
        strength  = strength,
        value     = c,
        reason    = reason,
        details   = {
            "pattern":      pattern,
            "open":         o,
            "high":         h,
            "low":          l,
            "close":        c,
            "body_size":    _body(o, c),
            "upper_shadow": _upper_shadow(o, c, h),
            "lower_shadow": _lower_shadow(o, c, l),
            "is_bullish":   c > o,
        },
    )
