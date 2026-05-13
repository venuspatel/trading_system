# -*- coding: utf-8 -*-
"""
EnhancedConvictionEngine
-------------------------
Extends the base strategy conviction score with 4 additional signal layers:

  Layer 1 (existing): Strategy votes — sum of weighted confidence scores
  Layer 2 (new):      News sentiment — positive/negative news = ±0.0 to ±1.5
  Layer 3 (new):      ADX trend strength — strong trend = 0 to +1.0 bonus
  Layer 4 (new):      Volume surge — institutional buying = 0 to +0.8 bonus
  Layer 5 (new):      Analyst consensus — Wall St ratings = ±0.0 to ±0.5

Final score = L1 + L2 + L3 + L4 + L5
Threshold   = 2.5 (Profit Maximizer) — same as before, but now reachable

Example — MU today:
  Without enhancement:  +2.05 → HOLD (below 2.5)
  With positive news:   +2.05 + 0.80 = +2.85 → BUY
  AMD with ADX trend:   +1.50 + 1.00 + 0.80 = +3.30 → BUY (would have caught it)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

try:
    from .multi_timeframe_conviction import MultiTimeframeConviction, MultiTimeframeResult
    _MTF = MultiTimeframeConviction()
except Exception:
    _MTF = None


@dataclass
class ConvictionBreakdown:
    """Full breakdown of how conviction was calculated."""
    symbol:            str
    strategy_score:    float = 0.0   # Layer 1 — base strategy votes
    news_score:        float = 0.0   # Layer 2 — news sentiment
    adx_score:         float = 0.0   # Layer 3 — trend strength bonus
    volume_score:      float = 0.0   # Layer 4 — volume surge bonus
    analyst_score:     float = 0.0   # Layer 5 — analyst consensus
    mtf_bonus:         float = 0.0   # Layer 6 — multi-timeframe alignment
    mtf_summary:       str   = ""    # W=+0.9 M=+0.8 Y=+0.5
    final_score:       float = 0.0   # sum of all layers
    threshold:         float = 2.5

    # Debug info
    adx_value:         float = 0.0
    volume_ratio:      float = 0.0
    news_headline:     str   = ""
    analyst_rating:    str   = ""

    @property
    def passes(self) -> bool:
        return self.final_score >= self.threshold

    @property
    def gap_to_threshold(self) -> float:
        return round(self.threshold - self.final_score, 3)

    def summary(self) -> str:
        parts = [f"strategies={self.strategy_score:+.2f}"]
        if self.news_score:    parts.append(f"news={self.news_score:+.2f}")
        if self.adx_score:     parts.append(f"adx={self.adx_score:+.2f}")
        if self.volume_score:  parts.append(f"vol={self.volume_score:+.2f}")
        if self.analyst_score: parts.append(f"analyst={self.analyst_score:+.2f}")
        if self.mtf_bonus:     parts.append(f"mtf={self.mtf_bonus:+.2f}({self.mtf_summary})")
        parts.append(f"= {self.final_score:+.2f}")
        return " | ".join(parts)


class EnhancedConvictionEngine:
    """
    Wraps the base strategy report and layers in additional signals.

    Usage:
        engine = EnhancedConvictionEngine(config)
        breakdown = engine.score(symbol, df, strategy_report, news_data)
        if breakdown.passes:
            # trade executes
    """

    # Layer weights — tunable per mode
    NEWS_WEIGHT    = 1.0   # news sentiment multiplier
    ADX_MAX_BONUS  = 1.0   # max ADX contribution when ADX >= 50
    ADX_THRESHOLD  = 25.0  # ADX must exceed this to add any bonus
    VOLUME_MAX     = 0.8   # max volume contribution at 3x average
    ANALYST_MAX    = 0.5   # max analyst contribution (Strong Buy)

    def __init__(self, threshold: float = 2.5):
        self.threshold = threshold

    def score(
        self,
        symbol:          str,
        df:              pd.DataFrame,   # daily OHLCV — used for ADX, volume, MTF
        strategy_score:  float,
        news_sentiment:  Optional[Dict] = None,
        analyst_data:    Optional[Dict] = None,
    ) -> ConvictionBreakdown:
        """
        Calculate the enhanced conviction score.

        Args:
            symbol:         Ticker symbol
            df:             OHLCV DataFrame
            strategy_score: Base conviction from strategy votes (Layer 1)
            news_sentiment: Dict with 'score' (-1 to +1) and 'headline'
            analyst_data:   Dict with 'rating' string and 'score' (-1 to +1)

        Returns:
            ConvictionBreakdown with all layers and final score
        """
        bd = ConvictionBreakdown(
            symbol=symbol,
            strategy_score=strategy_score,
            threshold=self.threshold,
        )

        # Layer 2 — News sentiment
        bd.news_score, bd.news_headline = self._news_layer(news_sentiment)

        # Layer 3 — ADX trend strength
        bd.adx_score, bd.adx_value = self._adx_layer(df)

        # Layer 4 — Volume surge
        bd.volume_score, bd.volume_ratio = self._volume_layer(df)

        # Layer 5 — Analyst consensus
        bd.analyst_score, bd.analyst_rating = self._analyst_layer(analyst_data)

        # Final score
        # Layer 6 — Multi-timeframe alignment (weekly/monthly/yearly)
        bd.mtf_bonus, bd.mtf_summary = self._mtf_layer(df)

        bd.final_score = round(
            bd.strategy_score +
            bd.news_score +
            bd.adx_score +
            bd.volume_score +
            bd.analyst_score +
            bd.mtf_bonus,
            3
        )

        logger.info(
            f"[Conviction] {symbol} | {bd.summary()} | "
            f"{'PASS' if bd.passes else f'HOLD gap={bd.gap_to_threshold:+.2f}'}"
        )

        return bd

    def _news_layer(self, news_data: Optional[Dict]) -> tuple:
        """
        Layer 2: News sentiment → conviction bonus.
        Strong positive news = +0.8 to +1.5
        Mild positive = +0.3 to +0.5
        Neutral = 0.0
        Negative = -0.5 to -1.0
        """
        if not news_data:
            return 0.0, ""

        raw_score = news_data.get("score", 0.0)
        headline  = news_data.get("top_headline", "")

        # Scale: raw score is -1 to +1, map to -1.0 to +1.5 range
        # Positive news gets a slight boost since we're long-biased
        if raw_score > 0:
            conviction_boost = raw_score * 1.5
        else:
            conviction_boost = raw_score * 1.0

        return round(min(1.5, max(-1.0, conviction_boost)), 3), headline

    def _adx_layer(self, df: pd.DataFrame) -> tuple:
        """
        Layer 3: ADX trend strength → conviction bonus.
        ADX < 25  = 0.0 bonus (no trend)
        ADX 25-40 = 0.0 to +0.5 bonus (developing trend)
        ADX 40-60 = +0.5 to +1.0 bonus (strong trend — AMD-style)
        ADX > 60  = +1.0 bonus (extreme trend, capped)
        """
        if len(df) < 30:
            return 0.0, 0.0

        try:
            from indicators.adx import ADXIndicator
            adx_ind  = ADXIndicator(period=14)
            adx_data = adx_ind.latest(df)
            adx_val  = adx_data["adx"]
            direction = adx_data["direction"]

            if adx_val < self.ADX_THRESHOLD or direction == "DOWN":
                return 0.0, adx_val

            # Linear scale from ADX_THRESHOLD to 60
            bonus = min(self.ADX_MAX_BONUS,
                        (adx_val - self.ADX_THRESHOLD) / (60 - self.ADX_THRESHOLD) * self.ADX_MAX_BONUS)
            return round(bonus, 3), adx_val

        except Exception as e:
            logger.debug(f"ADX layer error: {e}")
            return 0.0, 0.0

    def _volume_layer(self, df: pd.DataFrame) -> tuple:
        """
        Layer 4: Volume surge → conviction bonus.
        1x average  = 0.0 bonus
        2x average  = +0.4 bonus
        3x+ average = +0.8 bonus (capped)
        """
        if len(df) < 25 or "volume" not in df.columns:
            return 0.0, 0.0

        try:
            volume  = df["volume"].astype(float)
            avg_vol = volume.iloc[-22:-2].mean()  # 20-day avg, excluding last 2 days

            if avg_vol <= 0:
                return 0.0, 0.0

            today_vol = volume.iloc[-1]
            ratio     = today_vol / avg_vol

            if ratio < 1.2:
                return 0.0, round(ratio, 2)

            # Scale from 1.2x to 3x
            bonus = min(self.VOLUME_MAX,
                        (ratio - 1.2) / (3.0 - 1.2) * self.VOLUME_MAX)
            return round(bonus, 3), round(ratio, 2)

        except Exception as e:
            logger.debug(f"Volume layer error: {e}")
            return 0.0, 0.0

    def _analyst_layer(self, analyst_data: Optional[Dict]) -> tuple:
        """
        Layer 5: Analyst consensus → conviction bonus.
        Strong Buy  = +0.50
        Buy         = +0.25
        Hold        = 0.00
        Underperform= -0.25
        Sell        = -0.50
        """
        if not analyst_data:
            return 0.0, ""

        rating = analyst_data.get("rating", "").lower()
        score  = analyst_data.get("score", 0.0)

        # If numeric score provided, use it directly
        if score != 0.0:
            return round(min(0.5, max(-0.5, score)), 3), rating

        # Map text rating to score
        rating_map = {
            "strong buy":     0.50,
            "buy":            0.25,
            "outperform":     0.25,
            "overweight":     0.25,
            "hold":           0.00,
            "neutral":        0.00,
            "underperform":  -0.25,
            "underweight":   -0.25,
            "sell":          -0.50,
            "strong sell":   -0.50,
        }

        numeric = 0.0
        for key, val in rating_map.items():
            if key in rating:
                numeric = val
                break

        return round(numeric, 3), rating

    def _mtf_layer(self, df: pd.DataFrame) -> tuple:
        """
        Layer 6: Multi-timeframe conviction bonus.
        Weekly/monthly/yearly alignment adds up to +2.3 conviction.
        """
        if _MTF is None or df is None or len(df) < 30:
            return 0.0, ""
        try:
            result = _MTF.analyse("symbol", df)
            return result.total_bonus, result.summary()
        except Exception as e:
            logger.debug(f"MTF layer error: {e}")
            return 0.0, ""

    def for_mode(self, approach: str) -> "EnhancedConvictionEngine":
        """Return a conviction engine tuned for the trading mode."""
        thresholds = {
            "Conservative":     3.5,
            "Balanced":         3.0,
            "Aggressive":       2.0,
            "Profit Maximizer": 2.5,
            "Long Term":        4.0,
        }
        return EnhancedConvictionEngine(
            threshold=thresholds.get(approach, 2.5)
        )
