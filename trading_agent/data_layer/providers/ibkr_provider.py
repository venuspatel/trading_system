"""
Interactive Brokers (IBKR) data provider  — STUB / FUTURE PLUG-IN
------------------------------------------------------------------
This stub satisfies the DataProvider interface so the rest of the
agent compiles and runs today.  Replace the NotImplementedError bodies
with real ib_insync or ibapi calls when you're ready to go live with IBKR.

Setup (when ready):
    pip install ib_insync

Prerequisites:
    - TWS (Trader Workstation) or IB Gateway running locally
    - API access enabled in TWS settings (port 7497 for paper, 7496 for live)

Environment variables (when ready):
    IBKR_HOST   (default: 127.0.0.1)
    IBKR_PORT   (default: 7497 for paper)
    IBKR_CLIENT_ID (default: 1)
"""

import logging
from datetime import datetime
from typing import List, Optional

from .base import Bar, BarCallback, DataProvider, Quote, QuoteCallback, Trade, TradeCallback

logger = logging.getLogger(__name__)

_SETUP_HINT = (
    "\n\n  Interactive Brokers provider is not yet implemented.\n"
    "  To activate:\n"
    "    1. pip install ib_insync\n"
    "    2. Start TWS or IB Gateway (paper port 7497, live port 7496)\n"
    "    3. Replace the NotImplementedError stubs in ibkr_provider.py\n"
    "       with real ib_insync calls.\n"
)


class IBKRProvider(DataProvider):
    """
    Stub for Interactive Brokers.  Raises NotImplementedError on every call
    until the implementation is filled in.
    """

    def __init__(
        self,
        host:      str = "127.0.0.1",
        port:      int = 7497,
        client_id: int = 1,
    ):
        self._host      = host
        self._port      = port
        self._client_id = client_id
        self._ib        = None   # will hold ib_insync.IB() instance

    @property
    def name(self) -> str:
        return "InteractiveBrokers"

    # ------------------------------------------------------------------
    def connect(self) -> None:
        logger.warning("[IBKR] Provider is a stub — not yet implemented." + _SETUP_HINT)
        # TODO:
        # from ib_insync import IB
        # self._ib = IB()
        # self._ib.connect(self._host, self._port, clientId=self._client_id)

    def disconnect(self) -> None:
        if self._ib:
            self._ib.disconnect()

    # ------------------------------------------------------------------
    def get_bars(self, symbol, timeframe, start, end=None, limit=1000) -> List[Bar]:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: use reqHistoricalData via ib_insync

    def get_latest_bar(self, symbol: str) -> Bar:
        raise NotImplementedError(_SETUP_HINT)

    def subscribe_quotes(self, symbols, callback: QuoteCallback) -> None:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: ib.reqMktData + event hook

    def subscribe_trades(self, symbols, callback: TradeCallback) -> None:
        raise NotImplementedError(_SETUP_HINT)

    def subscribe_bars(self, symbols, callback: BarCallback) -> None:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: reqRealTimeBars (5-sec) or reqHistoricalData with keepUpToDate=True

    def unsubscribe(self, symbols) -> None:
        pass   # no-op until implemented

    def is_market_open(self) -> bool:
        raise NotImplementedError(_SETUP_HINT)
        # TODO: self._ib.reqMarketDataType or check trading hours via contractDetails
