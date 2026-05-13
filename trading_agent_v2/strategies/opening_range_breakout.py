# -*- coding: utf-8 -*-
"""
OpeningRangeBreakout (ORB) — Phase 2 intraday strategy
--------------------------------------------------------
The opening range is the high and low of the FIRST 30 MINUTES
of trading (9:30-10:00 AM ET). This range sets the day's battlefield.

Rules:
  BUY  — price breaks ABOVE the opening range high with volume
  SELL — price breaks BELOW the opening range low (exit signal)

Why this works:
  - Institutions place their big orders in the first 30 min
  - The high/low of that range = key support/resistance for the day
  - A breakout above OR high = institutions bullish, follow them
  - AMD today: OR high was ~$96. When AMD broke above $96 at 10:15 AM
    with volume, that was the clean entry. ORB would have caught it.

Additional filters:
  - Volume must be 1.5x+ average to confirm institutional participation
  - Price must also be above VWAP (trend confirmation)
  - Only trade the first breakout (not re-entries after false breaks)
"""

import logging
from datetime import datetime, timezone

import pandas as pd

from .base import BaseStrategy, StrategyRole, TradeAction, TradeSignal

logger = logging.getLogger(__name__)

# Opening range = first 2 x 15-min bars = first 30 minutes
OR_BARS = 2


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """
    Detects breakouts above/below the first 30-min opening range.
    Requires intraday (15-min) bar data attached to summary.
    """

    def __init__(
        self,
        min_vol_ratio:     float = 1.5,    # volume must be 1.5x avg
        max_or_width_pct:  float = 0.05,   # ignore if OR is wider than 5% (too volatile)
        min_or_width_pct:  float = 0.001,  # ignore if OR is too narrow (no range)
    ):
        self.min_vol_ratio    = min_vol_ratio
        self.max_or_width_pct = max_or_width_pct
        self.min_or_width_pct = min_or_width_pct

    @property
    def name(self) -> str:
        return "OpeningRangeBreakout"

    @property
    def description(self) -> str:
        return "Buys breakouts above the first 30-min high with volume confirmation"

    @property
    def role(self) -> str:
        return StrategyRole.INTRADAY

    def generate_signal(self, symbol: str, df: pd.DataFrame, summary) -> TradeSignal:
        intraday_df = getattr(summary, 'intraday_df', None)
        if intraday_df is None or len(intraday_df) <= OR_BARS:
            return self._hold(symbol, df, "No intraday data or too few bars for ORB")

        try:
            return self._evaluate_orb(symbol, df, intraday_df)
        except Exception as ex:
            logger.debug(f"[ORB] {symbol} failed: {ex}")
            return self._hold(symbol, df, f"ORB error: {ex}")

    def _evaluate_orb(self, symbol: str, daily_df: pd.DataFrame,
                      intra_df: pd.DataFrame) -> TradeSignal:
        close  = intra_df["close"]
        high   = intra_df["high"]   if "high"   in intra_df.columns else close
        low    = intra_df["low"]    if "low"    in intra_df.columns else close
        volume = intra_df["volume"] if "volume" in intra_df.columns else \
                 pd.Series([1]*len(close), index=close.index)
        vwap   = intra_df["vwap"]   if "vwap"   in intra_df.columns else None

        price      = float(close.iloc[-1])
        prev_price = float(close.iloc[-2]) if len(close) > 1 else price
        timestamp  = daily_df.index[-1].to_pydatetime() if len(daily_df) > 0 \
                     else datetime.now(timezone.utc)

        # ── Opening range (first OR_BARS bars) ───────────────────────
        or_high = float(high.iloc[:OR_BARS].max())
        or_low  = float(low.iloc[:OR_BARS].min())
        or_width_pct = (or_high - or_low) / or_low if or_low > 0 else 0

        # Skip if OR is too wide (crazy volatile) or too narrow (no range)
        if or_width_pct > self.max_or_width_pct:
            return self._hold(symbol, daily_df,
                f"ORB: range too wide ({or_width_pct:.1%}) — skip")
        if or_width_pct < self.min_or_width_pct:
            return self._hold(symbol, daily_df,
                f"ORB: range too narrow ({or_width_pct:.1%}) — skip")

        # ── Volume confirmation ───────────────────────────────────────
        avg_vol   = float(volume.rolling(min(10, len(volume))).mean().iloc[-1])
        curr_vol  = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        # ── VWAP filter ───────────────────────────────────────────────
        above_vwap = True  # default if no VWAP
        if vwap is not None:
            vwap_val   = float(vwap.iloc[-1])
            above_vwap = price > vwap_val

        # ── BUY: breakout above OR high ───────────────────────────────
        broke_above = prev_price <= or_high and price > or_high
        if broke_above and vol_ratio >= self.min_vol_ratio and above_vwap:
            confidence = min(0.95, 0.65 + (vol_ratio - 1.5) * 0.10)
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = round(confidence, 3),
                reason     = (f"ORB breakout ↑ above ${or_high:.2f} | "
                              f"vol={vol_ratio:.1f}x | OR={or_width_pct:.1%}"),
                strategy   = self.name,
                price      = price,
            )

        # ── Already above OR high with strong volume ──────────────────
        # (didn't catch the exact candle but stock is running)
        running_above = price > or_high * 1.005  # 0.5% above OR high
        if running_above and vol_ratio >= self.min_vol_ratio * 1.2 and above_vwap:
            # Only if not too extended
            extension = (price - or_high) / or_high
            if extension < 0.03:  # within 3% of OR high — not too chased
                return TradeSignal(
                    symbol     = symbol,
                    timestamp  = timestamp,
                    action     = TradeAction.BUY,
                    confidence = 0.60,
                    reason     = (f"ORB continuation above ${or_high:.2f} "
                                  f"+{extension:.1%} | vol={vol_ratio:.1f}x"),
                    strategy   = self.name,
                    price      = price,
                )

        # ── SELL: price falls back below OR high (exit signal) ────────
        broke_below_or_high = prev_price > or_high and price <= or_high
        if broke_below_or_high:
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.SELL,
                confidence = 0.70,
                reason     = f"ORB failed — price fell back below ${or_high:.2f}",
                strategy   = self.name,
                price      = price,
            )

        return self._hold(
            symbol, daily_df,
            f"OR: high=${or_high:.2f} low=${or_low:.2f} price=${price:.2f} "
            f"vol={vol_ratio:.1f}x above_vwap={above_vwap}"
        )
