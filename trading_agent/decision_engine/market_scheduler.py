# -*- coding: utf-8 -*-
"""
MarketScheduler
---------------
Replaces the naive "sleep N minutes" loop with a proper
market-aware scheduler that fires scans at the right time.

Industry-correct scan times for daily-bar swing trading:

  CONSERVATIVE  → one scan: 4:05pm ET (after daily bar closes)
  BALANCED      → two scans: 8:30am ET (pre-market confirm) + 4:05pm ET
  AGGRESSIVE    → every completed hour during market hours (9:30am–4:00pm ET)
                  NOTE: aggressive uses 1H bars, not daily — flagged for MTF upgrade

Also provides:
  - Bar completion check  (never analyse an incomplete bar)
  - Duplicate entry guard (never enter same symbol twice in one day)
  - Market holiday awareness
"""

import logging
import time
import threading
from datetime import datetime, date, timedelta
from typing import Callable, List, Optional, Set
from zoneinfo import ZoneInfo        # Python 3.9+

from .agent_config import AgentConfig, Approach

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Market hours (Eastern Time)
MARKET_OPEN  = (9, 30)    # 9:30am ET
MARKET_CLOSE = (16, 0)    # 4:00pm ET
EOD_SCAN     = (16, 5)    # 4:05pm ET  — daily bar fully closed
PREMARKET    = (8, 30)    # 8:30am ET  — pre-market confirmation

# NYSE holidays 2025-2026 (simplified — production uses a full calendar)
NYSE_HOLIDAYS = {
    date(2025, 1, 1),   date(2025, 1, 20),  date(2025, 2, 17),
    date(2025, 4, 18),  date(2025, 5, 26),  date(2025, 6, 19),
    date(2025, 7, 4),   date(2025, 9, 1),   date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),   date(2026, 1, 19),  date(2026, 2, 16),
    date(2026, 4, 3),   date(2026, 5, 25),  date(2026, 6, 19),
    date(2026, 7, 3),   date(2026, 9, 7),   date(2026, 11, 26),
    date(2026, 12, 25),
}


def is_trading_day(d: date = None) -> bool:
    """Return True if d is a NYSE trading day (Mon-Fri, not holiday)."""
    d = d or datetime.now(ET).date()
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def is_market_open(now: datetime = None) -> bool:
    """Return True if US market is currently open."""
    now = now or datetime.now(ET)
    if not is_trading_day(now.date()):
        return False
    t = (now.hour, now.minute)
    return MARKET_OPEN <= t < MARKET_CLOSE


def next_scan_times(approach: Approach, now: datetime = None) -> List[datetime]:
    """
    Return the next scheduled scan datetime(s) for the given approach.

    Conservative  → next 4:05pm ET on a trading day
    Balanced      → next of: 8:30am or 4:05pm ET on a trading day
    Aggressive    → next top-of-hour during market hours (9:30-16:00 ET)
                    falls back to next 4:05pm ET if market is closed
    """
    now = now or datetime.now(ET)
    today = now.date()

    def et(h, m, d=None) -> datetime:
        d = d or today
        return datetime(d.year, d.month, d.day, h, m, tzinfo=ET)

    def next_trading_day(from_date: date) -> date:
        d = from_date + timedelta(days=1)
        while not is_trading_day(d):
            d += timedelta(days=1)
        return d

    candidates = []

    if approach == Approach.CONSERVATIVE:
        eod = et(*EOD_SCAN)
        if now < eod and is_trading_day():
            candidates.append(eod)
        else:
            nxt = next_trading_day(today)
            candidates.append(et(*EOD_SCAN, d=nxt))

    elif approach == Approach.BALANCED:
        premarket_today = et(*PREMARKET)
        eod_today       = et(*EOD_SCAN)
        if now < premarket_today and is_trading_day():
            candidates.extend([premarket_today, eod_today])
        elif now < eod_today and is_trading_day():
            candidates.append(eod_today)
        else:
            nxt = next_trading_day(today)
            candidates.extend([et(*PREMARKET, d=nxt), et(*EOD_SCAN, d=nxt)])

    elif approach in (Approach.AGGRESSIVE, Approach.PROFIT_MAXIMIZER):
        # Profit Maximizer + Aggressive: every 10 min during market hours
        interval_mins = getattr(approach, '_scan_interval', 10)
        if approach == Approach.PROFIT_MAXIMIZER:
            interval_mins = 10
        if is_trading_day() and is_market_open(now):
            # Next 10-min boundary
            minutes_past = now.minute % interval_mins
            mins_to_next = interval_mins - minutes_past if minutes_past > 0 else interval_mins
            next_scan = now.replace(second=0, microsecond=0) + timedelta(minutes=mins_to_next)
            market_close_today = et(*MARKET_CLOSE)
            if next_scan <= market_close_today:
                candidates.append(next_scan)
        # Always also schedule EOD scan
        eod = et(*EOD_SCAN)
        if now < eod and is_trading_day():
            candidates.append(eod)
        else:
            nxt = next_trading_day(today)
            candidates.append(et(*EOD_SCAN, d=nxt))

    return sorted(set(candidates))


