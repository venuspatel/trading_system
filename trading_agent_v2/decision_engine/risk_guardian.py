# -*- coding: utf-8 -*-
"""
RiskGuardian
------------
The last line of defense before any trade is placed.
Checks every safety rule in AgentConfig and blocks trades that violate them.

Rules checked:
  1. Daily loss limit not breached
  2. Market hours (if enabled)
  3. Max open positions not exceeded
  4. Max portfolio risk not exceeded
  5. Earnings blackout window
  6. Market crash protection (SPY drawdown)
  7. Minimum risk/reward ratio
  8. Paper vs live mode
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Dict, List, Optional

from .agent_config import AgentConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    """Result of a risk guardian check."""
    approved:    bool
    rule:        str
    reason:      str
    severity:    str    # "block" | "warn"

    def __str__(self):
        icon = "PASS" if self.approved else "BLOCK"
        return f"[{icon}] {self.rule}: {self.reason}"


@dataclass
class RiskAssessment:
    """Full risk assessment result for one trade decision."""
    symbol:       str
    approved:     bool
    checks:       List[RiskCheck]
    blocking:     List[RiskCheck]   # checks that blocked the trade
    warnings:     List[RiskCheck]   # checks that warned but allowed

    def __str__(self):
        lines = [f"Risk Assessment: {self.symbol} — {'APPROVED' if self.approved else 'BLOCKED'}"]
        for c in self.checks:
            lines.append(f"  {c}")
        return "\n".join(lines)


class RiskGuardian:
    """
    Enforces all risk rules before any trade is executed.
    Called by the DecisionEngine before sending orders to the broker.
    """

    def __init__(self, config: AgentConfig):
        self.config        = config
        self._daily_pnl    = 0.0      # updated by DecisionEngine
        self._spy_week_chg = 0.0      # updated by market data
        self._open_count   = 0        # updated by DecisionEngine
        self._portfolio_risk = 0.0    # current dollars at risk
        self._portfolio_val  = 10000.0
        self._market_regime  = 'UNKNOWN'  # updated each cycle

    def update_state(
        self,
        daily_pnl:       float,
        open_count:      int,
        portfolio_risk:  float,
        portfolio_value: float,
        spy_week_change: float = 0.0,
        market_regime:  str   = 'UNKNOWN',
    ):
        """Called before each scan cycle to update live state."""
        self._daily_pnl      = daily_pnl
        self._open_count     = open_count
        self._portfolio_risk = portfolio_risk
        self._portfolio_val  = portfolio_value
        self._spy_week_chg   = spy_week_change
        self._market_regime  = market_regime

    def assess(
        self,
        symbol:        str,
        action:        str,             # "BUY" or "SELL"
        position_size: "PositionSize",
        earnings_date: Optional[datetime] = None,
    ) -> RiskAssessment:
        """
        Run all risk checks for a proposed trade.
        Returns RiskAssessment — trade only proceeds if approved=True.
        """
        cfg    = self.config
        checks = []

        # 1. Paper trading notice (never blocks, just logs)
        checks.append(RiskCheck(
            approved = True,
            rule     = "Trading mode",
            reason   = f"{'PAPER (simulated)' if cfg.paper_trading else 'LIVE — real money'}",
            severity = "warn" if not cfg.paper_trading else "warn",
        ))

        # 2. Daily loss limit
        daily_loss_pct = abs(self._daily_pnl) / self._portfolio_val if self._portfolio_val > 0 else 0
        daily_ok       = self._daily_pnl >= -(self._portfolio_val * cfg.daily_loss_limit_pct)
        checks.append(RiskCheck(
            approved = daily_ok,
            rule     = "Daily loss limit",
            reason   = (f"Daily P&L: {self._daily_pnl:+.2f} "
                       f"({daily_loss_pct:.1%} of portfolio). "
                       f"Limit: {cfg.daily_loss_limit_pct:.0%}"),
            severity = "block",
        ))

        # 3. Market hours — use ET explicitly (Mac may be in PT/other timezone)
        if cfg.market_hours_only:
            try:
                from zoneinfo import ZoneInfo
                now_et = datetime.now(ZoneInfo("America/New_York"))
            except Exception:
                # Fallback: UTC-4 (EDT summer) or UTC-5 (EST winter)
                from datetime import timezone, timedelta
                import time as _t
                utc_offset = -4 if _t.localtime().tm_isdst else -5
                now_et = datetime.now(timezone(timedelta(hours=utc_offset)))
            market_open  = time(9, 30)
            market_close = time(16, 0)
            in_hours     = market_open <= now_et.time() <= market_close
            is_weekday   = now_et.weekday() < 5
            hours_ok     = in_hours and is_weekday
            checks.append(RiskCheck(
                approved = hours_ok,
                rule     = "Market hours",
                reason   = (f"Current time: {now_et.strftime('%H:%M')}. "
                           f"Market {'open' if hours_ok else 'closed'}."),
                severity = "block",
            ))

        # 4. Max open positions — expand to 7 on BULL regime days
        _effective_max = 7 if self._market_regime == 'BULL' else cfg.max_open_positions
        pos_ok = self._open_count < _effective_max
        checks.append(RiskCheck(
            approved = pos_ok,
            rule     = "Max positions",
            reason   = f"{self._open_count}/{_effective_max} positions open (regime={self._market_regime})",
            severity = "block",
        ))

        # 5. Portfolio risk budget
        new_risk      = position_size.max_loss
        total_risk    = self._portfolio_risk + new_risk
        risk_pct      = total_risk / self._portfolio_val if self._portfolio_val > 0 else 0
        risk_ok       = risk_pct <= cfg.max_portfolio_risk_pct
        checks.append(RiskCheck(
            approved = risk_ok,
            rule     = "Portfolio risk budget",
            reason   = (f"New risk: ${new_risk:.0f}. "
                       f"Total would be {risk_pct:.1%} vs limit {cfg.max_portfolio_risk_pct:.0%}"),
            severity = "block",
        ))

        # 6. Risk/reward ratio
        rr_ok = position_size.risk_reward >= cfg.min_risk_reward
        checks.append(RiskCheck(
            approved = rr_ok,
            rule     = "Risk/reward ratio",
            reason   = (f"R:R = {position_size.risk_reward:.1f}:1 "
                       f"(min required: {cfg.min_risk_reward:.1f}:1)"),
            severity = "block",
        ))

        # 7. Earnings blackout
        if earnings_date and cfg.earnings_blackout_days > 0:
            try:
                from zoneinfo import ZoneInfo as _ZI
                _now = datetime.now(_ZI("America/New_York")).replace(tzinfo=None)
            except Exception:
                from datetime import timezone as _tz, timedelta as _td
                _now = datetime.now(_tz(_td(hours=-4))).replace(tzinfo=None)
            days_to_earnings = (earnings_date - _now).days
            in_blackout      = 0 <= days_to_earnings <= cfg.earnings_blackout_days
            checks.append(RiskCheck(
                approved = not in_blackout,
                rule     = "Earnings blackout",
                reason   = (f"{days_to_earnings} days to earnings. "
                           f"Blackout window: {cfg.earnings_blackout_days} days"),
                severity = "block",
            ))

        # 8. Market crash protection
        if cfg.regime_filter and abs(self._spy_week_chg) > 0:
            crash_ok = self._spy_week_chg > -cfg.market_crash_threshold
            checks.append(RiskCheck(
                approved = crash_ok,
                rule     = "Market crash protection",
                reason   = (f"SPY weekly change: {self._spy_week_chg:.1%}. "
                           f"Threshold: -{cfg.market_crash_threshold:.0%}"),
                severity = "block",
            ))

        blocking = [c for c in checks if not c.approved and c.severity == "block"]
        warnings = [c for c in checks if not c.approved and c.severity == "warn"]
        approved = len(blocking) == 0

        assessment = RiskAssessment(
            symbol   = symbol,
            approved = approved,
            checks   = checks,
            blocking = blocking,
            warnings = warnings,
        )

        if approved:
            logger.info(f"[RiskGuardian] {symbol} {action} — APPROVED")
        else:
            logger.warning(
                f"[RiskGuardian] {symbol} {action} — BLOCKED: "
                f"{'; '.join(c.rule for c in blocking)}"
            )

        return assessment
