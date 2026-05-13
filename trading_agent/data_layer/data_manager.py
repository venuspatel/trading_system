"""
DataManager — single entry point for all market data needs
-----------------------------------------------------------
Every other part of the trading agent talks to DataManager.
DataManager talks to whichever DataProvider is configured.

Switching from Alpaca to IBKR later requires changing ONE line:
    manager = DataManager(provider=IBKRProvider(...))
"""

import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

import pandas as pd

from .providers.base import Bar, BarCallback, DataProvider, Quote, QuoteCallback, Trade, TradeCallback

logger = logging.getLogger(__name__)


class DataManager:
    """
    Wraps a DataProvider and adds:
      - In-memory rolling bar cache (per symbol / timeframe)
      - Quote cache (latest quote per symbol)
      - Pandas DataFrame helpers for strategies
      - Simple pub/sub so multiple strategies can listen to the same stream
    """

    def __init__(
        self,
        provider:        DataProvider,
        bar_cache_size:  int = 500,   # bars kept per symbol per timeframe
    ):
        self._provider       = provider
        self._bar_cache_size = bar_cache_size

        # Cache stores: {(symbol, timeframe): deque[Bar]}
        self._bar_cache:   Dict[tuple, deque] = defaultdict(lambda: deque(maxlen=bar_cache_size))
        self._quote_cache: Dict[str, Quote]   = {}
        self._trade_cache: Dict[str, Trade]   = {}

        # Internal subscriber lists
        self._quote_subs: Dict[str, List[QuoteCallback]] = defaultdict(list)
        self._trade_subs: Dict[str, List[TradeCallback]] = defaultdict(list)
        self._bar_subs:   Dict[str, List[BarCallback]]   = defaultdict(list)

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the underlying provider."""
        self._provider.connect()
        logger.info(f"[DataManager] Connected via {self._provider.name}")

    def disconnect(self) -> None:
        self._provider.disconnect()
        logger.info("[DataManager] Disconnected")

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def is_market_open(self) -> bool:
        return self._provider.is_market_open()

    # ------------------------------------------------------------------
    # Historical data  (returns DataFrames for strategy convenience)
    # ------------------------------------------------------------------

    def get_bars_df(
        self,
        symbol:    str,
        timeframe: str,
        start:     datetime,
        end:       Optional[datetime] = None,
        limit:     int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch historical bars and return as a pandas DataFrame.

        Columns: timestamp, open, high, low, close, volume, vwap
        Index:   DatetimeIndex (UTC)

        Example:
            df = manager.get_bars_df("AAPL", "1Day",
                                     start=datetime(2023,1,1, tzinfo=timezone.utc))
            df["close"].plot()
        """
        bars = self._provider.get_bars(symbol, timeframe, start, end, limit)
        self._cache_bars(symbol, timeframe, bars)
        return self._bars_to_df(bars)

    def get_latest_bar(self, symbol: str) -> Optional[Bar]:
        """Return the most recent bar for a symbol."""
        return self._provider.get_latest_bar(symbol)

    def get_cached_bars_df(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """
        Return whatever bars are already in the in-memory cache
        (populated by streaming or prior get_bars_df calls).
        Useful for fast access inside streaming callbacks.
        """
        key = (symbol.upper(), timeframe)
        with self._lock:
            bars = list(self._bar_cache.get(key, []))
        return self._bars_to_df(bars)

    def warm_cache(
        self,
        symbols:   List[str],
        timeframe: str,
        lookback_days: int = 30,
    ) -> None:
        """
        Pre-load historical bars into the in-memory cache.
        Call this once at startup so strategies have data immediately.

        Example:
            manager.warm_cache(["AAPL", "TSLA", "NVDA"], "1Day", lookback_days=90)
        """
        start = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        for symbol in symbols:
            try:
                bars = self._provider.get_bars(symbol, timeframe, start)
                self._cache_bars(symbol, timeframe, bars)
                logger.info(f"[DataManager] Warmed {len(bars)} {timeframe} bars for {symbol}")
            except Exception as exc:
                logger.warning(f"[DataManager] warm_cache({symbol}) failed: {exc}")

    # ------------------------------------------------------------------
    # Real-time streaming  (pub/sub wrapper over provider streams)
    # ------------------------------------------------------------------

    def subscribe_quotes(self, symbols: List[str], callback: QuoteCallback) -> None:
        """
        Register a callback for live quote updates.
        Multiple callbacks can subscribe to the same symbols.
        """
        for sym in symbols:
            self._quote_subs[sym.upper()].append(callback)

        # Only wire provider subscription once per symbol
        new_symbols = [s for s in symbols if len(self._quote_subs[s.upper()]) == 1]
        if new_symbols:
            self._provider.subscribe_quotes(new_symbols, self._on_quote)

    def subscribe_trades(self, symbols: List[str], callback: TradeCallback) -> None:
        for sym in symbols:
            self._trade_subs[sym.upper()].append(callback)
        new_symbols = [s for s in symbols if len(self._trade_subs[s.upper()]) == 1]
        if new_symbols:
            self._provider.subscribe_trades(new_symbols, self._on_trade)

    def subscribe_bars(self, symbols: List[str], callback: BarCallback) -> None:
        for sym in symbols:
            self._bar_subs[sym.upper()].append(callback)
        new_symbols = [s for s in symbols if len(self._bar_subs[s.upper()]) == 1]
        if new_symbols:
            self._provider.subscribe_bars(new_symbols, self._on_bar)

    def unsubscribe(self, symbols: List[str]) -> None:
        for sym in symbols:
            s = sym.upper()
            self._quote_subs.pop(s, None)
            self._trade_subs.pop(s, None)
            self._bar_subs.pop(s, None)
        self._provider.unsubscribe(symbols)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def latest_quote(self, symbol: str) -> Optional[Quote]:
        return self._quote_cache.get(symbol.upper())

    def latest_trade(self, symbol: str) -> Optional[Trade]:
        return self._trade_cache.get(symbol.upper())

    # ------------------------------------------------------------------
    # Internal callbacks (provider → cache → subscribers)
    # ------------------------------------------------------------------

    def _on_quote(self, q: Quote) -> None:
        self._quote_cache[q.symbol.upper()] = q
        for cb in self._quote_subs.get(q.symbol.upper(), []):
            try:
                cb(q)
            except Exception as exc:
                logger.error(f"[DataManager] Quote callback error: {exc}")

    def _on_trade(self, t: Trade) -> None:
        self._trade_cache[t.symbol.upper()] = t
        for cb in self._trade_subs.get(t.symbol.upper(), []):
            try:
                cb(t)
            except Exception as exc:
                logger.error(f"[DataManager] Trade callback error: {exc}")

    def _on_bar(self, b: Bar) -> None:
        self._cache_bars(b.symbol, "1Min", [b])
        for cb in self._bar_subs.get(b.symbol.upper(), []):
            try:
                cb(b)
            except Exception as exc:
                logger.error(f"[DataManager] Bar callback error: {exc}")

    def _cache_bars(self, symbol: str, timeframe: str, bars: List[Bar]) -> None:
        key = (symbol.upper(), timeframe)
        with self._lock:
            self._bar_cache[key].extend(bars)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bars_to_df(bars: List[Bar]) -> pd.DataFrame:
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap"])
        records = [
            {
                "timestamp": b.timestamp,
                "open":      b.open,
                "high":      b.high,
                "low":       b.low,
                "close":     b.close,
                "volume":    b.volume,
                "vwap":      b.vwap,
            }
            for b in bars
        ]
        df = pd.DataFrame(records).set_index("timestamp")
        df.index = pd.to_datetime(df.index, utc=True)
        return df.sort_index()
