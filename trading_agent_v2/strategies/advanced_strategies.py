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
        if len(df) < 10:
            return self._hold(symbol, df, "Not enough bars")

        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()
        ma_sig    = summary.signals.get("MA")

        # Three White Soldiers: 3 consecutive bullish candles, each closing higher
        three_white = all(
            df["close"].iloc[-i] > df["open"].iloc[-i] and
            df["close"].iloc[-i] > df["close"].iloc[-(i+1)]
            for i in range(1, 4)
        )

        # Three Black Crows: 3 consecutive bearish candles, each closing lower
        three_black = all(
            df["close"].iloc[-i] < df["open"].iloc[-i] and
            df["close"].iloc[-i] < df["close"].iloc[-(i+1)]
            for i in range(1, 4)
        )

        bullish_trend = ma_sig and ma_sig.details.get("above_sma50", False)
        bearish_trend = ma_sig and not ma_sig.details.get("above_sma50", True)

        if three_white and bullish_trend:
            confs = ["Three White Soldiers", "MA trend bullish"]
            stop  = float(df["low"].iloc[-3]) * 0.99
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY, confidence=0.72,
                reason="Three White Soldiers in uptrend",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price + (price - stop) * 2, 2),
            )

        if three_black and bearish_trend:
            confs = ["Three Black Crows", "MA trend bearish"]
            stop  = float(df["high"].iloc[-3]) * 1.01
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL, confidence=0.70,
                reason="Three Black Crows in downtrend",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price - (stop - price) * 2, 2),
            )

        return self._hold(symbol, df, "No continuation pattern")


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

    def _find_swing(self, df, window=10):
        """Find the most recent significant swing high and low."""
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
        if len(df) < 30:
            return self._hold(symbol, df, "Not enough bars")

        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        swing_high, swing_low = self._find_swing(df)
        if not swing_high or not swing_low:
            return self._hold(symbol, df, "No clear swing points")

        sh_idx, sh_price = swing_high
        sl_idx, sl_price = swing_low

        candle_sig = summary.signals.get("CANDLE")
        rsi_sig    = summary.signals.get("RSI")
        rsi_val    = rsi_sig.details.get("rsi", 50) if rsi_sig else 50

        # Uptrend retracement: swing low came before swing high
        if sl_idx < sh_idx:
            move   = sh_price - sl_price
            levels = {f"{lvl*100:.1f}%": sh_price - move * lvl
                      for lvl in self.FIB_LEVELS}

            for label, fib_price in levels.items():
                if abs(price - fib_price) / price < 0.01:    # within 1%
                    confs = [f"At {label} Fibonacci ({fib_price:.2f})",
                             f"Uptrend retracement"]
                    if candle_sig and candle_sig.direction == SignalDirection.BUY:
                        confs.append(f"Candle confirmation: {candle_sig.details.get('pattern')}")
                    if rsi_val < 50:
                        confs.append(f"RSI supportive ({rsi_val:.1f})")

                    confidence = 0.60 + len(confs) * 0.07
                    stop = fib_price * 0.985
                    return TradeSignal(
                        strategy=self.name, symbol=symbol, timestamp=timestamp,
                        action=TradeAction.BUY,
                        confidence=min(confidence, 0.90),
                        reason=f"Fib retracement to {label} at ${fib_price:.2f}",
                        confirmations=confs,
                        stop_loss=round(stop, 2),
                        take_profit=round(sh_price, 2),
                        details={"fib_level": label, "fib_price": fib_price,
                                 "swing_high": sh_price, "swing_low": sl_price},
                    )

        return self._hold(symbol, df, "Price not at Fibonacci level")


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
        if len(df) < 22:
            return self._hold(symbol, df, "Not enough bars")

        price      = float(df["close"].iloc[-1])
        prev_price = float(df["close"].iloc[-2])
        price_chg  = (price - prev_price) / prev_price
        timestamp  = df.index[-1].to_pydatetime()

        avg_vol  = float(df["volume"].rolling(20).mean().iloc[-1])
        curr_vol = float(df["volume"].iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        ma_sig  = summary.signals.get("MA")
        rsi_sig = summary.signals.get("RSI")
        rsi_val = rsi_sig.details.get("rsi", 50) if rsi_sig else 50

        if vol_ratio < self.volume_factor:
            return self._hold(symbol, df,
                f"Volume not significant ({vol_ratio:.1f}x avg)")

        confs = [f"Volume {vol_ratio:.1f}x average (institutional activity)"]

        if price_chg >= self.price_move:
            if ma_sig and ma_sig.details.get("above_sma20", False):
                confs.append("above SMA20")
            if rsi_val < 70:
                confs.append(f"RSI not overbought ({rsi_val:.1f})")

            confidence = min(0.55 + vol_ratio * 0.06 + len(confs) * 0.05, 0.90)
            stop = price * 0.98

            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=confidence,
                reason=f"Volume surge ({vol_ratio:.1f}x) with +{price_chg*100:.1f}% price move",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 1.04, 2),
                details={"volume_ratio": round(vol_ratio, 2), "price_change": round(price_chg, 4)},
            )

        if price_chg <= -self.price_move:
            confs.append(f"Price down {abs(price_chg)*100:.1f}%")
            confidence = min(0.55 + vol_ratio * 0.06, 0.85)
            stop = price * 1.02

            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=confidence,
                reason=f"Volume surge ({vol_ratio:.1f}x) with -{abs(price_chg)*100:.1f}% price drop",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 0.96, 2),
                details={"volume_ratio": round(vol_ratio, 2), "price_change": round(price_chg, 4)},
            )

        return self._hold(symbol, df,
            f"Volume surge ({vol_ratio:.1f}x) but no significant price move")


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
        if len(df) < 30:
            return self._hold(symbol, df, "Not enough bars")

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

        # Classify regime
        if high_vol:
            regime = "HIGH_VOLATILITY"
        elif adx > 25 and above_sma50:
            regime = "TRENDING_UP"
        elif adx > 25 and not above_sma50:
            regime = "TRENDING_DOWN"
        else:
            regime = "RANGING"

        confs = [f"Regime: {regime}", f"ADX: {adx:.1f}"]

        if regime == "HIGH_VOLATILITY":
            return self._hold(symbol, df,
                f"High volatility regime (ADX={adx:.1f}, BW={bw:.3f}) -- waiting for clarity")

        if regime == "TRENDING_UP" and score >= 1.5:
            confs += [f"Trend confirmed (ADX={adx:.1f})", f"Score={score:+.1f}"]
            stop = price * 0.97
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=min(0.60 + adx/100 + score*0.04, 0.92),
                reason=f"Trending up regime with bullish score ({score:+.1f})",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 1.05, 2),
                details={"regime": regime, "adx": round(adx, 1), "score": score},
            )

        if regime == "TRENDING_DOWN" and score <= -1.5:
            confs += [f"Downtrend confirmed (ADX={adx:.1f})", f"Score={score:+.1f}"]
            stop = price * 1.03
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=min(0.60 + adx/100 + abs(score)*0.04, 0.90),
                reason=f"Trending down regime with bearish score ({score:+.1f})",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 0.95, 2),
                details={"regime": regime, "adx": round(adx, 1), "score": score},
            )

        if regime == "RANGING":
            # In ranging markets, fade extremes (mean reversion logic)
            rsi_sig = summary.signals.get("RSI")
            rsi_val = rsi_sig.details.get("rsi", 50) if rsi_sig else 50

            if rsi_val < 32:
                confs.append(f"Ranging + oversold RSI ({rsi_val:.1f})")
                return TradeSignal(
                    strategy=self.name, symbol=symbol, timestamp=timestamp,
                    action=TradeAction.BUY, confidence=0.65,
                    reason=f"Ranging market + oversold (RSI={rsi_val:.1f})",
                    confirmations=confs,
                    stop_loss=round(price * 0.985, 2),
                    take_profit=round(price * 1.025, 2),
                    details={"regime": regime, "adx": round(adx, 1)},
                )
            if rsi_val > 68:
                confs.append(f"Ranging + overbought RSI ({rsi_val:.1f})")
                return TradeSignal(
                    strategy=self.name, symbol=symbol, timestamp=timestamp,
                    action=TradeAction.SELL, confidence=0.65,
                    reason=f"Ranging market + overbought (RSI={rsi_val:.1f})",
                    confirmations=confs,
                    stop_loss=round(price * 1.015, 2),
                    take_profit=round(price * 0.975, 2),
                    details={"regime": regime, "adx": round(adx, 1)},
                )

        return self._hold(symbol, df,
            f"Regime={regime}, ADX={adx:.1f}, score={score:+.1f} -- no clear entry")
