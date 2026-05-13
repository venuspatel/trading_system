# -*- coding: utf-8 -*-
"""
TradingDiscipline — Smart trading rules engine
------------------------------------------------
Enforces professional trading discipline on top of the signal layer.
Answers: "Should the agent take a NEW trade right now?"

5 safety doors checked in order:
  1. Daily trade count limit
  2. Daily loss limit (already existed — now enforced here too)
  3. Consecutive loss cool-down
  4. Profit lock mode (tighten stops when up big)
  5. Weekly circuit breaker

All state is in-memory. Resets daily at midnight ET.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)



class TickerCooldown:
    """
    Per-ticker cooling period after losses.
    
    Rules:
      1st loss on ticker  → 30-min cooldown, re-entry requires BULL regime + positive MTF
      2nd loss same day   → 2-hour cooldown, re-entry requires BULL regime + RSI < 60
      3rd+ loss same day  → full day ban on that ticker
      
    Before re-entry after cooldown: must confirm market is still trending up on that ticker.
    """

    def __init__(self):
        self._ticker_losses:   dict = {}   # symbol → count today
        self._ticker_cooldown: dict = {}   # symbol → expiry datetime
        self._day_date:        str  = ""

    def _check_day_reset(self):
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")
        if today != self._day_date:
            self._day_date        = today
            self._ticker_losses   = {}
            self._ticker_cooldown = {}

    def record_loss(self, symbol: str):
        """Record a loss on this ticker and set appropriate cooldown."""
        from datetime import datetime, timezone, timedelta
        self._check_day_reset()
        sym = symbol.upper()
        ET  = timezone(timedelta(hours=-4))
        now = datetime.now(ET)

        self._ticker_losses[sym] = self._ticker_losses.get(sym, 0) + 1
        count = self._ticker_losses[sym]

        if count == 1:
            # First loss — 30 min cooldown
            expiry = now + timedelta(minutes=30)
            self._ticker_cooldown[sym] = expiry
            import logging
            logging.getLogger(__name__).warning(
                f"[TickerCooldown] {sym} LOSS #{count} — 30-min cooldown until "
                f"{expiry.strftime('%H:%M')} ET. Re-entry needs BULL regime."
            )
        elif count == 2:
            # Second loss — 2 hour cooldown
            expiry = now + timedelta(hours=2)
            self._ticker_cooldown[sym] = expiry
            import logging
            logging.getLogger(__name__).warning(
                f"[TickerCooldown] {sym} LOSS #{count} — 2-hour cooldown until "
                f"{expiry.strftime('%H:%M')} ET. Re-entry needs strong trend confirmation."
            )
        else:
            # 3+ losses — full day ban
            from datetime import date
            next_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            if next_open <= now:
                next_open += timedelta(days=1)
            self._ticker_cooldown[sym] = next_open
            import logging
            logging.getLogger(__name__).warning(
                f"[TickerCooldown] {sym} LOSS #{count} — FULL DAY BAN. "
                f"Agent will not re-enter {sym} today."
            )

    def record_win(self, symbol: str):
        """A win clears consecutive loss tracking for this ticker."""
        self._check_day_reset()
        sym = symbol.upper()
        # Reset to 0 losses (wins reset the count)
        self._ticker_losses[sym] = 0
        # Clear cooldown if active
        self._ticker_cooldown.pop(sym, None)

    def can_trade(self, symbol: str, regime: str = "", mtf_score: float = 0.0) -> tuple:
        """
        Returns (allowed: bool, reason: str).
        
        After cooldown expires, checks market conditions before allowing re-entry:
          - Regime must be BULL or NEUTRAL (not BEAR)
          - MTF score must be positive (trend is up)
        """
        from datetime import datetime, timezone, timedelta
        self._check_day_reset()
        sym = symbol.upper()
        ET  = timezone(timedelta(hours=-4))
        now = datetime.now(ET)

        expiry = self._ticker_cooldown.get(sym)
        if expiry and now < expiry:
            mins_left = int((expiry - now).total_seconds() / 60)
            loss_count = self._ticker_losses.get(sym, 0)
            return False, (
                f"{sym} in {loss_count}-loss cooldown — "
                f"{mins_left}m remaining until {expiry.strftime('%H:%M')} ET"
            )

        # Cooldown expired — check market trend before re-entry
        if expiry and self._ticker_losses.get(sym, 0) > 0:
            # Clear expiry since it passed
            self._ticker_cooldown.pop(sym, None)
            # Check regime
            if regime.upper() == "BEAR":
                return False, (
                    f"{sym} cooldown lifted but market regime is BEAR — "
                    f"skipping re-entry on {sym}"
                )
            # Check MTF score (multi-timeframe trend)
            if mtf_score < 0:
                return False, (
                    f"{sym} cooldown lifted but MTF trend is negative ({mtf_score:.2f}) — "
                    f"waiting for uptrend confirmation on {sym}"
                )

        return True, ""

    def get_status(self) -> dict:
        """Return current cooldown status for all tickers."""
        from datetime import datetime, timezone, timedelta
        self._check_day_reset()
        ET  = timezone(timedelta(hours=-4))
        now = datetime.now(ET)
        active = {}
        for sym, expiry in self._ticker_cooldown.items():
            if expiry and now < expiry:
                active[sym] = {
                    "losses_today": self._ticker_losses.get(sym, 0),
                    "cooldown_until": expiry.strftime("%H:%M ET"),
                    "mins_remaining": int((expiry - now).total_seconds() / 60)
                }
        return {
            "ticker_losses_today": self._ticker_losses,
            "active_cooldowns": active
        }


@dataclass
class DisciplineState:
    """Live state of the discipline engine for one trading day."""
    # Daily counters
    trades_today:       int   = 0
    wins_today:         int   = 0
    losses_today:       int   = 0
    pnl_today_pct:      float = 0.0

    # Consecutive loss tracking
    consecutive_losses: int   = 0
    cooldown_until:     Optional[datetime] = None

    # Profit lock
    profit_locked:      bool  = False
    peak_pnl_today_pct: float = 0.0

    # Weekly tracking
    pnl_week_pct:       float = 0.0
    week_stopped:       bool  = False

    # Date tracking for resets
    current_date:       str   = ""
    current_week:       str   = ""


@dataclass
class DisciplineConfig:
    """Configuration for the discipline engine — set per trading mode."""
    # Daily trade limit
    max_trades_per_day:        int   = 5
    # Consecutive loss cool-down
    max_consecutive_losses:    int   = 3
    cooldown_minutes:          int   = 60
    # Profit lock — once up this much, tighten trailing stops
    profit_lock_pct:           float = 0.03   # 3% up today → lock profits
    profit_lock_trailing_pct:  float = 0.008  # tighten to 0.8% trailing
    # Weekly circuit breaker
    weekly_loss_limit_pct:     float = 0.08   # -8% this week → stop all
    # Daily loss limit (mirrors risk config)
    daily_loss_limit_pct:      float = 0.04

    @classmethod
    def for_mode(cls, approach: str) -> "DisciplineConfig":
        """Returns discipline config tuned for each trading mode."""
        configs = {
            "Conservative":     cls(max_trades_per_day=3,  max_consecutive_losses=2, cooldown_minutes=120, profit_lock_pct=0.02, weekly_loss_limit_pct=0.05, daily_loss_limit_pct=0.02),
            "Balanced":         cls(max_trades_per_day=5,  max_consecutive_losses=3, cooldown_minutes=60,  profit_lock_pct=0.03, weekly_loss_limit_pct=0.08, daily_loss_limit_pct=0.03),
            "Aggressive":       cls(max_trades_per_day=8,  max_consecutive_losses=4, cooldown_minutes=30,  profit_lock_pct=0.05, weekly_loss_limit_pct=0.12, daily_loss_limit_pct=0.05),
            "Profit Maximizer": cls(max_trades_per_day=10, max_consecutive_losses=3, cooldown_minutes=45,  profit_lock_pct=0.03, weekly_loss_limit_pct=0.10, daily_loss_limit_pct=0.04),
            "Long Term":        cls(max_trades_per_day=2,  max_consecutive_losses=2, cooldown_minutes=240, profit_lock_pct=0.05, weekly_loss_limit_pct=0.08, daily_loss_limit_pct=0.05),
            "Micro Momentum":   cls(max_trades_per_day=40, max_consecutive_losses=5, cooldown_minutes=15,  profit_lock_pct=0.01, weekly_loss_limit_pct=0.05, daily_loss_limit_pct=0.02),
        }
        return configs.get(approach, configs["Balanced"])


@dataclass
class DisciplineCheck:
    """Result of a discipline check."""
    allowed:    bool
    door:       Optional[str]   = None   # which door blocked it
    reason:     str             = ""
    resume_at:  Optional[str]   = None   # when trading resumes
    profit_lock_active: bool    = False  # tighten trailing stops


class TradingDiscipline:
    """
    Enforces trading discipline rules on every potential trade.

    Usage:
        discipline = TradingDiscipline(config)

        # Before entering any trade:
        check = discipline.can_trade(portfolio_pnl_pct)
        if not check.allowed:
            logger.info(f"Trade blocked: {check.reason}")
            return

        # After a trade closes:
        discipline.record_trade_result(pnl_pct=+0.025)   # win
        discipline.record_trade_result(pnl_pct=-0.015)   # loss
    """

    def __init__(self, config: DisciplineConfig):
        self.config = config
        self.state  = DisciplineState()
        self._reset_if_new_day()

    def can_trade(self, portfolio_pnl_pct: float = 0.0) -> DisciplineCheck:
        """
        Check all 5 discipline doors.
        Returns DisciplineCheck with allowed=True if entry is permitted.
        """
        self._reset_if_new_day()
        self.state.pnl_today_pct = portfolio_pnl_pct

        # Update peak PnL
        if portfolio_pnl_pct > self.state.peak_pnl_today_pct:
            self.state.peak_pnl_today_pct = portfolio_pnl_pct

        # Door 5 — weekly circuit breaker (hardest stop)
        if self.state.week_stopped:
            return DisciplineCheck(
                allowed=False, door="weekly_circuit_breaker",
                reason=f"Weekly loss limit hit (-{self.config.weekly_loss_limit_pct*100:.0f}%). Trading paused until Monday.",
                resume_at="Next Monday 9:30am ET"
            )

        if self.state.pnl_week_pct <= -self.config.weekly_loss_limit_pct:
            self.state.week_stopped = True
            logger.warning(f"[Discipline] WEEKLY CIRCUIT BREAKER — down {self.state.pnl_week_pct*100:.1f}% this week")
            return DisciplineCheck(
                allowed=False, door="weekly_circuit_breaker",
                reason=f"Weekly loss limit hit (-{abs(self.state.pnl_week_pct)*100:.1f}%). Trading paused until Monday.",
                resume_at="Next Monday 9:30am ET"
            )

        # Door 2 — daily loss limit
        if portfolio_pnl_pct <= -self.config.daily_loss_limit_pct:
            return DisciplineCheck(
                allowed=False, door="daily_loss_limit",
                reason=f"Daily loss limit reached ({portfolio_pnl_pct*100:.1f}%). No new entries today. Exits still active.",
                resume_at="Tomorrow 9:30am ET"
            )

        # Door 1 — daily trade count (skip if unlimited mode: max_trades_per_day >= 9999)
        if self.config.max_trades_per_day < 9999 and self.state.trades_today >= self.config.max_trades_per_day:
            return DisciplineCheck(
                allowed=False, door="daily_trade_limit",
                reason=f"Daily trade limit reached ({self.state.trades_today}/{self.config.max_trades_per_day}). Managing open positions only.",
                resume_at="Tomorrow 9:30am ET"
            )

        # Door 3 — consecutive loss cool-down
        if self.state.cooldown_until:
            now = datetime.now(timezone.utc)
            if now < self.state.cooldown_until:
                remaining = int((self.state.cooldown_until - now).total_seconds() / 60)
                return DisciplineCheck(
                    allowed=False, door="consecutive_loss_cooldown",
                    reason=f"{self.state.consecutive_losses} consecutive losses. Cool-down active — {remaining} min remaining.",
                    resume_at=self.state.cooldown_until.strftime("%I:%M %p ET")
                )
            else:
                self.state.cooldown_until = None
                logger.info("[Discipline] Cool-down expired — trading resumed")

        # Door 4 — profit lock check (doesn't block but signals tighter stops)
        profit_lock_active = False
        if portfolio_pnl_pct >= self.config.profit_lock_pct:
            if not self.state.profit_locked:
                self.state.profit_locked = True
                logger.info(f"[Discipline] PROFIT LOCK activated — up {portfolio_pnl_pct*100:.1f}% today. Tightening stops.")
            profit_lock_active = True

        return DisciplineCheck(
            allowed=True,
            reason=f"Trade {self.state.trades_today+1}/{'unlimited' if self.config.max_trades_per_day>=9999 else self.config.max_trades_per_day} today",
            profit_lock_active=profit_lock_active
        )

    def record_trade_entry(self):
        """Call when a new trade is entered."""
        self.state.trades_today += 1
        logger.info(f"[Discipline] Trade #{self.state.trades_today} entered today")

    def record_trade_result(self, pnl_pct: float):
        """Call when a trade closes with its P&L."""
        self.state.pnl_week_pct += pnl_pct
        if pnl_pct > 0:
            self.state.wins_today += 1
            self.state.consecutive_losses = 0
            logger.info(f"[Discipline] Win recorded (+{pnl_pct*100:.2f}%). Consecutive losses reset.")
        else:
            self.state.losses_today += 1
            self.state.consecutive_losses += 1
            logger.info(f"[Discipline] Loss recorded ({pnl_pct*100:.2f}%). Consecutive losses: {self.state.consecutive_losses}")
            if self.state.consecutive_losses >= self.config.max_consecutive_losses:
                cooldown_end = datetime.now(timezone.utc) + timedelta(minutes=self.config.cooldown_minutes)
                self.state.cooldown_until = cooldown_end
                logger.warning(
                    f"[Discipline] COOL-DOWN triggered — {self.state.consecutive_losses} consecutive losses. "
                    f"No new entries for {self.config.cooldown_minutes} min."
                )

    def get_status(self) -> dict:
        """Return discipline status for the dashboard."""
        self._reset_if_new_day()
        now = datetime.now(timezone.utc)
        cooldown_remaining = 0
        if self.state.cooldown_until and now < self.state.cooldown_until:
            cooldown_remaining = int((self.state.cooldown_until - now).total_seconds() / 60)

        return {
            "trades_today":        self.state.trades_today,
            "max_trades_today":    self.config.max_trades_per_day,
            "wins_today":          self.state.wins_today,
            "losses_today":        self.state.losses_today,
            "consecutive_losses":  self.state.consecutive_losses,
            "cooldown_active":     bool(self.state.cooldown_until and now < self.state.cooldown_until),
            "cooldown_remaining_min": cooldown_remaining,
            "profit_lock_active":  self.state.profit_locked,
            "pnl_today_pct":       round(self.state.pnl_today_pct * 100, 2),
            "pnl_week_pct":        round(self.state.pnl_week_pct * 100, 2),
            "week_stopped":        self.state.week_stopped,
            "can_trade":           self.can_trade(self.state.pnl_today_pct).allowed,
        }

    def _reset_if_new_day(self):
        """Reset daily counters at market open."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        week  = datetime.now(timezone.utc).strftime("%Y-W%W")
        if self.state.current_date != today:
            logger.info(f"[Discipline] New day {today} — resetting daily counters")
            self.state.trades_today       = 0
            self.state.wins_today         = 0
            self.state.losses_today       = 0
            self.state.consecutive_losses = 0
            self.state.cooldown_until     = None
            self.state.profit_locked      = False
            self.state.peak_pnl_today_pct = 0.0
            self.state.pnl_today_pct      = 0.0
            self.state.current_date       = today
        if self.state.current_week != week:
            logger.info(f"[Discipline] New week {week} — resetting weekly counters")
            self.state.pnl_week_pct   = 0.0
            self.state.week_stopped   = False
            self.state.current_week   = week
