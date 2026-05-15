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

        # Fix 12: EPS surprise magnitude + gap-fill detection + ATR stops

        # ── Fix 12a: ATR for adaptive stops ──────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # Check price is still holding above gap open
        gap_open_price = float(open_.iloc[gap_bar])
        gap_close_price = float(close.iloc[gap_bar])
        gap_hold_pct   = (price - gap_open_price) / gap_open_price

        # ── Fix 12b: Gap-fill detection ───────────────────────────────────
        # If price has filled back to pre-gap level, the move is over
        gap_day_idx   = gap_bar
        prev_close_before_gap = float(close.iloc[gap_day_idx - 1]) if abs(gap_day_idx) < len(close) else gap_open_price
        gap_filled    = price < prev_close_before_gap * 1.005  # within 0.5% of pre-gap close = filled

        if gap_filled:
            return TradeSignal(
                symbol=symbol, strategy=self.name,
                action=TradeAction.SELL,
                confidence=0.75, timestamp=timestamp,
                reason=f"Earnings gap FILLED — price ${price:.2f} back to pre-gap ${prev_close_before_gap:.2f}",
                stop_loss=round(price + atr14, 2),
                take_profit=round(price - (2 * atr14), 2),
            )

        if gap_hold_pct < -self.hold_threshold:
            return TradeSignal(
                symbol=symbol, strategy=self.name,
                action=TradeAction.SELL,
                confidence=0.70, timestamp=timestamp,
                reason=f"Earnings gap failed — {gap_hold_pct*100:.1f}% below gap open ${gap_open_price:.2f}",
                stop_loss=round(price + atr14, 2),
                take_profit=round(price - (2 * atr14), 2),
            )

        post_gap_momentum = (price - gap_close_price) / max(gap_close_price, 0.01)
        bars_since_gap    = abs(gap_bar)

        # ── Fix 12c: EPS surprise magnitude boost ─────────────────────────
        # Try to get EPS surprise from news sentiment on summary
        # Larger gap = larger implied beat = higher confidence
        # Gap >3% = small beat, >6% = strong beat, >10% = blowout
        eps_boost = 0.0
        if gap_pct >= 0.10:
            eps_boost = 0.12   # blowout: >10% gap
        elif gap_pct >= 0.06:
            eps_boost = 0.08   # strong: 6-10% gap
        elif gap_pct >= 0.03:
            eps_boost = 0.04   # normal: 3-6% gap

        # Volume strength boost
        vol_boost = min(0.08, (gap_vol_mult - self.volume_mult) * 0.02)

        # Post-gap continuation boost
        cont_boost = min(0.06, post_gap_momentum * 1.5) if post_gap_momentum > 0 else 0.0

        # Recency penalty — gaps older than 10 bars are stale
        recency_penalty = min(0.10, (bars_since_gap - 5) * 0.01) if bars_since_gap > 5 else 0.0

        confidence = min(0.92,
            0.55 + eps_boost + vol_boost + cont_boost - recency_penalty)

        # Stops: below gap open (strong support) or 1.5x ATR whichever is tighter
        atr_stop  = price - (1.5 * atr14)
        gap_stop  = gap_open_price * 0.99   # just below gap open = key support
        stop      = max(atr_stop, gap_stop)  # tighter of the two
        tp        = price + (3.0 * atr14)

        return TradeSignal(
            symbol=symbol, strategy=self.name,
            action=TradeAction.BUY,
            confidence=round(confidence, 3),
            timestamp=timestamp,
            reason=(f"Earnings gap +{gap_pct*100:.1f}% ({gap_vol_mult:.1f}x vol) "
                    f"{bars_since_gap}d ago · post-gap {post_gap_momentum*100:.1f}% · "
                    f"holding ✓ eps_boost={eps_boost:.2f}"),
            stop_loss=round(stop, 2),
            take_profit=round(tp, 2),
            details={
                "gap_pct":           round(gap_pct*100, 2),
                "gap_vol_mult":      round(gap_vol_mult, 1),
                "post_gap_momentum": round(post_gap_momentum*100, 2),
                "bars_since_gap":    bars_since_gap,
                "eps_boost":         eps_boost,
                "gap_filled":        False,
                "atr14":             round(atr14, 3),
            },
        )
