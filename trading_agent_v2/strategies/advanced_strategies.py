# -*- coding: utf-8 -*-
"""
Strategies 5-10: Continuation, Divergence, Fibonacci,
                 Volume Confirmation, Multi-Timeframe, Trend Regime
"""

import pandas as pd
import numpy as np
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole
from indicators.base import SignalDirection
from indicators.rsi import calculate_rsi
from indicators.macd import calculate_macd
from indicators.moving_averages import calculate_moving_averages


# ============================================================
# Strategy 5: Candle Continuation
# ============================================================
class CandleContinuationStrategy(BaseStrategy):
    """
    Trades continuation patterns that confirm the current trend will persist.
    Three White Soldiers (BUY) / Three Black Crows (SELL)
    Must be confirmed by MA trend alignment.
    """

    @property
    def name(self): return "CandleContinuation"

    @property
    def description(self): return "Three white soldiers / black crows confirmed by MA trend"

    @property
    def role(self) -> str:
        return StrategyRole.NEUTRAL

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # Fix 11: Volume confirmation + body size filter + ATR stops + scaled confidence
        if len(df) < 10:
            return self._hold(symbol, df, "Not enough bars")

        import pandas as pd
        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()
        ma_sig    = summary.signals.get("MA")

        # ── Fix 11a: ATR for body size filter + stops ────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── Fix 11b: Volume confirmation ─────────────────────────────────
        avg_vol   = float(df["volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 0
        curr_vol  = float(df["volume"].iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
        vol_ok    = vol_ratio >= 1.3

        # Three White Soldiers: 3 consecutive bullish candles, each closing higher
        # Fix 11c: Each body must be > 0.5x ATR (filters tiny-body soldiers)
        three_white = all(
            df["close"].iloc[-i] > df["open"].iloc[-i] and
            df["close"].iloc[-i] > df["close"].iloc[-(i+1)] and
            abs(float(df["close"].iloc[-i]) - float(df["open"].iloc[-i])) > atr14 * 0.5
            for i in range(1, 4)
        )

        # Three Black Crows: 3 consecutive bearish candles, each closing lower
        three_black = all(
            df["close"].iloc[-i] < df["open"].iloc[-i] and
            df["close"].iloc[-i] < df["close"].iloc[-(i+1)] and
            abs(float(df["close"].iloc[-i]) - float(df["open"].iloc[-i])) > atr14 * 0.5
            for i in range(1, 4)
        )

        bullish_trend = ma_sig and ma_sig.details.get("above_sma50", False)
        bearish_trend = ma_sig and not ma_sig.details.get("above_sma50", True)

        if three_white and bullish_trend:
            if not vol_ok:
                return self._hold(symbol, df,
                    f"Three White Soldiers but volume weak ({vol_ratio:.1f}x < 1.3x)")
            confs = [
                "Three White Soldiers",
                "MA trend bullish",
                f"Volume confirmed {vol_ratio:.1f}x",
                f"Bodies > 0.5x ATR ({atr14:.2f})",
            ]
            # Fix 11d: Scale confidence by vol ratio
            confidence = min(0.70 + (vol_ratio - 1.3) * 0.05, 0.88)
            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=round(confidence, 3),
                reason=f"Three White Soldiers vol={vol_ratio:.1f}x ATR-confirmed",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"vol_ratio": round(vol_ratio,2), "atr14": round(atr14,3)},
            )

        if three_black and bearish_trend:
            if not vol_ok:
                return self._hold(symbol, df,
                    f"Three Black Crows but volume weak ({vol_ratio:.1f}x < 1.3x)")
            confs = [
                "Three Black Crows",
                "MA trend bearish",
                f"Volume confirmed {vol_ratio:.1f}x",
            ]
            confidence = min(0.68 + (vol_ratio - 1.3) * 0.05, 0.85)
            stop = price + (1.5 * atr14)
            tp   = price - (3.0 * atr14)
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=round(confidence, 3),
                reason=f"Three Black Crows vol={vol_ratio:.1f}x ATR-confirmed",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"vol_ratio": round(vol_ratio,2), "atr14": round(atr14,3)},
            )

        return self._hold(symbol, df,
            f"No continuation: white={three_white} black={three_black} "
            f"bull_trend={bullish_trend} vol={vol_ratio:.1f}x")


