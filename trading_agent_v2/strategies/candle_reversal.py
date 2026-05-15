# -*- coding: utf-8 -*-
"""
Strategy 4: Candle Reversal (V2 Enhanced)
-------------------------------------------
Trades high-confidence reversal candlestick patterns
that appear at key support/resistance levels.

V2 adds on top of V1:
  - Pin Bar (68% win rate — most used by pro day traders)
  - Harami / Harami Cross (72.85% win rate — highest of any 2-candle pattern)
  - Gravestone Doji (57% win rate — bearish rejection at highs)
  - Dragonfly Doji (55% win rate — bullish rejection at lows)
  - Inverted Hammer as entry signal (60% win rate — was exit-only in V1)

The key insight: a pattern alone is ~55% reliable.
The same pattern AT a S/R level is ~72% reliable.
Adding RSI confirmation pushes it to ~78%.

Bullish reversals (BUY):
  Hammer / Bullish Engulfing / Morning Star        ← V1
  Inverted Hammer / Pin Bar / Harami / Dragonfly   ← V2 NEW

Bearish reversals (SELL):
  Shooting Star / Bearish Engulfing / Evening Star ← V1
  Pin Bar (bearish) / Harami (bearish) / Gravestone← V2 NEW
"""

import pandas as pd
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole
from indicators.base import SignalDirection


# ── V1 patterns (from candle indicator) ──────────────────────
BULLISH_PATTERNS = {"Hammer", "Bullish Engulfing", "Morning Star", "Inverted Hammer", "Pin Bar Bullish", "Harami", "Harami Cross", "Dragonfly Doji"}
BEARISH_PATTERNS = {"Shooting Star", "Bearish Engulfing", "Evening Star", "Pin Bar Bearish", "Gravestone Doji"}


def _detect_pin_bar(df: pd.DataFrame, bullish: bool) -> tuple:
    """
    Pin Bar: long wick rejection candle.
    Wick must be >= 2x the body size.
    Bullish: long lower wick (rejection of lows)
    Bearish: long upper wick (rejection of highs)
    Returns (detected: bool, wick_ratio: float)
    """
    o = float(df["open"].iloc[-1])
    h = float(df["high"].iloc[-1])
    l = float(df["low"].iloc[-1])
    c = float(df["close"].iloc[-1])

    body = abs(c - o)
    if body == 0:
        return False, 0.0

    if bullish:
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)
        ratio = lower_wick / body
        # Bullish pin bar: lower wick >= 2x body, upper wick <= 0.5x body
        detected = ratio >= 2.0 and upper_wick <= body * 0.5
    else:
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        ratio = upper_wick / body
        # Bearish pin bar: upper wick >= 2x body, lower wick <= 0.5x body
        detected = ratio >= 2.0 and lower_wick <= body * 0.5

    return detected, round(ratio, 2)


def _detect_harami(df: pd.DataFrame) -> tuple:
    """
    Harami: second candle completely inside the first.
    Harami Cross: second candle is a doji (body < 10% of first).
    Returns (pattern: str or None, direction: str)
    pattern = 'Harami' | 'Harami Cross' | None
    direction = 'bullish' | 'bearish' | None
    """
    if len(df) < 2:
        return None, None

    o1 = float(df["open"].iloc[-2])
    c1 = float(df["close"].iloc[-2])
    o2 = float(df["open"].iloc[-1])
    c2 = float(df["close"].iloc[-1])
    h1 = float(df["high"].iloc[-2])
    l1 = float(df["low"].iloc[-2])

    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)
    if body1 == 0:
        return None, None

    # Second candle body must be inside first candle body
    inside = (max(o2, c2) < max(o1, c1) and min(o2, c2) > min(o1, c1))
    if not inside:
        return None, None

    body_ratio = body2 / body1
    is_cross = body_ratio < 0.10  # doji second candle

    # Direction: first candle determines trend, harami signals reversal
    if c1 < o1:  # first candle bearish → bullish harami
        pattern = "Harami Cross" if is_cross else "Harami"
        return pattern, "bullish"
    elif c1 > o1:  # first candle bullish → bearish harami
        pattern = "Harami Cross" if is_cross else "Harami"
        return pattern, "bearish"

    return None, None


