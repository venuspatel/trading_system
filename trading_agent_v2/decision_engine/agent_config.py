# -*- coding: utf-8 -*-
"""
AgentConfig — the single configuration object that drives ALL decisions.
Set once at launch (via the interactive UI), readable by every component.
Can be updated live mid-session without restarting the agent.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import json, os


class Approach(Enum):
    CONSERVATIVE      = "Conservative"
    BALANCED          = "Balanced"
    AGGRESSIVE        = "Aggressive"
    PROFIT_MAXIMIZER  = "Profit Maximizer"
    LONG_TERM         = "Long Term"
    MICRO_MOMENTUM    = "Micro Momentum"


class SizingMethod(Enum):
    KELLY       = "Kelly Criterion"
    FIXED       = "Fixed Fractional"
    CONFIDENCE  = "Confidence-Scaled"


@dataclass
class AgentConfig:
    """
    Complete runtime configuration for the autonomous agent.
    Every decision the agent makes references this object.

    Defaults represent a safe, balanced starting point.
    The interactive UI and AI recommender populate this at launch.
    """

    # ── Intraday mode ─────────────────────────────────────────
    intraday_mode:         bool          = True    # 2-min scans + auto-close 3:45 PM (always on by default)
    max_trades_per_symbol: int           = 9999   # max trades per symbol per day (unlimited by default)
    trade_cooldown_minutes:int           = 0      # minutes to wait between trades on same symbol
    consecutive_loss_limit:int           = 3      # pause after N consecutive losses
    consecutive_loss_pause_hours: int    = 2      # hours to pause after consecutive loss limit
    daily_profit_target_pct: float       = 0.0    # stop trading when daily profit hits this % (0=disabled)
    max_trades_per_day:    int           = 9999   # max trades per day (unlimited by default)
    intraday_interval_min: int           = 2       # scan interval in intraday mode

    # ── Identity ──────────────────────────────────────────────
    approach:              Approach      = Approach.BALANCED
    user_goal:             str           = "Grow capital steadily"
    market:                str           = "US stocks"

    # ── Strategy gate ─────────────────────────────────────────
    min_strategies_agree:  int           = 3      # minimum BUY/SELL signals needed
    confidence_threshold:  float         = 0.65   # minimum avg confidence to trade
    min_conviction_score:  float         = 2.0    # minimum StrategyReport conviction

    # ── Position sizing ───────────────────────────────────────
    sizing_method:         SizingMethod  = SizingMethod.CONFIDENCE
    max_position_pct:      float         = 0.10   # max 10% of portfolio per position
    max_open_positions:    int           = 3
    kelly_fraction:        float         = 0.5    # half-Kelly (safer than full Kelly)

    # ── Risk limits ───────────────────────────────────────────
    stop_loss_pct:         float         = 0.03   # 3% stop loss per trade
    take_profit_pct:       float         = 0.06   # 6% take profit (2:1 R:R)
    min_risk_reward:       float         = 2.0    # reject trades below 2:1
    max_portfolio_risk_pct: float        = 0.05   # max 5% total portfolio at risk
    daily_loss_limit_pct:  float         = 0.03   # pause if down 3% in a day

    # ── Trading frequency ─────────────────────────────────────
    # Scan timing is now handled by MarketScheduler (market-aware).
    # Conservative -> EOD only (4:05pm ET)
    # Balanced     -> Pre-market + EOD (8:30am + 4:05pm ET)
    # Aggressive   -> Hourly intraday (every completed 1H bar, 9:30-16:00 ET)
    scan_interval_minutes: int           = 0      # deprecated - use MarketScheduler
    trading_timeframe:     str           = "1Day" # bar timeframe for analysis

    # ── Safeguards ────────────────────────────────────────────
    paper_trading:         bool          = True   # ALWAYS start in paper mode
    market_hours_only:     bool          = True   # no pre/post market trading
    earnings_blackout_days: int          = 3      # avoid N days before earnings
    market_crash_threshold: float        = 0.05   # pause if SPY down 5% in a week
    regime_filter:         bool          = True   # only trade in right regime

    # ── Watchlist ─────────────────────────────────────────────
    watchlist:             List[str]     = field(
        default_factory=lambda: ["AAPL","TSLA","NVDA","MSFT","AMZN"]
    )

    # ── Enabled strategies ────────────────────────────────────
    enabled_strategies:    List[str]     = field(default_factory=lambda: [
        "Momentum", "MeanReversion", "Breakout",
        "CandleReversal", "CandleContinuation",
        "Divergence", "Fibonacci", "VolumeConfirmation",
        "MultiTimeframe", "TrendRegime",
        "TrendStrength", "EarningsMomentum",
    ])

    # ── Exit intelligence ─────────────────────────────────────
    trailing_stop:         bool          = False   # enable trailing stop
    trailing_stop_pct:     float         = 0.015   # 1.5% trail from peak
    partial_profit_pct:    float         = 0.015   # trigger partial sell at +1.5%
    partial_profit_ratio:  float         = 0.50    # sell 50% at partial trigger
    momentum_exit:         bool          = False   # exit on conviction drop
    candle_exit:           bool          = False   # exit on reversal candle
    max_hold_days:         int           = 0       # 0 = unlimited hold

    # ── Logging ───────────────────────────────────────────────
    decision_logging:      bool          = True
    log_path:              str           = "logs/decisions.jsonl"

    # ------------------------------------------------------------------
    # Approach presets — AI recommender calls these
    # ------------------------------------------------------------------

    def apply_conservative(self):
        self.approach             = Approach.CONSERVATIVE
        self.min_strategies_agree = 5
        self.confidence_threshold = 0.75
        self.min_conviction_score = 4.0
        self.max_position_pct     = 0.05
        self.max_open_positions   = 2
        self.stop_loss_pct        = 0.02
        self.take_profit_pct      = 0.05
        self.max_portfolio_risk_pct = 0.03
        self.daily_loss_limit_pct = 0.02
        self.scan_interval_minutes  = 0
        self.scan_frequency_minutes = 0
        self.trading_timeframe      = "1Day"
        self.max_trades_per_day     = 3
        self.max_consecutive_losses = 2
        self.cooldown_minutes       = 120
        self.profit_lock_pct        = 0.02
        self.weekly_loss_limit_pct  = 0.05

    def apply_balanced(self):
        self.approach             = Approach.BALANCED
        self.min_strategies_agree = 3
        self.confidence_threshold = 0.65
        self.min_conviction_score = 2.0
        self.max_position_pct     = 0.10
        self.max_open_positions   = 3
        self.stop_loss_pct        = 0.03
        self.take_profit_pct      = 0.06
        self.max_portfolio_risk_pct = 0.05
        self.daily_loss_limit_pct = 0.03
        self.scan_interval_minutes = 0    # Pre-mkt + EOD — MarketScheduler handles timing
        self.trading_timeframe      = "1Day"

    def apply_micro_momentum(self):
        """
        Micro Momentum — scalping mode, very tight stops, fast entries.
        Low conviction threshold, single strategy confirmation enough.
        Target: +0.5% per trade, many trades per day.
        """
        self.approach             = Approach.MICRO_MOMENTUM if hasattr(Approach, 'MICRO_MOMENTUM') else Approach.BALANCED
        self.min_strategies_agree = 1       # single strategy enough
        self.confidence_threshold = 0.55    # lower bar — scalping needs fast entries
        self.min_conviction_score = 1.5     # low threshold for micro moves
        self.max_position_pct     = 0.10
        self.max_open_positions   = 10
        self.stop_loss_pct        = 0.0025  # 0.25% tight stop
        self.take_profit_pct      = 0.005   # 0.5% quick target
        self.trailing_stop        = False
        self.trailing_stop_pct    = 0.0025
        self.max_portfolio_risk_pct = 0.10
        self.daily_loss_limit_pct = 0.05
        self.scan_interval_minutes = 1
        self.trading_timeframe     = "15Min"

    def apply_profit_maximizer(self):
        """
        Profit Maximizer — short-term, high-frequency, max profit extraction.
        Uses trailing stops, candlestick exits, momentum exits, hourly scans.
        Target: +1.5-3% per trade, 10-20 trades/week.
        """
        self.approach              = Approach.PROFIT_MAXIMIZER
        self.min_strategies_agree  = 3
        self.confidence_threshold  = 0.65
        self.min_conviction_score  = 2.5
        self.max_position_pct      = 0.12
        self.max_open_positions    = 5
        # Tight risk, quick profit
        self.stop_loss_pct         = 0.01   # 1% stop — matches saved config
        self.take_profit_pct       = 0.03   # 3% target — matches saved config
        self.min_risk_reward       = 1.5
        self.max_portfolio_risk_pct = 0.08
        self.daily_loss_limit_pct  = 0.04
        # Trailing stop — core feature of this mode
        self.trailing_stop         = True
        self.trailing_stop_pct     = 0.01   # trail 1% from peak — matches stop_loss_pct
        # Partial profit lock
        self.partial_profit_pct    = 0.015  # sell half at +1.5%
        self.partial_profit_ratio  = 0.50
        # Smart exits
        self.momentum_exit         = True   # exit when momentum weakens
        self.candle_exit           = True   # exit on shooting star/bearish engulfing
        self.max_hold_days         = 2      # max 2 days hold
        # Smart trade frequency
        self.max_trades_per_day      = 6     # max 6 trades per day
        self.max_trades_per_symbol   = 2     # max 2 per symbol
        self.trade_cooldown_minutes  = 30    # 30 min cooldown
        self.consecutive_loss_limit  = 2     # pause after 2 straight losses
        self.consecutive_loss_pause_hours = 2.0
        self.daily_profit_target_pct = 0.03  # stop at +3% daily profit
        # Hourly scans
        self.scan_interval_minutes = 0      # MarketScheduler handles hourly
        self.trading_timeframe     = "1Day"
        self.user_goal             = "Maximize short-term profits with quick in/out trades"
        self.scan_frequency_minutes = 10
        self.max_trades_per_day     = 10
        self.max_consecutive_losses = 3
        self.cooldown_minutes       = 45
        self.profit_lock_pct        = 0.03
        self.weekly_loss_limit_pct  = 0.10

    def apply_long_term(self):
        """
        Long Term — patient, high-conviction, fundamental + technical.
        Uses wide stops, staged profit taking, weekly candle confirmation.
        Target: +15-25% per trade, 1-3 trades/week.
        """
        self.approach              = Approach.LONG_TERM
        self.min_strategies_agree  = 6
        self.confidence_threshold  = 0.80
        self.min_conviction_score  = 4.0
        self.max_position_pct      = 0.15
        self.max_open_positions    = 4
        # Wide risk, big target
        self.stop_loss_pct         = 0.07   # 7% wide stop
        self.take_profit_pct       = 0.20   # 20% target
        self.min_risk_reward       = 2.5
        self.max_portfolio_risk_pct = 0.05
        self.daily_loss_limit_pct  = 0.05
        # No trailing (let winners run)
        self.trailing_stop         = False
        self.partial_profit_pct    = 0.10   # take partial at +10%
        self.partial_profit_ratio  = 0.30   # sell only 30%, keep 70% running
        self.momentum_exit         = False  # don't exit on short-term weakness
        self.candle_exit           = False  # ignore daily candles
        self.max_hold_days         = 0      # hold as long as needed
        self.max_trades_per_day      = 2     # max 2 trades per day
        self.max_trades_per_symbol   = 1     # only buy a symbol once per day
        self.trade_cooldown_minutes  = 60    # 60 min cooldown
        self.consecutive_loss_limit  = 2
        self.consecutive_loss_pause_hours = 24.0  # pause a full day after losses
        self.daily_profit_target_pct = 0.0   # no daily target - hold for big moves
        # EOD only — no overtrading
        self.scan_interval_minutes = 0
        self.trading_timeframe     = "1Day"
        self.user_goal             = "Build long-term wealth with high-conviction positions"
        self.scan_frequency_minutes = 0
        self.max_trades_per_day     = 2
        self.max_consecutive_losses = 2
        self.cooldown_minutes       = 240
        self.profit_lock_pct        = 0.05
        self.weekly_loss_limit_pct  = 0.08

    def apply_aggressive(self):
        self.approach             = Approach.AGGRESSIVE
        self.min_strategies_agree = 2
        self.confidence_threshold = 0.55
        self.min_conviction_score = 1.5
        self.max_position_pct     = 0.20
        self.max_open_positions   = 5
        self.stop_loss_pct        = 0.05
        self.take_profit_pct      = 0.10
        self.max_portfolio_risk_pct = 0.10
        self.daily_loss_limit_pct = 0.05
        self.scan_interval_minutes  = 0
        self.scan_frequency_minutes = 30
        self.trading_timeframe      = "1Day"
        self.max_trades_per_day     = 8
        self.max_consecutive_losses = 4
        self.cooldown_minutes       = 30
        self.profit_lock_pct        = 0.05
        self.weekly_loss_limit_pct  = 0.12

    # ------------------------------------------------------------------
    # Serialization — save/load config to JSON
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "approach":               (self.approach.value if hasattr(self.approach, "value") else self.approach),
            "user_goal":              self.user_goal,
            "market":                 self.market,
            "min_strategies_agree":   self.min_strategies_agree,
            "confidence_threshold":   self.confidence_threshold,
            "min_conviction_score":   self.min_conviction_score,
            "sizing_method":          (self.sizing_method.value if hasattr(self.sizing_method, "value") else self.sizing_method),
            "max_position_pct":       self.max_position_pct,
            "max_open_positions":     self.max_open_positions,
            "stop_loss_pct":          self.stop_loss_pct,
            "take_profit_pct":        self.take_profit_pct,
            "min_risk_reward":        self.min_risk_reward,
            "max_portfolio_risk_pct": self.max_portfolio_risk_pct,
            "daily_loss_limit_pct":   self.daily_loss_limit_pct,
            "scan_interval_minutes":  self.scan_interval_minutes,
            "paper_trading":          self.paper_trading,
            "market_hours_only":      self.market_hours_only,
            "earnings_blackout_days": self.earnings_blackout_days,
            "regime_filter":          self.regime_filter,
            "watchlist":              self.watchlist,
            "enabled_strategies":     self.enabled_strategies,
            "decision_logging":       self.decision_logging,
            "max_trades_per_day":      self.max_trades_per_day,
            "max_trades_per_symbol":   self.max_trades_per_symbol,
            "trade_cooldown_minutes":  self.trade_cooldown_minutes,
            "consecutive_loss_limit":  self.consecutive_loss_limit,
            "consecutive_loss_pause_hours": self.consecutive_loss_pause_hours,
            "daily_profit_target_pct": self.daily_profit_target_pct,
            "trailing_stop":           self.trailing_stop,
            "trailing_stop_pct":      self.trailing_stop_pct,
            "partial_profit_pct":     self.partial_profit_pct,
            "partial_profit_ratio":   self.partial_profit_ratio,
            "momentum_exit":          self.momentum_exit,
            "candle_exit":            self.candle_exit,
            "max_hold_days":          self.max_hold_days,
        }

    def save(self, path: str = "config/agent_config.json"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str = "config/agent_config.json") -> "AgentConfig":
        with open(path) as f:
            d = json.load(f)
        cfg = cls()
        for k, v in d.items():
            if k == "approach":
                setattr(cfg, k, Approach(v))
            elif k == "sizing_method":
                setattr(cfg, k, SizingMethod(v))
            elif hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    def __str__(self):
        _approach_str = self.approach.value if hasattr(self.approach, 'value') else self.approach
        return (
            f"AgentConfig [{_approach_str}] | "
            f"min_strategies={self.min_strategies_agree} | "
            f"confidence={self.confidence_threshold:.0%} | "
            f"max_positions={self.max_open_positions} | "
            f"paper={self.paper_trading}"
        )
