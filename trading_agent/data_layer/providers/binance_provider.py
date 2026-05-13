"""
Binance data provider  — STUB / FUTURE PLUG-IN
-----------------------------------------------
This stub satisfies the DataProvider interface so the rest of the
agent compiles and runs today.  Replace the NotImplementedError bodies
with real python-binance or binance-connector calls when you're ready.

Setup (when ready):
    pip install python-binance

Environment variables (when ready):
    BINANCE_API_KEY
    BINANCE_SECRET_KEY
    BINANCE_TESTNET   (set to '1' to use Binance testnet)

Notes:
    - Binance uses different symbol notation: 'BTCUSDT' not 'BTC/USD'
    - Testnet available at https://testnet.binance.vision
    - WebSocket streams are at wss://stream.binance.com:9443
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from .base import Bar, BarCallback, DataProvider, Quote, QuoteCallback, Trade, TradeCallback

logger = logging.getLogger(__name__)

_SETUP_HINT = (
    "\n\n  Binance provider is not yet implemented.\n"
    "  To activate:\n"
    "    1. pip install python-binance\n"
    "    2. Set BINANCE_API_KEY and BINANCE_SECRET_KEY env vars\n"
    "       (or BINANCE_TESTNET=1 for the testnet)\n"
    "    3. Replace the NotImplementedError stubs in binance_provider.py\n"
    "       with real python-binance calls.\n"
)

# Binance kline interval mapping  (agent notation → Binance notation)
_INTERVAL_MAP = {
    "1Min":  "1m",
    "5Min":  "5m",
    "15Min": "15m",
    "30Min": "30m",
    "1Hour": "1h",
    "4Hour": "4h",
    "1Day":  "1d",
}


class BinanceProvider(DataProvider):
    """
    Stub for Binance.  Raises NotImplementedError on every call
    until the implementation is filled in.
    """

    def __init__(
        self,
        api_key:    Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet:    bool = False,
    ):
        self._api_key    = api_key    or os.getenv("BINANCE_API_KEY",    "")
        self._secret_key = secret_key or os.getenv("BINANCE_SECRET_KEY", "")
        self._testnet    = testnet or bool(os.getenv("BINANCE_TESTNET"))
        self._client     = None   # will hold binance.Client instance
        self._bm         = None   # will hold BinanceSocketManager

    @property
    def name(self) -> str:
        return "Binance"

    # ------------------------------------------------------------------
    def connect(self) -> None:
        logger.warning("[Binance] Provider is a stub — not yet implemented." + _SETUP_HINT)
        # TODO:
        # from binance.client import Client
        # self._client = Client(self._api_key, self._secret_key,
        #                       testnet=self._testnet)
        # logger.info(f"[Binance] Connected (testnet={self._testnet})")

    def disconnect(self) -> None:
        if self._bm:
            pass   # TODO: close all socket connections

    # ------------------------------------------------------------------
    def get_bars(self, symbol, timeframe, start, end=None, limit=1000) -> List[Bar]:
        raise NotImplementedError(_SETUP_HINT)
        # TODO:
        # interval = _INTERVAL_MAP[timeframe]
        # klines = self._client.get_historical_klines(symbol, interval,
        #               str(int(start.timestamp()*1000)),
        #               str(int(end.timestamp()*1000)) if end else None,
        #               limit=limit)
        # return [_kline_to_bar(symbol, k) for k in klines]

    def get_latest_bar(self, symbol: str) -> Bar:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: self._client.get_klines(symbol=symbol, interval='1m', limit=1)[-1]

    def subscribe_quotes(self, symbols, callback: QuoteCallback) -> None:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: BinanceSocketManager + bookTicker stream

    def subscribe_trades(self, symbols, callback: TradeCallback) -> None:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: BinanceSocketManager + trade stream

    def subscribe_bars(self, symbols, callback: BarCallback) -> None:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: BinanceSocketManager + kline stream (closed candles only)

    def unsubscribe(self, symbols) -> None:
        pass   # no-op until implemented

    def is_market_open(self) -> bool:
        return True   # Crypto never closes


# ------------------------------------------------------------------
# Helper (activate when implementing)
# ------------------------------------------------------------------
def _kline_to_bar(symbol: str, k: list) -> Bar:
    """Convert a Binance raw kline list to our internal Bar dataclass."""
    from datetime import timezone
    return Bar(
        symbol    = symbol,
        timestamp = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
        open      = float(k[1]),
        high      = float(k[2]),
        low       = float(k[3]),
        close     = float(k[4]),
        volume    = float(k[5]),
        vwap      = None,
    )
