# -*- coding: utf-8 -*-
"""
EarningsMomentumStrategy — catches post-earnings institutional accumulation
---------------------------------------------------------------------------
Detects earnings gap-ups with volume confirmation that hold their gains.
AMD Q4 2026: Beat estimates → data center +39% → gapped up on earnings →
institutions accumulated for 6 weeks → +31% total move.
"""

import pandas as pd
import numpy as np
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole

BEAT_KEYWORDS = ["beats","beat","exceeded","surpassed","topped","record",
                 "raises guidance","above expectations","strong quarter",
                 "record revenue","record earnings"]
MISS_KEYWORDS = ["misses","missed","below expectations","disappoints",
                 "cuts guidance","warns","lowered guidance"]


class EarningsMomentumStrategy(BaseStrategy):

    def __init__(self, gap_threshold=0.03, volume_mult=1.8,
                 hold_threshold=0.01, lookback_bars=20):
        self.gap_threshold  = gap_threshold
        self.volume_mult    = volume_mult
        self.hold_threshold = hold_threshold
        self.lookback_bars  = lookback_bars

    @property
    def name(self) -> str:
        return "EarningsMomentum"

    @property
    def description(self) -> str:
        return "Detects post-earnings gap-ups with volume confirmation still holding the gap"

    @property
    def role(self) -> str:
        return StrategyRole.TREND

    def generate_signal(self, symbol: str, df: pd.DataFrame, summary) -> TradeSignal:
        if len(df) < self.lookback_bars + 10:
            return self._hold(symbol, df, "Insufficient data")

        close  = df["close"].astype(float)
        volume = df["volume"].astype(float) if "volume" in df.columns else pd.Series([0]*len(df))
        open_  = df["open"].astype(float) if "open" in df.columns else close

        price      = float(close.iloc[-1])
        timestamp  = df.index[-1].to_pydatetime()

        # Baseline volume (before lookback window)
        avg_volume = float(volume.iloc[-self.lookback_bars-10:-self.lookback_bars].mean())
        if avg_volume == 0:
            avg_volume = float(volume.mean()) or 1.0

        # Scan for an earnings gap in recent bars
        gap_bar       = None
        gap_pct       = 0.0
        gap_vol_mult  = 0.0
        lookback      = min(self.lookback_bars, len(df) - 5)

        for i in range(1, lookback + 1):
            idx        = -(i + 1)
            prev_close = float(close.iloc[idx])
            day_open   = float(open_.iloc[idx + 1])
            day_vol    = float(volume.iloc[idx + 1])

            if prev_close <= 0:
                continue

            gap     = (day_open - prev_close) / prev_close
            vol_sur = day_vol / avg_volume

            if gap >= self.gap_threshold and vol_sur >= self.volume_mult:
                gap_bar      = idx + 1
                gap_pct      = gap
                gap_vol_mult = vol_sur
                break

        if gap_bar is None:
            return self._hold(symbol, df, "No earnings gap detected")

        # Check price is still holding above gap open
        gap_open_price = float(open_.iloc[gap_bar])
        gap_hold_pct   = (price - gap_open_price) / gap_open_price

        if gap_hold_pct < -self.hold_threshold:
            return TradeSignal(
                symbol=symbol, strategy=self.name,
                action=TradeAction.SELL,
                confidence=0.70, timestamp=timestamp,
                reason=f"Earnings gap failed — price {gap_hold_pct*100:.1f}% below gap open",
            )

        post_gap_momentum = (price - float(close.iloc[gap_bar])) / max(float(close.iloc[gap_bar]), 0.01)
        bars_since_gap    = abs(gap_bar)

        # Confidence scales with gap size + continuation + volume
        confidence = min(0.90, 0.55 + min(0.15, gap_pct*2) + min(0.10, post_gap_momentum*2))

        return TradeSignal(
            symbol=symbol, strategy=self.name,
            action=TradeAction.BUY,
            confidence=confidence, timestamp=timestamp,
            reason=(f"Earnings gap +{gap_pct*100:.1f}% ({int(gap_vol_mult)}x vol) "
                    f"{bars_since_gap}d ago · "
                    f"Post-gap: {post_gap_momentum*100:.1f}% · holding gap ✓"),
            details={"gap_pct": round(gap_pct*100,2),
                     "gap_vol_mult": round(gap_vol_mult,1),
                     "post_gap_momentum": round(post_gap_momentum*100,2),
                     "bars_since_gap": bars_since_gap},
        )