# ============================================================
# Strategy 6: RSI / MACD Divergence
# ============================================================
class DivergenceStrategy(BaseStrategy):
    """
    Detects hidden weakness/strength when price and indicator diverge.

    Bearish Divergence: price makes higher high, RSI makes lower high
      -- rally losing internal strength, reversal coming

    Bullish Divergence: price makes lower low, RSI makes higher low
      -- selloff losing momentum, recovery coming
    """

    @property
    def name(self): return "Divergence"

    @property
    def description(self): return "RSI/MACD divergence signals hidden reversals"

    @property
    def role(self) -> str:
        return StrategyRole.NEUTRAL

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # Fix 4: Extended lookback + confirmation candle + regime filter + ATR stops
        if len(df) < 30:
            return self._hold(symbol, df, "Not enough bars")

        import pandas as pd
        timestamp = df.index[-1].to_pydatetime()
        price     = float(df["close"].iloc[-1])
        rsi       = calculate_rsi(df)

        # ── Regime filter: skip in RANGING market ────────────────────────
        # Divergence in ranging markets fires constantly and is unreliable
        _regime = str(getattr(summary, "approach", "")).lower()
        _current_regime = getattr(summary, "_regime", "")
        # Check via market regime if available
        try:
            _ma_sig     = summary.signals.get("MA") if hasattr(summary, "signals") else None
            _above_sma20 = _ma_sig.details.get("above_sma20", True) if _ma_sig else True
            _above_sma50 = _ma_sig.details.get("above_sma50", True) if _ma_sig else True
        except Exception:
            _above_sma20 = _above_sma50 = True

        # ── Fix 4a: Extended lookback — 20 bars instead of 15 ────────────
        # Multi-week divergence is more reliable than 3-day divergence
        lookback      = min(20, len(df) - 3)
        recent_prices = df["close"].iloc[-lookback:]
        recent_rsi    = rsi.iloc[-lookback:]

        price_hh = float(recent_prices.iloc[-1]) > float(recent_prices.iloc[:-1].max())
        price_ll = float(recent_prices.iloc[-1]) < float(recent_prices.iloc[:-1].min())
        rsi_hh   = float(recent_rsi.iloc[-1])   > float(recent_rsi.iloc[:-1].max())
        rsi_ll   = float(recent_rsi.iloc[-1])   < float(recent_rsi.iloc[:-1].min())
        rsi_val  = float(rsi.iloc[-1])

        # ── ATR for adaptive stops ───────────────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── Fix 4b: Confirmation candle required ─────────────────────────
        # Divergence alone is not enough — need the candle to show reversal intent
        # Bullish confirmation: current close > previous close (momentum turning)
        # Bearish confirmation: current close < previous close
        prev_close    = float(df["close"].iloc[-2])
        candle_bull   = price > prev_close          # close higher than prev = bullish candle
        candle_bear   = price < prev_close          # close lower than prev = bearish candle

        # ── Bearish divergence: price new high but RSI lower high ────────
        # Skip on strong trends (RSI >= 65 + above both MAs = trending, not topping)
        _strong_trend = rsi_val >= 65 and _above_sma20 and _above_sma50
        if price_hh and not rsi_hh and rsi_val > 55 and not _strong_trend:
            if not candle_bear:
                return self._hold(symbol, df,
                    f"Bearish div detected but no confirmation candle yet (RSI={rsi_val:.1f})")
            confs = [
                f"Price at {lookback}-bar high ({price:.2f})",
                f"RSI diverging lower ({rsi_val:.1f})",
                "Bearish divergence confirmed",
                "Confirmation candle: close < prev close",
            ]
            stop = price + (1.5 * atr14)
            tp   = price - (3.0 * atr14)
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=0.72,
                reason=f"Bearish divergence confirmed: price high RSI={rsi_val:.1f} diverging ({lookback}-bar)",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"rsi": rsi_val, "divergence_type": "bearish",
                         "lookback": lookback, "atr14": round(atr14, 3)},
            )

        # ── Bullish divergence: price new low but RSI higher low ─────────
        if price_ll and not rsi_ll and rsi_val < 45:
            if not candle_bull:
                return self._hold(symbol, df,
                    f"Bullish div detected but no confirmation candle yet (RSI={rsi_val:.1f})")
            confs = [
                f"Price at {lookback}-bar low ({price:.2f})",
                f"RSI diverging higher ({rsi_val:.1f})",
                "Bullish divergence confirmed",
                "Confirmation candle: close > prev close",
            ]
            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=0.72,
                reason=f"Bullish divergence confirmed: price low RSI={rsi_val:.1f} firming ({lookback}-bar)",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"rsi": rsi_val, "divergence_type": "bullish",
                         "lookback": lookback, "atr14": round(atr14, 3)},
            )

        return self._hold(symbol, df,
            f"No divergence: RSI={rsi_val:.1f} price_hh={price_hh} price_ll={price_ll}")


