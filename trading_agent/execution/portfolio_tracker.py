# -*- coding: utf-8 -*-
"""
PortfolioTracker — Professional Reporting Edition
--------------------------------------------------
Tracks portfolio state with clean session boundaries.

Reporting metrics:
  1. Capital:    total_invested · remaining_liquid · buying_power
  2. Session:    session_pnl (resets each restart) · session_trades
  3. Day:        day_pnl (resets midnight ET) · day_trades · day_win_rate
  4. Week:       week_pnl (Mon-Fri rolling)
  5. Month:      month_pnl (calendar month)
  6. All-time:   total_closed_pnl · win_rate · profit_factor · TWRR
  7. Risk:       max_drawdown · sharpe · avg_win · avg_loss · expectancy
  8. Positions:  unrealised_pnl · concentration per symbol
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from .order_models import Order, OrderSide, Position

logger = logging.getLogger(__name__)

ET_OFFSET = timedelta(hours=-4)   # EDT  (use -5 for EST)


def _now_et() -> datetime:
    return datetime.now(timezone.utc).astimezone(timezone(ET_OFFSET))


def _et_date_str() -> str:
    return _now_et().strftime("%Y-%m-%d")


def _et_week_str() -> str:
    d = _now_et()
    # ISO week: Mon=0 … Sun=6
    mon = d - timedelta(days=d.weekday())
    return mon.strftime("%Y-W%W")


def _et_month_str() -> str:
    return _now_et().strftime("%Y-%m")


@dataclass
class ClosedTrade:
    """Record of a completed round-trip trade (entry + exit)."""
    symbol:        str
    entry_price:   float
    exit_price:    float
    qty:           int
    entry_time:    str
    exit_time:     str
    pnl:           float
    pnl_pct:       float
    exit_reason:   str
    strategy:      str = ""
    approach:      str = ""

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state — stored for charting."""
    timestamp:       str
    portfolio_value: float
    cash:            float
    open_positions:  int
    daily_pnl:       float
    total_pnl:       float
    drawdown:        float


