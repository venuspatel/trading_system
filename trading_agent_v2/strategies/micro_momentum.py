# -*- coding: utf-8 -*-
"""
MicroMomentumStrategy — catches stocks in the FIRST 1-3 minutes of a move
--------------------------------------------------------------------------
Unlike our swing momentum (RSI/MACD on daily bars), this strategy watches
for volume spikes and rapid price acceleration on 1-min bars, entering
immediately and exiting fast with a small profit.

Rules:
  Entry:  Volume spike (2x avg) + price moving up 0.2%+ in last 2 bars
  Exit:   +0.5% take profit OR -0.25% stop loss (very tight)
  Hold:   Max 5 minutes — if not profitable, exit anyway

This works best in BULL markets with high-liquidity large caps.
"""

import logging
from datetime import datetime, timezone

import pandas as pd

from .base import BaseStrategy, StrategyRole, TradeAction, TradeSignal

logger = logging.getLogger(__name__)


class MicroMomentumStrategy(BaseStrategy):
    """
    1-minute bar strategy for early momentum detection.
    Enters on volume spike + rapid price acceleration.
    Exits quickly — this is a scalp, not a swing.
    """

    def __init__(
        self,
        min_vol_spike:       float = 2.0,    # volume must be 2x average
        min_price_move_pct:  float = 0.002,  # 0.2% move in last 2 bars
        max_spread_pct:      float = 0.003,  # skip if spread > 0.3%
        min_bars:            int   = 5,      # need at least 5 bars of history
    ):
        self.min_vol_spike      = min_vol_spike
        self.min_price_move_pct = min_price_move_pct
        self.max_spread_pct     = max_spread_pct
        self.min_bars           = min_bars

    @property
    def name(self) -> str:
        return "MicroMomentum"

    @property
    def description(self) -> str:
        return "1-min volume spike + price acceleration — scalp 0.3-0.8% fast"

    @property
    def role(self) -> str:
        return StrategyRole.INTRADAY

    def generate_signal(self, symbol: str, df: pd.DataFrame, summary) -> TradeSignal:
        # Get 1-min bar data from summary
        micro_df = getattr(summary, 'micro_df', None)
        if micro_df is None or len(micro_df) < self.min_bars:
            return self._hold(symbol, df, "No 1-min data available")
        try:
            return self._evaluate(symbol, df, micro_df)
        except Exception as ex:
            logger.debug(f"[MicroMomentum] {symbol} error: {ex}")
            return self._hold(symbol, df, f"Error: {ex}")

    def _evaluate(self, symbol: str, daily_df: pd.DataFrame,
                  micro_df: pd.DataFrame) -> TradeSignal:
        # Fix 15: Lower vol threshold + time filter + VWAP direction + stops
        close  = micro_df["close"]
        volume = micro_df["volume"] if "volume" in micro_df.columns else \
                 pd.Series([1]*len(close), index=close.index)
        high   = micro_df["high"]   if "high"   in micro_df.columns else close
        low    = micro_df["low"]    if "low"    in micro_df.columns else close

        price      = float(close.iloc[-1])
        prev1      = float(close.iloc[-2]) if len(close) > 1 else price
        prev2      = float(close.iloc[-3]) if len(close) > 2 else prev1
        timestamp  = daily_df.index[-1].to_pydatetime() if len(daily_df) > 0 \
                     else datetime.now(timezone.utc)

        # Fix 15a: Time-of-day filter — only trade in prime scalping windows
        # Avoid: first 15min (9:30-9:45 ET) = chaotic, last 30min (3:30-4PM) = dangerous
        # Best windows: 9:45-11:30 AM and 2:00-3:30 PM ET
        try:
            from datetime import timezone as _tz, timedelta
            ET  = _tz(timedelta(hours=-4))
            now = datetime.now(ET)
            et_hour   = now.hour
            et_minute = now.minute
            et_time   = et_hour * 60 + et_minute  # minutes since midnight ET

            # Market open windows (ET):
            # 9:45 AM = 585 min, 11:30 AM = 690 min
            # 2:00 PM = 840 min, 3:30 PM = 930 min
            in_morning  = 585 <= et_time <= 690
            in_afternoon= 840 <= et_time <= 930
            good_time   = in_morning or in_afternoon

            if not good_time:
                return self._hold(symbol, daily_df,
                    f"Micro: outside scalp window (ET {et_hour:02d}:{et_minute:02d}) "
                    f"— best: 9:45-11:30 or 2:00-3:30 PM")
        except Exception:
            good_time = True  # if time check fails, proceed

        # ── Volume spike — Fix 15b: lower threshold 2.0x → 1.3x ──────
        # Real institutional moves are 1.3-1.5x, not always 2x
        avg_vol   = float(volume.rolling(min(10, len(volume))).mean().iloc[-1])
        curr_vol  = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        # ── Price acceleration ────────────────────────────────────────
        move_2bar = (price - prev2) / prev2 if prev2 > 0 else 0.0
        move_1bar = (price - prev1) / prev1 if prev1 > 0 else 0.0

        # ── Spread check ──────────────────────────────────────────────
        bar_spread = (float(high.iloc[-1]) - float(low.iloc[-1])) / price
        if bar_spread > self.max_spread_pct:
            return self._hold(symbol, daily_df,
                f"Spread too wide ({bar_spread:.2%}) — skip micro entry")

        # ── Fix 15c: VWAP direction filter ───────────────────────────
        # Only scalp long when price is above VWAP (institutional bullish bias)
        above_vwap = True
        try:
            tp_series  = (high + low + close) / 3
            vwap_s     = (tp_series * volume).cumsum() / volume.cumsum()
            vwap_val   = float(vwap_s.iloc[-1])
            above_vwap = price > vwap_val
        except Exception:
            above_vwap = True

        # ── Fix 15d: Use effective threshold (1.3x instead of 2.0x) ──
        effective_vol_spike = max(1.3, self.min_vol_spike * 0.65)
        vol_ok   = vol_ratio >= effective_vol_spike
        move_ok  = move_2bar >= self.min_price_move_pct
        accel_ok = move_1bar > 0

        if vol_ok and move_ok and accel_ok and above_vwap:
            # ATR-based stop from daily bars
            try:
                hi_d = daily_df["high"] if "high" in daily_df.columns else daily_df["close"]
                lo_d = daily_df["low"]  if "low"  in daily_df.columns else daily_df["close"]
                cl_d = daily_df["close"]
                tr_d = pd.concat([hi_d-lo_d, (hi_d-cl_d.shift(1)).abs(),
                                  (lo_d-cl_d.shift(1)).abs()], axis=1).max(axis=1)
                atr14 = float(tr_d.rolling(14).mean().iloc[-1])
            except Exception:
                atr14 = price * 0.005  # 0.5% fallback for scalp

            # Tight scalp stops: 0.5x ATR for stop, 1x ATR for target
            stop = price - (0.5 * atr14)
            tp   = price + (1.0 * atr14)

            confidence = min(0.90, 0.58 + (vol_ratio - effective_vol_spike) * 0.08
                             + move_2bar * 15)
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = round(confidence, 3),
                reason     = (f"Micro: vol={vol_ratio:.1f}x "
                              f"+{move_2bar:.2%}/2bars "
                              f"accel={move_1bar:+.2%} "
                              f"above_vwap={above_vwap}"),
                strategy   = self.name,
                stop_loss  = round(stop, 2),
                take_profit= round(tp, 2),
                details    = {
                    "vol_ratio":   round(vol_ratio, 2),
                    "move_2bar":   round(move_2bar, 4),
                    "move_1bar":   round(move_1bar, 4),
                    "above_vwap":  above_vwap,
                    "atr14":       round(atr14, 3),
                },
            )

        # ── Sell: momentum fading ─────────────────────────────────────
        if move_1bar < -self.min_price_move_pct and vol_ratio >= 1.5:
            try:
                hi_d = daily_df["high"] if "high" in daily_df.columns else daily_df["close"]
                lo_d = daily_df["low"]  if "low"  in daily_df.columns else daily_df["close"]
                cl_d = daily_df["close"]
                tr_d = pd.concat([hi_d-lo_d, (hi_d-cl_d.shift(1)).abs(),
                                  (lo_d-cl_d.shift(1)).abs()], axis=1).max(axis=1)
                atr14 = float(tr_d.rolling(14).mean().iloc[-1])
            except Exception:
                atr14 = price * 0.005
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.SELL,
                confidence = 0.65,
                reason     = f"Micro: fading {move_1bar:.2%} vol={vol_ratio:.1f}x",
                strategy   = self.name,
                stop_loss  = round(price + (0.5 * atr14), 2),
                take_profit= round(price - (1.0 * atr14), 2),
            )

        return self._hold(symbol, daily_df,
            f"Micro: vol={vol_ratio:.1f}x(need {effective_vol_spike:.1f}x) "
            f"move={move_2bar:+.2%} vwap={above_vwap}")
