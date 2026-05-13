"""
Base interface that every data provider must implement.
Alpaca, IBKR, and Binance all conform to this contract so the rest
of the agent never needs to know which provider is active.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional


@dataclass
class Bar:
    """One OHLCV candlestick bar."""
    symbol:     str
    timestamp:  datetime
    open:       float
    high:       float
    low:        float
    close:      float
    volume:     float
    vwap:       Optional[float] = None


@dataclass
class Quote:
    """Real-time best bid/ask snapshot."""
    symbol:     str
    timestamp:  datetime
    bid:        float
    ask:        float
    bid_size:   float
    ask_size:   float

    @property
    def mid(self) -> float:
        return round((self.bid + self.ask) / 2, 6)

    @property
    def spread(self) -> float:
        return round(self.ask - self.bid, 6)


@dataclass
class Trade:
    """A single executed trade (tick data)."""
    symbol:     str
    timestamp:  datetime
    price:      float
    size:       float
    conditions: List[str] = field(default_factory=list)


# Type alias for streaming callbacks
QuoteCallback = Callable[[Quote], None]
TradeCallback = Callable[[Trade], None]
BarCallback   = Callable[[Bar],   None]


class DataProvider(ABC):
    """
    Abstract base class for all market data providers.
    Each provider must implement every method below.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name, e.g. 'Alpaca'."""

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Bar]:
        """
        Fetch historical OHLCV bars.

        Args:
            symbol:    Ticker symbol, e.g. 'AAPL' or 'BTC/USD'
            timeframe: '1Min', '5Min', '15Min', '1Hour', '1Day'
            start:     Start of the range (UTC)
            end:       End of the range (UTC). Defaults to now.
            limit:     Max number of bars to return.

        Returns:
            List of Bar objects, oldest first.
        """

    @abstractmethod
    def get_latest_bar(self, symbol: str) -> Bar:
        """Return the single most recent completed bar."""

    # ------------------------------------------------------------------
    # Real-time streaming
    # ------------------------------------------------------------------

    @abstractmethod
    def subscribe_quotes(self, symbols: List[str], callback: QuoteCallback) -> None:
        """
        Stream real-time quotes for the given symbols.
        `callback` is invoked on every incoming Quote.
        """

    @abstractmethod
    def subscribe_trades(self, symbols: List[str], callback: TradeCallback) -> None:
        """Stream real-time trade ticks."""

    @abstractmethod
    def subscribe_bars(self, symbols: List[str], callback: BarCallback) -> None:
        """Stream real-time minute bars as they close."""

    @abstractmethod
    def unsubscribe(self, symbols: List[str]) -> None:
        """Stop streaming for the given symbols."""

    # ------------------------------------------------------------------
    # Account / connectivity
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """Establish connection / authenticate."""

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly close connections."""

    @abstractmethod
    def is_market_open(self) -> bool:
        """Return True if the primary market is currently open."""