class PortfolioTracker:
    """
    Professional-grade portfolio tracker with clean session boundaries
    and multi-timeframe P&L reporting.
    """

    def __init__(self, data_path: str = "logs/portfolio.json"):
        self.data_path         = data_path
        self._trades:          List[ClosedTrade]       = []
        self._snapshots:       List[PortfolioSnapshot] = []
        self._peak_value:      float = 0.0
        self._starting_value:  float = 0.0
        self._historical_pnl_offset: float = 0.0
        self._synthetic_curve: list = []

        # ── Session tracking (resets every restart) ─────────────────
        self._session_start_pnl: float = 0.0   # total_pnl at session start
        self._session_start_time: str  = datetime.now(timezone.utc).isoformat()
        self._session_trade_count: int = 0

        # ── Day tracking (resets midnight ET) ────────────────────────
        self._day_date:       str   = _et_date_str()
        self._day_start_pnl:  float = 0.0       # set on first trade of day

        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        self._load()

        # Set session baseline from historical total
        existing_pnl = sum(t.pnl for t in self._trades)
        self._session_start_pnl = existing_pnl
        logger.info(
            f"[Portfolio] Session started — baseline P&L: ${existing_pnl:.2f} "
            f"over {len(self._trades)} historical trades"
        )

        # Auto-heal historical_pnl_offset against Alpaca ground truth on every startup
        self._alpaca_key    = None  # set externally via set_alpaca_credentials()
        self._alpaca_secret = None

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_trade(self, trade: ClosedTrade):
        """Record a completed trade."""
        self._check_day_rollover()
        self._trades.append(trade)
        self._session_trade_count += 1
        self._rebuild_synthetic_curve()
        self._save()
        icon = "WIN" if trade.is_winner else "LOSS"
        logger.info(
            f"[Portfolio] [{icon}] {trade.symbol} "
            f"{'+'if trade.pnl>=0 else ''}${trade.pnl:.2f} "
            f"({trade.pnl_pct:+.1%}) via {trade.exit_reason}"
        )

    def record_snapshot(
        self,
        portfolio_value: float,
        cash:            float,
        open_positions:  int,
        daily_pnl:       float,
    ):
        """Record a portfolio snapshot (called each cycle)."""
        self._check_day_rollover()

        if self._starting_value == 0:
            self._starting_value = portfolio_value

        self._peak_value = max(self._peak_value, portfolio_value)
        drawdown = (
            (self._peak_value - portfolio_value) / self._peak_value
            if self._peak_value > 0 else 0
        )
        total_pnl = sum(t.pnl for t in self._trades)

        snap = PortfolioSnapshot(
            timestamp       = datetime.now(timezone.utc).isoformat(),
            portfolio_value = round(portfolio_value, 2),
            cash            = round(cash, 2),
            open_positions  = open_positions,
            daily_pnl       = round(daily_pnl, 2),
            total_pnl       = round(total_pnl, 2),
            drawdown        = round(drawdown, 4),
        )
        self._snapshots.append(snap)
        if len(self._snapshots) > 1000:
            self._snapshots = self._snapshots[-1000:]
        self._save()

    # ------------------------------------------------------------------
    # Champion evaluation
    # ------------------------------------------------------------------

    def daily_summary(self) -> dict:
        """
        Returns today's performance summary for champion evaluation.
        Called by _evaluate_champion() in trading_agent.py at EOD.
        """
        from datetime import datetime, timezone, timedelta
        ET    = timezone(timedelta(hours=-4))
        today = datetime.now(ET).strftime('%Y-%m-%d')
        trades = [t for t in self._trades
                  if (t.exit_time or '').startswith(today)]
        if not trades:
            return {
                'date':        today,
                'trades':      0,
                'win_rate':    0.0,
                'day_pnl':     0.0,
                'max_drawdown':0.0,
                'qualifies':   False,
                'reason':      'No trades today',
            }
        winners  = [t for t in trades if t.is_winner]
        win_rate = len(winners) / len(trades)
        day_pnl  = sum(t.pnl for t in trades)
        max_dd   = max(
            (s.drawdown for s in self._snapshots
             if (s.timestamp or '').startswith(today)),
            default=0.0
        )
        CRITERIA = {
            'win_rate_min': 0.75,
            'pnl_min':      300.0,
            'drawdown_max': 0.03,
            'trades_min':   3,
        }
        fails = []
        if win_rate < CRITERIA['win_rate_min']:
            fails.append(f"win_rate {win_rate:.0%} < {CRITERIA['win_rate_min']:.0%}")
        if day_pnl < CRITERIA['pnl_min']:
            fails.append(f"P&L ${day_pnl:.0f} < ${CRITERIA['pnl_min']:.0f}")
        if max_dd > CRITERIA['drawdown_max']:
            fails.append(f"drawdown {max_dd:.1%} > {CRITERIA['drawdown_max']:.0%}")
        if len(trades) < CRITERIA['trades_min']:
            fails.append(f"only {len(trades)} trades < {CRITERIA['trades_min']} min")
        return {
            'date':        today,
            'trades':      len(trades),
            'win_rate':    round(win_rate, 4),
            'day_pnl':     round(day_pnl, 2),
            'max_drawdown':round(max_dd, 4),
            'qualifies':   len(fails) == 0,
            'reason':      'All criteria met' if not fails else ' | '.join(fails),
        }

    # ------------------------------------------------------------------
    # Day rollover
    # ------------------------------------------------------------------

    def _check_day_rollover(self):
        today = _et_date_str()
        if today != self._day_date:
            logger.info(f"[Portfolio] Day rollover {self._day_date} → {today}")
            self._day_date      = today
            self._day_start_pnl = sum(t.pnl for t in self._trades)

    # ------------------------------------------------------------------
    # Stats (fed to dashboard)
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        trades  = self._trades
        winners = [t for t in trades if t.is_winner]
        losers  = [t for t in trades if not t.is_winner]

        total_closed_pnl = sum(t.pnl for t in trades) + self._historical_pnl_offset
        win_rate   = len(winners) / len(trades) if trades else 0
        avg_win    = sum(t.pnl for t in winners) / len(winners) if winners else 0
        avg_loss   = sum(t.pnl for t in losers)  / len(losers)  if losers  else 0
        gross_win  = sum(t.pnl for t in winners)
        gross_loss = abs(sum(t.pnl for t in losers))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0

        max_dd = max((s.drawdown for s in self._snapshots[-200:]), default=0)

        best  = max(trades, key=lambda t: t.pnl, default=None)
        worst = min(trades, key=lambda t: t.pnl, default=None)

        # ── Session P&L ─────────────────────────────────────────────
        session_pnl    = total_closed_pnl - self._session_start_pnl
        session_trades = self._session_trade_count

        # ── Day P&L ──────────────────────────────────────────────────
        self._check_day_rollover()
        today     = _et_date_str()
        day_trades = [
            t for t in trades
            if (t.exit_time or "").startswith(today)
            or self._trade_in_et_date(t, today)
        ]
        day_pnl      = sum(t.pnl for t in day_trades)
        day_winners  = [t for t in day_trades if t.is_winner]
        day_win_rate = len(day_winners) / len(day_trades) if day_trades else 0

        # ── Week P&L ─────────────────────────────────────────────────
        week = _et_week_str()
        week_trades = [t for t in trades if self._trade_in_et_week(t, week)]
        week_pnl    = sum(t.pnl for t in week_trades)

        # ── Month P&L ────────────────────────────────────────────────
        month = _et_month_str()
        month_trades = [t for t in trades if self._trade_in_et_month(t, month)]
        month_pnl    = sum(t.pnl for t in month_trades)

        # ── TWRR — time-weighted return ──────────────────────────────
        twrr = (
            total_closed_pnl / self._starting_value
            if self._starting_value > 0 else 0
        )

        # ── Expectancy ───────────────────────────────────────────────
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        # ── Reward/Risk ratio ────────────────────────────────────────
        reward_risk = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        # ── Sharpe (simple daily estimate) ───────────────────────────
        snaps = self._snapshots[-20:]
        if len(snaps) > 1:
            returns = [
                (snaps[i].portfolio_value - snaps[i-1].portfolio_value)
                / snaps[i-1].portfolio_value
                for i in range(1, len(snaps))
                if snaps[i-1].portfolio_value > 0
            ]
            if returns:
                import statistics
                avg_r = statistics.mean(returns)
                std_r = statistics.stdev(returns) if len(returns) > 1 else 1
                sharpe = (avg_r / std_r) * (252 ** 0.5) if std_r > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        # ── Consecutive losses ───────────────────────────────────────
        max_consec_loss = 0
        curr_consec     = 0
        for t in trades:
            if not t.is_winner:
                curr_consec += 1
                max_consec_loss = max(max_consec_loss, curr_consec)
            else:
                curr_consec = 0

        return {
            # Closed trade totals
            "total_trades":      len(trades),
            "winners":           len(winners),
            "losers":            len(losers),
            "win_rate":          round(win_rate, 4),
            "total_pnl":         round(total_closed_pnl, 2),
            "verified_pnl":      round(total_closed_pnl, 2),  # sum of stored records

            # Session (since last restart)
            "session_pnl":       round(session_pnl, 2),
            "session_trades":    session_trades,

            # Day
            "day_pnl":           round(day_pnl, 2),
            "day_trades":        len(day_trades),
            "day_win_rate":      round(day_win_rate, 4),

            # Week / Month
            "week_pnl":          round(week_pnl, 2),
            "month_pnl":         round(month_pnl, 2),

            # Risk metrics
            "avg_win":           round(avg_win, 2),
            "avg_loss":          round(avg_loss, 2),
            "profit_factor":     round(profit_factor, 2),
            "max_drawdown":      round(max_dd, 4),
            "sharpe":            round(sharpe, 2),
            "expectancy":        round(expectancy, 2),
            "reward_risk":       round(reward_risk, 2),
            "max_consec_losses": max_consec_loss,
            "twrr":              round(twrr, 4),

            # Reference
            "best_trade":        {"symbol": best.symbol,  "pnl": best.pnl}  if best  else None,
            "worst_trade":       {"symbol": worst.symbol, "pnl": worst.pnl} if worst else None,
            "starting_value":    self._starting_value,
            "peak_value":        self._peak_value,
        }

    def symbol_stats(self, symbol: str) -> dict:
        """Per-symbol win rate and avg P&L — feeds Kelly sizer for smarter sizing."""
        sym = symbol.upper()
        trades = [vars(t) if not isinstance(t, dict) else t 
                  for t in self._trades 
                  if (vars(t) if not isinstance(t, dict) else t).get('symbol','').upper() == sym]
        if not trades:
            return {'win_rate': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0, 'count': 0}
        wins   = [t for t in trades if t.get('pnl', 0) >= 0]
        losses = [t for t in trades if t.get('pnl', 0) < 0]
        win_rate = len(wins) / len(trades)
        avg_win  = sum(t.get('pnl',0) for t in wins) / len(wins)   if wins   else 0.0
        avg_loss = sum(t.get('pnl',0) for t in losses) / len(losses) if losses else 0.0
        return {
            'win_rate': win_rate,
            'avg_win':  avg_win,
            'avg_loss': abs(avg_loss),
            'count':    len(trades)
        }

    def get_recent_trades(self, symbol: str, n: int = 3) -> List[dict]:
        """Get last n trades for a specific symbol — handles both dict and Trade objects."""
        sym = symbol.upper()
        result = []
        for t in reversed(self._trades):
            # Handle both Trade objects and plain dicts
            if isinstance(t, dict):
                t_sym = t.get('symbol', '').upper()
                t_dict = t
            else:
                t_sym = getattr(t, 'symbol', '').upper()
                t_dict = vars(t)
            if t_sym == sym:
                result.append(t_dict)
            if len(result) >= n:
                break
        return result

    @property
    def recent_trades(self) -> List[dict]:
        """Last 50 trades for the dashboard (up from 20)."""
        return [vars(t) for t in self._trades[-50:]]

    @property
    def all_trades(self) -> List[dict]:
        """ALL closed trades — used for accurate P&L calculations."""
        return [vars(t) for t in self._trades]

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    @property
    def equity_curve(self) -> List[dict]:
        return [
            {"t": s.timestamp, "v": s.portfolio_value, "dd": s.drawdown}
            for s in self._snapshots
        ]

    @property
    def synthetic_curve(self) -> List[dict]:
        """Trade-based equity curve from $1M start — full history."""
        return self._synthetic_curve

    def _rebuild_synthetic_curve(self):
        """Rebuild synthetic curve from trade history."""
        BASE = 1_000_000.0
        trades = sorted(
            [t for t in self._trades if t.exit_time
             and t.exit_reason != "Historical P&L adjustment"],
            key=lambda t: t.exit_time
        )
        curve = [{"t": "2026-04-14T00:00:00+00:00", "v": BASE, "dd": 0.0}]
        running = BASE
        peak = BASE
        for t in trades:
            running += t.pnl
            peak = max(peak, running)
            dd = round((peak - running) / peak, 4) if peak > 0 else 0.0
            exit_t = t.exit_time
            if exit_t and not exit_t.endswith("Z") and "+" not in exit_t:
                exit_t += "+00:00"
            curve.append({"t": exit_t, "v": round(running, 2), "dd": dd})
        self._synthetic_curve = curve

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    def _trade_exit_et(self, t: ClosedTrade) -> Optional[datetime]:
        try:
            raw = (t.exit_time or "").strip()
            if not raw:
                return None
            # Handle various formats
            raw = raw.replace("Z", "+00:00")
            if "+" not in raw and "T" in raw:
                # Naive datetime — assume UTC
                raw = raw + "+00:00"
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone(ET_OFFSET))
        except Exception:
            return None

    def _trade_in_et_date(self, t: ClosedTrade, date_str: str) -> bool:
        et = self._trade_exit_et(t)
        return et.strftime("%Y-%m-%d") == date_str if et else False

    def _trade_in_et_week(self, t: ClosedTrade, week_str: str) -> bool:
        et = self._trade_exit_et(t)
        if not et:
            return False
        mon = et - timedelta(days=et.weekday())
        return mon.strftime("%Y-W%W") == week_str

    def _trade_in_et_month(self, t: ClosedTrade, month_str: str) -> bool:
        et = self._trade_exit_et(t)
        return et.strftime("%Y-%m") == month_str if et else False

    # ------------------------------------------------------------------
    # Strategy breakdown
    # ------------------------------------------------------------------

    def strategy_breakdown(self) -> List[dict]:
        by_strategy: Dict[str, List[ClosedTrade]] = {}
        for t in self._trades:
            by_strategy.setdefault(t.strategy, []).append(t)
        result = []
        for strat, trades in by_strategy.items():
            winners = [t for t in trades if t.is_winner]
            result.append({
                "strategy":  strat,
                "trades":    len(trades),
                "win_rate":  round(len(winners) / len(trades), 4),
                "total_pnl": round(sum(t.pnl for t in trades), 2),
                "avg_pnl":   round(sum(t.pnl for t in trades) / len(trades), 2),
            })
        return sorted(result, key=lambda x: -x["total_pnl"])

    # ------------------------------------------------------------------
    # Data integrity
    # ------------------------------------------------------------------

    def clean_bad_trades(self, max_single_pnl: float = 500.0) -> int:
        before = len(self._trades)
        self._trades = [
            t for t in self._trades
            if t.qty > 0 and abs(t.pnl) <= max_single_pnl and t.entry_price > 0
        ]
        removed = before - len(self._trades)
        if removed > 0:
            logger.info(f"[Portfolio] Cleaned {removed} bad trades")
            self._save()
        return removed

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self):
        try:
            data = {
                "starting_value":    self._starting_value,
                "historical_pnl_offset": self._historical_pnl_offset,
                "peak_value":        self._peak_value,
                "day_date":          self._day_date,
                "day_start_pnl":     self._day_start_pnl,
                "trades":            [vars(t) for t in self._trades],
                "snapshots":         [vars(s) for s in self._snapshots[-200:]],
            }
            with open(self.data_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.error(f"[Portfolio] Save failed: {exc}")


    def set_alpaca_credentials(self, api_key: str, secret_key: str, paper: bool = True):
        """
        Call this after init with Alpaca credentials.
        Auto-heals historical_pnl_offset to match Alpaca ground truth.
        """
        self._alpaca_key    = api_key
        self._alpaca_secret = secret_key
        self._alpaca_paper  = paper
        self._heal_offset()

    def _heal_offset(self):
        """
        Recalculates historical_pnl_offset so that:
            sum(trades.pnl) + historical_pnl_offset == alpaca_true_pnl
        Runs on every startup — keeps dashboard P&L in sync with Alpaca.
        """
        if not self._alpaca_key or not self._alpaca_secret:
            return
        try:
            import urllib.request as _ur, json as _json
            base = "https://paper-api.alpaca.markets" if getattr(self, "_alpaca_paper", True) else "https://api.alpaca.markets"
            req  = _ur.Request(
                f"{base}/v2/account",
                headers={
                    "APCA-API-KEY-ID":     self._alpaca_key,
                    "APCA-API-SECRET-KEY": self._alpaca_secret,
                }
            )
            acct        = _json.loads(_ur.urlopen(req, timeout=8).read())
            true_equity = float(acct["equity"])
            true_pnl    = true_equity - 1_000_000
            trade_pnl   = sum(t.pnl for t in self._trades)
            new_offset  = true_pnl - trade_pnl
            old_offset  = self._historical_pnl_offset
            if abs(new_offset - old_offset) > 50:  # only update if gap > $50
                self._historical_pnl_offset = new_offset
                self._save()
                logger.info(
                    f"[Portfolio] Auto-healed offset: ${old_offset:+.2f} → ${new_offset:+.2f} "
                    f"(Alpaca equity=${true_equity:,.2f}, trade_pnl=${trade_pnl:+.2f})"
                )
            else:
                logger.info(f"[Portfolio] Offset OK — gap ${abs(new_offset-old_offset):.2f} < $50 threshold")
        except Exception as e:
            logger.warning(f"[Portfolio] Offset heal failed: {e}")

    def _load(self):
        if not os.path.exists(self.data_path):
            return
        try:
            with open(self.data_path) as f:
                data = json.load(f)
            self._starting_value = data.get("starting_value", 0)
            self._peak_value     = data.get("peak_value", 0)
            self._day_date       = data.get("day_date", _et_date_str())
            self._day_start_pnl  = data.get("day_start_pnl", 0)
            self._trades             = [ClosedTrade(**t) for t in data.get("trades", [])]
            self._snapshots          = [PortfolioSnapshot(**s) for s in data.get("snapshots", [])]
            self._historical_pnl_offset = data.get("historical_pnl_offset", 0.0)
            if self._trades:
                logger.info(f"[Portfolio] Loaded {len(self._trades)} historical trades")
            self._rebuild_synthetic_curve()
        except Exception as exc:
            logger.warning(f"[Portfolio] Load failed: {exc}")