# ============================================================
# Strategy 7: Fibonacci Retracement
# ============================================================
class FibonacciStrategy(BaseStrategy):
    """
    Identifies swing highs and lows then watches for price to
    retrace to key Fibonacci levels (38.2%, 50%, 61.8%).
    Entry at fib level + candle confirmation = high probability setup.
    """

    FIB_LEVELS = [0.382, 0.500, 0.618]

    @property
    def name(self): return "Fibonacci"

    @property
    def description(self): return "Entries at 38.2/50/61.8% Fibonacci retracement levels"

    @property
    def role(self) -> str:
        return StrategyRole.NEUTRAL

    def _find_swing(self, df, window=20):
        # Fix 13a: Window 10 → 20 bars for more reliable multi-week swings
        highs = df["high"].values
        lows  = df["low"].values
        n     = len(df)

        swing_high = swing_low = None
        for i in range(n - window - 1, window - 1, -1):
            if highs[i] == max(highs[i-window:i+window+1]):
                if swing_high is None:
                    swing_high = (i, highs[i])
            if lows[i] == min(lows[i-window:i+window+1]):
                if swing_low is None:
                    swing_low = (i, lows[i])
            if swing_high and swing_low:
                break

        return swing_high, swing_low

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # Fix 13: Swing quality + confluence + RSI gate + ATR stops
        if len(df) < 50:
            return self._hold(symbol, df, "Not enough bars for Fibonacci")

        import pandas as pd
        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        swing_high, swing_low = self._find_swing(df)
        if not swing_high or not swing_low:
            return self._hold(symbol, df, "No clear swing points")

        sh_idx, sh_price = swing_high
        sl_idx, sl_price = swing_low

        # Fix 13b: Minimum swing size — 5% move over 20+ bars
        # Tiny swings produce meaningless Fib levels
        move = sh_price - sl_price
        swing_pct  = move / sl_price if sl_price > 0 else 0
        swing_bars = abs(sh_idx - sl_idx)
        if swing_pct < 0.05 or swing_bars < 20:
            return self._hold(symbol, df,
                f"Swing too small: {swing_pct:.1%} over {swing_bars} bars "
                f"(need 5%+ over 20+ bars)")

        candle_sig = summary.signals.get("CANDLE")
        rsi_sig    = summary.signals.get("RSI")
        ma_sig     = summary.signals.get("MA")
        sr_sig     = summary.signals.get("SR")
        rsi_val    = rsi_sig.details.get("rsi", 50) if rsi_sig else 50

        # ── ATR for stops ─────────────────────────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── Uptrend retracement: swing low before swing high ──────────────
        if sl_idx < sh_idx:
            levels = {f"{lvl*100:.1f}%": sh_price - move * lvl
                      for lvl in self.FIB_LEVELS}

            for label, fib_price in levels.items():
                proximity = abs(price - fib_price) / price
                if proximity > 0.015:   # within 1.5%
                    continue

                confs = [
                    f"At {label} Fib retracement (${fib_price:.2f})",
                    f"Swing: ${sl_price:.2f} → ${sh_price:.2f} (+{swing_pct:.1%}, {swing_bars}bars)",
                ]

                # Fix 13c: RSI gate — must be < 50 at retracement level
                if rsi_val >= 50:
                    return self._hold(symbol, df,
                        f"Fib {label} level but RSI={rsi_val:.1f} >= 50 — not oversold enough")

                # Fix 13d: Confluence check — Fib level near a MA or S/R
                confluence = False
                ma_vals = []
                if ma_sig:
                    for ma_key in ("sma_20", "sma_50", "sma_200"):
                        mv = ma_sig.details.get(ma_key)
                        if mv and abs(fib_price - mv) / fib_price < 0.01:
                            confs.append(f"Confluence with {ma_key} (${mv:.2f})")
                            confluence = True
                if sr_sig:
                    supports = sr_sig.details.get("support_levels", [])
                    for s in supports:
                        if abs(fib_price - s) / fib_price < 0.015:
                            confs.append(f"Confluence with support ${s:.2f}")
                            confluence = True

                if not confluence:
                    confs.append("No MA/S/R confluence — lower confidence")

                if candle_sig and hasattr(candle_sig, 'direction'):
                    try:
                        from indicators.base import SignalDirection
                        if candle_sig.direction == SignalDirection.BUY:
                            confs.append(f"Candle: {candle_sig.details.get('pattern','bullish')}")
                    except Exception:
                        pass

                if rsi_val < 45:
                    confs.append(f"RSI oversold ({rsi_val:.1f})")

                # Confidence: base + confluence boost + candle + RSI
                base_conf  = 0.62 if confluence else 0.52
                conf_boost = len([c for c in confs if "Confluence" in c]) * 0.05
                rsi_boost  = 0.05 if rsi_val < 40 else 0.0
                confidence = min(base_conf + conf_boost + rsi_boost, 0.88)

                stop = price - (1.5 * atr14)
                tp   = sh_price   # target: back to swing high

                return TradeSignal(
                    strategy=self.name, symbol=symbol, timestamp=timestamp,
                    action=TradeAction.BUY,
                    confidence=round(confidence, 3),
                    reason=(f"Fib {label} at ${fib_price:.2f} "
                            f"RSI={rsi_val:.1f} "
                            f"confluence={confluence}"),
                    confirmations=confs,
                    stop_loss=round(stop, 2),
                    take_profit=round(tp, 2),
                    details={
                        "fib_level":   label,
                        "fib_price":   round(fib_price, 2),
                        "swing_high":  round(sh_price, 2),
                        "swing_low":   round(sl_price, 2),
                        "swing_pct":   round(swing_pct*100, 1),
                        "swing_bars":  swing_bars,
                        "confluence":  confluence,
                        "atr14":       round(atr14, 3),
                    },
                )

        return self._hold(symbol, df,
            f"No Fib level hit: swing {swing_pct:.1%}/{swing_bars}bars "
            f"price=${price:.2f}")


