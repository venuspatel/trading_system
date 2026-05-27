# -*- coding: utf-8 -*-
"""
AlpacaExecutor
--------------
Places orders, manages stop-losses and take-profits,
and tracks all open positions via the Alpaca Trading API.

Paper trading and live trading use the same code —
the only difference is the paper=True/False flag in AlpacaProvider.

Order flow for each BUY decision:
  1. Place market order for N shares
  2. On fill confirmation — place stop-loss order (stop)
  3. On fill confirmation — place take-profit order (limit)
  4. Monitor both bracket orders until one fills

Order flow for each SELL decision:
  1. Close the existing position (market order)
  2. Cancel any open stop/TP orders for that symbol
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .order_models import (
    Order, OrderSide, OrderStatus, OrderType,
    Position, TimeInForce
)

logger = logging.getLogger(__name__)


class AlpacaExecutor:
    """
    Executes TradeDecisions from Layer 4 via the Alpaca Trading API.

    Usage:
        executor = AlpacaExecutor(api_key, secret_key, paper=True)
        executor.connect()

        # Called by TradingAgent after each approved decision:
        result = executor.execute(trade_decision)
    """

    def __init__(
        self,
        api_key:    str,
        secret_key: str,
        paper:      bool = True,
    ):
        self._api_key    = api_key
        self._secret_key = secret_key
        self._paper      = paper
        self._client     = None     # alpaca.trading.TradingClient
        self._connected  = False

        # Local position + order tracking
        self._positions:   Dict[str, Position] = {}
        self._today_fills                       = None  # FILL_PRICE_CACHE — None=unfetched, {}=fetched/cleared
        self._orders:     Dict[str, Order]    = {}   # keyed by client_order_id

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self):
        try:
            from alpaca.trading.client import TradingClient
            self._client    = TradingClient(
                self._api_key, self._secret_key, paper=self._paper
            )
            self._connected = True
            mode = "PAPER" if self._paper else "LIVE"
            logger.info(f"[Executor] Connected to Alpaca ({mode})")
            self._sync_positions()
        except ImportError:
            raise ImportError("alpaca-py not installed. Run: pip install alpaca-py")
        except Exception as exc:
            logger.error(f"[Executor] Connection failed: {exc}")
            raise

    def disconnect(self):
        self._connected = False
        logger.info("[Executor] Disconnected")

    # ------------------------------------------------------------------
    # Main entry point — called by TradingAgent
    # ------------------------------------------------------------------

    def execute(self, decision) -> Optional[Order]:
        """
        Execute a TradeDecision from Layer 4.

        Args:
            decision: TradeDecision from DecisionEngine

        Returns:
            Order if submitted, None if skipped
        """
        if not self._connected:
            raise RuntimeError("Call connect() first")

        if decision.action == "BUY":
            return self._open_position(decision)
        elif decision.action == "SELL":
            return self._close_position(decision)
        return None

    # ------------------------------------------------------------------
    # Open a new position
    # ------------------------------------------------------------------

    def _open_position(self, decision) -> Optional[Order]:
        symbol = decision.symbol
        qty    = decision.shares

        if qty <= 0:
            logger.warning(f"[Executor] {symbol} BUY skipped — zero shares")
            return None

        if symbol in self._positions:
            logger.warning(f"[Executor] {symbol} BUY skipped — already have position")
            return None

        # 1. Market order to enter
        order = self._place_order(
            symbol    = symbol,
            side      = OrderSide.BUY,
            qty       = qty,
            order_type = OrderType.MARKET,
        )

        # Paper trading: market orders return SUBMITTED immediately, fill is async.
        # Poll once for fill confirmation before placing stop/TP orders.
        if order.status == OrderStatus.SUBMITTED and order.broker_order_id:
            try:
                import time as _t
                _t.sleep(1.0)  # paper fills within ~1s
                _fo = self._client.get_order_by_id(order.broker_order_id)
                if str(_fo.status).lower() in ('filled', 'partially_filled'):
                    order.status           = OrderStatus.FILLED
                    order.filled_avg_price = float(_fo.filled_avg_price or 0) or order.filled_avg_price
                    order.filled_qty       = int(_fo.filled_qty or 0)
                    logger.info(f"[Executor] {symbol} fill confirmed @ ${order.filled_avg_price:.2f}")
            except Exception as _fe:
                logger.warning(f"[Executor] Fill poll failed for {symbol}: {_fe}")

        if order.status == OrderStatus.FILLED:
            fill_price = order.filled_avg_price or decision.stop_loss / 0.97

            # Record position
            self._positions[symbol] = Position(
                symbol       = symbol,
                qty          = qty,
                entry_price  = fill_price,
                current_price = fill_price,
                stop_loss    = decision.stop_loss,
                take_profit  = decision.take_profit,
                entry_time   = datetime.now(timezone.utc),
            )

            # 2. Place stop-loss order
            if decision.stop_loss > 0:
                stop_order = self._place_order(
                    symbol     = symbol,
                    side       = OrderSide.SELL,
                    qty        = qty,
                    order_type = OrderType.STOP,
                    stop_price = decision.stop_loss,
                    tif        = TimeInForce.GTC,
                )
                self._positions[symbol].stop_order_id = stop_order.client_order_id

            # 3. Place take-profit limit order
            if decision.take_profit > 0:
                tp_order = self._place_order(
                    symbol      = symbol,
                    side        = OrderSide.SELL,
                    qty         = qty,
                    order_type  = OrderType.LIMIT,
                    limit_price = decision.take_profit,
                    tif         = TimeInForce.GTC,
                )
                self._positions[symbol].tp_order_id = tp_order.client_order_id

            self._today_fills[symbol] = fill_price  # keep cache current
            logger.info(
                f"[Executor] OPENED {symbol}: {qty} shares @ ${fill_price:.2f} | "
                f"stop=${decision.stop_loss:.2f} tp=${decision.take_profit:.2f}"
            )

        return order

    # ------------------------------------------------------------------
    # Close an existing position
    # ------------------------------------------------------------------

    def _close_position(self, decision) -> Optional[Order]:
        symbol = decision.symbol

        if symbol not in self._positions:
            logger.warning(f"[Executor] {symbol} SELL skipped — no open position")
            return None

        pos = self._positions[symbol]

        # Cancel any open stop/TP orders first
        self._cancel_bracket_orders(symbol)

        # Close with market order
        order = self._place_order(
            symbol     = symbol,
            side       = OrderSide.SELL,
            qty        = pos.qty,
            order_type = OrderType.MARKET,
        )

        if order.status == OrderStatus.FILLED:
            fill_price = order.filled_avg_price or 0
            pnl        = (fill_price - pos.entry_price) * pos.qty
            pnl_pct    = (fill_price - pos.entry_price) / pos.entry_price

            logger.info(
                f"[Executor] CLOSED {symbol}: {pos.qty} shares @ ${fill_price:.2f} | "
                f"P&L: {'+'if pnl>=0 else ''}${pnl:.2f} ({pnl_pct:+.1%})"
            )
            del self._positions[symbol]

        return order

    def _close_partial(self, symbol: str, shares: int) -> Optional[Order]:
        """Sell a partial number of shares from an open position."""
        if symbol not in self._positions:
            logger.warning(f"[Executor] {symbol} PARTIAL SELL skipped — no open position")
            return None

        pos = self._positions[symbol]
        shares = min(shares, pos.qty)  # never sell more than held
        shares = max(0, shares)        # never negative
        if shares <= 0:
            return None

        order = self._place_order(
            symbol     = symbol,
            side       = OrderSide.SELL,
            qty        = shares,
            order_type = OrderType.MARKET,
        )

        if order.status == OrderStatus.FILLED:
            fill_price = order.filled_avg_price or 0
            pnl        = (fill_price - pos.entry_price) * shares
            pnl_pct    = (fill_price - pos.entry_price) / pos.entry_price
            pos.qty   -= shares  # reduce remaining position size
            logger.info(
                f"[Executor] PARTIAL CLOSE {symbol}: sold {shares} of {pos.qty+shares} shares @ "
                f"${fill_price:.2f} | P&L: {'+' if pnl>=0 else ''}${pnl:.2f} ({pnl_pct:+.1%}) | "
                f"Remaining: {pos.qty} shares"
            )
            # Remove fully closed position
            if pos.qty <= 0:
                del self._positions[symbol]

        return order

    # ------------------------------------------------------------------
    # Position monitoring — called each cycle by TradingAgent
    # ------------------------------------------------------------------

    def update_positions(self) -> Dict[str, Position]:
        """
        Sync current prices and check if any stop/TP orders have filled.
        Also imports any positions on Alpaca not currently tracked locally.
        Called by TradingAgent at the start of each scan cycle.
        """
        if not self._connected:
            return self._positions

        try:
            # Get current prices from Alpaca
            alpaca_positions = self._client.get_all_positions()
            alpaca_pos_map   = {p.symbol: p for p in alpaca_positions}

            # Update existing tracked positions
            for symbol, pos in list(self._positions.items()):
                if symbol in alpaca_pos_map:
                    ap = alpaca_pos_map[symbol]
                    pos.current_price = float(ap.current_price)
                    pos.qty           = int(ap.qty)
                    # entry_price is immutable once set from the fill.
                    # Never overwrite with avg_entry_price (lifetime blended basis).
                    # current_price and qty are the only fields synced from Alpaca.
                else:
                    # Position no longer exists — stop or TP was hit
                    logger.info(
                        f"[Executor] {symbol} position closed by stop/TP order"
                    )
                    del self._positions[symbol]

            # Import any Alpaca positions not yet tracked locally
            # FILL_PRICE_CACHE — fetch orders API only once per session
            # None = never fetched. {} = fetched (or intentionally cleared) — don't re-fetch.
            if self._today_fills is None:
                # FILL_PRICE_FROM_ORDERS — architectural fix 2026-05-22
                # Always use today's BUY order fill price, never avg_entry_price.
                # avg_entry_price = Alpaca's lifetime blended cost basis across ALL sessions.
                # e.g. ARM bought at $163 for months, today's fill $307 →
                #      avg_entry_price=$163 causes phantom +$53k P&L when stop fires at $305.
                from datetime import datetime, timezone, timedelta
                import urllib.request as _ur, json as _json

                # Fetch today's filled BUY orders once for all symbols
                _today_fills: dict = {}  # symbol → fill_price from today's BUY orders
                try:
                    _base_url = (
                        "https://paper-api.alpaca.markets"
                        if self._paper else "https://api.alpaca.markets"
                    )
                    _utc_midnight = datetime.now(timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    _hdrs = {
                        "APCA-API-KEY-ID":     self._api_key,
                        "APCA-API-SECRET-KEY": self._secret_key,
                    }
                    _req = _ur.Request(
                        f"{_base_url}/v2/orders"
                        f"?status=all&after={_utc_midnight}&limit=200&direction=asc",
                        headers=_hdrs
                    )
                    _orders = _json.loads(_ur.urlopen(_req, timeout=8).read())
                    for _o in _orders:
                        if (str(_o.get("side", "")).lower() == "buy"
                                and str(_o.get("status", "")).lower() == "filled"
                                and _o.get("filled_avg_price")):
                            _sym = str(_o.get("symbol", "")).upper()
                            # Keep the latest fill price for each symbol
                            _today_fills[_sym] = float(_o["filled_avg_price"])
                    logger.info(
                        f"[Executor] Today's fill prices loaded: {list(_today_fills.keys())}"
                    )
                except Exception as _fe:
                    logger.warning(f"[Executor] Could not fetch today fills: {_fe}")

                # Assign populated local dict to self — self was None until now
                self._today_fills = _today_fills
                logger.info(
                    f"[Executor] Today fill prices cached: "
                    f"{list(self._today_fills.keys())}"
                )
            _today_fills = self._today_fills or {}

            for symbol, ap in alpaca_pos_map.items():
                if symbol not in self._positions:
                    curr = float(ap.current_price)
                    qty  = int(ap.qty)

                    # Use today's fill price — the price we actually paid
                    if symbol in _today_fills:
                        entry = _today_fills[symbol]
                        logger.info(
                            f"[Executor] Imported {symbol} from Alpaca: "
                            f"{qty} shares @ ${entry:.2f} (today fill price)"
                        )
                    else:
                        # No today fill found — this is a position from a previous session.
                        # Skip it. We cannot know the correct entry price.
                        # avg_entry_price would be the blended lifetime cost basis = wrong.
                        logger.warning(
                            f"[Executor] SKIPPED import {symbol}: "
                            f"no today fill found, avg_entry=${float(ap.avg_entry_price):.2f} "
                            f"is lifetime basis — cannot use for P&L"
                        )
                        continue

                    self._positions[symbol] = Position(
                        symbol        = symbol,
                        qty           = qty,
                        entry_price   = entry,
                        current_price = curr,
                    )

        except Exception as exc:
            logger.warning(f"[Executor] Position sync failed: {exc}")

        return self._positions

    def get_account(self) -> dict:
        """Return account summary — portfolio value, buying power, P&L."""
        if not self._connected:
            return {}
        try:
            acct = self._client.get_account()
            return {
                "portfolio_value": float(acct.portfolio_value),
                "cash":            float(acct.cash),
                "buying_power":    float(acct.buying_power),
                "equity":          float(acct.equity),
                "last_equity":     float(acct.last_equity),
                "daily_pnl":       float(acct.equity) - float(acct.last_equity),
                "paper":           self._paper,
            }
        except Exception as exc:
            logger.warning(f"[Executor] Account fetch failed: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Low-level order placement
    # ------------------------------------------------------------------

    def _place_order(
        self,
        symbol:      str,
        side:        OrderSide,
        qty:         int,
        order_type:  OrderType   = OrderType.MARKET,
        limit_price: float       = None,
        stop_price:  float       = None,
        tif:         TimeInForce = TimeInForce.DAY,
    ) -> Order:
        """Place a single order via Alpaca API."""
        # Hard duplicate-buy guard at executor level
        if side == OrderSide.BUY:
            try:
                sym_up = symbol.upper()
                # Check open positions
                self.update_positions()
                if sym_up in self.open_positions:
                    logger.warning(f"[Executor] BLOCKED {sym_up}: already in open positions")
                    o = Order(symbol=symbol, side=side, qty=qty,
                              order_type=order_type, time_in_force=tif)
                    o.status = OrderStatus.FAILED
                    o.error_message = "duplicate_buy_blocked"
                    return o
                # Check pending orders
                try:
                    open_orders = self._client.get_orders(filter=None)
                    pending = {
                        ord.symbol.upper() for ord in (open_orders or [])
                        if str(ord.side).lower() in ('buy', 'orderside.buy')
                        and str(ord.status).lower() in ('new','accepted','pending_new','held','partially_filled')
                    }
                    if sym_up in pending:
                        logger.warning(f"[Executor] BLOCKED {sym_up}: already has pending BUY order")
                        o = Order(symbol=symbol, side=side, qty=qty,
                                  order_type=order_type, time_in_force=tif)
                        o.status = OrderStatus.FAILED
                        o.error_message = "duplicate_buy_blocked"
                        return o
                    logger.debug(f"[Executor] {sym_up} guard passed: positions={list(self.open_positions.keys())} pending={list(pending)}")
                except Exception as _oe:
                    logger.warning(f"[Executor] Order check failed for {sym_up}: {_oe} — proceeding")
            except Exception as _ge:
                logger.warning(f"[Executor] Duplicate guard failed for {symbol}: {_ge} — proceeding")
        from alpaca.trading.requests import (
            MarketOrderRequest, LimitOrderRequest, StopOrderRequest
        )
        from alpaca.trading.enums import (
            OrderSide as AlpacaSide,
            TimeInForce as AlpacaTIF
        )

        client_id = str(uuid.uuid4())[:8]
        order     = Order(
            symbol           = symbol,
            side             = side,
            qty              = qty,
            order_type       = order_type,
            limit_price      = limit_price,
            stop_price       = stop_price,
            time_in_force    = tif,
            client_order_id  = client_id,
            submitted_at     = datetime.now(timezone.utc),
        )
        self._orders[client_id] = order

        try:
            alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL
            alpaca_tif  = AlpacaTIF.DAY if tif == TimeInForce.DAY else AlpacaTIF.GTC

            if order_type == OrderType.MARKET:
                req = MarketOrderRequest(
                    symbol       = symbol,
                    qty          = qty,
                    side         = alpaca_side,
                    time_in_force = alpaca_tif,
                )
            elif order_type == OrderType.LIMIT:
                req = LimitOrderRequest(
                    symbol        = symbol,
                    qty           = qty,
                    side          = alpaca_side,
                    limit_price   = limit_price,
                    time_in_force = alpaca_tif,
                )
            elif order_type == OrderType.STOP:
                req = StopOrderRequest(
                    symbol        = symbol,
                    qty           = qty,
                    side          = alpaca_side,
                    stop_price    = stop_price,
                    time_in_force = alpaca_tif,
                )

            response = self._client.submit_order(req)

            order.broker_order_id = str(response.id)
            order.status          = self._map_status(str(response.status))
            order.filled_qty      = int(response.filled_qty or 0)
            order.filled_avg_price = float(response.filled_avg_price or 0) or None
            order.filled_at       = response.filled_at

            logger.info(
                f"[Executor] Order submitted: {order} | "
                f"broker_id={order.broker_order_id} status={order.status.value}"
            )

        except Exception as exc:
            order.status        = OrderStatus.FAILED
            order.error_message = str(exc)
            logger.error(f"[Executor] Order failed for {symbol}: {exc}")

        return order

    def _cancel_bracket_orders(self, symbol: str):
        """Cancel open stop/TP orders for a symbol."""
        pos = self._positions.get(symbol)
        if not pos:
            return
        for oid in [pos.stop_order_id, pos.tp_order_id]:
            if oid and oid in self._orders:
                try:
                    o = self._orders[oid]
                    if o.broker_order_id:
                        self._client.cancel_order_by_id(o.broker_order_id)
                    o.status = OrderStatus.CANCELLED
                    logger.info(f"[Executor] Cancelled order {oid} for {symbol}")
                except Exception as exc:
                    logger.warning(f"[Executor] Cancel failed for {oid}: {exc}")

    def _sync_positions(self):
        """Load existing positions from Alpaca on startup."""
        try:
            alpaca_positions = self._client.get_all_positions()
            for ap in alpaca_positions:
                raw_qty = int(ap.qty)
                if raw_qty < 0:
                    # Negative qty = short position — skip, we only trade long
                    logger.warning(f"[Executor] {ap.symbol} has negative qty ({raw_qty}) — skipping (short position)")
                    continue
                self._positions[ap.symbol] = Position(
                    symbol        = ap.symbol,
                    qty           = raw_qty,
                    entry_price   = float(ap.avg_entry_price),
                    current_price = float(ap.current_price),
                    entry_time    = datetime.now(timezone.utc),  # best estimate on startup
                )
            if self._positions:
                logger.info(
                    f"[Executor] Synced {len(self._positions)} existing positions: "
                    f"{list(self._positions.keys())}"
                )
        except Exception as exc:
            logger.warning(f"[Executor] Position sync on startup failed: {exc}")

    @staticmethod
    def _map_status(alpaca_status: str) -> OrderStatus:
        return {
            "new":            OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIAL,
            "filled":         OrderStatus.FILLED,
            "canceled":       OrderStatus.CANCELLED,
            "expired":        OrderStatus.CANCELLED,
            "rejected":       OrderStatus.REJECTED,
            "pending_new":    OrderStatus.SUBMITTED,
            "accepted":       OrderStatus.SUBMITTED,
        }.get(alpaca_status, OrderStatus.SUBMITTED)

    # ------------------------------------------------------------------
    # Accessors for dashboard
    # ------------------------------------------------------------------

    @property
    def open_positions(self) -> Dict[str, Position]:
        return self._positions

    @property
    def order_history(self) -> List[Order]:
        return list(self._orders.values())

    @property
    def is_paper(self) -> bool:
        return self._paper
