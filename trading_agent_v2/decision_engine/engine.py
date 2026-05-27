# -*- coding: utf-8 -*-
"""
DecisionEngine  — Layer 4 core
--------------------------------
The autonomous brain. Takes StrategyReports from Layer 3, applies
risk rules, sizes positions, and produces final TradeDecisions.

Flow for each symbol each cycle:
  1. Receive StrategyReport (Layer 3 output)
  2. Check gate: enough strategies agree? Confidence high enough?
  3. Calculate position size
  4. Run RiskGuardian — all safety rules
  5. Produce TradeDecision
  6. Log with full reasoning
  7. Return decision to the executor (Layer 5)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from .agent_config   import AgentConfig
from .position_sizer import PositionSizer, PositionSize
from .risk_guardian  import RiskGuardian, RiskAssessment
from .decision_logger import DecisionLogger, DecisionRecord
from .ai_reviewer    import AIReviewer, AIVerdict
from strategies.base  import TradeAction
from strategies.engine import StrategyReport
from .conviction_engine  import EnhancedConvictionEngine, ConvictionBreakdown
from .market_regime      import MarketRegimeDetector, RegimeReading, MomentumOverrideDetector, MomentumOverride

logger = logging.getLogger(__name__)


@dataclass
class TradeDecision:
    """
    Final output of the DecisionEngine for one symbol.
    This is what Layer 5 (Executor) acts on.
    """
    symbol:          str
    timestamp:       datetime
    action:          str             # "BUY" | "SELL" | "HOLD" | "BLOCKED"
    approved:        bool

    # Position details (only set when action=BUY/SELL)
    shares:          int             = 0
    dollar_amount:   float           = 0.0
    stop_loss:       float           = 0.0
    take_profit:     float           = 0.0
    risk_reward:     float           = 0.0

    # Reasoning (feeds the dashboard)
    conviction_score: float          = 0.0
    avg_confidence:   float          = 0.0
    buy_signals:      int            = 0
    sell_signals:     int            = 0
    top_reasons:      List[str]      = field(default_factory=list)
    strategies_fired: List[str]      = field(default_factory=list)
    block_reasons:    List[str]      = field(default_factory=list)
    approach:         str            = ""
    paper_trade:      bool           = True
    # Trend classification
    trend_state:      str            = "UNKNOWN"   # UPTREND | DOWNTREND | NEUTRAL | UNKNOWN

    # AI reviewer fields
    ai_approved:      Optional[bool] = None
    ai_confidence:    float          = 0.0
    ai_reasoning:     str            = ""
    ai_concerns:      List[str]      = field(default_factory=list)
    ai_suggestion:    str            = ""
    ai_used:          bool           = False

    def __str__(self):
        if self.action in ("BUY", "SELL"):
            return (
                f"[{self.action}] {self.symbol} | "
                f"{self.shares} shares @ stop={self.stop_loss:.2f} tp={self.take_profit:.2f} | "
                f"conviction={self.conviction_score:+.2f} | "
                f"{self.top_reasons[0] if self.top_reasons else ''}"
            )
        return f"[{self.action}] {self.symbol} | {self.block_reasons[0] if self.block_reasons else 'no signal'}"


class DecisionEngine:
    """
    Autonomous decision-making engine.

    Usage:
        config   = AgentConfig()
        config.apply_balanced()

        engine   = DecisionEngine(config)

        # Each cycle:
        decision = engine.decide(symbol, df, strategy_report, portfolio_value)
        print(decision)
    """

    def __init__(self, config: AgentConfig):
        self.config   = config
        self.sizer    = PositionSizer(config)
        self.guardian = RiskGuardian(config)
        self.logger   = DecisionLogger(config.log_path)
        self.reviewer = AIReviewer(
            min_ai_confidence = getattr(config, 'min_ai_confidence', 0.55),
            veto_enabled      = getattr(config, 'ai_veto_enabled', True),
        )
        self._daily_pnl     = 0.0
        self._open_positions: Dict[str, dict] = {}
        self._portfolio_risk = 0.0
        self._regime_detector   = MarketRegimeDetector()
        self._momentum_detector = MomentumOverrideDetector()
        self._current_regime    = None

    # ------------------------------------------------------------------
    # State management (called by the main agent loop)
    # ------------------------------------------------------------------

    def update_portfolio_state(
        self,
        daily_pnl:       float,
        open_positions:  Dict[str, dict],
        portfolio_value: float,
        spy_week_change: float = 0.0,
        market_regime:  str   = 'UNKNOWN',
    ):
        """Update live portfolio state before each scan cycle."""
        self._daily_pnl      = daily_pnl
        self._open_positions = open_positions
        self._portfolio_risk = sum(
            p.get("max_loss", 0) for p in open_positions.values()
        )
        self.guardian.update_state(
            daily_pnl       = daily_pnl,
            open_count      = len(open_positions),
            portfolio_risk  = self._portfolio_risk,
            portfolio_value = portfolio_value,
            spy_week_change = spy_week_change,
            market_regime   = market_regime,
        )

    # ------------------------------------------------------------------
    # Core decision logic
    # ------------------------------------------------------------------

    def decide(
        self,
        symbol:          str,
        df:              pd.DataFrame,
        report:          StrategyReport,
        portfolio_value: float,
        earnings_date:   Optional[datetime] = None,
    ) -> TradeDecision:
        """
        Make a fully autonomous trade decision for one symbol.

        Args:
            symbol:          Ticker
            df:              OHLCV DataFrame (for price reference)
            report:          StrategyReport from Layer 3
            portfolio_value: Current total portfolio value
            earnings_date:   Next earnings date (for blackout check)

        Returns:
            TradeDecision — Layer 5 executor acts on this
        """
        timestamp = datetime.now(timezone.utc)
        price     = float(df["close"].iloc[-1])
        cfg       = self.config

        # --- Already in this position? ---
        if symbol in self._open_positions and report.recommendation in ("BUY", "STRONG BUY"):
            return self._make_decision(
                symbol, "HOLD", False, report, price, None, None,
                timestamp, ["Already holding this position"], portfolio_value
            )

        # --- Gate 1: Enough strategies agree? ---
        dominant_action, signal_count = self._dominant_action(report)
        if dominant_action == "HOLD" or signal_count < cfg.min_strategies_agree:
            return self._make_decision(
                symbol, "HOLD", False, report, price, None, None,
                timestamp,
                [f"Only {signal_count} strategies agree (need {cfg.min_strategies_agree})"],
                portfolio_value
            )

        # --- Gate 2: Enhanced conviction score ---
        # Layer 1 — regime-aware base threshold
        _regime_threshold = (self._current_regime.thresholds.conviction
                             if self._current_regime else cfg.min_conviction_score)

        # Micro Momentum regime cap — scalping can't clear swing-trade thresholds.
        # RANGING=2.5 is calibrated for V1 swing trades; V2 raw scores max ~1.8.
        # Cap to cfg.min_conviction_score + 0.3. V1 Profit Maximizer unaffected.
        # Detect Micro Momentum approach once — used by regime cap, NEUTRAL block, ADX filter
        _is_micro_mm = False
        try:
            _approach_val = getattr(cfg, 'approach', '')
            _approach_str = _approach_val.value if hasattr(_approach_val, 'value') else str(_approach_val)
            _is_micro_mm  = _approach_str.lower() in ('micro momentum', 'micro_momentum')
        except Exception:
            pass

        # Micro Momentum regime cap — scalping can't clear swing-trade thresholds.
        # RANGING=2.5 is calibrated for V1 swing trades; V2 raw scores max ~1.8.
        # Cap to cfg.min_conviction_score + 0.3. V1 Profit Maximizer unaffected.
        if _is_micro_mm:
            _micro_cap = cfg.min_conviction_score + 0.3
            if _regime_threshold > _micro_cap:
                logger.debug(
                    f"[Engine] Micro Momentum regime cap: {_regime_threshold:.1f} "
                    f"-> {_micro_cap:.1f} (floor {cfg.min_conviction_score:.1f} + 0.3)"
                )
                _regime_threshold = _micro_cap

        # TREND CLASSIFICATION — dynamic per-stock trend state
        # Replaces the fixed high_loss_symbols list.
        # Classifies every stock as UPTREND / DOWNTREND / NEUTRAL before entry.
        # DOWNTREND stocks are always blocked regardless of conviction score.
        if report.recommendation in ("BUY", "STRONG BUY"):
            try:
                import math
                close   = df["close"]
                price   = float(close.iloc[-1])
                ma5     = float(close.rolling(5).mean().iloc[-1])
                ma20    = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else ma5

                # ── Trend direction score (-3 to +3) ─────────────────
                trend_score = 0

                # 1. Price vs MAs
                if price > ma20:  trend_score += 1
                else:             trend_score -= 1
                if price > ma5:   trend_score += 1
                else:             trend_score -= 1

                # 2. Recent price direction — last 10 closes for multi-day trend reliability
                if len(close) >= 11:
                    recent = close.iloc[-11:].values
                    up_days   = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
                    down_days = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i-1])
                    if up_days >= 7:     trend_score += 1   # 7+ up days in last 10 = strong uptrend
                    elif down_days >= 6: trend_score -= 1   # 6+ down days = clear downtrend

                # 3. 10-day price change direction (catches multi-day slides like ORCL)
                if len(close) >= 11:
                    price_10d_ago = float(close.iloc[-11])
                    ten_day_chg   = (price - price_10d_ago) / price_10d_ago if price_10d_ago > 0 else 0
                    if ten_day_chg <= -0.05:  trend_score -= 1  # down 5%+ over 10 days = downtrend
                    elif ten_day_chg >= 0.05: trend_score += 1  # up 5%+ over 10 days = uptrend

                # ── Classify ──────────────────────────────────────────
                if trend_score >= 2:
                    trend_state = "UPTREND"
                elif trend_score <= -1:
                    trend_state = "DOWNTREND"
                else:
                    trend_state = "NEUTRAL"

                # ── Block DOWNTREND entries always ────────────────────
                if trend_state == "DOWNTREND" and not math.isnan(ma5):
                    return self._make_decision(
                        symbol, df, report, cfg,
                        action="HOLD",
                        reason=f"{symbol} DOWNTREND (score={trend_score}) — price ${price:.2f} vs MA5 ${ma5:.2f} MA20 ${ma20:.2f}. Blocked.",
                    )

                # ── Block NEUTRAL entries in RANGING market ───────
                # Exception: Micro Momentum scalps don't need a confirmed swing trend.
                # A 0.5% TP trade works on NEUTRAL stocks — the regime cap above guards entry bar.
                regime_name = self._current_regime.regime if self._current_regime else "UNKNOWN"
                if trend_state == "NEUTRAL" and regime_name == "RANGING" and not _is_micro_mm:
                    return self._make_decision(
                        symbol, df, report, cfg,
                        action="HOLD",
                        reason=f"{symbol} NEUTRAL trend in RANGING market — waiting for clear direction",
                    )

                # Store trend state for dashboard display
                if not hasattr(self, '_trend_states'):
                    self._trend_states = {}
                self._trend_states[symbol] = trend_state

                # Log uptrend confirmation
                if trend_state == "UPTREND":
                    logger.debug(f"[Engine] {symbol} UPTREND confirmed (score={trend_score}) — entry approved")

            except Exception as _te:
                logger.debug(f"[Engine] {symbol} trend classification failed: {_te}")

        # Fix 3: RANGING regime individual stock trend filter
        # In a RANGING market, only enter if the individual stock itself is trending (ADX > 20)
        # This prevents entering choppy stocks that bounce around without direction
        if (self._current_regime and self._current_regime.regime == "RANGING"
                and report.recommendation in ("BUY", "STRONG BUY")):
            try:
                import pandas as pd
                high  = df["high"]  if "high"  in df.columns else df["close"]
                low   = df["low"]   if "low"   in df.columns else df["close"]
                close = df["close"]
                tr    = pd.concat([
                    high - low,
                    (high - close.shift(1)).abs(),
                    (low  - close.shift(1)).abs()
                ], axis=1).max(axis=1)
                atr14 = tr.rolling(14).mean()
                plus_dm  = (high.diff()).clip(lower=0)
                minus_dm = (-low.diff()).clip(lower=0)
                plus_di  = 100 * plus_dm.rolling(14).mean()  / atr14.replace(0, float('nan'))
                minus_di = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, float('nan'))
                dx       = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float('nan')))
                adx      = dx.rolling(14).mean().iloc[-1]
                # Micro Momentum uses a lower ADX floor — scalping doesn't need
                # the sustained directional trend ADX>20 measures.
                _adx_floor = 12 if _is_micro_mm else 20
                if not pd.isna(adx) and adx < _adx_floor:
                    return self._make_decision(
                        symbol, df, report, cfg,
                        action = "HOLD",
                        reason = f"RANGING market + {symbol} ADX={adx:.1f}<{_adx_floor} (no trend) — skipping entry",
                    )
                logger.debug(f"[Engine] {symbol} ADX={adx:.1f} — trend confirmed in RANGING market")
            except Exception as _e:
                logger.debug(f"[Engine] {symbol} ADX filter failed: {_e}")

        # Layer 1b — UPTREND discount: confirmed uptrend lowers bar to enter
        # UPTREND stocks in RANGING market: lower both conviction threshold AND min strategies
        _uptrend_active = False
        try:
            _trend_now = self._trend_states.get(symbol, "UNKNOWN") if hasattr(self, "_trend_states") else "UNKNOWN"
            if _trend_now == "UPTREND":
                _uptrend_active = True
                if _regime_threshold > 1.8:
                    _regime_threshold = max(1.5, _regime_threshold - 1.0)
                    logger.info(f"[Engine] {symbol} UPTREND — conviction threshold lowered to {_regime_threshold:.1f}")
        except Exception:
            pass

        # Layer 2 — per-stock momentum override (takes it lower if stock is rallying)
        _momentum = self._momentum_detector.analyse(symbol, df)
        if _momentum.override_active:
            _final_conv_threshold = min(_regime_threshold, _momentum.conviction_floor)
            _final_conf_threshold = min(
                self._current_regime.thresholds.confidence if self._current_regime else cfg.confidence_threshold,
                _momentum.confidence_floor
            )
            _final_min_strats = min(cfg.min_strategies_agree, _momentum.min_strategies)
            logger.info(f"[Override] {symbol} | {_momentum.reason} | "
                        f"conv>={_final_conv_threshold} conf>={_final_conf_threshold:.0%} strats>={_final_min_strats}")
        else:
            _final_conv_threshold = _regime_threshold
            _final_conf_threshold = (self._current_regime.thresholds.confidence
                                     if self._current_regime else cfg.confidence_threshold)
            # UPTREND stocks need fewer strategy agreements (1 instead of 2)
            _final_min_strats = max(1, cfg.min_strategies_agree - 1) if _uptrend_active else cfg.min_strategies_agree

        _conv_engine = EnhancedConvictionEngine(threshold=_final_conv_threshold)
        _breakdown   = _conv_engine.score(
            symbol         = symbol,
            df             = df,
            strategy_score = report.conviction_score,
            news_sentiment = getattr(cfg, '_news_cache', {}).get(symbol),
            analyst_data   = getattr(cfg, '_analyst_cache', {}).get(symbol),
        )
        _enhanced_score = _breakdown.final_score

        if _enhanced_score < cfg.min_conviction_score:
            return self._make_decision(
                symbol, "HOLD", False, report, price, None, None,
                timestamp,
                [f"Conviction {_enhanced_score:+.2f} below threshold {cfg.min_conviction_score:+.1f} ({_breakdown.summary()})"],
                portfolio_value
            )

        # --- Gate 3: Average confidence high enough? ---
        if report.avg_confidence < _final_conf_threshold:
            return self._make_decision(
                symbol, "HOLD", False, report, price, None, None,
                timestamp,
                [f"Avg confidence {report.avg_confidence:.0%} below threshold {cfg.confidence_threshold:.0%}"],
                portfolio_value
            )

        # --- Gates passed: size the position ---
        position = self.sizer.calculate(
            symbol          = symbol,
            price           = price,
            confidence      = report.avg_confidence,
            portfolio_value = portfolio_value,
            current_risk    = self._portfolio_risk,
        )

        if not position.is_valid:
            return self._make_decision(
                symbol, "HOLD", False, report, price, position, None,
                timestamp, ["Position size too small after risk limits"],
                portfolio_value
            )

        # --- Gate 4: RiskGuardian ---
        risk = self.guardian.assess(symbol, dominant_action, position, earnings_date)

        if not risk.approved:
            block_reasons = [c.reason for c in risk.blocking]
            return self._make_decision(
                symbol, "BLOCKED", False, report, price, position, risk,
                timestamp, block_reasons, portfolio_value
            )

        # --- Gate 5: AI Reviewer ---
        verdict = self.reviewer.review(
            symbol           = symbol,
            action           = dominant_action,
            conviction_score = report.conviction_score,
            strategies_fired = [s.strategy for s in report.signals if s.action.value == dominant_action],
            top_reasons      = [s.reason for s in report.signals if s.action.value == dominant_action][:3],
            buy_signals      = report.buy_count,
            sell_signals     = report.sell_count,
            price            = price,
            stop_loss        = position.stop_loss,
            take_profit      = position.take_profit,
            shares           = position.shares,
            dollar_amount    = position.dollar_amount,
            portfolio_value  = portfolio_value,
            open_positions   = self._open_positions,
            df               = df,
        )

        if not verdict.approved and verdict.used_ai:
            decision = self._make_decision(
                symbol, "BLOCKED", False, report, price, position, risk,
                timestamp,
                [f"AI reviewer vetoed: {verdict.reasoning}"],
                portfolio_value,
            )
            decision.ai_approved   = False
            decision.ai_confidence = verdict.confidence
            decision.ai_reasoning  = verdict.reasoning
            decision.ai_concerns   = verdict.concerns
            decision.ai_suggestion = verdict.suggestion
            decision.ai_used       = verdict.used_ai
            return decision

        # --- AI Confidence-Based Position Sizing ---
        # Scale position size by AI confidence so high-confidence trades get full size
        # and borderline approvals (just above 0.60 veto threshold) get reduced size.
        if verdict.used_ai and verdict.approved:
            ai_conf = verdict.confidence
            if ai_conf >= 0.85:
                size_scale = 1.0          # full size — AI very confident
            elif ai_conf >= 0.75:
                size_scale = 0.75         # 75% size — AI confident
            elif ai_conf >= 0.65:
                size_scale = 0.50         # 50% size — AI borderline
            else:
                size_scale = 0.35         # 35% size — AI barely approved
            if size_scale < 1.0:
                original_shares = position.shares
                position.shares       = max(1, int(position.shares * size_scale))
                position.dollar_amount = position.shares * price
                logger.info(
                    f"[Engine] {symbol} AI confidence {ai_conf:.0%} → "
                    f"size scaled {size_scale:.0%}: "
                    f"{original_shares} → {position.shares} shares "
                    f"(${position.dollar_amount:,.0f})"
                )

        # --- All gates passed: TRADE ---
        decision = self._make_decision(
            symbol, dominant_action, True, report, price, position, risk,
            timestamp, [], portfolio_value,
        )
        decision.ai_approved   = verdict.approved
        decision.ai_confidence = verdict.confidence
        decision.ai_reasoning  = verdict.reasoning
        decision.ai_concerns   = verdict.concerns
        decision.ai_suggestion = verdict.suggestion
        decision.ai_used       = verdict.used_ai
        return decision

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dominant_action(self, report: StrategyReport):
        """Return the dominant action and how many strategies support it."""
        if report.buy_count > report.sell_count:
            return "BUY", report.buy_count
        elif report.sell_count > report.buy_count:
            return "SELL", report.sell_count
        return "HOLD", 0

    def _make_decision(
        self, symbol, action, approved, report, price,
        position, risk, timestamp, extra_blocks, portfolio_value
    ) -> TradeDecision:
        """Construct TradeDecision, log it, and return it."""
        cfg = self.config

        # Gather top reasons from best strategies
        actionable = [s for s in report.signals
                      if s.action.value == action and s.action.value != "HOLD"]
        actionable.sort(key=lambda s: -s.confidence)
        top_reasons      = [s.reason for s in actionable[:3]]
        strategies_fired = [s.strategy for s in actionable]
        # Full per-strategy signal breakdown for dashboard vote panel
        all_strategy_signals = [
            {
                "strategy":   s.strategy,
                "action":     s.action.value,
                "confidence": round(s.confidence, 3),
                "reason":     s.reason[:80] if s.reason else "",
            }
            for s in report.signals
        ]

        decision = TradeDecision(
            symbol           = symbol,
            timestamp        = timestamp,
            action           = action,
            approved         = approved,
            shares           = position.shares        if position else 0,
            dollar_amount    = position.dollar_amount if position else 0,
            stop_loss        = position.stop_loss     if position else 0,
            take_profit      = position.take_profit   if position else 0,
            risk_reward      = position.risk_reward   if position else 0,
            conviction_score = report.conviction_score,
            avg_confidence   = report.avg_confidence,
            buy_signals      = report.buy_count,
            sell_signals     = report.sell_count,
            top_reasons      = top_reasons or extra_blocks,
            strategies_fired = strategies_fired,
            block_reasons    = extra_blocks + ([c.reason for c in risk.blocking] if risk else []),
            approach         = (cfg.approach.value if hasattr(cfg.approach, "value") else cfg.approach),
            paper_trade      = cfg.paper_trading,
        )

        # Log every decision
        if cfg.decision_logging:
            record = DecisionRecord(
                timestamp        = timestamp.isoformat(),
                symbol           = symbol,
                action           = action,
                approach         = (cfg.approach.value if hasattr(cfg.approach, "value") else cfg.approach),
                conviction_score = report.conviction_score,
                buy_signals      = report.buy_count,
                sell_signals     = report.sell_count,
                avg_confidence   = report.avg_confidence,
                strategies_fired = strategies_fired,
                strategy_signals = all_strategy_signals,
                top_reasons      = top_reasons or extra_blocks,
                risk_approved    = approved,
                risk_blocks      = decision.block_reasons,
                position_shares  = decision.shares,
                position_dollars = decision.dollar_amount,
                stop_loss        = decision.stop_loss,
                take_profit      = decision.take_profit,
                risk_reward      = decision.risk_reward,
                portfolio_value  = portfolio_value,
                paper_trade      = cfg.paper_trading,
                ai_approved      = decision.ai_approved,
                ai_confidence    = decision.ai_confidence,
                ai_reasoning     = decision.ai_reasoning,
                ai_concerns      = decision.ai_concerns,
                ai_used          = decision.ai_used,
            )
            self.logger.log(record)

        return decision

    # ------------------------------------------------------------------
    # Scan cycle — runs all symbols in one pass
    # ------------------------------------------------------------------

    def scan_watchlist(
        self,
        watchlist_data:   Dict[str, pd.DataFrame],
        strategy_reports: Dict[str, StrategyReport],
        portfolio_value:  float,
    ) -> List[TradeDecision]:
        """
        Run the decision engine across the entire watchlist.
        Called by the main agent loop every scan_interval_minutes.

        Returns list of TradeDecisions sorted by conviction (strongest first).
        """
        # Detect market regime once per scan using SPY data
        spy_df = watchlist_data.get("SPY")
        if spy_df is None or (hasattr(spy_df, "empty") and spy_df.empty):
            spy_df = next(iter(watchlist_data.values()), None)
        self._current_regime = self._regime_detector.detect(spy_df) if spy_df is not None else None

        decisions = []
        for symbol, df in watchlist_data.items():
            report = strategy_reports.get(symbol)
            if report is None:
                continue
            try:
                decision = self.decide(symbol, df, report, portfolio_value)
                decisions.append(decision)
            except Exception as exc:
                logger.error(f"[DecisionEngine] {symbol} failed: {exc}")

        # Sort: actionable trades first, then by conviction
        decisions.sort(
            key=lambda d: (0 if d.action in ("BUY","SELL") else 1, -d.conviction_score)
        )

        actionable = [d for d in decisions if d.action in ("BUY","SELL")]
        logger.info(
            f"[DecisionEngine] Scan complete: "
            f"{len(actionable)} actionable / {len(decisions)} total symbols"
        )
        return decisions