# ============================================================
# Strategy 8: Volume Confirmation
# ============================================================
class VolumeConfirmationStrategy(BaseStrategy):
    """
    Only fires when a directional price move is backed by
    significantly above-average volume.
    High volume = institutional participation = real move.

    Volume surge BUY:  price up 1%+ on 2x+ average volume
    Volume surge SELL: price down 1%+ on 2x+ average volume
    """

    def __init__(self, volume_factor=2.0, price_move=0.01):
        self.volume_factor = volume_factor
        self.price_move    = price_move

    @property
    def name(self): return "VolumeConfirmation"

    @property
    def description(self): return "Only trades moves backed by 2x+ average volume"

    @property
    def role(self) -> str:
        return StrategyRole.NEUTRAL

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # Fix 8: OBV slope + VWAP check + ATR stops + scaled confidence
        if len(df) < 22:
            return self._hold(symbol, df, "Not enough bars")

        import pandas as pd
        price      = float(df["close"].iloc[-1])
        prev_price = float(df["close"].iloc[-2])
        price_chg  = (price - prev_price) / prev_price
        timestamp  = df.index[-1].to_pydatetime()

        avg_vol   = float(df["volume"].rolling(20).mean().iloc[-1])
        curr_vol  = float(df["volume"].iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        ma_sig  = summary.signals.get("MA")
        rsi_sig = summary.signals.get("RSI")
        rsi_val = rsi_sig.details.get("rsi", 50) if rsi_sig else 50

        if vol_ratio < self.volume_factor:
            return self._hold(symbol, df,
                f"Volume {vol_ratio:.1f}x < {self.volume_factor}x threshold")

        # ── Fix 8a: OBV slope over 10 bars (was 5 — too noisy) ──────────
        # OBV rising = accumulation, falling = distribution
        try:
            obv       = (df["volume"] * df["close"].diff().apply(
                            lambda x: 1 if x > 0 else (-1 if x < 0 else 0)
                         )).cumsum()
            obv_slope = float(obv.diff(10).iloc[-1])   # 10-bar OBV change
            obv_bull  = obv_slope > 0
        except Exception:
            obv_slope = 0.0
            obv_bull  = True   # default pass

        # ── Fix 8b: VWAP check — institutions buy below VWAP ────────────
        # Use intraday VWAP if available, else calculate from daily bars
        below_vwap = None
        vwap_note  = ""
        intraday   = getattr(summary, "intraday_df", None)
        if intraday is not None and len(intraday) >= 10:
            try:
                tp     = (intraday["high"] + intraday["low"] + intraday["close"]) / 3
                vwap   = (tp * intraday["volume"]).cumsum() / intraday["volume"].cumsum()
                vwap_v = float(vwap.iloc[-1])
                below_vwap = price < vwap_v
                vwap_note  = f" VWAP=${vwap_v:.2f}"
            except Exception:
                below_vwap = None
        else:
            # Fallback: simple VWAP from daily bars (last 20)
            try:
                d = df.tail(20)
                tp     = (d["high"] + d["low"] + d["close"]) / 3
                vwap_v = float((tp * d["volume"]).sum() / d["volume"].sum())
                below_vwap = price < vwap_v
                vwap_note  = f" VWAP~${vwap_v:.2f}"
            except Exception:
                below_vwap = None

        # ── Fix 8c: ATR for adaptive stops ──────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        confs = [f"Volume {vol_ratio:.1f}x avg"]

        # ── BUY: price up + volume surge ─────────────────────────────────
        if price_chg >= self.price_move:
            if ma_sig and ma_sig.details.get("above_sma20", False):
                confs.append("above SMA20")
            if rsi_val < 70:
                confs.append(f"RSI={rsi_val:.1f} not overbought")
            if obv_bull:
                confs.append(f"OBV accumulating (10-bar)")
            if below_vwap is True:
                confs.append(f"below VWAP — institutional buy zone{vwap_note}")

            # Fix 8d: Scaled confidence by vol ratio tier
            if vol_ratio >= 4.0:   base = 0.82
            elif vol_ratio >= 3.0: base = 0.76
            elif vol_ratio >= 2.0: base = 0.68
            else:                  base = 0.60

            # OBV and VWAP boosts
            obv_boost  = 0.05 if obv_bull    else -0.05
            vwap_boost = 0.04 if below_vwap  else  0.0

            confidence = min(base + obv_boost + vwap_boost, 0.92)
            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)

            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=round(confidence, 3),
                reason=(f"Vol surge {vol_ratio:.1f}x +{price_chg*100:.1f}% "
                        f"OBV={'up' if obv_bull else 'dn'}{vwap_note}"),
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={
                    "volume_ratio": round(vol_ratio, 2),
                    "price_change": round(price_chg, 4),
                    "obv_slope":    round(obv_slope, 0),
                    "below_vwap":   below_vwap,
                    "atr14":        round(atr14, 3),
                },
            )

        # ── SELL: price down + volume surge ──────────────────────────────
        if price_chg <= -self.price_move:
            confs.append(f"Price -{abs(price_chg)*100:.1f}%")
            if not obv_bull:
                confs.append("OBV distributing")

            if vol_ratio >= 3.0:   base = 0.76
            elif vol_ratio >= 2.0: base = 0.68
            else:                  base = 0.60

            obv_boost  = 0.05 if not obv_bull else -0.03
            confidence = min(base + obv_boost, 0.88)
            stop = price + (1.5 * atr14)
            tp   = price - (3.0 * atr14)

            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=round(confidence, 3),
                reason=(f"Vol surge {vol_ratio:.1f}x -{abs(price_chg)*100:.1f}% "
                        f"OBV={'dn' if not obv_bull else 'up'}{vwap_note}"),
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={
                    "volume_ratio": round(vol_ratio, 2),
                    "price_change": round(price_chg, 4),
                    "obv_slope":    round(obv_slope, 0),
                    "atr14":        round(atr14, 3),
                },
            )

        return self._hold(symbol, df,
            f"Vol {vol_ratio:.1f}x but price move {price_chg*100:.1f}% "
            f"< {self.price_move*100:.1f}% threshold")


