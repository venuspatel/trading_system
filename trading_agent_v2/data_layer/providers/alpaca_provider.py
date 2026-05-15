"""
Alpaca Markets data provider  (ACTIVE default provider)
--------------------------------------------------------
Supports:
  - US equities + crypto
  - Free tier (paper trading) and live accounts
  - REST for historical data, WebSocket for real-time streaming

Setup:
    pip install alpaca-py

Keys (set as environment variables or pass directly):
    ALPACA_API_KEY
    ALPACA_SECRET_KEY
    ALPACA_BASE_URL   (optional — defaults to paper trading)
"""

import os
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from .base import Bar, BarCallback, DataProvider, Quote, QuoteCallback, Trade, TradeCallback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timeframe mapping  (agent notation  →  Alpaca SDK notation)
# ---------------------------------------------------------------------------
_TIMEFRAME_MAP = {
    "1Min":  "1Min",
    "5Min":  "5Min",
    "15Min": "15Min",
    "30Min": "30Min",
    "1Hour": "1Hour",
    "4Hour": "4Hour",
    "1Day":  "1Day",
}


class AlpacaProvider(DataProvider):
    """
    Full Alpaca Markets implementation of DataProvider.

    Example usage:
        provider = AlpacaProvider(
            api_key="YOUR_KEY",
            secret_key="YOUR_SECRET",
            paper=True,          # True = paper account, False = live
        )
        provider.connect()

        bars = provider.get_bars("AAPL", "1Day",
                                 start=datetime(2024, 1, 1, tzinfo=timezone.utc))
        for bar in bars:
            print(bar)

        provider.subscribe_quotes(["AAPL", "TSLA"], callback=my_quote_handler)
    """

    # ------------------------------------------------------------------
    def __init__(
        self,
        api_key:    Optional[str] = None,
        secret_key: Optional[str] = None,
        paper:      bool          = True,
    ):
        self._api_key    = api_key    or os.getenv("ALPACA_API_KEY",    "")
        self._secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self._paper      = paper

        self._stock_client   = None   # alpaca.data.historical.StockHistoricalDataClient
        self._crypto_client  = None   # alpaca.data.historical.CryptoHistoricalDataClient
        self._stream         = None   # alpaca.data.live.StockDataStream
        self._crypto_stream  = None   # alpaca.data.live.CryptoDataStream
        self._trading_client = None   # alpaca.trading.TradingClient
        self._connected      = False

        self._stream_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return "Alpaca"

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Authenticate and initialise all Alpaca SDK clients."""
        try:
            from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
            from alpaca.data.live      import StockDataStream, CryptoDataStream
            from alpaca.trading        import TradingClient

            self._stock_client   = StockHistoricalDataClient(self._api_key, self._secret_key)
            self._crypto_client  = CryptoHistoricalDataClient()             # public endpoint
            self._trading_client = TradingClient(self._api_key, self._secret_key, paper=self._paper)

            self._stream        = StockDataStream(self._api_key, self._secret_key)
            self._crypto_stream = CryptoDataStream(self._api_key, self._secret_key)

            self._connected = True
            mode = "paper" if self._paper else "LIVE"
            logger.info(f"[Alpaca] Connected ({mode} mode)")

        except ImportError:
            raise ImportError(
                "alpaca-py is not installed.\n"
                "Run:  pip install alpaca-py"
            )
        except Exception as exc:
            logger.error(f"[Alpaca] Connection failed: {exc}")
            raise

    def disconnect(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
        if self._crypto_stream:
            try:
                self._crypto_stream.stop()
            except Exception:
                pass
        self._connected = False
        logger.info("[Alpaca] Disconnected")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_crypto(self, symbol: str) -> bool:
        return "/" in symbol or symbol.upper() in {"BTCUSD", "ETHUSD", "SOLUSD"}

    def _to_alpaca_timeframe(self, tf: str):
        """Convert agent timeframe string to alpaca-py TimeFrame object."""
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        mapping = {
            "1Min":  TimeFrame(1,  TimeFrameUnit.Minute),
            "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "30Min": TimeFrame(30, TimeFrameUnit.Minute),
            "1Hour": TimeFrame(1,  TimeFrameUnit.Hour),
            "4Hour": TimeFrame(4,  TimeFrameUnit.Hour),
            "1Day":  TimeFrame(1,  TimeFrameUnit.Day),
        }
        if tf not in mapping:
            raise ValueError(f"Unknown timeframe '{tf}'. Valid: {list(mapping)}")
        return mapping[tf]

    @staticmethod
    def _alpaca_bar_to_bar(symbol: str, ab) -> Bar:
        """Convert an alpaca-py Bar object to our internal Bar dataclass."""
        return Bar(
            symbol    = symbol,
            timestamp = ab.timestamp.replace(tzinfo=timezone.utc)
                        if ab.timestamp.tzinfo is None else ab.timestamp,
            open      = float(ab.open),
            high      = float(ab.high),
            low       = float(ab.low),
            close     = float(ab.close),
            volume    = float(ab.volume),
            vwap      = float(ab.vwap) if hasattr(ab, "vwap") and ab.vwap else None,
        )

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    def get_bars(
        self,
        symbol:    str,
        timeframe: str,
        start:     datetime,
        end:       Optional[datetime] = None,
        limit:     int = 1000,
    ) -> List[Bar]:
        """Fetch historical OHLCV bars from Alpaca."""
        if not self._connected:
            raise RuntimeError("Call connect() first.")

        tf = self._to_alpaca_timeframe(timeframe)
        end = end or datetime.now(timezone.utc)

        try:
            if self._is_crypto(symbol):
                from alpaca.data.requests import CryptoBarsRequest
                req  = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=tf,
                                         start=start, end=end, limit=limit)
                data = self._crypto_client.get_crypto_bars(req)
            else:
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.enums import DataFeed
                req  = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf,
                                        start=start, end=end, limit=limit,
                                        adjustment="all", feed=DataFeed.IEX)
                data = self._stock_client.get_stock_bars(req)

            bars = [self._alpaca_bar_to_bar(symbol, b) for b in data[symbol]]
            logger.debug(f"[Alpaca] Fetched {len(bars)} bars for {symbol} ({timeframe})")
            return bars

        except Exception as exc:
            logger.error(f"[Alpaca] get_bars({symbol}) failed: {exc}")
            raise

    def get_latest_bar(self, symbol: str) -> Bar:
        """Return the most recent completed bar for a symbol."""
        if not self._connected:
            raise RuntimeError("Call connect() first.")
        try:
            if self._is_crypto(symbol):
                from alpaca.data.requests import CryptoLatestBarRequest
                req  = CryptoLatestBarRequest(symbol_or_symbols=symbol)
                data = self._crypto_client.get_crypto_latest_bar(req)
            else:
                from alpaca.data.requests import StockLatestBarRequest
                from alpaca.data.enums import DataFeed
                req  = StockLatestBarRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
                data = self._stock_client.get_stock_latest_bar(req)

            return self._alpaca_bar_to_bar(symbol, data[symbol])
        except Exception as exc:
            logger.error(f"[Alpaca] get_latest_bar({symbol}) failed: {exc}")
            raise

    # ------------------------------------------------------------------
    # Real-time streaming
    # ------------------------------------------------------------------

    def subscribe_quotes(self, symbols: List[str], callback: QuoteCallback) -> None:
        """Stream live quotes; fires callback(Quote) on every tick."""
        if not self._connected:
            raise RuntimeError("Call connect() first.")

        async def _handler(q):
            callback(Quote(
                symbol    = q.symbol,
                timestamp = q.timestamp,
                bid       = float(q.bid_price),
                ask       = float(q.ask_price),
                bid_size  = float(q.bid_size),
                ask_size  = float(q.ask_size),
            ))

        self._stream.subscribe_quotes(_handler, *symbols)
        self._ensure_stream_running()
        logger.info(f"[Alpaca] Subscribed quotes: {symbols}")

    def subscribe_trades(self, symbols: List[str], callback: TradeCallback) -> None:
        """Stream live trade ticks; fires callback(Trade) on every tick."""
        if not self._connected:
            raise RuntimeError("Call connect() first.")

        async def _handler(t):
            callback(Trade(
                symbol     = t.symbol,
                timestamp  = t.timestamp,
                price      = float(t.price),
                size       = float(t.size),
                conditions = list(t.conditions) if t.conditions else [],
            ))

        self._stream.subscribe_trades(_handler, *symbols)
        self._ensure_stream_running()
        logger.info(f"[Alpaca] Subscribed trades: {symbols}")

    def subscribe_bars(self, symbols: List[str], callback: BarCallback) -> None:
        """Stream real-time 1-minute bars as they close."""
        if not self._connected:
            raise RuntimeError("Call connect() first.")

        async def _handler(b):
            callback(self._alpaca_bar_to_bar(b.symbol, b))

        self._stream.subscribe_bars(_handler, *symbols)
        self._ensure_stream_running()
        logger.info(f"[Alpaca] Subscribed bars: {symbols}")

    def unsubscribe(self, symbols: List[str]) -> None:
        if self._stream:
            self._stream.unsubscribe_quotes(*symbols)
            self._stream.unsubscribe_trades(*symbols)
            self._stream.unsubscribe_bars(*symbols)
        logger.info(f"[Alpaca] Unsubscribed: {symbols}")

    # ------------------------------------------------------------------
    # Market hours
    # ------------------------------------------------------------------

    def is_market_open(self) -> bool:
        """Check if US equities market is currently open."""
        if not self._connected or not self._trading_client:
            return False
        try:
            clock = self._trading_client.get_clock()
            return clock.is_open
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_stream_running(self) -> None:
        """Start the WebSocket stream in a background thread if not already running."""
        if self._stream_thread and self._stream_thread.is_alive():
            return

        def _run():
            try:
                self._stream.run()
            except Exception as exc:
                logger.error(f"[Alpaca] Stream error: {exc}")

        self._stream_thread = threading.Thread(target=_run, daemon=True, name="alpaca-stream")
        self._stream_thread.start()
        logger.debug("[Alpaca] Stream thread started")
