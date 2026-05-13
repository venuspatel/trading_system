# -*- coding: utf-8 -*-
"""
PerformanceAnalyzer
--------------------
Calculates the full suite of trading performance metrics
from the portfolio trade history.

Metrics calculated:
  - Win rate, profit factor, expectancy
  - Sharpe ratio, Sortino ratio
  - Max drawdown, drawdown duration
  - Average win/loss, largest win/loss
  - Strategy-level breakdown
  - Approach-level breakdown
  - Rolling 7-day and 30-day performance
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PerformanceReport:
    """Complete performance snapshot — fed to dashboard and strategy ranker."""

    # Overview
    total_trades:      int     = 0
    winners:           int     = 0
    losers:            int     = 0
    win_rate:          float   = 0.0
    total_pnl:         float   = 0.0
    total_pnl_pct:     float   = 0.0

    # Risk-adjusted
    profit_factor:     float   = 0.0   # gross profit / gross loss
    expectancy:        float   = 0.0   # avg $ per trade
    sharpe_ratio:      float   = 0.0
    sortino_ratio:     float   = 0.0

    # Drawdown
    max_drawdown:      float   = 0.0   # peak-to-trough %
    max_drawdown_days: int     = 0     # how long it lasted
    current_drawdown:  float   = 0.0

    # Trade stats
    avg_win:           float   = 0.0
    avg_loss:          float   = 0.0
    largest_win:       float   = 0.0
    largest_loss:      float   = 0.0
    avg_hold_days:     float   = 0.0

    # Rolling windows
    pnl_7d:            float   = 0.0
    pnl_30d:           float   = 0.0
    win_rate_30d:      float   = 0.0

    # By strategy
    by_strategy:       List[dict] = field(default_factory=list)

    # By approach
    by_approach:       List[dict] = field(default_factory=list)

    # Grade
    grade:             str     = "N/A"
    grade_reason:      str     = ""

    def __str__(self):
        lines = [
            f"\n{'='*55}",
            f"  PERFORMANCE REPORT",
            f"{'='*55}",
            f"  Total trades:    {self.total_trades}",
            f"  Win rate:        {self.win_rate:.1%}  ({self.winners}W / {self.losers}L)",
            f"  Total P&L:       ${self.total_pnl:+,.2f}  ({self.total_pnl_pct:+.1%})",
            f"  Profit factor:   {self.profit_factor:.2f}",
            f"  Expectancy:      ${self.expectancy:+.2f} per trade",
            f"  Sharpe ratio:    {self.sharpe_ratio:.2f}",
            f"  Max drawdown:    {self.max_drawdown:.1%}  ({self.max_drawdown_days} days)",
            f"  Avg win:         ${self.avg_win:.2f}",
            f"  Avg loss:        ${self.avg_loss:.2f}",
            f"  7-day P&L:       ${self.pnl_7d:+,.2f}",
            f"  30-day P&L:      ${self.pnl_30d:+,.2f}",
            f"{'─'*55}",
            f"  Grade: {self.grade}  —  {self.grade_reason}",
            f"{'='*55}\n",
        ]
        return "\n".join(lines)


class PerformanceAnalyzer:
    """
    Calculates all performance metrics from a list of closed trades
    and portfolio snapshots.

    Usage:
        analyzer = PerformanceAnalyzer()
        report   = analyzer.analyze(trades, snapshots, starting_value=100000)
        print(report)
    """

    def analyze(
        self,
        trades:          List,      # List[ClosedTrade]
        snapshots:       List,      # List[PortfolioSnapshot]
        starting_value:  float = 100000.0,
    ) -> PerformanceReport:
        """Generate a complete performance report."""
        report = PerformanceReport()

        if not trades:
            report.grade        = "N/A"
            report.grade_reason = "No completed trades yet"
            return report

        winners = [t for t in trades if t.pnl > 0]
        losers  = [t for t in trades if t.pnl <= 0]

        # Basic stats
        report.total_trades = len(trades)
        report.winners      = len(winners)
        report.losers       = len(losers)
        report.win_rate     = len(winners) / len(trades)
        report.total_pnl    = sum(t.pnl for t in trades)
        report.total_pnl_pct = report.total_pnl / starting_value

        # Profit factor
        gross_profit = sum(t.pnl for t in winners)
        gross_loss   = abs(sum(t.pnl for t in losers))
        report.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # Expectancy (avg $ per trade)
        report.expectancy = report.total_pnl / len(trades)

        # Win/loss averages
        report.avg_win      = gross_profit / len(winners) if winners else 0
        report.avg_loss     = gross_loss   / len(losers)  if losers  else 0
        report.largest_win  = max((t.pnl for t in winners), default=0)
        report.largest_loss = min((t.pnl for t in losers),  default=0)

        # Sharpe & Sortino from daily returns
        if snapshots and len(snapshots) > 1:
            daily_returns = self._daily_returns(snapshots)
            if daily_returns:
                report.sharpe_ratio  = self._sharpe(daily_returns)
                report.sortino_ratio = self._sortino(daily_returns)
                report.max_drawdown, report.max_drawdown_days = \
                    self._max_drawdown(snapshots)
                report.current_drawdown = self._current_drawdown(snapshots)

        # Rolling windows
        now     = datetime.now(timezone.utc)
        week    = now - timedelta(days=7)
        month   = now - timedelta(days=30)

        trades_7d  = [t for t in trades if self._parse_dt(t.exit_time) >= week]
        trades_30d = [t for t in trades if self._parse_dt(t.exit_time) >= month]

        report.pnl_7d       = sum(t.pnl for t in trades_7d)
        report.pnl_30d      = sum(t.pnl for t in trades_30d)
        report.win_rate_30d = (
            len([t for t in trades_30d if t.pnl > 0]) / len(trades_30d)
            if trades_30d else 0
        )

        # Strategy breakdown
        report.by_strategy = self._by_group(trades, "strategy")
        report.by_approach = self._by_group(trades, "approach")

        # Grade
        report.grade, report.grade_reason = self._grade(report)

        return report

    # ------------------------------------------------------------------
    # Metric helpers
    # ------------------------------------------------------------------

    def _daily_returns(self, snapshots) -> List[float]:
        """Extract daily return % from portfolio snapshots."""
        values = [s.portfolio_value for s in snapshots]
        returns = []
        for i in range(1, len(values)):
            if values[i-1] > 0:
                returns.append((values[i] - values[i-1]) / values[i-1])
        return returns

    def _sharpe(self, returns: List[float], risk_free: float = 0.05/252) -> float:
        """Annualised Sharpe ratio."""
        if len(returns) < 2:
            return 0.0
        avg = sum(returns) / len(returns)
        std = math.sqrt(sum((r - avg) ** 2 for r in returns) / (len(returns) - 1))
        if std == 0:
            return 0.0
        return round((avg - risk_free) / std * math.sqrt(252), 2)

    def _sortino(self, returns: List[float], risk_free: float = 0.05/252) -> float:
        """Annualised Sortino ratio (only penalises downside volatility)."""
        if len(returns) < 2:
            return 0.0
        avg         = sum(returns) / len(returns)
        neg_returns = [r for r in returns if r < 0]
        if not neg_returns:
            return 0.0
        downside_std = math.sqrt(
            sum(r ** 2 for r in neg_returns) / len(neg_returns)
        )
        if downside_std == 0:
            return 0.0
        return round((avg - risk_free) / downside_std * math.sqrt(252), 2)

    def _max_drawdown(self, snapshots) -> tuple:
        """Returns (max_drawdown_pct, duration_in_days)."""
        values    = [s.portfolio_value for s in snapshots]
        peak      = values[0]
        max_dd    = 0.0
        dd_start  = 0
        max_dur   = 0

        for i, v in enumerate(values):
            if v > peak:
                peak     = v
                dd_start = i
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd  = dd
                max_dur = i - dd_start

        return round(max_dd, 4), max_dur

    def _current_drawdown(self, snapshots) -> float:
        if not snapshots:
            return 0.0
        values  = [s.portfolio_value for s in snapshots]
        peak    = max(values)
        current = values[-1]
        return round((peak - current) / peak, 4) if peak > 0 else 0.0

    def _by_group(self, trades, attr: str) -> List[dict]:
        """Group trades by an attribute and calculate per-group stats."""
        groups: Dict[str, list] = {}
        for t in trades:
            key = getattr(t, attr, "unknown") or "unknown"
            groups.setdefault(key, []).append(t)

        result = []
        for key, group in groups.items():
            wins = [t for t in group if t.pnl > 0]
            result.append({
                "name":       key,
                "trades":     len(group),
                "win_rate":   round(len(wins) / len(group), 3),
                "total_pnl":  round(sum(t.pnl for t in group), 2),
                "avg_pnl":    round(sum(t.pnl for t in group) / len(group), 2),
            })
        return sorted(result, key=lambda x: -x["total_pnl"])

    def _grade(self, r: PerformanceReport) -> tuple:
        """Grade the overall performance A-F with reasoning."""
        if r.total_trades < 5:
            return "N/A", "Need at least 5 trades to grade"

        score = 0
        reasons = []

        if r.win_rate >= 0.60:   score += 2; reasons.append("win rate excellent")
        elif r.win_rate >= 0.50: score += 1; reasons.append("win rate acceptable")
        else:                    reasons.append("win rate below 50%")

        if r.profit_factor >= 2.0:   score += 2; reasons.append("profit factor strong")
        elif r.profit_factor >= 1.5: score += 1; reasons.append("profit factor ok")
        else:                        reasons.append("profit factor weak")

        if r.sharpe_ratio >= 1.5:   score += 2; reasons.append("Sharpe excellent")
        elif r.sharpe_ratio >= 0.5: score += 1; reasons.append("Sharpe acceptable")
        else:                       reasons.append("Sharpe poor")

        if r.max_drawdown <= 0.05:   score += 2; reasons.append("low drawdown")
        elif r.max_drawdown <= 0.10: score += 1; reasons.append("moderate drawdown")
        else:                        reasons.append("high drawdown")

        grades = {8: "A", 7: "A-", 6: "B+", 5: "B", 4: "B-", 3: "C", 2: "D"}
        grade  = grades.get(score, "F")
        return grade, " | ".join(reasons[:3])

    @staticmethod
    def _parse_dt(dt_str: str) -> datetime:
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            # Always return timezone-aware — treat naive as UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return datetime.now(timezone.utc)