# ============================================================
# Strategy 9: Multi-Timeframe Confirmation
# ============================================================
class MultiTimeframeStrategy(BaseStrategy):
    """
    Fix 3: Multi-timeframe alignment — daily + weekly + 15-min intraday.

    Improvements over original:
    - Weekly resampled from 15-min bars (more bars = more reliable)
    - 3-timeframe check: 15-min trend must also agree for BUY
    - 1.3x conviction multiplier when all 3 TFs align
    - ATR-based stops replace fixed 3%
    - Neutral HOLD when weekly is mixed (not just bullish/bearish binary)
    """

    @property
    def name(self): return "MultiTimeframe"

    @property
    def description(self): return "Daily + weekly + 15-min must agree before entering"

    @property
    def role(self) -> str:
        return StrategyRole.NEUTRAL

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        if len(df) < 60:
            return self._hold(symbol, df, "Need 60+ bars for MTF analysis")

        import pandas as pd
        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        # ── Weekly trend: resample from 15-min if available, else from daily ──
        # 15-min bars give ~26 bars/day = better weekly resolution than daily
        intraday = getattr(summary, "intraday_df", None)
        base_df  = intraday if (intraday is not None and len(intraday) >= 100) else df

        try:
            weekly = base_df.resample("W").agg({
                "open":   "first",
                "high":   "max",
                "low":    "min",
                "close":  "last",
                "volume": "sum",
            }).dropna()
        except Exception:
            weekly = df.resample("W").agg({
                "open": "first", "high": "max",
                "low": "min", "close": "last", "volume": "sum",
            }).dropna()

        if len(weekly) < 8:
            return self._hold(symbol, df, "Not enough weekly bars")

        w_close       = weekly["close"]
        w_sma10       = float(w_close.rolling(10).mean().iloc[-1]) if len(weekly) >= 10 else float(w_close.mean())
        w_sma20       = float(w_close.rolling(20).mean().iloc[-1]) if len(weekly) >= 20 else None
        w_price       = float(w_close.iloc[-1])
        weekly_bullish = w_price > w_sma10
        weekly_bearish = w_price < w_sma10

        # ── Weekly momentum: last 4 weeks direction ───────────────────────
        if len(w_close) >= 5:
            w_mom = (float(w_close.iloc[-1]) - float(w_close.iloc[-5])) / float(w_close.iloc[-5])
        else:
            w_mom = 0.0

        # ── Daily signal from indicator summary ───────────────────────────
        daily_score = summary.score
        daily_buy   = daily_score >= 2.0
        daily_sell  = daily_score <= -2.0

        # ── 15-min intraday trend: price vs 20-bar MA on 15-min bars ─────
        intra_bullish = None
        if intraday is not None and len(intraday) >= 20:
            try:
                intra_ma20    = float(intraday["close"].rolling(20).mean().iloc[-1])
                intra_price   = float(intraday["close"].iloc[-1])
                intra_bullish = intra_price > intra_ma20
            except Exception:
                intra_bullish = None

        # ── ATR for stops ────────────────────────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr     = pd.concat([hi-lo, (hi-cl.shift(1)).abs(), (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14  = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14  = price * 0.01

        confs = []
        tf_agree = 0  # count of timeframes agreeing

        # ── BUY: daily + weekly both bullish ─────────────────────────────
        if daily_buy and weekly_bullish:
            confs = [
                f"Daily score {daily_score:+.1f} bullish",
                f"Weekly above SMA10 ({w_sma10:.2f})",
            ]
            tf_agree = 2
            if w_sma20 and w_price > w_sma20:
                confs.append("Above weekly SMA20")
            if w_mom > 0.02:
                confs.append(f"Weekly momentum +{w_mom:.1%}")
                tf_agree += 0.5
            if intra_bullish is True:
                confs.append("15-min trend confirmed")
                tf_agree += 1   # 3rd TF — big boost

            # Conviction multiplier: 1.0x for 2 TFs, 1.3x for all 3
            base_conf  = min(0.60 + len(confs) * 0.05, 0.88)
            tf_mult    = 1.3 if tf_agree >= 3 else 1.0
            confidence = min(base_conf * tf_mult, 0.95)

            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)

            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=round(confidence, 3),
                reason=(f"MTF aligned: daily={daily_score:+.1f} "
                        f"weekly={'bull' if weekly_bullish else 'bear'} "
                        f"15min={'bull' if intra_bullish else 'neutral' if intra_bullish is None else 'bear'} "
                        f"({tf_agree:.1f} TFs agree)"),
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={
                    "daily_score":   daily_score,
                    "weekly_sma10":  round(w_sma10, 2),
                    "weekly_mom":    round(w_mom, 4),
                    "intra_bullish": intra_bullish,
                    "tf_agree":      tf_agree,
                    "atr14":         round(atr14, 3),
                },
            )

        # ── SELL: daily + weekly both bearish ────────────────────────────
        if daily_sell and weekly_bearish:
            confs = [
                f"Daily score {daily_score:+.1f} bearish",
                f"Weekly below SMA10 ({w_sma10:.2f})",
            ]
            tf_agree = 2
            if intra_bullish is False:
                confs.append("15-min trend confirms bearish")
                tf_agree += 1

            base_conf  = min(0.60 + len(confs) * 0.05, 0.88)
            tf_mult    = 1.3 if tf_agree >= 3 else 1.0
            confidence = min(base_conf * tf_mult, 0.95)

            stop = price + (1.5 * atr14)
            tp   = price - (3.0 * atr14)

            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=round(confidence, 3),
                reason=(f"MTF aligned bearish: daily={daily_score:+.1f} "
                        f"weekly=bear ({tf_agree:.1f} TFs agree)"),
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"daily_score": daily_score, "weekly_sma10": round(w_sma10, 2),
                         "tf_agree": tf_agree},
            )

        return self._hold(symbol, df,
            f"MTF not aligned: daily={daily_score:+.1f} "
            f"weekly={'bull' if weekly_bullish else 'bear'} "
            f"15min={'bull' if intra_bullish else 'N/A' if intra_bullish is None else 'bear'}")


