# -*- coding: utf-8 -*-
"""
IntradayFetcher — fetches and caches 15-min bars for the current trading day
-----------------------------------------------------------------------------
Runs once per scan cycle, fetches today's 15-min bars for all watchlist
symbols, calculates VWAP, and makes data available to intraday strategies.

Caches results to avoid hitting the API repeatedly within a scan cycle.
Cache expires every 5 minutes — fresh enough for 10-min scan cycles.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

ET_OFFSET = timedelta(hours=5)  # UTC-5 (EST); adjust for EDT automatically


class IntradayFetcher:
    """
    Fetches 15-min intraday bars and calculates VWAP for the current day.

    Usage:
        fetcher = IntradayFetcher(data_manager)
        intraday_data = fetcher.fetch_all(watchlist)
        df_15min = intraday_data.get("AMD")  # None if unavailable
    """

    CACHE_TTL_SECONDS = 300   # 5 minutes

    def __init__(self, data_manager):
        self._dm    = data_manager
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_time: Optional[datetime] = None

    def fetch_all(self, symbols: list) -> Dict[str, pd.DataFrame]:
        """
        Fetch 15-min bars for all symbols.
        Returns {symbol: DataFrame} — DataFrame has VWAP column added.
        """
        # Check cache freshness
        now = datetime.now(timezone.utc)
        if (self._cache_time and
                (now - self._cache_time).total_seconds() < self.CACHE_TTL_SECONDS):
            return self._cache

        # Today's market open in UTC — 9:30 AM ET = 13:30 UTC (EDT) or 14:30 UTC (EST)
        # Use a 15-min delay buffer for IEX feed
        offset_hours = 4 if self._is_dst(now) else 5   # EDT=4, EST=5
        market_open_utc = now.replace(
            hour=13 + (5 - offset_hours), minute=30, second=0, microsecond=0
        )
        # Start from market open today; if before open, go back 1 day
        start = market_open_utc
        if now < market_open_utc:
            start = market_open_utc - timedelta(days=1)

        fresh: Dict[str, pd.DataFrame] = {}
        fetched = 0
        errors  = 0

        for sym in symbols:
            try:
                # Use DataManager.get_bars_df — no adjustment param for intraday
                df = self._dm.get_bars_df(
                    sym, "15Min", start=start, limit=30
                )
                if df is None or len(df) < 2:
                    continue
                df = self._add_vwap(df)
                fresh[sym] = df
                fetched += 1
            except Exception as ex:
                errors += 1
                logger.warning(f"[IntradayFetcher] {sym} failed: {ex}")

        if fetched == 0 and errors > 0:
            logger.warning(f"[IntradayFetcher] ALL {errors} symbols failed — check Alpaca feed access")
        logger.info(
            f"[IntradayFetcher] 15-min bars: {fetched} fetched, "
            f"{errors} errors, {len(symbols)-fetched-errors} skipped"
        )
        self._cache      = fresh
        self._cache_time = now
        return fresh

    def get(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return cached 15-min df for a symbol, or None."""
        return self._cache.get(symbol.upper())

    def _add_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate VWAP and add as a column."""
        df = df.copy()
        high   = df["high"]   if "high"   in df.columns else df["close"]
        low    = df["low"]    if "low"    in df.columns else df["close"]
        close  = df["close"]
        volume = df["volume"] if "volume" in df.columns else pd.Series([1]*len(close), index=close.index)

        typical = (high + low + close) / 3
        df["vwap"] = (typical * volume).cumsum() / volume.cumsum().replace(0, float('nan'))
        return df

    @staticmethod
    def _is_dst(dt: datetime) -> bool:
        """Rough DST check — US clocks spring forward 2nd Sunday March."""
        month = dt.month
        return 3 <= month <= 11   # approximate
