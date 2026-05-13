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
        min_vol_spike:       float = 1.3,    # volume must be 1.3x average (was 2.0x — too strict)
        min_price_move_pct:  float = 0.0003, # 0.03% move in last 2 bars (was 0.2% — too strict)
        max_spread_pct:      float = 0.005,  # skip if spread > 0.5% (was 0.3%)
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

        # ── Volume spike ──────────────────────────────────────────────
        avg_vol   = float(volume.rolling(min(10, len(volume))).mean().iloc[-1])
        curr_vol  = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        # ── Price acceleration — last 2 bars moving up ────────────────
        move_2bar = (price - prev2) / prev2 if prev2 > 0 else 0.0
        move_1bar = (price - prev1) / prev1 if prev1 > 0 else 0.0

        # ── Spread check (high-low of last bar as proxy) ──────────────
        bar_spread = (float(high.iloc[-1]) - float(low.iloc[-1])) / price
        if bar_spread > self.max_spread_pct:
            return self._hold(symbol, daily_df,
                f"Spread too wide ({bar_spread:.2%}) — skip micro entry")

        # ── Momentum score ────────────────────────────────────────────
        # Volume AND price must confirm
        vol_ok   = vol_ratio >= self.min_vol_spike
        move_ok  = move_2bar >= self.min_price_move_pct
        accel_ok = move_1bar > -self.min_price_move_pct  # not actively falling

        if vol_ok and move_ok and accel_ok:
            confidence = min(0.95, 0.55 + (vol_ratio - self.min_vol_spike) * 0.1 + move_2bar * 20)
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = round(confidence, 3),
                reason     = (f"Micro: vol={vol_ratio:.1f}x spike "
                              f"price +{move_2bar:.2%} in 2 bars "
                              f"accel={move_1bar:+.2%}"),
                strategy   = self.name,
                price      = price,
            )

        # ── Sell signal — momentum fading ─────────────────────────────
        if move_1bar < -self.min_price_move_pct and vol_ratio >= 1.5:
            return TradeSignal(
                symbol    = symbol,
                timestamp = timestamp,
                action    = TradeAction.SELL,
                confidence= 0.65,
                reason    = f"Micro: momentum fading {move_1bar:.2%} — exit",
                strategy  = self.name,
                price     = price,
            )

        return self._hold(symbol, daily_df,
            f"Micro: vol={vol_ratio:.1f}x move={move_2bar:+.2%} "
            f"(need {self.min_vol_spike}x + {self.min_price_move_pct:.1%})")
