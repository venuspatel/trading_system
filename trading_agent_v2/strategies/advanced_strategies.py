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
        if len(df) < 20:
            return self._hold(symbol, df, "Not enough bars")

        timestamp = df.index[-1].to_pydatetime()
        price     = float(df["close"].iloc[-1])
        rsi       = calculate_rsi(df)

        # Look back 5-15 bars for divergence
        lookback = min(15, len(df) - 2)
        recent_prices = df["close"].iloc[-lookback:]
        recent_rsi    = rsi.iloc[-lookback:]

        price_hh = recent_prices.iloc[-1] > recent_prices.iloc[:-1].max()  # new high
        price_ll = recent_prices.iloc[-1] < recent_prices.iloc[:-1].min()  # new low
        rsi_hh   = recent_rsi.iloc[-1]   > recent_rsi.iloc[:-1].max()
        rsi_ll   = recent_rsi.iloc[-1]   < recent_rsi.iloc[:-1].min()

        rsi_val  = float(rsi.iloc[-1])

        # Bearish divergence: price new high but RSI not confirming
        if price_hh and not rsi_hh and rsi_val > 55:
            confs = [
                f"Price at new high ({price:.2f})",
                f"RSI not confirming ({rsi_val:.1f})",
                "Bearish divergence detected",
            ]
            stop = price * 1.02
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL, confidence=0.70,
                reason=f"Bearish divergence: price high but RSI weak ({rsi_val:.1f})",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 0.96, 2),
                details={"rsi": rsi_val, "divergence_type": "bearish"},
            )

        # Bullish divergence: price new low but RSI not confirming
        if price_ll and not rsi_ll and rsi_val < 45:
            confs = [
                f"Price at new low ({price:.2f})",
                f"RSI not confirming ({rsi_val:.1f})",
                "Bullish divergence detected",
            ]
            stop = price * 0.98
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY, confidence=0.70,
                reason=f"Bullish divergence: price low but RSI firming ({rsi_val:.1f})",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 1.04, 2),
                details={"rsi": rsi_val, "divergence_type": "bullish"},
            )

        return self._hold(symbol, df, "No divergence detected")


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
        return StrategyRole.COUNTER_TREND

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
    Requires the same directional signal on BOTH the daily AND
    the weekly timeframe before entering.

    Weekly trend is approximated from the daily DataFrame by
    resampling to weekly bars. This eliminates a huge class of
    false signals that look good on daily but are counter-trend weekly.
    """

    @property
    def name(self): return "MultiTimeframe"

    @property
    def description(self): return "Requires daily and weekly to agree before entering"

    @property
    def role(self) -> str:
        return StrategyRole.NEUTRAL

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        if len(df) < 60:
            return self._hold(symbol, df, "Need 60+ bars for MTF analysis")

        price     = float(df["close"].iloc[-1])
        timestamp = df.index[-1].to_pydatetime()

        # Resample daily → weekly
        weekly = df.resample("W").agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna()

        if len(weekly) < 10:
            return self._hold(symbol, df, "Not enough weekly bars")

        # Weekly trend via SMA
        w_sma10 = weekly["close"].rolling(10).mean().iloc[-1]
        w_sma20 = weekly["close"].rolling(20).mean().iloc[-1] if len(weekly) >= 20 else None
        weekly_bullish = weekly["close"].iloc[-1] > w_sma10
        weekly_bearish = weekly["close"].iloc[-1] < w_sma10

        # Daily signal from summary
        daily_score = summary.score
        daily_buy   = daily_score >= 2.0
        daily_sell  = daily_score <= -2.0

        confs = []

        if daily_buy and weekly_bullish:
            confs = [
                f"Daily score: {daily_score:+.1f} (BUY)",
                f"Weekly trend: bullish (above W-SMA10 {w_sma10:.2f})",
                "Daily and weekly aligned",
            ]
            if w_sma20 and weekly["close"].iloc[-1] > w_sma20:
                confs.append("Above weekly SMA20")

            stop = price * 0.97
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=min(0.65 + len(confs) * 0.06, 0.92),
                reason=f"Daily+Weekly aligned bullish (score={daily_score:+.1f})",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 1.06, 2),
                details={"daily_score": daily_score, "weekly_sma10": round(w_sma10, 2)},
            )

        if daily_sell and weekly_bearish:
            confs = [
                f"Daily score: {daily_score:+.1f} (SELL)",
                f"Weekly trend: bearish (below W-SMA10 {w_sma10:.2f})",
                "Daily and weekly aligned",
            ]
            stop = price * 1.03
            return TradeSignal(
                strategy=self.name, symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL,
                confidence=min(0.65 + len(confs) * 0.06, 0.92),
                reason=f"Daily+Weekly aligned bearish (score={daily_score:+.1f})",
                confirmations=confs,
                stop_loss=round(stop, 2),
                take_profit=round(price * 0.94, 2),
                details={"daily_score": daily_score, "weekly_sma10": round(w_sma10, 2)},
            )

        return self._hold(symbol, df,
            f"Daily/weekly not aligned (daily={daily_score:+.1f}, "
            f"weekly_bull={weekly_bullish})")


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
