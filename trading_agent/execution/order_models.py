# -*- coding: utf-8 -*-
"""
Order models
------------
Clean data types that flow between the DecisionEngine,
Executor, and the broker API. Provider-agnostic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderType(Enum):
    MARKET = "market"
    LIMIT  = "limit"
    STOP   = "stop"


class OrderSide(Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING   = "pending"
    SUBMITTED = "submitted"
    FILLED    = "filled"
    PARTIAL   = "partial"
    CANCELLED = "cancelled"
    REJECTED  = "rejected"
    FAILED    = "failed"


class TimeInForce(Enum):
    DAY = "day"    # expires at market close
    GTC = "gtc"    # good till cancelled
    IOC = "ioc"    # immediate or cancel
    OPG = "opg"    # at open


@dataclass
class Order:
    """A single order sent to the broker."""
    symbol:        str
    side:          OrderSide
    qty:           int
    order_type:    OrderType       = OrderType.MARKET
    limit_price:   Optional[float] = None
    stop_price:    Optional[float] = None
    time_in_force: TimeInForce     = TimeInForce.DAY
    client_order_id: Optional[str] = None    # our internal ID

    # Filled in by broker response
    broker_order_id: Optional[str] = None
    status:          OrderStatus   = OrderStatus.PENDING
    filled_qty:      int           = 0
    filled_avg_price: Optional[float] = None
    submitted_at:    Optional[datetime] = None
    filled_at:       Optional[datetime] = None
    error_message:   Optional[str] = None

    @property
    def is_complete(self) -> bool:
        return self.status in (
            OrderStatus.FILLED, OrderStatus.CANCELLED,
            OrderStatus.REJECTED, OrderStatus.FAILED
        )

    @property
    def dollar_value(self) -> float:
        price = self.filled_avg_price or self.limit_price or 0
        return round(self.filled_qty * price, 2)

    def __str__(self):
        return (
            f"[{self.status.value.upper()}] {self.side.value.upper()} "
            f"{self.qty} {self.symbol} @ "
            f"{'MKT' if self.order_type == OrderType.MARKET else f'${self.limit_price:.2f}'}"
        )


@dataclass
class Position:
    """A currently open position tracked by the executor."""
    symbol:       str
    qty:          int
    entry_price:  float
    current_price: float           = 0.0
    stop_loss:    Optional[float]  = None
    take_profit:  Optional[float]  = None
    entry_time:   Optional[datetime] = None
    stop_order_id: Optional[str]  = None
    tp_order_id:   Optional[str]  = None

    @property
    def unrealised_pnl(self) -> float:
        return round((self.current_price - self.entry_price) * self.qty, 2)

    @property
    def unrealised_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return round((self.current_price - self.entry_price) / self.entry_price, 4)

    @property
    def market_value(self) -> float:
        return round(self.current_price * self.qty, 2)

    @property
    def cost_basis(self) -> float:
        return round(self.entry_price * self.qty, 2)

    def __str__(self):
        pnl_sign = "+" if self.unrealised_pnl >= 0 else ""
        return (
            f"{self.symbol} {self.qty} shares | "
            f"entry=${self.entry_price:.2f} now=${self.current_price:.2f} | "
            f"P&L: {pnl_sign}${self.unrealised_pnl:.2f} ({pnl_sign}{self.unrealised_pnl_pct:.1%})"
        )
