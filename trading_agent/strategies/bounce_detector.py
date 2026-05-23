# -*- coding: utf-8 -*-
"""
BounceDetector — Strategy for bounces within confirmed downtrends.

Entry logic (3 of 4 conditions required):
  C1: Price has dropped ≥ 1.0% from recent 15-min leg high
  C2: RSI(14) < 40  (oversold)
  C3: Hammer candle OR 2-bar low hold  (exhaustion)
  C4: Volume < 85% of 50-bar average  (sellers drying up)

Only fires when called from the bounce routing gate in engine.py.
Normal trend strategies are suppressed when this runs.
"""

import logging
from typing import Optional

import pandas as pd
from datetime import datetime, timezone

from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole

logger = logging.getLogger(__name__)


class BounceDetectorStrategy(BaseStrategy):
    """
    Detects intraday bounce setups within stocks confirmed as DOWNTREND
    by the decision engine's trend classifier.

    Strategy role: BOUNCE — only active when decision engine routes to
    bounce mode. Never runs alongside normal trend strategies.
    """

    name = "BounceDetector"
    role = StrategyRole.BOUNCE

    @property
    def description(self) -> str:
        return (
            "Detects bounce setups within confirmed downtrends. "
            "Enters when price drops ≥1% from recent high, RSI<40, "
            "hammer candle or 2-bar low hold, and volume drying — 3 of 4 required."
        )

    # ── Parameters ────────────────────────────────────────────────────
    LEG_MIN        = 0.010   # minimum leg drop from recent high to qualify
    RSI_THRESHOLD  = 40      # RSI must be below this to confirm oversold
    VOL_DRY_RATIO  = 0.85    # volume must be below this fraction of avg
    VOL_AVG_PERIOD = 50      # bars for volume average
    RSI_PERIOD     = 14
    CONDITIONS_REQ = 3       # need 3 of 4 conditions

    def generate_signal(
        self,
        symbol:  str,
        df:      pd.DataFrame,
        summary: "AnalysisSummary",
    ) -> TradeSignal:

        _now  = datetime.now(timezone.utc)
        hold = TradeSignal(
            strategy=self.name,
            symbol=symbol,
            timestamp=_now,
            action=TradeAction.HOLD,
            confidence=0.0,
            reason="Bounce conditions not met",
        )

        if df is None or len(df) < max(self.RSI_PERIOD + 2, self.VOL_AVG_PERIOD + 2):
            return hold

        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        opens  = df["open"]
        volume = df["volume"]

        price   = float(close.iloc[-1])
        bar_idx = len(close) - 1

        # ── C1: Leg drop ≥ 1% from rolling recent high ────────────────
        lookback  = min(20, bar_idx)
        leg_high  = float(high.iloc[-lookback:].max())
        leg_drop  = (leg_high - price) / leg_high if leg_high > 0 else 0.0
        c1_leg    = leg_drop >= self.LEG_MIN

        # ── C2: RSI < 40 ──────────────────────────────────────────────
        rsi_val = self._rsi(close, self.RSI_PERIOD)
        c2_rsi  = rsi_val < self.RSI_THRESHOLD

        # ── C3: Hammer candle OR 2-bar low stabilisation ──────────────
        c3_hammer = self._is_hammer(opens, close, high, low, bar_idx)
        c3_hold   = (
            bar_idx >= 3
            and float(low.iloc[-1]) >= float(low.iloc[-2]) * 0.998
            and float(low.iloc[-2]) >= float(low.iloc[-3]) * 0.998
        )
        c3_ok = c3_hammer or c3_hold

        # ── C4: Volume drying up ──────────────────────────────────────
        avg_vol = float(volume.iloc[-self.VOL_AVG_PERIOD:].mean()) if bar_idx >= self.VOL_AVG_PERIOD else float(volume.mean())
        cur_vol = float(volume.iloc[-1])
        c4_vol  = avg_vol > 0 and (cur_vol / avg_vol) < self.VOL_DRY_RATIO

        # ── Count conditions ──────────────────────────────────────────
        conds     = [c1_leg, c2_rsi, c3_ok, c4_vol]
        met_count = sum(conds)

        logger.debug(
            f"[Bounce] {symbol} @ ${price:.2f}  "
            f"leg={leg_drop*100:.2f}% RSI={rsi_val:.1f} "
            f"hammer={c3_hammer} hold={c3_hold} "
            f"vol_ratio={cur_vol/avg_vol:.2f}  "
            f"conds={met_count}/4"
        )

        if met_count < self.CONDITIONS_REQ:
            return TradeSignal(
                strategy=self.name,
                symbol=symbol,
                timestamp=_now,
                action=TradeAction.HOLD,
                confidence=0.0,
                reason=(
                    f"Only {met_count}/4 bounce conditions met "
                    f"(leg={leg_drop*100:.1f}% RSI={rsi_val:.0f})"
                ),
            )

        # ── Confidence score: scales with conditions met and RSI depth ─
        base_conf    = 0.6 + (met_count - self.CONDITIONS_REQ) * 0.15
        rsi_bonus    = max(0.0, (self.RSI_THRESHOLD - rsi_val) / self.RSI_THRESHOLD) * 0.20
        leg_bonus    = min(0.15, (leg_drop - self.LEG_MIN) * 2)
        confidence   = min(1.0, base_conf + rsi_bonus + leg_bonus)

        cond_str = (
            f"leg={leg_drop*100:.1f}% "
            f"RSI={rsi_val:.0f} "
            f"{'hammer ' if c3_hammer else 'hold ' if c3_hold else ''}"
            f"{'vol_dry' if c4_vol else ''}"
        ).strip()

        return TradeSignal(
            strategy    = self.name,
            symbol      = symbol,
            timestamp   = _now,
            action      = TradeAction.BUY,
            confidence  = round(confidence, 3),
            reason      = f"Bounce {met_count}/4 — {cond_str}",
            confirmations = [
                f"Leg drop {leg_drop*100:.1f}% from ${leg_high:.2f}" if c1_leg else "",
                f"RSI oversold {rsi_val:.0f}" if c2_rsi else "",
                "Hammer candle" if c3_hammer else ("2-bar low hold" if c3_hold else ""),
                "Volume drying" if c4_vol else "",
            ],
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _rsi(self, close: pd.Series, period: int) -> float:
        if len(close) < period + 1:
            return 50.0
        delta = close.diff().dropna()
        gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-9)
        return float(100 - 100 / (1 + rs.iloc[-1]))

    def _is_hammer(
        self,
        opens: pd.Series,
        close: pd.Series,
        high:  pd.Series,
        low:   pd.Series,
        i:     int,
    ) -> bool:
        if i < 1:
            return False
        o = float(opens.iloc[i])
        c = float(close.iloc[i])
        h = float(high.iloc[i])
        l = float(low.iloc[i])
        body  = abs(c - o)
        lower = min(o, c) - l
        upper = h - max(o, c)
        total = h - l
        if total < 1e-9 or body < 1e-9:
            return False
        return lower >= 1.5 * body and upper <= 0.25 * total
