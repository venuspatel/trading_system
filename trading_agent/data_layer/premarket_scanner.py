# -*- coding: utf-8 -*-
"""
PremarketScanner — finds the day's best momentum stocks before open
--------------------------------------------------------------------
Runs at 8:30 AM ET (or on startup if between 8:30-9:30 AM ET).

Scores each watchlist symbol on:
  1. Overnight gap    — how much did it move since yesterday's close?
  2. Pre-market volume — is anyone trading it before open?
  3. 5-day trend      — is it above its recent MA?
  4. RSI momentum     — is it trending up without being overbought?

Output: ranked list of symbols with a "heat score" 0-10.
The top stocks get priority in the first scan cycle at 9:30 AM.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PremarketScore:
    symbol:        str
    heat_score:    float      # 0-10, higher = more likely to trend today
    gap_pct:       float      # overnight gap % vs yesterday close
    vol_ratio:     float      # pre-market volume vs 20-day avg daily volume
    above_ma5:     bool
    above_ma20:    bool
    rsi:           float
    reason:        str        # human-readable summary


class PremarketScanner:
    """
    Scores watchlist stocks before market open.
    Identifies which stocks have the best setup for the day.

    The key insight: MARA ran yesterday because it had:
      - Strong overnight momentum (gap up)
      - RSI in sweet spot (60-75)
      - Price above all key MAs
      - Volume already picking up pre-market

    This scanner finds that pattern every morning automatically.

    Usage:
        scanner = PremarketScanner(data_manager)
        scores = scanner.scan(watchlist)
        top_picks = [s.symbol for s in scores[:5]]
    """

    def __init__(self, data_manager):
        self._dm = data_manager

    def scan(self, watchlist: List[str], top_n: int = 10) -> List[PremarketScore]:
        """
        Score all watchlist symbols on pre-market momentum.
        Returns list sorted by heat_score descending.
        """
        logger.info(f"[PremarketScanner] Scanning {len(watchlist)} symbols...")
        scores = []
        start  = datetime.now(timezone.utc) - timedelta(days=30)

        for sym in watchlist:
            try:
                score = self._score_symbol(sym, start)
                if score:
                    scores.append(score)
            except Exception as ex:
                logger.debug(f"[PremarketScanner] {sym} skipped: {ex}")

        scores.sort(key=lambda s: s.heat_score, reverse=True)
        top = scores[:top_n]

        if top:
            logger.info(
                f"[PremarketScanner] Top picks: "
                + ", ".join(f"{s.symbol}({s.heat_score:.1f})" for s in top[:5])
            )
        return top

    def _score_symbol(self, symbol: str, start: datetime) -> Optional[PremarketScore]:
        """Score one symbol. Returns None if insufficient data."""
        # Get daily bars for trend analysis
        df = self._dm.get_bars_df(symbol, "1Day", start=start, limit=30)
        if df is None or len(df) < 5:
            return None

        close  = df["close"]
        volume = df["volume"] if "volume" in df.columns else pd.Series([1e6]*len(close))
        high   = df["high"]   if "high"   in df.columns else close
        low    = df["low"]    if "low"    in df.columns else close

        price     = close.iloc[-1]
        prev_close = close.iloc[-2] if len(close) > 1 else price

        # ── Gap analysis ──────────────────────────────────────────────
        # Use last bar close vs prior bar close as proxy for overnight gap
        gap_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0

        # ── Volume ratio ─────────────────────────────────────────────
        avg_vol   = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else volume.mean()
        last_vol  = volume.iloc[-1]
        vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else 1.0

        # ── Moving averages ───────────────────────────────────────────
        ma5  = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else ma5
        above_ma5  = price > ma5
        above_ma20 = price > ma20

        # ── RSI ───────────────────────────────────────────────────────
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float('nan'))
        rsi   = float((100 - 100 / (1 + rs)).iloc[-1]) if len(close) >= 14 else 50.0

        # ── Heat score (0-10) ─────────────────────────────────────────
        score   = 0.0
        reasons = []

        # Positive gap = bullish momentum overnight
        if gap_pct >= 3.0:
            score += 3.0
            reasons.append(f"gap +{gap_pct:.1f}%")
        elif gap_pct >= 1.0:
            score += 2.0
            reasons.append(f"gap +{gap_pct:.1f}%")
        elif gap_pct >= 0.0:
            score += 0.5
        else:
            score -= 1.0  # gapping down = bearish

        # Volume spike = institutional interest
        if vol_ratio >= 2.0:
            score += 2.0
            reasons.append(f"vol {vol_ratio:.1f}x")
        elif vol_ratio >= 1.3:
            score += 1.0

        # RSI sweet spot: trending but not overbought
        if 58 <= rsi <= 75:
            score += 2.0
            reasons.append(f"RSI={rsi:.0f}")
        elif 50 <= rsi < 58:
            score += 1.0
        elif rsi > 75:
            score += 0.5  # overbought, caution

        # Price above MAs = trend confirmed
        if above_ma5 and above_ma20:
            score += 2.0
            reasons.append("above MAs")
        elif above_ma20:
            score += 1.0

        # Consistency bonus — strong recent 3-day run
        if len(close) >= 3:
            three_day = (price - close.iloc[-4]) / close.iloc[-4] * 100 if len(close) >= 4 else 0
            if three_day >= 5:
                score += 1.0
                reasons.append(f"+{three_day:.1f}% 3d")

        score = min(10.0, max(0.0, score))

        return PremarketScore(
            symbol     = symbol,
            heat_score = round(score, 2),
            gap_pct    = round(gap_pct, 2),
            vol_ratio  = round(vol_ratio, 2),
            above_ma5  = above_ma5,
            above_ma20 = above_ma20,
            rsi        = round(rsi, 1),
            reason     = " · ".join(reasons) if reasons else "neutral",
        )
