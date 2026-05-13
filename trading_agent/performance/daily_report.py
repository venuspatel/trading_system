# -*- coding: utf-8 -*-
"""
DailyReportGenerator
---------------------
Produces a structured end-of-day report after every trading session.
Saved as JSON for the dashboard and as a human-readable text summary.

Report contains:
  - Day's trades and P&L
  - Running portfolio stats
  - Strategy rankings update
  - Risk events (if any limits were hit)
  - Agent decisions (buy/sell/hold/blocked counts)
  - Recommendations for next session
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DailyReport:
    """Structured daily report — written to JSON and readable text."""
    date:              str
    approach:          str
    paper_trading:     bool

    # Session activity
    total_scans:       int     = 0
    decisions_made:    int     = 0
    buys_executed:     int     = 0
    sells_executed:    int     = 0
    blocked:           int     = 0
    holds:             int     = 0

    # P&L
    day_pnl:           float   = 0.0
    day_pnl_pct:       float   = 0.0
    portfolio_value:   float   = 0.0
    total_pnl:         float   = 0.0

    # Risk events
    risk_events:       List[str] = field(default_factory=list)

    # Open positions
    open_positions:    List[dict] = field(default_factory=list)

    # Strategy performance
    top_strategy:      Optional[str]  = None
    worst_strategy:    Optional[str]  = None
    strategy_rankings: List[dict]     = field(default_factory=list)

    # Performance metrics
    win_rate:          float   = 0.0
    profit_factor:     float   = 0.0
    sharpe_ratio:      float   = 0.0
    max_drawdown:      float   = 0.0
    grade:             str     = "N/A"

    # Recommendations
    recommendations:   List[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Human-readable text version of the report."""
        mode  = "PAPER" if self.paper_trading else "LIVE"
        lines = [
            f"\n{'='*60}",
            f"  DAILY TRADING REPORT — {self.date}",
            f"  Approach: {self.approach} | Mode: {mode}",
            f"{'='*60}",
            f"",
            f"  SESSION ACTIVITY",
            f"  {'─'*40}",
            f"  Total scans:     {self.total_scans}",
            f"  Decisions made:  {self.decisions_made}",
            f"  Buys executed:   {self.buys_executed}",
            f"  Sells executed:  {self.sells_executed}",
            f"  Blocked:         {self.blocked}",
            f"  Holds:           {self.holds}",
            f"",
            f"  PORTFOLIO",
            f"  {'─'*40}",
            f"  Day P&L:         ${self.day_pnl:+,.2f} ({self.day_pnl_pct:+.1%})",
            f"  Portfolio value: ${self.portfolio_value:,.2f}",
            f"  Total P&L:       ${self.total_pnl:+,.2f}",
            f"  Win rate:        {self.win_rate:.1%}",
            f"  Profit factor:   {self.profit_factor:.2f}",
            f"  Sharpe ratio:    {self.sharpe_ratio:.2f}",
            f"  Max drawdown:    {self.max_drawdown:.1%}",
            f"  Grade:           {self.grade}",
        ]

        if self.open_positions:
            lines += ["", f"  OPEN POSITIONS ({len(self.open_positions)})"]
            lines.append(f"  {'─'*40}")
            for p in self.open_positions:
                lines.append(f"  {p.get('symbol','?')} — {p.get('pnl_str','')}")

        if self.risk_events:
            lines += ["", "  RISK EVENTS"]
            lines.append(f"  {'─'*40}")
            for e in self.risk_events:
                lines.append(f"  ! {e}")

        if self.strategy_rankings:
            lines += ["", "  STRATEGY RANKINGS"]
            lines.append(f"  {'─'*40}")
            for r in self.strategy_rankings[:5]:
                icon = "^" if r.get("status") == "PROMOTED" else \
                       "v" if r.get("status") == "DEMOTED"  else "-"
                lines.append(
                    f"  {icon} {r.get('name','?'):<22} "
                    f"win={r.get('win_rate',0):.0%} "
                    f"pnl=${r.get('total_pnl',0):+.0f}"
                )

        if self.recommendations:
            lines += ["", "  RECOMMENDATIONS FOR TOMORROW"]
            lines.append(f"  {'─'*40}")
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"  {i}. {rec}")

        lines += ["", f"{'='*60}", ""]
        return "\n".join(lines)