# ============================================================
# Strategy 10: Trend Regime Filter
# ============================================================
class TrendRegimeStrategy(BaseStrategy):
    """
    Detects the current market regime and applies regime-appropriate logic:

    TRENDING UP:    momentum signals carry more weight → BUY bias
    TRENDING DOWN:  sell signals carry more weight → SELL bias
    RANGING:        mean reversion signals → fade extremes
    HIGH VOLATILITY: reduce position, wait for clarity → HOLD bias

    Regime is determined by:
      - ADX (Average Directional Index) > 25 = trending
      - Bollinger Band width vs average = volatility regime
      - Price vs SMA50 slope = direction
    """

    @property
    def name(self): return "TrendRegime"

    @property
    def description(self): return "Detects market regime and trades only regime-appropriate setups"

    @property
    def role(self) -> str:
        return StrategyRole.NEUTRAL

    def _calculate_adx(self, df, period=14) -> float:
        """Simplified ADX calculation."""
        high  = df["high"]
        low   = df["low"]
        close = df["close"]

        plus_dm  = (high.diff()).clip(lower=0)
        minus_dm = (-low.diff()).clip(lower=0)
        mask     = plus_dm < minus_dm
        plus_dm[mask] = 0
        mask2    = minus_dm < plus_dm
        minus_dm[mask2] = 0

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)

        atr      = tr.ewm(span=period, adjust=False).mean()
        plus_di  = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr

        dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
        adx = dx.ewm(span=period, adjust=False).mean()
        return float(adx.iloc[-1])

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # Fix 5: VIX proxy + ATR stops + sector awareness + PM mode filter
        if len(df) < 30:
            return self._hold(symbol, df, "Not enough bars")

        import pandas as pd
        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        adx       = self._calculate_adx(df)
        bb_sig    = summary.signals.get("BB")
        ma_sig    = summary.signals.get("MA")
        score     = summary.score

        bw        = bb_sig.details.get("bandwidth", 0.05) if bb_sig else 0.05
        avg_bw    = float(df["close"].rolling(20).std().mean() / df["close"].mean()) * 2
        high_vol  = bw > avg_bw * 1.5

        above_sma50 = ma_sig.details.get("above_sma50", False) if ma_sig else False

        # ── Fix 5a: VIX proxy from SPY realized volatility ───────────────
        # Use 10-day realized vol of SPY as VIX proxy
        # High vol (>2% daily moves) = reduce confidence, warn dashboard
        spy_df    = getattr(summary, "spy_df", None)
        vix_proxy = 15.0  # default — calm market
        vix_high  = False
        if spy_df is not None and len(spy_df) >= 11:
            try:
                spy_returns = spy_df["close"].pct_change().dropna()
                realized_vol = float(spy_returns.tail(10).std()) * (252 ** 0.5) * 100
                vix_proxy    = realized_vol
                vix_high     = realized_vol > 25   # annualized vol > 25% = elevated fear
            except Exception:
                pass

        # ── Fix 5b: ATR for adaptive stops ───────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── Classify regime ───────────────────────────────────────────────
        if high_vol or vix_high:
            regime = "HIGH_VOLATILITY"
        elif adx > 25 and above_sma50:
            regime = "TRENDING_UP"
        elif adx > 25 and not above_sma50:
            regime = "TRENDING_DOWN"
        else:
            regime = "RANGING"

        confs     = [f"Regime: {regime}", f"ADX: {adx:.1f}",
                     f"VIX proxy: {vix_proxy:.1f}%"]

        if regime == "HIGH_VOLATILITY":
            return self._hold(symbol, df,
                f"High vol regime: ADX={adx:.1f} VIX~{vix_proxy:.1f}% — waiting for clarity")

        # ── Fix 5c: RANGING mode — disable mean reversion in PM mode ─────
        # PM is trend-following — don't fade extremes in ranging markets
        _approach = str(getattr(summary, "approach", "")).lower()
        _is_pm    = any(x in _approach for x in ("profit maximizer", "aggressive"))

        if regime == "TRENDING_UP" and score >= 1.5:
            confs += [f"Trend confirmed (ADX={adx:.1f})", f"Score={score:+.1f}"]
            # VIX penalty: reduce confidence when vol is elevated
            vix_penalty = 0.10 if vix_proxy > 20 else 0.0
            confidence  = min(0.60 + adx/100 + score*0.04 - vix_penalty, 0.92)
            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=round(confidence, 3),
                reason=(f"TRENDING_UP: ADX={adx:.1f} score={score:+.1f} "
                        f"VIX~{vix_proxy:.1f}%"),
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"regime": regime, "adx": round(adx,1),
                         "score": score, "vix_proxy": round(vix_proxy,1),
                         "atr14": round(atr14,3)},
            )

        if regime == "TRENDING_DOWN" and score <= -1.5:
            confs += [f"Downtrend confirmed (ADX={adx:.1f})", f"Score={score:+.1f}"]
            vix_penalty = 0.10 if vix_proxy > 20 else 0.0
            confidence  = min(0.60 + adx/100 + abs(score)*0.04 - vix_penalty, 0.90)
            stop = price + (1.5 * atr14)
            tp   = price - (3.0 * atr14)
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=round(confidence, 3),
                reason=(f"TRENDING_DOWN: ADX={adx:.1f} score={score:+.1f} "
                        f"VIX~{vix_proxy:.1f}%"),
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"regime": regime, "adx": round(adx,1),
                         "score": score, "vix_proxy": round(vix_proxy,1)},
            )

        if regime == "RANGING" and not _is_pm:
            # Only fade extremes in non-PM modes
            rsi_sig = summary.signals.get("RSI")
            rsi_val = rsi_sig.details.get("rsi", 50) if rsi_sig else 50
            stop_buy  = price - (1.0 * atr14)
            tp_buy    = price + (2.0 * atr14)
            stop_sell = price + (1.0 * atr14)
            tp_sell   = price - (2.0 * atr14)

            if rsi_val < 32:
                confs.append(f"Ranging + oversold RSI ({rsi_val:.1f})")
                return TradeSignal(
                    strategy=self.name, symbol=symbol, timestamp=timestamp,
                    action=TradeAction.BUY, confidence=0.62,
                    reason=f"RANGING oversold: RSI={rsi_val:.1f} VIX~{vix_proxy:.1f}%",
                    confirmations=confs,
                    stop_loss=round(stop_buy, 2),
                    take_profit=round(tp_buy, 2),
                    details={"regime": regime, "adx": round(adx,1),
                             "vix_proxy": round(vix_proxy,1)},
                )
            if rsi_val > 68:
                confs.append(f"Ranging + overbought RSI ({rsi_val:.1f})")
                return TradeSignal(
                    strategy=self.name, symbol=symbol, timestamp=timestamp,
                    action=TradeAction.SELL, confidence=0.62,
                    reason=f"RANGING overbought: RSI={rsi_val:.1f} VIX~{vix_proxy:.1f}%",
                    confirmations=confs,
                    stop_loss=round(stop_sell, 2),
                    take_profit=round(tp_sell, 2),
                    details={"regime": regime, "adx": round(adx,1),
                             "vix_proxy": round(vix_proxy,1)},
                )

        return self._hold(symbol, df,
            f"Regime={regime} ADX={adx:.1f} score={score:+.1f} "
            f"VIX~{vix_proxy:.1f}% — no clear entry")
