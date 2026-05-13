# -*- coding: utf-8 -*-
"""
TrailingStopManager
--------------------
Tracks open positions and manages trailing stops + momentum exits.

Called on every scan cycle to check:
  1. Has price hit the trailing stop? → SELL
  2. Has price hit the take profit?   → SELL
  3. Has a reversal candle formed?    → SELL (if candle_exit enabled)
  4. Has conviction dropped 50%?      → SELL (if momentum_exit enabled)
  5. Has partial profit level hit?    → PARTIAL SELL
  6. Has max hold days exceeded?      → SELL

Used by Profit Maximizer mode primarily.
Swing and Conservative modes use fixed brackets (handled by broker).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Reversal candle patterns that trigger exit in Profit Maximizer mode
EXIT_CANDLE_PATTERNS = {
    "SHOOTING_STAR",
    "BEARISH_ENGULFING",
    "EVENING_STAR",
    "DARK_CLOUD_COVER",
    "HANGING_MAN",
}


@dataclass
class PositionState:
    """Tracks the trailing stop state for one open position."""
    symbol:          str
    entry_price:     float
    entry_time:      datetime
    shares:          int
    peak_price:      float      # highest price seen since entry
    current_stop:    float      # current trailing stop level
    fixed_stop:      float      # original fixed stop (backup)
    take_profit:     float      # original take profit target
    partial_done:    bool = False  # whether partial profit already taken
    entry_conviction: float = 0.0  # conviction at entry

    @property
    def days_held(self) -> int:
        return (datetime.now(timezone.utc) - self.entry_time).days

    @property
    def unrealised_pct(self) -> float:
        return (self.peak_price - self.entry_price) / self.entry_price


@dataclass
class ExitSignal:
    """Signal to exit or partially exit a position."""
    symbol:     str
    action:     str     # "SELL" | "PARTIAL_SELL"
    reason:     str
    urgency:    str     # "IMMEDIATE" | "EOD" | "NEXT_SCAN"
    shares:     int     = 0
    price:      float   = 0.0


class TrailingStopManager:
    """
    Manages trailing stops and smart exits for all open positions.

    Usage:
        manager = TrailingStopManager(config)

        # Call on every scan cycle
        signals = manager.check_exits(
            positions      = executor.open_positions,
            current_prices = {sym: price, ...},
            strategy_reports = {sym: report, ...},
            candle_signals = {sym: ["SHOOTING_STAR", ...], ...},
        )

        for signal in signals:
            if signal.action == "SELL":
                executor.close_position(signal.symbol)
    """

    def __init__(self, config):
        self.config   = config
        self._states: Dict[str, PositionState] = {}

    def register_position(
        self,
        symbol:      str,
        entry_price: float,
        shares:      int,
        stop_loss:   float,
        take_profit: float,
        conviction:  float = 0.0,
    ):
        """Register a new position for trailing stop tracking."""
        initial_stop = stop_loss
        if self.config.trailing_stop:
            # Start trailing stop at fixed stop level
            initial_stop = entry_price * (1 - self.config.trailing_stop_pct)

        self._states[symbol] = PositionState(
            symbol           = symbol,
            entry_price      = entry_price,
            entry_time       = datetime.now(timezone.utc),
            shares           = shares,
            peak_price       = entry_price,
            current_stop     = initial_stop,
            fixed_stop       = stop_loss,
            take_profit      = take_profit,
            entry_conviction = conviction,
        )
        logger.info(
            f"[TrailingStop] Registered {symbol} @ ${entry_price:.2f} | "
            f"stop=${initial_stop:.2f} | target=${take_profit:.2f}"
        )

    def update_and_check(
        self,
        positions:        Dict,      # executor.open_positions
        current_prices:   Dict[str, float],
        strategy_reports: Dict       = None,
        candle_signals:   Dict[str, List[str]] = None,
    ) -> List[ExitSignal]:
        """
        Update trailing stops and return any exit signals.
        Call this on every scan cycle.
        """
        signals = []
        strategy_reports = strategy_reports or {}
        candle_signals   = candle_signals or {}

        for symbol, pos in list(positions.items()):
            price = current_prices.get(symbol)
            if not price:
                continue

            # Auto-register if not tracked yet
            if symbol not in self._states:
                ep = pos.entry_price or price or 0
                # Always calculate from config — never trust Alpaca stop_loss (always null)
                sl = ep * (1 - self.config.stop_loss_pct)  if ep else 0
                tp = ep * (1 + self.config.take_profit_pct) if ep else 0
                self.register_position(
                    symbol      = symbol,
                    entry_price = ep,
                    shares      = pos.qty,
                    stop_loss   = sl,
                    take_profit = tp,
                )
            else:
                # Fix any existing state where stop is wider than configured stop_loss_pct
                state = self._states[symbol]
                ep = state.entry_price
                if ep > 0:
                    max_allowed_stop = ep * (1 - self.config.stop_loss_pct)
                    if state.current_stop < max_allowed_stop:
                        logger.info(
                            f"[TrailingStop] {symbol} stop corrected: "
                            f"${state.current_stop:.2f} → ${max_allowed_stop:.2f} "
                            f"(was {(ep-state.current_stop)/ep*100:.2f}% wide, "
                            f"corrected to {self.config.stop_loss_pct*100:.1f}%)"
                        )
                        state.current_stop = max_allowed_stop
                        state.fixed_stop   = max_allowed_stop

            state = self._states[symbol]

            # Update peak price
            if price > state.peak_price:
                state.peak_price = price
                # Move trailing stop up
                if self.config.trailing_stop:
                    new_stop = price * (1 - self.config.trailing_stop_pct)
                    if new_stop > state.current_stop:
                        old_stop = state.current_stop
                        state.current_stop = new_stop
                        logger.debug(
                            f"[TrailingStop] {symbol} peak=${price:.2f} → "
                            f"stop moved ${old_stop:.2f} → ${new_stop:.2f}"
                        )

            # --- Check exits ---

            # 1. Trailing/fixed stop hit
            effective_stop = state.current_stop if self.config.trailing_stop else state.fixed_stop
            if price <= effective_stop:
                gain_pct = (price - state.entry_price) / state.entry_price * 100
                signals.append(ExitSignal(
                    symbol  = symbol,
                    action  = "SELL",
                    reason  = f"{'Trailing' if self.config.trailing_stop else 'Fixed'} stop hit at ${effective_stop:.2f} ({gain_pct:+.1f}%)",
                    urgency = "IMMEDIATE",
                    shares  = state.shares,
                    price   = price,
                ))
                continue

            # 2. Take profit hit
            if price >= state.take_profit:
                gain_pct = (price - state.entry_price) / state.entry_price * 100
                signals.append(ExitSignal(
                    symbol  = symbol,
                    action  = "SELL",
                    reason  = f"Take profit hit at ${state.take_profit:.2f} (+{gain_pct:.1f}%)",
                    urgency = "IMMEDIATE",
                    shares  = state.shares,
                    price   = price,
                ))
                continue

            # 3. Partial profit taking (Profit Maximizer)
            if (not state.partial_done and
                self.config.partial_profit_pct > 0 and
                price >= state.entry_price * (1 + self.config.partial_profit_pct)):

                partial_shares = max(1, int(state.shares * self.config.partial_profit_ratio))
                state.partial_done = True
                gain_pct = (price - state.entry_price) / state.entry_price * 100
                signals.append(ExitSignal(
                    symbol  = symbol,
                    action  = "PARTIAL_SELL",
                    reason  = f"Partial profit locked at +{gain_pct:.1f}% — selling {partial_shares} of {state.shares} shares",
                    urgency = "NEXT_SCAN",
                    shares  = partial_shares,
                    price   = price,
                ))

            # 4. Candlestick reversal exit (Profit Maximizer)
            if self.config.candle_exit:
                candles = candle_signals.get(symbol, [])
                exit_candle = next(
                    (c for c in candles if c.upper().replace(" ", "_") in EXIT_CANDLE_PATTERNS),
                    None
                )
                if exit_candle and price > state.entry_price:  # only exit if in profit
                    signals.append(ExitSignal(
                        symbol  = symbol,
                        action  = "SELL",
                        reason  = f"Reversal candle: {exit_candle} — taking profit before reversal",
                        urgency = "EOD",
                        shares  = state.shares,
                        price   = price,
                    ))
                    continue

            # 5. Momentum exit (Profit Maximizer)
            if self.config.momentum_exit and symbol in strategy_reports:
                report = strategy_reports[symbol]
                current_conviction = abs(report.conviction_score)
                entry_conviction   = abs(state.entry_conviction)
                if (entry_conviction > 0 and
                    current_conviction < entry_conviction * 0.5 and
                    price > state.entry_price):  # only exit momentum if in profit
                    signals.append(ExitSignal(
                        symbol  = symbol,
                        action  = "SELL",
                        reason  = f"Momentum weakened: conviction dropped from {entry_conviction:.1f} to {current_conviction:.1f}",
                        urgency = "EOD",
                        shares  = state.shares,
                        price   = price,
                    ))
                    continue

            # 6. Max hold days exceeded (Profit Maximizer)
            if self.config.max_hold_days > 0 and state.days_held >= self.config.max_hold_days:
                gain_pct = (price - state.entry_price) / state.entry_price * 100
                signals.append(ExitSignal(
                    symbol  = symbol,
                    action  = "SELL",
                    reason  = f"Max hold period reached ({state.days_held} days) — exiting at {gain_pct:+.1f}%",
                    urgency = "EOD",
                    shares  = state.shares,
                    price   = price,
                ))

        return signals

    def remove_position(self, symbol: str):
        """Remove a position from tracking (called after close)."""
        self._states.pop(symbol, None)

    def get_state(self, symbol: str) -> Optional[PositionState]:
        return self._states.get(symbol)

    def summary(self) -> List[dict]:
        return [
            {
                "symbol":       s.symbol,
                "entry_price":  s.entry_price,
                "peak_price":   s.peak_price,
                "current_stop": s.current_stop,
                "take_profit":  s.take_profit,
                "days_held":    s.days_held,
                "partial_done": s.partial_done,
                "unrealised_pct": round(s.unrealised_pct * 100, 2),
            }
            for s in self._states.values()
        ]