class DailyReportGenerator:
    """
    Generates end-of-day reports by combining data from:
      - DecisionLogger (today's decisions)
      - PortfolioTracker (trade history + P&L)
      - PerformanceAnalyzer (metrics)
      - StrategyRanker (rankings)
      - AlpacaExecutor (open positions + account)

    Usage:
        generator = DailyReportGenerator()
        report    = generator.generate(
            logger, portfolio, analyzer, ranker, executor, config
        )
        print(report.to_text())
    """

    def __init__(self, reports_path: str = "logs/reports"):
        self.reports_path = reports_path
        os.makedirs(reports_path, exist_ok=True)

    def generate(
        self,
        decision_logger,
        portfolio_tracker,
        performance_analyzer,
        strategy_ranker,
        executor,
        config,
    ) -> DailyReport:
        """Generate today's complete daily report."""
        today    = datetime.now(timezone.utc).date().isoformat()
        summary  = decision_logger.today_summary()
        trades   = portfolio_tracker._trades
        snaps    = portfolio_tracker._snapshots
        stats    = portfolio_tracker.stats
        acct     = executor.get_account() if executor else {}

        # Performance metrics
        perf = performance_analyzer.analyze(
            trades, snaps,
            starting_value = portfolio_tracker._starting_value or 100000
        )

        # Strategy rankings
        ranks = strategy_ranker.rank(trades) if trades else []

        # Open positions
        positions_detail = []
        if executor:
            for sym, pos in executor.open_positions.items():
                positions_detail.append({
                    "symbol":  sym,
                    "qty":     pos.qty,
                    "entry":   pos.entry_price,
                    "current": pos.current_price,
                    "pnl":     pos.unrealised_pnl,
                    "pnl_str": str(pos),
                })

        # Risk events from decision log
        risk_events = []
        for rec in decision_logger.recent(50):
            if rec.action == "BLOCKED" and rec.risk_blocks:
                risk_events.append(f"{rec.symbol}: {rec.risk_blocks[0]}")

        # Recommendations
        recommendations = self._build_recommendations(perf, ranks, config)

        report = DailyReport(
            date             = today,
            approach         = config.approach.value,
            paper_trading    = config.paper_trading,
            total_scans      = summary.get("total_scans", 0),
            decisions_made   = summary.get("total_scans", 0),
            buys_executed    = summary.get("buys", 0),
            sells_executed   = summary.get("sells", 0),
            blocked          = summary.get("blocked", 0),
            holds            = summary.get("holds", 0),
            day_pnl          = acct.get("daily_pnl", 0),
            day_pnl_pct      = acct.get("daily_pnl", 0) / max(acct.get("portfolio_value", 100000), 1),
            portfolio_value  = acct.get("portfolio_value", 0),
            total_pnl        = stats.get("total_pnl", 0),
            risk_events      = list(set(risk_events))[:5],
            open_positions   = positions_detail,
            top_strategy     = ranks[0].name if ranks else None,
            worst_strategy   = ranks[-1].name if ranks else None,
            strategy_rankings = [
                {"name": r.name, "win_rate": r.win_rate,
                 "total_pnl": r.total_pnl, "status": r.status}
                for r in ranks[:5]
            ],
            win_rate         = perf.win_rate,
            profit_factor    = perf.profit_factor,
            sharpe_ratio     = perf.sharpe_ratio,
            max_drawdown     = perf.max_drawdown,
            grade            = perf.grade,
            recommendations  = recommendations,
        )

        self._save(report)
        logger.info(f"[DailyReport] Generated report for {today} — Grade: {report.grade}")
        return report

    def _build_recommendations(self, perf, ranks, config) -> List[str]:
        """Build actionable recommendations for next session."""
        recs = []

        if perf.total_trades < 5:
            recs.append("More trades needed before meaningful analysis — keep running paper trading")
            return recs

        if perf.win_rate < 0.45:
            recs.append(
                f"Win rate is low ({perf.win_rate:.0%}) — "
                f"consider switching to Conservative approach to raise quality threshold"
            )

        if perf.max_drawdown > 0.08:
            recs.append(
                f"Max drawdown is elevated ({perf.max_drawdown:.1%}) — "
                f"consider tightening stop-loss from {config.stop_loss_pct:.0%} to {config.stop_loss_pct*0.75:.0%}"
            )

        if perf.profit_factor < 1.2:
            recs.append(
                "Profit factor below 1.2 — review losing trades for pattern. "
                "Consider raising min_strategies_agree by 1."
            )

        demoted = [r for r in ranks if r.status == "DEMOTED"]
        if demoted:
            names = ", ".join(r.name for r in demoted[:2])
            recs.append(f"Underperforming strategies: {names} — agent has reduced their weight automatically")

        promoted = [r for r in ranks if r.status == "PROMOTED"]
        if promoted:
            names = ", ".join(r.name for r in promoted[:2])
            recs.append(f"Top performing strategies: {names} — agent has increased their weight")

        if perf.sharpe_ratio > 1.5:
            recs.append(
                f"Sharpe ratio is strong ({perf.sharpe_ratio:.1f}) — "
                f"consider gradually increasing position size if paper trading results hold"
            )

        if not recs:
            recs.append("Performance looks good — continue current approach")

        return recs[:4]

    def _save(self, report: DailyReport):
        """Save report as JSON and text."""
        try:
            base = os.path.join(self.reports_path, report.date)
            with open(f"{base}.json", "w") as f:
                json.dump(asdict(report), f, indent=2)
            with open(f"{base}.txt", "w") as f:
                f.write(report.to_text())
        except Exception as exc:
            logger.error(f"[DailyReport] Save failed: {exc}")
