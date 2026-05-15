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
        # Fix 14: Adaptive OR duration + gap-and-go detection + ATR stops
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

        # Fix 14a: Adaptive OR duration based on recent volatility
        try:
            recent_vol_pct = float(daily_df["close"].pct_change().abs().tail(5).mean())
            if recent_vol_pct > 0.025:
                or_bars = 3; or_label = "45-min"
            elif recent_vol_pct < 0.008:
                or_bars = 1; or_label = "15-min"
            else:
                or_bars = OR_BARS; or_label = "30-min"
        except Exception:
            or_bars = OR_BARS; or_label = "30-min"

        if len(intra_df) <= or_bars:
            return self._hold(symbol, daily_df, f"Not enough bars for {or_label} OR")

        or_high      = float(high.iloc[:or_bars].max())
        or_low       = float(low.iloc[:or_bars].min())
        or_width_pct = (or_high - or_low) / or_low if or_low > 0 else 0

        if or_width_pct > self.max_or_width_pct:
            return self._hold(symbol, daily_df,
                f"ORB: {or_label} range too wide ({or_width_pct:.1%})")
        if or_width_pct < self.min_or_width_pct:
            return self._hold(symbol, daily_df,
                f"ORB: {or_label} range too narrow ({or_width_pct:.1%})")

        # Volume
        avg_vol   = float(volume.rolling(min(10, len(volume))).mean().iloc[-1])
        curr_vol  = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        # VWAP — calculate from bars if not in dataframe
        above_vwap = True
        vwap_val   = None
        if vwap is not None:
            vwap_val   = float(vwap.iloc[-1])
            above_vwap = price > vwap_val
        else:
            try:
                tp         = (high + low + close) / 3
                vwap_s     = (tp * volume).cumsum() / volume.cumsum()
                vwap_val   = float(vwap_s.iloc[-1])
                above_vwap = price > vwap_val
            except Exception:
                above_vwap = True

        # Fix 14b: Gap-and-go detection — 2%+ open gap = higher confidence
        is_gap_and_go = False
        try:
            if len(daily_df) >= 2:
                prev_close    = float(daily_df["close"].iloc[-2])
                today_open    = float(intra_df["open"].iloc[0]) if "open" in intra_df.columns else float(close.iloc[0])
                gap_pct       = (today_open - prev_close) / prev_close
                is_gap_and_go = gap_pct >= 0.02
        except Exception:
            is_gap_and_go = False

        # Fix 14c: ATR for adaptive stops
        try:
            hi_d, lo_d, cl_d = daily_df["high"], daily_df["low"], daily_df["close"]
            tr_d  = pd.concat([hi_d-lo_d, (hi_d-cl_d.shift(1)).abs(),
                               (lo_d-cl_d.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr_d.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # BUY: breakout above OR high
        broke_above = prev_price <= or_high and price > or_high
        if broke_above and vol_ratio >= self.min_vol_ratio and above_vwap:
            base_conf  = 0.72 if is_gap_and_go else 0.65
            confidence = min(0.95, base_conf + (vol_ratio - 1.5) * 0.08)
            stop       = max(or_low, price - (1.5 * atr14))
            tp         = price + (2.0 * atr14)
            gap_note   = " gap-and-go" if is_gap_and_go else ""
            return TradeSignal(
                symbol=symbol, timestamp=timestamp,
                action=TradeAction.BUY,
                confidence=round(confidence, 3),
                reason=(f"ORB {or_label} breakout ↑ ${or_high:.2f} "
                        f"vol={vol_ratio:.1f}x{gap_note}"),
                strategy=self.name,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"or_high": round(or_high,2), "or_label": or_label,
                         "vol_ratio": round(vol_ratio,2), "is_gap_and_go": is_gap_and_go,
                         "above_vwap": above_vwap, "atr14": round(atr14,3)},
            )

        # BUY: continuation above OR high
        running_above = price > or_high * 1.005
        if running_above and vol_ratio >= self.min_vol_ratio * 1.2 and above_vwap:
            extension = (price - or_high) / or_high
            if extension < 0.03:
                stop = max(or_high * 0.995, price - (1.5 * atr14))
                tp   = price + (1.5 * atr14)
                return TradeSignal(
                    symbol=symbol, timestamp=timestamp,
                    action=TradeAction.BUY, confidence=0.62,
                    reason=(f"ORB {or_label} continuation +{extension:.1%} "
                            f"vol={vol_ratio:.1f}x"),
                    strategy=self.name,
                    stop_loss=round(stop, 2),
                    take_profit=round(tp, 2),
                    details={"or_high": round(or_high,2), "extension": round(extension,3)},
                )

        # SELL: price falls back below OR high
        broke_below_or_high = prev_price > or_high and price <= or_high
        if broke_below_or_high:
            stop = price + (1.0 * atr14)
            tp   = or_low
            return TradeSignal(
                symbol=symbol, timestamp=timestamp,
                action=TradeAction.SELL, confidence=0.70,
                reason=f"ORB {or_label} failed — fell back below ${or_high:.2f}",
                strategy=self.name,
                stop_loss=round(stop, 2),
                take_profit=round(tp, 2),
                details={"or_high": round(or_high,2)},
            )

        return self._hold(
            symbol, daily_df,
            f"OR {or_label}: high=${or_high:.2f} price=${price:.2f} "
            f"vol={vol_ratio:.1f}x vwap={above_vwap}"
        )