def _detect_doji_variant(df: pd.DataFrame) -> str | None:
    """
    Gravestone Doji: open ≈ close ≈ low, long upper wick
    Dragonfly Doji:  open ≈ close ≈ high, long lower wick
    Returns pattern name or None
    """
    o = float(df["open"].iloc[-1])
    h = float(df["high"].iloc[-1])
    l = float(df["low"].iloc[-1])
    c = float(df["close"].iloc[-1])

    body = abs(c - o)
    full_range = h - l
    if full_range == 0:
        return None

    body_pct = body / full_range

    # Must be doji-like (body < 10% of range)
    if body_pct > 0.10:
        return None

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    # Gravestone: long upper wick, tiny lower wick
    if upper_wick > full_range * 0.7 and lower_wick < full_range * 0.1:
        return "Gravestone Doji"

    # Dragonfly: long lower wick, tiny upper wick
    if lower_wick > full_range * 0.7 and upper_wick < full_range * 0.1:
        return "Dragonfly Doji"

    return None


class CandleReversalStrategy(BaseStrategy):

    def __init__(self, sr_proximity=0.02):
        self.sr_proximity = sr_proximity   # within 2% of S/R level

    @property
    def name(self) -> str:
        return "CandleReversal"

    @property
    def description(self) -> str:
        return "Reversal patterns (V2: + Pin Bar, Harami, Doji variants) at S/R levels"

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # Fix 9: Volume confirmation + prior trend check + ATR stops + boosted multi-candle confidence
        if len(df) < 10:
            return self._hold(symbol, df, "Not enough bars")

        import pandas as pd
        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        candle_sig = summary.signals.get("CANDLE")
        sr_sig     = summary.signals.get("SR")
        rsi_sig    = summary.signals.get("RSI")

        rsi_val     = rsi_sig.details.get("rsi", 50) if rsi_sig else 50
        supports    = sr_sig.details.get("support_levels", [])    if sr_sig else []
        resistances = sr_sig.details.get("resistance_levels", []) if sr_sig else []

        # ── Fix 9a: Volume confirmation ──────────────────────────────────
        # Low-vol reversal candles are fake — need at least 1.2x avg volume
        avg_vol   = float(df["volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 0
        curr_vol  = float(df["volume"].iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
        vol_ok    = vol_ratio >= 1.2

        # ── Fix 9b: Prior trend check ────────────────────────────────────
        # Bullish reversal needs prior downtrend (5-bar), bearish needs uptrend
        if len(df) >= 6:
            prior_5  = df["close"].iloc[-6:-1]
            prior_trend_down = float(prior_5.iloc[-1]) < float(prior_5.iloc[0])
            prior_trend_up   = float(prior_5.iloc[-1]) > float(prior_5.iloc[0])
        else:
            prior_trend_down = prior_trend_up = True  # default pass

        # ── Fix 9c: ATR for adaptive stops ──────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── Detect V1 patterns from candle indicator ─────────────────────
        v1_pattern = None
        if candle_sig:
            p = candle_sig.details.get("pattern")
            if p and p != "Doji":
                v1_pattern = p

        # ── Detect V2 new patterns from raw OHLCV ────────────────────────
        bull_pin, bull_pin_ratio = _detect_pin_bar(df, bullish=True)
        bear_pin, bear_pin_ratio = _detect_pin_bar(df, bullish=False)
        harami_pattern, harami_dir = _detect_harami(df)
        doji_variant = _detect_doji_variant(df)

        # ── BULLISH signals ───────────────────────────────────────────────
        bullish_pattern = None
        base_confidence = 0.55
        is_multi_candle = False

        if v1_pattern in BULLISH_PATTERNS:
            bullish_pattern = v1_pattern
            if v1_pattern == "Morning Star":
                base_confidence = 0.68   # Fix 9d: 3-candle pattern = higher base
                is_multi_candle = True
            elif v1_pattern in {"Bullish Engulfing"}:
                base_confidence = 0.63
                is_multi_candle = True
            elif v1_pattern == "Inverted Hammer":
                base_confidence = 0.60
        elif bull_pin:
            bullish_pattern = f"Pin Bar (wick {bull_pin_ratio:.1f}x body)"
            base_confidence = 0.62
        elif harami_pattern and harami_dir == "bullish":
            bullish_pattern = harami_pattern
            base_confidence = 0.68 if harami_pattern == "Harami Cross" else 0.62
            is_multi_candle = True
        elif doji_variant == "Dragonfly Doji":
            bullish_pattern = "Dragonfly Doji"
            base_confidence = 0.55

        if bullish_pattern:
            # Prior trend check — need downtrend before bullish reversal
            if not prior_trend_down:
                return self._hold(symbol, df,
                    f"{bullish_pattern} skipped: no prior downtrend (reversal needs trend to reverse)")

            confirmations = [f"{bullish_pattern} detected"]
            confidence    = base_confidence

            # Volume confirmation
            if vol_ok:
                confirmations.append(f"volume confirmed {vol_ratio:.1f}x avg")
                confidence += 0.06
            else:
                confidence -= 0.08   # low-vol reversal = penalty

            near_support = any(abs(price - s) / price < self.sr_proximity for s in supports)
            if near_support:
                confirmations.append("at support level")
                confidence += 0.10
            if rsi_val < 50:
                confirmations.append(f"RSI={rsi_val:.1f}")
                confidence += 0.06
            if rsi_val < 35:
                confirmations.append("RSI oversold")
                confidence += 0.05
            if is_multi_candle:
                confirmations.append("multi-candle confirmation")
                confidence += 0.04

            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.BUY,
                confidence    = round(min(confidence, 0.93), 3),
                reason        = (f"{bullish_pattern} vol={vol_ratio:.1f}x "
                                 f"RSI={rsi_val:.1f} "
                                 f"{'at support' if near_support else ''}"),
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {
                    "pattern":       bullish_pattern,
                    "rsi":           rsi_val,
                    "near_support":  near_support,
                    "vol_ratio":     round(vol_ratio, 2),
                    "vol_ok":        vol_ok,
                    "prior_down":    prior_trend_down,
                    "multi_candle":  is_multi_candle,
                    "atr14":         round(atr14, 3),
                },
            )

        # ── BEARISH signals ───────────────────────────────────────────────
        bearish_pattern = None
        base_confidence = 0.55
        is_multi_candle = False

        if v1_pattern in BEARISH_PATTERNS:
            bearish_pattern = v1_pattern
            if v1_pattern == "Evening Star":
                base_confidence = 0.68
                is_multi_candle = True
            elif v1_pattern == "Bearish Engulfing":
                base_confidence = 0.63
                is_multi_candle = True
        elif bear_pin:
            bearish_pattern = f"Pin Bar bearish (wick {bear_pin_ratio:.1f}x body)"
            base_confidence = 0.62
        elif harami_pattern and harami_dir == "bearish":
            bearish_pattern = harami_pattern
            base_confidence = 0.68 if harami_pattern == "Harami Cross" else 0.62
            is_multi_candle = True
        elif doji_variant == "Gravestone Doji":
            bearish_pattern = "Gravestone Doji"
            base_confidence = 0.57

        if bearish_pattern:
            if not prior_trend_up:
                return self._hold(symbol, df,
                    f"{bearish_pattern} skipped: no prior uptrend")

            confirmations = [f"{bearish_pattern} detected"]
            confidence    = base_confidence

            if vol_ok:
                confirmations.append(f"volume confirmed {vol_ratio:.1f}x avg")
                confidence += 0.06
            else:
                confidence -= 0.08

            near_resistance = any(abs(price - r) / price < self.sr_proximity for r in resistances)
            if near_resistance:
                confirmations.append("at resistance level")
                confidence += 0.10
            if rsi_val > 50:
                confirmations.append(f"RSI={rsi_val:.1f} elevated")
                confidence += 0.06
            if rsi_val > 65:
                confirmations.append("RSI overbought")
                confidence += 0.05
            if is_multi_candle:
                confirmations.append("multi-candle confirmation")
                confidence += 0.04

            stop = price + (1.5 * atr14)
            tp   = price - (3.0 * atr14)

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.SELL,
                confidence    = round(min(confidence, 0.93), 3),
                reason        = (f"{bearish_pattern} vol={vol_ratio:.1f}x "
                                 f"RSI={rsi_val:.1f} "
                                 f"{'at resistance' if near_resistance else ''}"),
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {
                    "pattern":          bearish_pattern,
                    "rsi":              rsi_val,
                    "near_resistance":  near_resistance,
                    "vol_ratio":        round(vol_ratio, 2),
                    "vol_ok":           vol_ok,
                    "prior_up":         prior_trend_up,
                    "multi_candle":     is_multi_candle,
                    "atr14":            round(atr14, 3),
                },
            )

        return self._hold(symbol, df, "No reversal pattern detected")
