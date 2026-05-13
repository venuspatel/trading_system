# -*- coding: utf-8 -*-
"""
StockScanner — Dynamic watchlist builder
-----------------------------------------
Runs every morning before market open (9:15 AM ET).
Finds the best candidate stocks for the day by screening for:
  - Strong momentum  (RSI 55-75, price above key MAs)
  - Real trend       (ADX > 20)
  - Volume activity  (today's volume > 1.5x 20-day avg)
  - Clean technicals (not overbought, not in downtrend)

Output: ranked list of symbols to add to the day's watchlist.
Pinned symbols (user-defined) are always included.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Universe to screen from — liquid, volatile US stocks worth day-trading
# Expanded from the current 23-symbol watchlist
SCAN_UNIVERSE = [
    # Mega-cap tech
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA",
    # Semiconductors
    "AMD","INTC","AVGO","MU","QCOM","MRVL","SMCI",
    # High-beta / momentum
    "MARA","RKLB","PLTR","SOFI","HIMS","BMNR","SNAP","COIN","HOOD",
    # Energy / commodities
    "SMR","OKLO","NNE",
    # Finance
    "UPST","AFRM","SFM",
    # Healthcare
    "RXRX","ARKG",
    # ETFs for regime signals
    "SPY","QQQ","IWM",
    # Existing watchlist additions
    "NFLX","ORCL","AAL","SNDK",
]

# Always keep these in the watchlist regardless of scan score
DEFAULT_PINNED = ["NVDA","TSLA","MARA","META","RKLB"]


@dataclass
class CandidateScore:
    symbol:        str
    score:         float       # 0-10 composite score
    rsi:           float = 0.0
    adx:           float = 0.0
    vol_ratio:     float = 0.0  # today_volume / 20d_avg_volume
    above_ma20:    bool  = False
    above_ma50:    bool  = False
    momentum_pct:  float = 0.0  # 5-day % change
    reason:        str   = ""


class StockScanner:
    """
    Screens SCAN_UNIVERSE each morning and returns the top N candidates.

    Usage:
        scanner = StockScanner(data_manager)
        candidates = scanner.scan(top_n=15)
        new_watchlist = pinned + [c.symbol for c in candidates]
    """

    def __init__(self, data_manager):
        self._dm = data_manager

    def scan(self, top_n: int = 15, pinned: Optional[List[str]] = None) -> List[CandidateScore]:
        """
        Screen universe, score each stock, return top N candidates.
        Pinned symbols are excluded from scoring (they're always included).
        """
        pinned_set = set(s.upper() for s in (pinned or DEFAULT_PINNED))
        to_scan    = [s for s in SCAN_UNIVERSE if s.upper() not in pinned_set]

        logger.info(f"[Scanner] Scanning {len(to_scan)} symbols for top {top_n} candidates...")

        candidates = []
        start = datetime.now(timezone.utc) - timedelta(days=60)

        for sym in to_scan:
            try:
                df = self._dm.get_bars_df(sym, "1Day", start=start, limit=60)
                if df is None or len(df) < 20:
                    continue
                score = self._score(sym, df)
                if score is not None:
                    candidates.append(score)
            except Exception as ex:
                logger.debug(f"[Scanner] {sym} skipped: {ex}")

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        top = candidates[:top_n]

        logger.info(
            f"[Scanner] Top {len(top)} candidates: "
            + ", ".join(f"{c.symbol}({c.score:.1f})" for c in top)
        )
        return top

    def _score(self, symbol: str, df: pd.DataFrame) -> Optional[CandidateScore]:
        """Score a single stock 0-10 based on momentum, trend, volume."""
        try:
            close  = df["close"]
            high   = df["high"]  if "high"   in df.columns else close
            low    = df["low"]   if "low"    in df.columns else close
            volume = df["volume"] if "volume" in df.columns else pd.Series([1]*len(close))

            if len(close) < 20:
                return None

            # ── RSI (14) ─────────────────────────────────────────────
            delta  = close.diff()
            gain   = delta.clip(lower=0).rolling(14).mean()
            loss   = (-delta.clip(upper=0)).rolling(14).mean()
            rs     = gain / loss.replace(0, float('nan'))
            rsi    = (100 - (100 / (1 + rs))).iloc[-1]

            # ── ADX (14) ──────────────────────────────────────────────
            tr     = pd.concat([
                high - low,
                (high - close.shift(1)).abs(),
                (low  - close.shift(1)).abs()
            ], axis=1).max(axis=1)
            atr14  = tr.rolling(14).mean()
            pdm    = (high.diff()).clip(lower=0)
            mdm    = (-low.diff()).clip(lower=0)
            pdi    = 100 * pdm.rolling(14).mean() / atr14.replace(0, float('nan'))
            mdi    = 100 * mdm.rolling(14).mean() / atr14.replace(0, float('nan'))
            dx     = (100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, float('nan')))
            adx    = dx.rolling(14).mean().iloc[-1]

            # ── Moving averages ───────────────────────────────────────
            ma20   = close.rolling(20).mean().iloc[-1]
            ma50   = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else ma20
            price  = close.iloc[-1]
            above_ma20 = price > ma20
            above_ma50 = price > ma50

            # ── Volume ratio ──────────────────────────────────────────
            avg_vol   = volume.rolling(20).mean().iloc[-1]
            last_vol  = volume.iloc[-1]
            vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else 1.0

            # ── 5-day momentum ────────────────────────────────────────
            momentum_pct = ((price - close.iloc[-6]) / close.iloc[-6] * 100) if len(close) >= 6 else 0.0

            # ── Composite score (0-10) ────────────────────────────────
            score = 0.0
            reasons = []

            # RSI sweet spot: 55-75 (trending but not overbought)
            if 55 <= rsi <= 75:
                score += 3.0
                reasons.append(f"RSI={rsi:.0f}")
            elif 45 <= rsi < 55:
                score += 1.0
            elif rsi > 75:
                score += 0.5  # overbought — lower score

            # ADX > 20 means real trend
            if adx >= 30:
                score += 3.0
                reasons.append(f"ADX={adx:.0f}↑")
            elif adx >= 20:
                score += 2.0
                reasons.append(f"ADX={adx:.0f}")

            # Price above MAs
            if above_ma20:
                score += 1.0
            if above_ma50:
                score += 1.0
                reasons.append("above MA50")

            # Volume spike
            if vol_ratio >= 2.0:
                score += 2.0
                reasons.append(f"vol {vol_ratio:.1f}x")
            elif vol_ratio >= 1.5:
                score += 1.0

            # Strong recent momentum
            if momentum_pct >= 5:
                score += 1.0
                reasons.append(f"+{momentum_pct:.1f}% 5d")
            elif momentum_pct < -5:
                score -= 1.0   # penalise recent losers

            # Cap at 10
            score = min(10.0, max(0.0, score))

            return CandidateScore(
                symbol       = symbol,
                score        = round(score, 2),
                rsi          = round(rsi, 1),
                adx          = round(adx, 1),
                vol_ratio    = round(vol_ratio, 2),
                above_ma20   = above_ma20,
                above_ma50   = above_ma50,
                momentum_pct = round(momentum_pct, 2),
                reason       = " · ".join(reasons),
            )

        except Exception as ex:
            logger.debug(f"[Scanner] Score failed for {symbol}: {ex}")
            return None