class MarketScheduler:
    """
    Fires scan callbacks at market-correct times.
    Replaces the naive sleep loop in TradingAgent.

    Usage:
        scheduler = MarketScheduler(config)
        scheduler.on_scan(my_scan_function)
        scheduler.start()
        # fires my_scan_function at correct market times automatically
        scheduler.stop()
    """

    def __init__(self, config: AgentConfig):
        self.config       = config
        self._callback        : Optional[Callable] = None
        self._stop_event      = threading.Event()
        self._thread          : Optional[threading.Thread] = None
        self._intraday_mode   = True   # ON by default — 2-min scans every day
        self._intraday_interval = 2
        self._auto_close_fired  = False
        self._traded_today: Set[str] = set()   # duplicate entry guard
        self._last_bar_date: Optional[date] = None

    def on_scan(self, callback: Callable):
        """Register the function to call when a scan is due."""
        self._callback = callback

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="market-scheduler"
        )
        self._thread.start()
        _appr = self.config.approach.value if hasattr(self.config.approach, 'value') else self.config.approach
        logger.info(
            f"[Scheduler] Started — approach={_appr} | "
            f"next scans: {[t.strftime('%Y-%m-%d %H:%M ET') for t in self._next_scans()]}"
        )

    def stop(self):
        self._stop_event.set()
        logger.info("[Scheduler] Stopped")

    def reset_daily_guards(self):
        """Call at start of each trading day — clears duplicate entry tracking."""
        self._traded_today.clear()
        self._last_bar_date = None
        self.reset_stop_cooldowns()
        logger.info("[Scheduler] Daily guards reset")

    def mark_traded(self, symbol: str):
        """Record that a symbol was traded today — prevents duplicate entries."""
        self._traded_today.add(symbol.upper())

    def already_traded_today(self, symbol: str) -> bool:
        """Return True if this symbol was already entered today."""
        return symbol.upper() in self._traded_today

    def record_trade_result(self, symbol: str, was_win: bool):
        """Record whether the last trade on a symbol was a win or loss."""
        if not hasattr(self, '_last_trade_result'):
            self._last_trade_result = {}
        self._last_trade_result[symbol.upper()] = was_win

    def last_trade_was_win(self, symbol: str) -> bool:
        """Return True if the last completed trade on this symbol was profitable."""
        if not hasattr(self, '_last_trade_result'):
            return False
        return self._last_trade_result.get(symbol.upper(), False)

    # ── Fix 1: Stop-loss cooldown ─────────────────────────────────────
    def mark_stopped_out(self, symbol: str, cooldown_minutes: int = 120):
        """
        Record that a symbol was stopped out.
        First stop-out: 2hr cooldown.
        Second stop-out same day: full day cooldown (until next market open).
        """
        if not hasattr(self, '_stop_cooldowns'):
            self._stop_cooldowns = {}
        if not hasattr(self, '_stop_counts'):
            self._stop_counts = {}

        sym = symbol.upper()
        self._stop_counts[sym] = self._stop_counts.get(sym, 0) + 1
        count = self._stop_counts[sym]

        if count >= 2:
            # Second stop same day — lock out until tomorrow 9:30 AM
            now = datetime.now(ET)
            tomorrow = (now + timedelta(days=1)).replace(
                hour=9, minute=30, second=0, microsecond=0
            )
            # If it's already after market hours, skip to next trading day open
            expiry = tomorrow
            self._stop_cooldowns[sym] = expiry
            logger.info(
                f"[Scheduler] {sym} stopped out {count}x today — "
                f"FULL DAY cooldown until {expiry.strftime('%Y-%m-%d %H:%M')} ET"
            )
        else:
            expiry = datetime.now(ET) + timedelta(minutes=cooldown_minutes)
            self._stop_cooldowns[sym] = expiry
            logger.info(
                f"[Scheduler] {sym} stopped out (#{count}) — "
                f"re-entry blocked until {expiry.strftime('%H:%M')} ET"
            )

    def is_in_stop_cooldown(self, symbol: str) -> bool:
        """Return True if this symbol was recently stopped out and is still in cooldown."""
        if not hasattr(self, '_stop_cooldowns'):
            return False
        expiry = self._stop_cooldowns.get(symbol.upper())
        if expiry is None:
            return False
        if datetime.now(ET) < expiry:
            return True
        # Cooldown expired — clean up
        del self._stop_cooldowns[symbol.upper()]
        return False

    def reset_stop_cooldowns(self):
        """Clear all stop cooldowns and counts (called at start of new trading day)."""
        self._stop_cooldowns   = {}
        self._stop_counts      = {}
        self._auto_close_fired = False  # reset for new trading day

    def bar_is_complete(self, bar_timestamp: datetime) -> bool:
        """
        Return True if the bar is fully closed (not a partial/live bar).
        A daily bar is complete once the date has passed.
        """
        if bar_timestamp is None:
            return False
        bar_date = bar_timestamp.date() if hasattr(bar_timestamp, 'date') else bar_timestamp
        today    = datetime.now(ET).date()
        return bar_date < today

    # ------------------------------------------------------------------

    def _next_scans(self) -> List[datetime]:
        return next_scan_times(self.config.approach)

    # ── Phase 3: Intraday mode ────────────────────────────────────────
    def set_intraday_mode(self, enabled: bool, interval_minutes: int = 2):
        """Switch to fast intraday scanning (2-min intervals) or back to normal."""
        self._intraday_mode    = enabled
        self._intraday_interval = interval_minutes
        if enabled:
            logger.info(f"[Scheduler] INTRADAY MODE ON — scanning every {interval_minutes} min")
        else:
            logger.info("[Scheduler] Intraday mode OFF — back to normal schedule")

    def _loop(self):
        """Main scheduler loop — sleeps until next scan time then fires."""
        # ── Startup scan: fire immediately if market is currently open ──
        # Small delay ensures the callback is registered before we fire
        import time as _time
        _time.sleep(3)
        now = datetime.now(ET)
        market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
        if is_trading_day(now):
            if market_open <= now <= market_close:
                logger.info("[Scheduler] Market is open — firing startup scan immediately")
            else:
                logger.info("[Scheduler] Market closed — firing startup scan to sync positions")
            try:
                if self._callback:
                    self._callback("STARTUP")
                else:
                    logger.warning("[Scheduler] Startup scan skipped — callback not registered yet")
            except Exception as exc:
                logger.warning(f"[Scheduler] Startup scan failed: {exc}")

        while not self._stop_event.is_set():
            now = datetime.now(ET)

            # ── Intraday fast mode: 2-min scans + auto-close at 3:45 PM ──
            if getattr(self, '_intraday_mode', False):
                # Auto-close all positions at 3:45 PM ET
                close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
                if now >= close_time and is_trading_day(now.date()):
                    if not getattr(self, '_auto_close_fired', False):
                        logger.info("[Scheduler] 3:30 PM ET — running gap prediction scan")
                        try:
                            if self._callback:
                                self._callback("PREMARKET_GAP_SCAN")
                        except Exception as exc:
                            logger.warning(f"[Scheduler] Gap scan failed: {exc}")
                        logger.info("[Scheduler] 3:45 PM ET — firing smart close")
                        try:
                            if self._callback:
                                self._callback("INTRADAY_CLOSE")
                        except Exception as exc:
                            logger.warning(f"[Scheduler] Auto-close failed: {exc}")
                        self._auto_close_fired = True
                    # Fire EOD scan at 4:05 PM ET even in intraday mode
                    eod_time = now.replace(hour=16, minute=5, second=0, microsecond=0)
                    if not getattr(self, '_eod_scan_fired', False) and now >= eod_time:
                        logger.info("[Scheduler] 4:05 PM ET — firing EOD scan (intraday mode)")
                        try:
                            if self._callback:
                                self._callback("EOD")
                        except Exception as exc:
                            logger.warning(f"[Scheduler] EOD scan failed: {exc}")
                        self._eod_scan_fired = True
                    # After 3:45, sleep until tomorrow
                    self._stop_event.wait(timeout=60); continue

                # Fast scan every N minutes during market hours — sleep overnight
                market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
                market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
                if is_trading_day(now.date()) and market_open <= now <= market_close:
                    try:
                        if self._callback:
                            self._callback("INTRADAY")
                    except Exception as exc:
                        logger.warning(f"[Scheduler] Intraday scan failed: {exc}")
                    interval = getattr(self, '_intraday_interval', 2) * 60
                    self._stop_event.wait(timeout=interval)
                    continue
                else:
                    # Outside market hours — sleep until next market open
                    if now.hour >= 16 or not is_trading_day(now.date()):
                        # Sleep until 9:25 AM next trading day
                        next_open = now.replace(hour=9, minute=25, second=0, microsecond=0)
                        if now >= next_open:
                            next_open += timedelta(days=1)
                        # Skip weekends
                        while next_open.weekday() >= 5:
                            next_open += timedelta(days=1)
                        sleep_secs = (next_open - now).total_seconds()
                        logger.info(f"[Scheduler] Market closed — sleeping until {next_open.strftime('%Y-%m-%d %H:%M ET')}")
                        self._stop_event.wait(timeout=max(sleep_secs, 60))
                        # Reset auto_close flag for new day
                        self._auto_close_fired = False
                        self._eod_scan_fired = False
                    else:
                        self._stop_event.wait(timeout=30)
                    continue

            scans = self._next_scans()

            if not scans:
                # No scans today — sleep until tomorrow 8am
                tomorrow_8am = datetime(
                    now.year, now.month, now.day, 8, 0, tzinfo=ET
                ) + timedelta(days=1)
                sleep_secs = (tomorrow_8am - now).total_seconds()
                logger.info(
                    f"[Scheduler] No scans today — sleeping until "
                    f"{tomorrow_8am.strftime('%Y-%m-%d %H:%M ET')}"
                )
                self._stop_event.wait(timeout=max(sleep_secs, 60))
                continue

            next_scan = scans[0]
            sleep_secs = (next_scan - now).total_seconds()

            if sleep_secs > 0:
                logger.info(
                    f"[Scheduler] Next scan at {next_scan.strftime('%H:%M ET')} "
                    f"(in {sleep_secs/60:.0f} min)"
                )
                self._stop_event.wait(timeout=sleep_secs)

            if self._stop_event.is_set():
                break

            # Check it's still a valid trading time
            fire_now = datetime.now(ET)
            if not is_trading_day(fire_now.date()):
                logger.info("[Scheduler] Scan skipped — not a trading day")
                time.sleep(60)
                continue

            # Determine scan type for logging
            h, m = fire_now.hour, fire_now.minute
            if (h, m) >= EOD_SCAN:
                scan_type = "EOD"
                # Reset daily guards for tomorrow
                self.reset_daily_guards()
            elif (h, m) <= PREMARKET:
                scan_type = "PRE-MARKET"
            else:
                scan_type = "INTRADAY"

            logger.info(
                f"[Scheduler] Firing {scan_type} scan at "
                f"{fire_now.strftime('%H:%M:%S ET')}"
            )

            if self._callback:
                try:
                    self._callback(scan_type=scan_type)
                except Exception as exc:
                    logger.error(f"[Scheduler] Scan callback error: {exc}", exc_info=True)

            # Small sleep to avoid double-firing at exact boundary
            time.sleep(90)


def get_scan_interval_seconds(approach: str, scan_frequency_minutes: int) -> int:
    """
    Returns scan interval in seconds based on approach and user config.
    scan_frequency_minutes=0 means EOD only (handled by scheduler).
    """
    if scan_frequency_minutes > 0:
        return scan_frequency_minutes * 60
    # Defaults per mode
    defaults = {
        "Conservative":     0,    # EOD only
        "Balanced":         1800, # 30 min
        "Aggressive":       1800, # 30 min
        "Profit Maximizer": 600,  # 10 min
        "Long Term":        0,    # EOD only
    }
    return defaults.get(approach, 3600)
