# -*- coding: utf-8 -*-
"""
KellySizer — dynamic position sizing based on conviction + win rate
--------------------------------------------------------------------
Instead of a flat 8% portfolio risk per trade, size each position
proportional to its expected edge using the Kelly criterion.

Kelly formula:  f* = W - (L/R)
  W = win probability
  R = avg_win / avg_loss
  L = 1 - W

Then scaled by conviction score and regime multiplier.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── No-margin position sizing constants ──────────────────────────────
# Never use more than this fraction of available cash on one position
MAX_POSITION_FRACTION = 0.10       # 10% of deployable cash per trade
# Always keep this much cash idle as a buffer — never deploy everything
CASH_RESERVE_PCT     = 0.20        # keep 20% cash in reserve at all times
# Minimum position size
MIN_KELLY_FRACTION   = 0.005       # 0.5% minimum
# Legacy cap kept for reference — no longer used as primary limit
MAX_KELLY_FRACTION   = 0.10        # 10% hard cap (was 25% — reduced)


@dataclass
class SizingResult:
    symbol:          str
    dollar_amount:   float
    fraction:        float       # 0.0 to 0.25
    kelly_f:         float       # raw kelly output
    conviction_mult: float       # 0.5 to 1.5
    regime_mult:     float       # 0.6 to 1.2
    reason:          str         = ""


class KellySizer:
    """
    Sizes positions dynamically using Kelly criterion.

    Usage:
        sizer = KellySizer()
        result = sizer.size(
            symbol="MARA",
            portfolio_value=100000,
            conviction_score=3.5,
            regime="BULL",
            win_rate=0.75,
            avg_win=14.68,
            avg_loss=12.23,
        )
        dollars = result.dollar_amount
    """

    def size(
        self,
        symbol:           str,
        portfolio_value:  float,          # equity (kept for compatibility)
        conviction_score: float,
        regime:           str   = "RANGING",
        win_rate:         float = 0.5,
        avg_win:          float = 10.0,
        avg_loss:         float = 10.0,
        max_pct:          float = 0.08,   # config max_position_pct cap
        available_cash:   float = None,   # actual cash/buying_power from broker
    ) -> SizingResult:
        """
        Calculate optimal position size for a trade.
        Uses available_cash (not equity) to prevent margin usage.
        Returns dollar amount to invest — always within cash limits.
        """
        # ── Kelly fraction ────────────────────────────────────────────
        # Bootstrap defaults when no trade history yet
        if avg_win <= 0:  avg_win  = 50.0   # assume $50 avg win
        if avg_loss <= 0: avg_loss = 30.0   # assume $30 avg loss
        if win_rate <= 0: win_rate = 0.60   # assume 60% win rate for fresh start

        R = avg_win / avg_loss if avg_loss > 0 else 1.5
        W = max(0.1, min(0.95, win_rate))
        L = 1 - W

        # Kelly: W - L/R
        kelly_f = W - (L / R) if R > 0 else 0.0
        kelly_f = max(0.02, kelly_f)  # minimum 2% Kelly — never zero

        # Half-Kelly for safety (full Kelly is too aggressive)
        kelly_f = kelly_f * 0.5

        # ── Conviction multiplier (0.5x to 1.5x) ─────────────────────
        # conviction_score typically -10 to +10; 2.5 is our entry floor
        if conviction_score >= 4.0:
            conviction_mult = 1.5
        elif conviction_score >= 3.0:
            conviction_mult = 1.25
        elif conviction_score >= 2.5:
            conviction_mult = 1.0
        elif conviction_score >= 2.0:
            conviction_mult = 0.75
        else:
            conviction_mult = 0.5

        # ── Regime multiplier ─────────────────────────────────────────
        regime_mult = {
            "BULL":     1.2,
            "RANGING":  0.9,
            "BEAR":     0.6,
            "VOLATILE": 0.7,
        }.get(regime.upper(), 0.9)

        # ── Final fraction ────────────────────────────────────────────
        final_f = kelly_f * conviction_mult * regime_mult

        # Cap at max position fraction
        final_f = max(MIN_KELLY_FRACTION, min(MAX_POSITION_FRACTION, final_f))

        # ── Use CASH not EQUITY to prevent margin ─────────────────────
        # If broker cash is provided, size off that — not equity
        if available_cash and available_cash > 0:
            # Keep 20% as buffer — only deploy 80% of available cash
            deployable = available_cash * (1.0 - CASH_RESERVE_PCT)
            # Hard cap: never more than 10% of deployable cash per position
            max_dollars  = deployable * MAX_POSITION_FRACTION
            dollar_amount = round(min(deployable * final_f, max_dollars), 2)
            base_desc = f"cash=${deployable:,.0f}"
        else:
            # Fallback: use equity but with tighter cap
            deployable    = portfolio_value * (1.0 - CASH_RESERVE_PCT)
            max_dollars   = deployable * MAX_POSITION_FRACTION
            dollar_amount = round(min(deployable * final_f, max_dollars), 2)
            base_desc = f"equity=${deployable:,.0f}"

        reason = (
            f"Kelly={kelly_f:.3f} × conv={conviction_mult:.2f} × regime={regime_mult:.2f} "
            f"= {final_f:.2%} | {base_desc} → ${dollar_amount:,.0f} [NO MARGIN]"
        )

        logger.debug(f"[Kelly] {symbol}: {reason}")

        return SizingResult(
            symbol          = symbol,
            dollar_amount   = dollar_amount,
            fraction        = round(final_f, 4),
            kelly_f         = round(kelly_f, 4),
            conviction_mult = conviction_mult,
            regime_mult     = regime_mult,
            reason          = reason,
        )
