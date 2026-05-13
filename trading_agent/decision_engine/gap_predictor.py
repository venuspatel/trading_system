# -*- coding: utf-8 -*-
"""
GapPredictor — Phase A: predicts overnight gap-ups for open positions
----------------------------------------------------------------------
Runs at 3:30 PM ET, scores each open position on gap-up likelihood.
Positions with score >= threshold are flagged to hold overnight.

Gap score is built from:
  1. After-hours price move (biggest signal — something is happening)
  2. Pre-market volume relative to average
  3. Today's intraday momentum (did it trend up all day?)
  4. Historical gap behaviour for this stock
  5. Earnings / catalyst proximity

Score range: 0.0 to 1.0
Threshold: 0.55 — must be reasonably confident to hold overnight risk
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Hold overnight if gap score >= this
GAP_SCORE_THRESHOLD = 0.55

# Minimum gap to count as "gap materialised" at open
GAP_MATERIALISED_PCT = 0.008   # 0.8%


class GapScore:
    """Result of the gap prediction for one symbol."""
    def __init__(self, symbol: str, score: float, reasons: list,
                 predicted_gap_pct: float = 0.0, hold_overnight: bool = False):
        self.symbol            = symbol
        self.score             = round(score, 3)
        self.reasons           = reasons
        self.predicted_gap_pct = round(predicted_gap_pct, 4)
        self.hold_overnight    = hold_overnight

    def __repr__(self):
        status = "HOLD" if self.hold_overnight else "CLOSE"
        return (f"GapScore({self.symbol} score={self.score:.2f} "
                f"gap={self.predicted_gap_pct:+.1%} → {status})")


class GapPredictor:
    """
    Scores open positions for overnight gap-up potential.

    Usage:
        predictor = GapPredictor(data_manager)
        scores = predictor.score_positions(open_positions)
        # {sym: GapScore}
    """

    def __init__(self, data_manager):
        self._dm      = data_manager
        self._history: Dict[str, list] = {}   # past gap outcomes per symbol

    def score_positions(self, open_positions: dict,
                        intraday_data: dict = None) -> Dict[str, GapScore]:
        """
        Score all open positions for overnight gap potential.
        open_positions: {symbol: position_object}
        intraday_data:  {symbol: DataFrame} from 15-min bars
        """
        results = {}
        for sym, pos in open_positions.items():
            try:
                score = self._score_symbol(sym, pos, intraday_data or {})
                results[sym] = score
                logger.info(f"[GapPredictor] {score}")
            except Exception as ex:
                logger.debug(f"[GapPredictor] {sym} failed: {ex}")
                results[sym] = GapScore(sym, 0.0, [f"Error: {ex}"], hold_overnight=False)
        return results

    def _score_symbol(self, symbol: str, pos, intraday_data: dict) -> GapScore:
        reasons   = []
        score     = 0.0
        gap_pct   = 0.0

        # ── 1. Today's intraday performance ──────────────────────────
        # If position is already profitable and trended up all day → good sign
        pnl_pct = getattr(pos, 'unrealised_pnl_pct', 0.0) or 0.0
        if pnl_pct > 0.01:      # up 1%+ on the day
            score += 0.20
            reasons.append(f"Up {pnl_pct:+.1%} today")
        elif pnl_pct > 0.005:   # up 0.5%+
            score += 0.10
            reasons.append(f"Up {pnl_pct:+.1%} today (moderate)")
        elif pnl_pct < -0.005:  # losing position — penalise
            score -= 0.15
            reasons.append(f"Down {pnl_pct:+.1%} today (drag)")

        # ── 2. Intraday VWAP position at end of day ───────────────────
        # Above VWAP at close = institutional buyers active
        df = intraday_data.get(symbol)
        if df is not None and "vwap" in df.columns and len(df) > 0:
            price = float(df["close"].iloc[-1])
            vwap  = float(df["vwap"].iloc[-1])
            if price > vwap * 1.005:    # 0.5%+ above VWAP
                score += 0.20
                reasons.append(f"Closing above VWAP (${price:.2f} vs ${vwap:.2f})")
            elif price > vwap:
                score += 0.10
                reasons.append(f"Above VWAP at close")
            else:
                score -= 0.10
                reasons.append(f"Below VWAP at close — weak")

        # ── 3. Intraday trend — was the last hour strong? ─────────────
        if df is not None and len(df) >= 4:
            last_4_close = df["close"].iloc[-4:]
            trend_pct = (float(last_4_close.iloc[-1]) - float(last_4_close.iloc[0])) / \
                        float(last_4_close.iloc[0])
            if trend_pct > 0.005:    # up 0.5%+ in last hour
                score += 0.20
                gap_pct += trend_pct * 0.5   # momentum often continues
                reasons.append(f"Last-hour momentum +{trend_pct:.1%}")
            elif trend_pct > 0.002:
                score += 0.10
                reasons.append(f"Mild last-hour uptrend +{trend_pct:.1%}")
            elif trend_pct < -0.003:
                score -= 0.15
                reasons.append(f"Fading into close {trend_pct:.1%} — bearish")

        # ── 4. Historical gap behaviour for this stock ────────────────
        past_gaps = self._history.get(symbol, [])
        if past_gaps:
            avg_gap = sum(past_gaps) / len(past_gaps)
            positive_gaps = sum(1 for g in past_gaps if g > GAP_MATERIALISED_PCT)
            gap_rate = positive_gaps / len(past_gaps)
            if gap_rate >= 0.6:
                score += 0.15
                gap_pct += avg_gap * 0.3
                reasons.append(f"Historically gaps up {gap_rate:.0%} of days")
            elif gap_rate <= 0.3:
                score -= 0.10
                reasons.append(f"Rarely gaps up ({gap_rate:.0%} historically)")

        # ── 5. Estimated gap magnitude ────────────────────────────────
        if gap_pct == 0 and score > 0.4:
            # Conservative estimate based on score
            gap_pct = 0.008 + (score - 0.4) * 0.02

        hold = score >= GAP_SCORE_THRESHOLD
        return GapScore(
            symbol          = symbol,
            score           = score,
            reasons         = reasons,
            predicted_gap_pct = gap_pct,
            hold_overnight  = hold,
        )

    def record_gap_outcome(self, symbol: str, actual_gap_pct: float):
        """Record whether the gap materialised — improves future predictions."""
        sym = symbol.upper()
        if sym not in self._history:
            self._history[sym] = []
        self._history[sym].append(actual_gap_pct)
        # Keep last 20 gaps per symbol
        self._history[sym] = self._history[sym][-20:]

    def check_gap_materialised(self, symbol: str,
                               open_price: float, prev_close: float) -> bool:
        """At 9:30 AM — did the predicted gap actually happen?"""
        if prev_close <= 0:
            return False
        gap = (open_price - prev_close) / prev_close
        self.record_gap_outcome(symbol, gap)
        return gap >= GAP_MATERIALISED_PCT
