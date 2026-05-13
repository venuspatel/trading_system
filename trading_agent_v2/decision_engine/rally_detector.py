# -*- coding: utf-8 -*-
"""
RallyDetector — finds stocks having significant intraday rallies
----------------------------------------------------------------
Detects stocks that are:
  1. Up significantly today vs yesterday's close (gap + intraday move)
  2. Trading on elevated volume (institutional participation)
  3. Breaking above recent resistance levels
  4. Showing accelerating momentum (pace of move increasing)

This is exactly what MARA was doing yesterday — strong rally + volume.
The detector runs at the start of each scan cycle and boosts the
conviction score of rallying stocks, helping the agent find them faster.

Examples of what this catches:
  - AMD up +8% today with 3x volume = RALLY
  - NVDA breaking above 20-day high with volume spike = RALLY
  - MARA up +15% pre-market continuing = RALLY
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RallySignal:
    symbol:          str
    rally_score:     float      # 0-10
    intraday_pct:    float      # today's % gain vs yesterday close
    vol_ratio:       float      # today's volume vs 20-day avg
    breaking_high:   bool       # price above 20-day high
    acceleration:    bool       # last bar bigger than previous bars
    reason:          str


class RallyDetector:
    """
    Scans the watchlist for intraday rally candidates.

    Runs at the START of every scan cycle.
    Returns a dict of {symbol: rally_score} to boost conviction.

    A stock with rally_score >= 6 gets a +1.0 conviction bonus.
    A stock with rally_score >= 8 gets a +2.0 conviction bonus.
    This pushes rallying stocks over the entry threshold faster.
    """

    # Conviction bonus thresholds
    STRONG_RALLY_THRESHOLD = 8.0   # +2.0 conviction bonus
    RALLY_THRESHOLD        = 5.0   # +1.0 conviction bonus
    STRONG_BONUS           = 2.0
    NORMAL_BONUS           = 1.0

    def __init__(self, data_manager):
        self._dm       = data_manager
        self._signals: Dict[str, RallySignal] = {}
        self._last_run = None

    def scan(self, watchlist: List[str]) -> Dict[str, RallySignal]:
        """
        Scan watchlist for rally candidates.
        Returns {symbol: RallySignal} for all rallying stocks.
        """
        import pandas as pd
        rallies = {}
        start   = datetime.now(timezone.utc) - timedelta(days=30)

        for sym in watchlist:
            try:
                df = self._dm.get_bars_df(sym, "1Day", start=start, limit=30)
                if df is None or len(df) < 5:
                    continue
                sig = self._score_rally(sym, df)
                if sig and sig.rally_score >= self.RALLY_THRESHOLD:
                    rallies[sym] = sig
                    logger.info(
                        f"[Rally] {sym} RALLY detected! "
                        f"score={sig.rally_score:.1f} "
                        f"intraday={sig.intraday_pct:+.1f}% "
                        f"vol={sig.vol_ratio:.1f}x | {sig.reason}"
                    )
            except Exception as ex:
                logger.debug(f"[Rally] {sym} scan failed: {ex}")

        self._signals  = rallies
        self._last_run = datetime.now(timezone.utc)

        if rallies:
            logger.info(
                f"[Rally] Found {len(rallies)} rally stocks: "
                + ", ".join(f"{s}({r.rally_score:.1f})" for s, r in
                           sorted(rallies.items(), key=lambda x: -x[1].rally_score)[:5])
            )
        return rallies

    def get_conviction_bonus(self, symbol: str) -> float:
        """Return conviction bonus for a symbol based on rally score."""
        sig = self._signals.get(symbol.upper())
        if not sig:
            return 0.0
        if sig.rally_score >= self.STRONG_RALLY_THRESHOLD:
            return self.STRONG_BONUS
        if sig.rally_score >= self.RALLY_THRESHOLD:
            return self.NORMAL_BONUS
        return 0.0

    def get_all_signals(self) -> Dict[str, dict]:
        """Return all current rally signals as dicts for API exposure."""
        return {
            sym: {
                "rally_score":  sig.rally_score,
                "intraday_pct": sig.intraday_pct,
                "vol_ratio":    sig.vol_ratio,
                "breaking_high": sig.breaking_high,
                "reason":       sig.reason,
            }
            for sym, sig in self._signals.items()
        }

    def _score_rally(self, symbol: str, df) -> Optional[RallySignal]:
        """Score a single symbol for rally strength."""
        import pandas as pd, math
        try:
            close   = df["close"]
            volume  = df["volume"] if "volume" in df.columns else None
            high    = df["high"]   if "high"   in df.columns else close

            price      = float(close.iloc[-1])
            prev_close = float(close.iloc[-2]) if len(close) > 1 else price

            # ── 1. Intraday gain ─────────────────────────────────────
            intraday_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0

            # Must be up at least 2% to qualify as a rally
            if intraday_pct < 2.0:
                return None

            rally_score = 0.0
            reasons     = []

            # Score the intraday move
            if intraday_pct >= 10:
                rally_score += 4.0
                reasons.append(f"+{intraday_pct:.1f}% today")
            elif intraday_pct >= 6:
                rally_score += 3.0
                reasons.append(f"+{intraday_pct:.1f}% today")
            elif intraday_pct >= 4:
                rally_score += 2.0
                reasons.append(f"+{intraday_pct:.1f}% today")
            elif intraday_pct >= 2:
                rally_score += 1.0
                reasons.append(f"+{intraday_pct:.1f}% today")

            # ── 2. Volume spike ──────────────────────────────────────
            vol_ratio = 1.0
            if volume is not None:
                avg_vol   = float(volume.rolling(20).mean().iloc[-1])
                last_vol  = float(volume.iloc[-1])
                vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

                if vol_ratio >= 3.0:
                    rally_score += 3.0
                    reasons.append(f"vol {vol_ratio:.1f}x")
                elif vol_ratio >= 2.0:
                    rally_score += 2.0
                    reasons.append(f"vol {vol_ratio:.1f}x")
                elif vol_ratio >= 1.5:
                    rally_score += 1.0

            # ── 3. Breaking 20-day high ──────────────────────────────
            breaking_high = False
            if len(high) >= 20:
                recent_high = float(high.iloc[-21:-1].max())  # last 20 days excl today
                if price >= recent_high:
                    rally_score   += 2.0
                    breaking_high  = True
                    reasons.append("20d breakout")

            # ── 4. Multi-day momentum continuation ───────────────────
            acceleration = False
            if len(close) >= 3:
                day1_chg = abs(float(close.iloc[-2]) - float(close.iloc[-3]))
                day2_chg = abs(price                  - float(close.iloc[-2]))
                if day2_chg > day1_chg * 1.2:  # today's move > 120% of yesterday's
                    rally_score  += 1.0
                    acceleration  = True
                    reasons.append("accelerating")

            rally_score = min(10.0, rally_score)

            return RallySignal(
                symbol        = symbol,
                rally_score   = round(rally_score, 2),
                intraday_pct  = round(intraday_pct, 2),
                vol_ratio     = round(vol_ratio, 2),
                breaking_high = breaking_high,
                acceleration  = acceleration,
                reason        = " · ".join(reasons) if reasons else f"+{intraday_pct:.1f}%",
            )

        except Exception as ex:
            logger.debug(f"[Rally] Score failed for {symbol}: {ex}")
            return None
