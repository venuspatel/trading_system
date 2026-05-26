# -*- coding: utf-8 -*-
"""
TradingAgent  — the autonomous main loop
-----------------------------------------
This is the heart of the agent. It runs continuously,
waking up every scan_interval_minutes to:

  1. Fetch latest market data (Layer 1)
  2. Run all indicators (Layer 2)
  3. Run all strategies (Layer 3)
  4. Make decisions (Layer 4)
  5. Execute trades (Layer 5 — stub for now, wired in next layer)
  6. Log everything for the dashboard

The agent exposes a simple API so the web dashboard (Layer 7)
can start/stop/reconfigure it at any time.
"""

import logging
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

from .agent_config    import AgentConfig
from .market_scheduler import MarketScheduler, is_market_open, is_trading_day
from .engine          import DecisionEngine, TradeDecision
from data_layer       import DataManager, AlpacaProvider
from execution        import AlpacaExecutor, PortfolioTracker
from .trailing_stop       import TrailingStopManager, ExitSignal
from .adaptive_thresholds import AdaptiveThresholdEngine
from .strategy_ranker     import StrategyRanker          # has record_trade()
from .kelly_sizer         import KellySizer
# StockScanner imported lazily in __init__ to avoid circular imports
from .discipline      import TradingDiscipline, DisciplineConfig, TickerCooldown
from performance      import PerformanceAnalyzer, StrategyRanker as PerfStrategyRanker, DailyReportGenerator
from indicators       import IndicatorEngine
from strategies       import StrategyEngine

logger = logging.getLogger(__name__)


class AgentStatus:
    IDLE      = "idle"
    RUNNING   = "running"
    PAUSED    = "paused"
    STOPPED   = "stopped"
    ERROR     = "error"


class TradingAgent:
    """
    The fully autonomous trading agent.

    Usage:
        config = AgentConfig()
        config.apply_balanced()

        agent = TradingAgent(config)
        agent.start()          # starts the autonomous loop
        # ... agent runs on its own ...
        agent.pause()          # pause without losing state
        agent.reconfigure(new_config)  # change settings live
        agent.stop()           # clean shutdown
    """

    def __init__(self, config: AgentConfig):
        self.config        = config
        self.status        = AgentStatus.IDLE
        self._thread       : Optional[threading.Thread] = None
        self._stop_event   = threading.Event()
        self._pause_event  = threading.Event()
        self._scan_lock          = threading.Lock()  # prevent concurrent scans
        self._pending_buys: set  = set()          # symbols bought, not yet in Alpaca

        # Layers
        self._data_manager : Optional[DataManager]    = None
        self._ind_engine   = IndicatorEngine()
        # Safely extract approach string regardless of type (Enum, str, None)
        try:
            approach_str = config.approach.value
        except AttributeError:
            approach_str = str(config.approach) if config.approach else "Balanced"
        self._str_engine   = StrategyEngine(approach=approach_str)
        self._dec_engine   = DecisionEngine(config)
        self._executor     : Optional[AlpacaExecutor]  = None
        # Use separate portfolio file per agent instance
        import os as _os
        _portfolio_file = _os.environ.get("PORTFOLIO_FILE", "logs/portfolio.json")
        self._portfolio    = PortfolioTracker(data_path=_portfolio_file)
        # Auto-heal P&L offset against Alpaca ground truth on every startup
        import os as _os2
        _alpaca_key = _os2.getenv("ALPACA_API_KEY", _os2.getenv("APCA_API_KEY_ID", ""))
        _alpaca_sec = _os2.getenv("ALPACA_SECRET_KEY", _os2.getenv("APCA_API_SECRET_KEY", ""))
        if _alpaca_key and _alpaca_sec:
            self._portfolio.set_alpaca_credentials(
                api_key    = _alpaca_key,
                secret_key = _alpaca_sec,
                paper      = getattr(config, "paper_trading", True),
            )
            self._portfolio.sync_eod_from_alpaca()  # Fix A: inject missing EOD trades
        self._trailing_mgr  = TrailingStopManager(config)
        self._adaptive      = AdaptiveThresholdEngine()
        # Explicitly import from decision_engine.strategy_ranker (has record_trade)
        from decision_engine.strategy_ranker import StrategyRanker as _SR
        self._strategy_ranker = _SR()
        self._kelly_sizer     = KellySizer()
        # Lazy import to avoid circular dependency
        try:
            from data_layer.stock_scanner import StockScanner as _SS
            self._scanner = _SS(self._data_manager)
        except Exception as _e:
            logger.warning(f"[Agent] StockScanner unavailable: {_e}")
            self._scanner = None

        # Intraday fetcher — 15-min bars + VWAP
        try:
            from data_layer.intraday_fetcher import IntradayFetcher as _IF
            self._intraday_fetcher = _IF(self._data_manager)
        except Exception as _e:
            logger.warning(f"[Agent] IntradayFetcher unavailable: {_e}")
            self._intraday_fetcher = None

        # Rally detector — finds intraday momentum spikes
        try:
            from .rally_detector import RallyDetector as _RD
            self._rally_detector = _RD(self._data_manager)
        except Exception as _e:
            logger.warning(f"[Agent] RallyDetector unavailable: {_e}")
            self._rally_detector = None

        self._last_intraday_data: dict = {}  # populated each scan, read by state property
        self._gap_predictor    = None        # scores positions for overnight gap holds
        self._hold_overnight   : dict = {}   # {symbol: GapScore} — positions to hold overnight
        self._prev_close_prices: dict = {}   # {symbol: price} — for gap detection at open
        try:
            from .gap_predictor import GapPredictor as _GP
            self._gap_predictor = _GP(self._data_manager)
            logger.info("[Agent] GapPredictor loaded ✓")
        except Exception as _e:
            logger.warning(f"[Agent] GapPredictor unavailable: {_e}")

        # Pre-market scanner — finds heat scores before open
        try:
            from data_layer.premarket_scanner import PremarketScanner as _PS
            self._premarket_scanner = _PS(self._data_manager)
        except Exception as _e:
            logger.warning(f"[Agent] PremarketScanner unavailable: {_e}")
            self._premarket_scanner = None
        try:
            _disc_approach = config.approach.value
        except AttributeError:
            _disc_approach = str(config.approach) if config.approach else "Balanced"
        disc_cfg = DisciplineConfig.for_mode(_disc_approach)
        self._discipline   = TradingDiscipline(disc_cfg)
        self._ticker_cd    = TickerCooldown()   # per-ticker loss cooling
        self._analyzer     = PerformanceAnalyzer()
        self._ranker       = PerfStrategyRanker()
        self._reporter     = DailyReportGenerator()

        # Live state
        self._portfolio_value = 10000.0
        self._open_positions  : Dict[str, dict] = {}
        self._daily_pnl       = 0.0
        self._last_scan       : Optional[datetime] = None
        self._decisions_today : List[TradeDecision] = []
        self._cycle_count     = 0
        self._bounce_scan_idx : int  = 0   # increments each scan cycle
        # Per-ticker bounce mode: {sym: {active, consec_losses, next_sl, pause_until_bar}}
        self._bounce_tickers  : dict = {}

        # Callbacks — dashboard subscribes to these
        self._on_decision    : Optional[Callable] = None
        self._on_status_change: Optional[Callable] = None
        self._on_scan_complete: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Public API (called by dashboard / CLI)
    # ------------------------------------------------------------------

    def start(self):
        """Start the autonomous agent loop."""
        if self.status == AgentStatus.RUNNING:
            logger.warning("[Agent] Already running")
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._connect()
        self.status  = AgentStatus.RUNNING
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="trading-agent"
        )
        self._thread.start()
        self._notify_status()
        logger.info(f"[Agent] Started — {self.config}")

    def pause(self):
        """Pause the agent between cycles (clean pause, no mid-trade interruption)."""
        self._pause_event.set()
        self.status = AgentStatus.PAUSED
        self._notify_status()
        logger.info("[Agent] Paused")

    def resume(self):
        """Resume a paused agent."""
        self._pause_event.clear()
        self.status = AgentStatus.RUNNING
        self._notify_status()
        logger.info("[Agent] Resumed")

    def stop(self):
        """Cleanly stop the agent."""
        self._stop_event.set()
        self._pause_event.clear()
        if self._data_manager:
            self._data_manager.disconnect()
        self.status = AgentStatus.STOPPED
        self._notify_status()
        logger.info("[Agent] Stopped")


    def _activate_bounce_mode(self, symbol: str, reason: str = "PM_LOSS") -> None:
        """Flip ticker into D1+Adaptive bounce mode for rest of session."""
        existing = self._bounce_tickers.get(symbol, {})
        self._bounce_tickers[symbol] = {
            'active':          True,
            'consec_losses':   existing.get('consec_losses', 0),
            'next_sl':         existing.get('next_sl', 0.003),
            'pause_until_bar': existing.get('pause_until_bar', 0),
        }
        logger.info(
            f"[BounceMode] {symbol} ACTIVATED ({reason}) "
            f"sl={self._bounce_tickers[symbol]['next_sl']*100:.2f}% "
            f"consec={self._bounce_tickers[symbol]['consec_losses']}"
        )

    def _record_bounce_exit(self, symbol: str, pnl: float) -> None:
        """
        Update adaptive stop after bounce trade exits.
        WIN  → reset counter + restore normal stop.
        LOSS → tighten stop; pause after 3 consecutive.
        """
        BN_SL_NORMAL  = 0.003
        BN_SL_TIGHT   = 0.002
        BN_SL_TIGHTER = 0.0015
        PAUSE_CYCLES  = 6
        bt = self._bounce_tickers.get(symbol)
        if bt is None:
            return
        if pnl >= 0:
            bt['consec_losses']   = 0
            bt['next_sl']         = BN_SL_NORMAL
            bt['pause_until_bar'] = 0
            logger.info(f"[BounceMode] {symbol} bounce WIN — stop reset to {BN_SL_NORMAL*100:.2f}%")
        else:
            bt['consec_losses'] += 1
            c = bt['consec_losses']
            if c == 1:
                bt['next_sl'] = BN_SL_TIGHT
                logger.info(f"[BounceMode] {symbol} loss #1 — stop → {BN_SL_TIGHT*100:.2f}%")
            elif c == 2:
                bt['next_sl'] = BN_SL_TIGHTER
                logger.info(f"[BounceMode] {symbol} loss #2 — stop → {BN_SL_TIGHTER*100:.2f}%")
            else:
                bt['pause_until_bar'] = self._bounce_scan_idx + PAUSE_CYCLES
                bt['consec_losses']   = 0
                bt['next_sl']         = BN_SL_NORMAL
                logger.warning(f"[BounceMode] {symbol} loss #{c} — PAUSING {PAUSE_CYCLES} cycles")

    def _reset_bounce_tickers_for_new_day(self) -> None:
        """Clear all session bounce state at start of new trading day.
        Preserves bar2_preactivate entries set in THIS startup cycle.
        """
        # Keep tickers pre-activated this cycle (bar2_preactivate)
        # They were just set — clearing them would waste the pre-activation
        keep = {sym: bt for sym, bt in self._bounce_tickers.items()
                if bt.get("reason") in ("bar2_preactivate", "session_dip")}
        cleared = [s for s in self._bounce_tickers if s not in keep]
        if cleared:
            logger.info(
                f"[BounceMode] New day — clearing stale bounce state: {cleared}"
            )
        if keep:
            logger.info(
                f"[BounceMode] New day — preserving bar2 pre-activations: {list(keep.keys())}"
            )
        self._bounce_tickers  = keep
        self._bounce_scan_idx = 0

    def reconfigure(self, new_config: AgentConfig):
        """Hot-swap configuration without restarting the agent."""
        old_approach = self.config.approach
        self.config  = new_config
        self._dec_engine = DecisionEngine(new_config)
        # Update strategy role filter for new mode
        approach_str = new_config.approach.value if hasattr(new_config.approach,"value") else str(new_config.approach) if new_config.approach else "Balanced"
        if hasattr(self, "_str_engine"):
            self._str_engine.set_approach(approach_str)
        logger.info(
            f"[Agent] Reconfigured: {(old_approach.value if hasattr(old_approach, 'value') else old_approach)} -> {approach_str} | "
            f"Strategy roles updated"
        )

    def force_scan(self):
        """Trigger an immediate scan outside the normal schedule."""
        if self.status == AgentStatus.RUNNING:
            threading.Thread(
                target=lambda: self._scan_cycle(scan_type="INTRADAY"), daemon=True, name="agent-forced-scan"
            ).start()

    # ------------------------------------------------------------------
    # Dashboard subscriptions
    # ------------------------------------------------------------------

    def on_decision(self, callback: Callable):
        """Register callback: called every time a decision is made."""
        self._on_decision = callback

    def on_status_change(self, callback: Callable):
        """Register callback: called when agent status changes."""
        self._on_status_change = callback

    def on_scan_complete(self, callback: Callable):
        """Register callback: called after every full watchlist scan."""
        self._on_scan_complete = callback

    # ------------------------------------------------------------------
    # State accessors (for dashboard)
    # ------------------------------------------------------------------

    @property
    def state(self) -> dict:
        """Full current state snapshot — dashboard reads this."""
        return {
            "status":          self.status,
            "approach":        (self.config.approach.value if hasattr(self.config.approach, "value") else self.config.approach),
            "paper_trading":   self.config.paper_trading,
            "portfolio_value": self._portfolio_value,
            "daily_pnl":       self._daily_pnl,
            "open_positions":  self._open_positions,
            "last_scan":       self._last_scan.isoformat() if self._last_scan else None,
            "cycle_count":     self._cycle_count,  # increments each scan
            "watchlist":       self.config.watchlist,
            "decisions_today": len(self._decisions_today),
            "log_summary":     self._dec_engine.logger.today_summary(),
            "portfolio_stats": self._portfolio.stats,
            "equity_curve":    self._portfolio.equity_curve,
            "strategy_ranker": self._strategy_ranker.summary(),
            "rally_signals":   self._rally_detector.get_all_signals() if self._rally_detector else {},
            "intraday_vwap":   self._safe_intraday_vwap(),
            "hold_overnight":  {
                sym: {"score": gs.score, "gap_pct": gs.predicted_gap_pct,
                      "reasons": gs.reasons[:2]}
                for sym, gs in getattr(self, "_hold_overnight", {}).items()
            },
            "adaptive": {
                "recommendation": vars(self._adaptive.get_current()) if self._adaptive.get_current() else None,
                "last_trade_count": self._adaptive._last_analysed_count,
                "trades_until_next": max(0, self._adaptive.UPDATE_EVERY_N_TRADES -
                    (len(self._portfolio._trades) - self._adaptive._last_analysed_count))
                    if len(self._portfolio._trades) >= self._adaptive.MIN_TRADES_FOR_LEARNING else
                    max(0, self._adaptive.MIN_TRADES_FOR_LEARNING - len(self._portfolio._trades))
            },
            "performance":     self._analyzer.analyze(self._portfolio._trades, self._portfolio._snapshots).grade if self._portfolio._trades else "N/A",
            "open_positions_detail": [
                str(p) for p in (self._executor.open_positions.values() if self._executor else [])
            ],
        }

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _connect(self):
        """Initialise data connection and scheduler."""
        from config import cfg as app_cfg
        provider = AlpacaProvider(
            api_key    = app_cfg.alpaca_api_key,
            secret_key = app_cfg.alpaca_secret_key,
            paper      = self.config.paper_trading,
        )
        self._data_manager = DataManager(
            provider       = provider,
            bar_cache_size = app_cfg.bar_cache_size,
        )
        self._data_manager.connect()

        # Replace naive interval loop with market-aware scheduler
        self._scheduler = MarketScheduler(self.config)
        self._scheduler.on_scan(self._scheduled_scan)

        # Layer 5 — executor
        self._executor = AlpacaExecutor(
            api_key    = app_cfg.alpaca_api_key,
            secret_key = app_cfg.alpaca_secret_key,
            paper      = self.config.paper_trading,
        )
        self._executor.connect()

        # Sync real portfolio value from Alpaca + fix tracker baseline
        try:
            acct = self._executor.get_account()
            if acct and acct.get("equity"):
                real_equity = float(acct["equity"])
                self._portfolio_value = real_equity
                logger.info(f"[Agent] Portfolio value synced from Alpaca: ${real_equity:,.2f}")
                # Fix portfolio tracker baseline — if saved as wrong value, correct it
                if self._portfolio._starting_value < 50000:
                    self._portfolio._starting_value = real_equity
                    logger.info(f"[Agent] Portfolio tracker baseline corrected to ${real_equity:,.2f}")

        except Exception as ex:
            logger.warning(f"[Agent] Could not sync portfolio value: {ex}")

        # Clean any corrupted trades from history (negative qty, inflated P&L)
        try:
            removed = self._portfolio.clean_bad_trades(max_single_pnl=500.0)
            if removed:
                logger.info(f"[Agent] Removed {removed} corrupted trades from history")
        except Exception as ex:
            logger.debug(f"[Agent] Trade clean skipped: {ex}")

        # Register any existing open positions with trailing stop manager
        try:
            self._executor.update_positions()
            # Sync _open_positions from executor so duplicate-buy guard works immediately
            self._open_positions = {
                sym: {"symbol": sym, "qty": getattr(pos, "qty", 0), "entry_price": getattr(pos, "entry_price", 0)}
                for sym, pos in self._executor.open_positions.items()
            }

            # Sync today's closed trades from Alpaca into portfolio tracker
            # This catches trades missed when agent was restarted or stop/TP fired
            try:
                from datetime import date, datetime as _dt
                from execution.portfolio_tracker import ClosedTrade

                # Fetch today's filled orders via REST directly
                _today_str = date.today().isoformat()
                _after = f"{_today_str}T00:00:00Z"

                try:
                    # Try SDK approach first
                    from alpaca.trading.requests import GetOrdersRequest
                    from alpaca.trading.enums import QueryOrderStatus
                    _req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, after=_after, limit=100)
                    _orders = self._executor._client.get_orders(filter=_req) or []
                except Exception:
                    try:
                        # Fallback: use requests library directly
                        import requests as _rq
                        _acct = self._executor.get_account()
                        _base = "https://paper-api.alpaca.markets" if self._executor._paper else "https://api.alpaca.markets"
                        _hdrs = {
                            'APCA-API-KEY-ID': self._executor._api_key,
                            'APCA-API-SECRET-KEY': self._executor._secret_key,
                        }
                        _resp = _rq.get(f"{_base}/v2/orders",
                            headers=_hdrs,
                            params={'status':'closed','after':_after,'limit':100,'direction':'desc'},
                            timeout=10)
                        _orders = _resp.json() if _resp.status_code == 200 else []
                        # Convert dicts to simple objects
                        class _O:
                            def __init__(self, d):
                                self.__dict__.update(d)
                        _orders = [_O(o) for o in _orders]
                    except Exception as _re:
                        logger.warning(f"[Agent] Trade sync fallback failed: {_re}")
                        _orders = []

                # Separate buys and sells
                _sells = [o for o in _orders
                          if str(getattr(o,'side','')).lower() in ('sell','orderside.sell')
                          and str(getattr(o,'status','')).lower() == 'filled']
                _buys  = [o for o in _orders
                          if str(getattr(o,'side','')).lower() in ('buy','orderside.buy')
                          and str(getattr(o,'status','')).lower() == 'filled']

                # Build buy lookup per symbol
                _buy_map: dict = {}
                for b in _buys:
                    _buy_map.setdefault(getattr(b,'symbol',''), []).append(b)

                # Existing trades to avoid duplicates
                _existing = {(t.symbol, str(t.exit_time)[:16]) for t in self._portfolio._trades}

                _imported = 0
                for o in _sells:
                    sym        = getattr(o, 'symbol', '')
                    exit_t     = str(getattr(o, 'filled_at', '') or '')
                    if not sym or not exit_t:
                        continue
                    _key = (sym, exit_t[:16])
                    if _key in _existing:
                        continue
                    exit_price  = float(getattr(o, 'filled_avg_price', 0) or 0)
                    qty         = int(getattr(o, 'filled_qty', 0) or 0)
                    _sym_buys   = sorted(_buy_map.get(sym, []),
                                         key=lambda b: str(getattr(b,'filled_at','')))
                    entry_price = float(getattr(_sym_buys[-1], 'filled_avg_price', exit_price)) if _sym_buys else exit_price
                    entry_t     = str(getattr(_sym_buys[-1], 'filled_at', exit_t)) if _sym_buys else exit_t
                    pnl         = (exit_price - entry_price) * qty
                    pnl_pct     = (exit_price - entry_price) / entry_price if entry_price else 0
                    trade = ClosedTrade(
                        symbol=sym, entry_price=entry_price, exit_price=exit_price,
                        qty=qty, entry_time=entry_t, exit_time=exit_t,
                        pnl=pnl, pnl_pct=pnl_pct, exit_reason='alpaca_sync',
                        strategy='', approach=str(
                            self.config.approach.value if hasattr(self.config.approach,'value')
                            else self.config.approach),
                    )
                    self._portfolio.record_trade(trade)
                    _existing.add(_key)
                    _imported += 1
                if _imported:
                    logger.info(f"[Agent] Synced {_imported} missing trades from Alpaca into portfolio")
                else:
                    logger.info(f"[Agent] Trade sync: {len(_sells)} sells checked, all already recorded")
            except Exception as _te:
                logger.warning(f"[Agent] Trade sync from Alpaca failed: {_te}")
            registered = 0
            for sym, pos in self._executor.open_positions.items():
                ep = pos.entry_price or pos.current_price or 0
                cp = pos.current_price or ep  # live price
                if ep <= 0:
                    logger.warning(f"[Agent] {sym}: entry_price=0 — skipping trailing stop registration")
                    continue
                # Always calculate from entry price — never trust null from Alpaca
                tp  = ep * (1 + self.config.take_profit_pct)
                # For stop: use the HIGHER of (entry-based stop) or (current-price-based stop)
                # This prevents wide stops on losing positions from old trailing_stop_pct
                sl_from_entry   = ep * (1 - self.config.stop_loss_pct)
                sl_from_current = cp * (1 - self.config.stop_loss_pct)
                sl = max(sl_from_entry, sl_from_current)
                self._trailing_mgr.register_position(
                    symbol      = sym,
                    entry_price = ep,
                    shares      = pos.qty,
                    stop_loss   = sl,
                    take_profit = tp,
                    conviction  = 2.5,   # default conviction for pre-existing positions
                )
                logger.info(
                    f"[Agent] Registered {sym} @ ${ep:.2f} | "
                    f"stop=${sl:.2f} ({self.config.stop_loss_pct:.1%}) | "
                    f"tp=${tp:.2f} ({self.config.take_profit_pct:.1%})"
                )
                registered += 1
            if registered:
                logger.info(f"[Agent] Trailing stop tracking: {registered} existing positions registered")
        except Exception as ex:
            logger.warning(f"[Agent] Position registration failed: {ex}")
        logger.info("[Agent] Data connection established")

        # Alpaca ground truth sync — injects missing trades + rebuilds ticker loss counts
        self._sync_today_from_alpaca()

    def _run_loop(self):
        """Main autonomous loop — delegates timing to MarketScheduler."""
        self._scheduler.start()
        # Keep thread alive until stop() is called
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(5)
                continue
            time.sleep(10)
        self._scheduler.stop()

    def _evaluate_champion(self):
        """
        EOD champion evaluation — called after every trading day.
        Checks if today's performance qualifies for champion promotion.
        Writes evaluation to logs/champion_eval.json for dashboard to read.
        Two consecutive qualifying days → marks config as 'promote_ready'.
        """
        import json, os
        from datetime import datetime, timezone, timedelta

        try:
            summary = self._portfolio.daily_summary()
            eval_path  = os.path.join(os.path.dirname(__file__),
                                      '..', 'logs', 'champion_eval.json')
            champ_path = os.path.join(os.path.dirname(__file__),
                                      '..', 'logs', 'pm_champion.json')
            eval_path  = os.path.abspath(eval_path)
            champ_path = os.path.abspath(champ_path)

            # Load existing eval history
            history = []
            if os.path.exists(eval_path):
                try:
                    with open(eval_path) as f:
                        data = json.load(f)
                        history = data.get('history', [])
                except Exception:
                    history = []

            # Add today
            history.append(summary)
            history = history[-7:]  # keep last 7 days only

            # Check consecutive qualifying days
            consecutive = 0
            for day in reversed(history):
                if day.get('qualifies'):
                    consecutive += 1
                else:
                    break

            promote_ready = consecutive >= 2
            logger.info(
                f"[Champion] EOD eval: {summary['date']} | "
                f"trades={summary['trades']} win={summary['win_rate']:.0%} "
                f"pnl=${summary['day_pnl']:+.0f} dd={summary['max_drawdown']:.1%} | "
                f"qualifies={summary['qualifies']} | "
                f"consecutive={consecutive} | promote_ready={promote_ready}"
            )

            # Write eval file for dashboard
            eval_data = {
                'updated_at':     datetime.now(timezone.utc).isoformat(),
                'today':          summary,
                'consecutive':    consecutive,
                'promote_ready':  promote_ready,
                'history':        history,
                'criteria': {
                    'win_rate_min':  0.75,
                    'pnl_min':       300.0,
                    'drawdown_max':  0.03,
                    'trades_min':    3,
                    'days_required': 2,
                },
            }
            os.makedirs(os.path.dirname(eval_path), exist_ok=True)
            with open(eval_path, 'w') as f:
                json.dump(eval_data, f, indent=2)

            if promote_ready:
                logger.info(
                    f"[Champion] 🏆 Config qualifies for promotion after "
                    f"{consecutive} consecutive days! "
                    f"Use dashboard to promote → pm_champion.json"
                )

        except Exception as e:
            logger.warning(f"[Champion] EOD eval failed: {e}")

    def _evaluate_champion(self):
        """
        EOD champion evaluation — called after every trading day.
        Checks if today's performance qualifies for champion promotion.
        Writes evaluation to logs/champion_eval.json for dashboard to read.
        Two consecutive qualifying days → marks config as 'promote_ready'.
        """
        import json, os
        from datetime import datetime, timezone, timedelta

        try:
            summary = self._portfolio.daily_summary()
            eval_path  = os.path.join(os.path.dirname(__file__),
                                      '..', 'logs', 'champion_eval.json')
            champ_path = os.path.join(os.path.dirname(__file__),
                                      '..', 'logs', 'pm_champion.json')
            eval_path  = os.path.abspath(eval_path)
            champ_path = os.path.abspath(champ_path)

            # Load existing eval history
            history = []
            if os.path.exists(eval_path):
                try:
                    with open(eval_path) as f:
                        data = json.load(f)
                        history = data.get('history', [])
                except Exception:
                    history = []

            # Add today
            history.append(summary)
            history = history[-7:]  # keep last 7 days only

            # Check consecutive qualifying days
            consecutive = 0
            for day in reversed(history):
                if day.get('qualifies'):
                    consecutive += 1
                else:
                    break

            promote_ready = consecutive >= 2
            logger.info(
                f"[Champion] EOD eval: {summary['date']} | "
                f"trades={summary['trades']} win={summary['win_rate']:.0%} "
                f"pnl=${summary['day_pnl']:+.0f} dd={summary['max_drawdown']:.1%} | "
                f"qualifies={summary['qualifies']} | "
                f"consecutive={consecutive} | promote_ready={promote_ready}"
            )

            # Write eval file for dashboard
            eval_data = {
                'updated_at':     datetime.now(timezone.utc).isoformat(),
                'today':          summary,
                'consecutive':    consecutive,
                'promote_ready':  promote_ready,
                'history':        history,
                'criteria': {
                    'win_rate_min':  0.75,
                    'pnl_min':       300.0,
                    'drawdown_max':  0.03,
                    'trades_min':    3,
                    'days_required': 2,
                },
            }
            os.makedirs(os.path.dirname(eval_path), exist_ok=True)
            with open(eval_path, 'w') as f:
                json.dump(eval_data, f, indent=2)

            if promote_ready:
                logger.info(
                    f"[Champion] 🏆 Config qualifies for promotion after "
                    f"{consecutive} consecutive days! "
                    f"Use dashboard to promote → pm_champion.json"
                )

        except Exception as e:
            logger.warning(f"[Champion] EOD eval failed: {e}")

    def _scheduled_scan(self, scan_type: str = "EOD"):
        """Called by MarketScheduler at the correct market time."""
        if self._pause_event.is_set():
            logger.info(f"[Agent] Scan skipped — agent paused ({scan_type})")
            return

        # Phase A: 3:30 PM — run gap prediction, decide what to hold overnight
        if scan_type == "PREMARKET_GAP_SCAN":
            self._run_gap_scan()
            return

        # Phase B: 3:45 PM — smart close (skip positions flagged for overnight hold)
        if scan_type == "INTRADAY_CLOSE":
            self._smart_close(reason="Intraday auto-close at 3:45 PM ET")
            return
        # Prevent concurrent scans — skip if one is already running
        if not self._scan_lock.acquire(blocking=False):
            logger.info(f"[Agent] Scan skipped — previous scan still running ({scan_type})")
            return
        try:
            self._scan_cycle(scan_type=scan_type)
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"[Agent] Scan cycle error: {exc}\n{tb}")
            # Store error for API to expose — but stay RUNNING so agent recovers
            self._last_scan_error = str(exc)
            self._last_scan_traceback = tb
            # Only go to ERROR if it's a critical unrecoverable error
            # For normal scan errors, stay running and retry next cycle
            if "cannot import" in str(exc).lower() or "module" in str(exc).lower():
                self.status = AgentStatus.ERROR
                self._notify_status()
            else:
                # Stay running — next scan cycle will retry
                logger.warning(f"[Agent] Scan error recovered — will retry next cycle")
        finally:
            # Always release the lock so next scan can run
            self._scan_lock.release()

    def _close_all_positions(self, reason: str = "Manual close-all"):
        """Close every open position immediately."""
        positions = dict(self._executor.open_positions)
        if not positions:
            logger.info(f"[Agent] Close-all: no open positions")
            return
        logger.info(f"[Agent] Close-all: closing {len(positions)} positions — {reason}")
        for sym in list(positions.keys()):
            try:
                class _Exit:
                    def __init__(self, s): self.symbol = s; self.action = "SELL"
                self._executor._close_position(_Exit(sym))
                self._trailing_mgr.remove_position(sym)
                logger.info(f"[Agent] Closed {sym} — {reason}")
            except Exception as ex:
                logger.warning(f"[Agent] Failed to close {sym}: {ex}")

    def _run_gap_scan(self):
        """Phase A: 3:30 PM — score positions for overnight hold."""
        if not self._gap_predictor:
            logger.info("[Agent] Gap scan skipped — predictor not available")
            return
        positions = dict(self._executor.open_positions)
        if not positions:
            logger.info("[Agent] Gap scan: no open positions to evaluate")
            return

        # Record current close prices for gap detection tomorrow
        for sym, pos in positions.items():
            self._prev_close_prices[sym] = getattr(pos, 'current_price', 0.0)

        scores = self._gap_predictor.score_positions(
            positions, self._last_intraday_data
        )
        self._hold_overnight = {
            sym: score for sym, score in scores.items() if score.hold_overnight
        }
        hold_syms  = list(self._hold_overnight.keys())
        close_syms = [s for s in positions if s not in hold_syms]
        logger.info(
            f"[GapScan] HOLD overnight: {hold_syms or 'none'} | "
            f"CLOSE at 3:45: {close_syms or 'none'}"
        )

    def _smart_close(self, reason: str = "Smart close"):
        """Phase B: 3:45 PM — close only positions NOT flagged for overnight hold."""
        positions  = dict(self._executor.open_positions)
        hold_syms  = set(self._hold_overnight.keys())
        to_close   = [s for s in positions if s not in hold_syms]

        if not to_close:
            logger.info(f"[Agent] Smart close: all positions held overnight {list(hold_syms)}")
            return

        logger.info(
            f"[Agent] Smart close: closing {to_close} | "
            f"holding overnight: {list(hold_syms) or 'none'}"
        )
        for sym in to_close:
            try:
                class _Exit:
                    def __init__(self, s): self.symbol = s; self.action = "SELL"
                self._executor._close_position(_Exit(sym))
                self._trailing_mgr.remove_position(sym)
                logger.info(f"[Agent] Smart closed {sym}")
            except Exception as ex:
                logger.warning(f"[Agent] Smart close failed {sym}: {ex}")

    def _check_gap_open_exits(self):
        """Phase C: 9:30-9:45 AM — sell held positions into gap, then re-enter if trending."""
        if not self._hold_overnight:
            return
        positions = dict(self._executor.open_positions)
        for sym, gap_score in list(self._hold_overnight.items()):
            if sym not in positions:
                # Already closed or never held
                del self._hold_overnight[sym]
                continue
            pos        = positions[sym]
            curr_price = getattr(pos, 'current_price', 0.0)
            prev_close = self._prev_close_prices.get(sym, curr_price)
            # Check if gap materialised
            gap_ok = self._gap_predictor.check_gap_materialised(sym, curr_price, prev_close)                      if self._gap_predictor else False
            actual_gap = ((curr_price - prev_close) / prev_close) if prev_close > 0 else 0
            if gap_ok:
                logger.info(
                    f"[GapOpen] {sym} gapped up {actual_gap:+.1%} — "
                    f"selling into gap at ${curr_price:.2f}"
                )
            else:
                logger.info(
                    f"[GapOpen] {sym} gap did not materialise ({actual_gap:+.1%}) — "
                    f"exiting at open"
                )
            # Sell the overnight position
            try:
                class _Exit:
                    def __init__(self, s): self.symbol = s; self.action = "SELL"
                self._executor._close_position(_Exit(sym))
                self._trailing_mgr.remove_position(sym)
                # Record result for future predictions
                if self._gap_predictor:
                    self._gap_predictor.record_gap_outcome(sym, actual_gap)
            except Exception as ex:
                logger.warning(f"[GapOpen] Failed to close {sym}: {ex}")
            del self._hold_overnight[sym]

    def _safe_intraday_vwap(self) -> dict:
        """Safely read intraday VWAP data — never crashes even on missing attr."""
        try:
            data = getattr(self, "_last_intraday_data", {}) or {}
            result = {}
            for sym, df in data.items():
                if df is not None and "vwap" in df.columns and len(df) > 0:
                    price = float(df["close"].iloc[-1])
                    vwap  = float(df["vwap"].iloc[-1])
                    result[sym] = {"vwap": round(vwap,2), "price": round(price,2),
                                   "bars": len(df), "above_vwap": price > vwap}
            return result
        except Exception:
            return {}

    @staticmethod
    def _calc_atr_stop(df, entry_price: float, atr_multiplier: float = 1.5) -> float:
        """
        Fix 2: Calculate ATR-based stop loss for a symbol.
        Uses 14-period ATR * multiplier to set stop wide enough to survive noise.
        Returns stop price (not percentage).
        """
        try:
            import pandas as pd
            high = df["high"] if "high" in df.columns else df["close"]
            low  = df["low"]  if "low"  in df.columns else df["close"]
            close = df["close"]
            # True Range
            tr = pd.concat([
                high - low,
                (high - close.shift(1)).abs(),
                (low  - close.shift(1)).abs()
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            if atr > 0:
                stop = entry_price - (atr * atr_multiplier)
                stop_pct = (entry_price - stop) / entry_price
                # Clamp: never wider than 5%, never tighter than 0.5%
                stop_pct = max(0.005, min(0.05, stop_pct))
                return entry_price * (1 - stop_pct)
        except Exception:
            pass
        return 0.0  # fallback — caller uses config stop_loss_pct


    def _sync_today_from_alpaca(self):
        """
        Pulls today's closed orders from Alpaca on every startup and:
        1. Injects any missing trades into portfolio.json
        2. Rebuilds _ticker_cd loss counts so session ban survives restarts
        3. Fixes day P&L and trade count to be calendar-based not session-based
        """
        try:
            import urllib.request as _ur, json as _json
            from datetime import datetime, timezone, timedelta
            from execution.portfolio_tracker import ClosedTrade

            KEY = getattr(self._executor, '_api_key', '') or getattr(self._executor, 'api_key', '')
            SEC = getattr(self._executor, '_secret_key', '') or getattr(self._executor, 'secret_key', '')
            if not KEY or not SEC:
                logger.warning("[SyncAlpaca] No credentials — skipping")
                return

            base = "https://paper-api.alpaca.markets" if getattr(self._executor, '_paper', True) else "https://api.alpaca.markets"

            req = _ur.Request(
                f"{base}/v2/orders?status=closed&limit=50&direction=desc",
                headers={"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC}
            )
            orders = _json.loads(_ur.urlopen(req, timeout=8).read())

            ET    = timezone(timedelta(hours=-4))
            today = datetime.now(ET).strftime("%Y-%m-%d")

            buys  = {}
            sells = {}
            for o in orders:
                filled_at = (o.get("filled_at") or "")[:10]
                if filled_at != today:
                    continue
                sym   = o.get("symbol","").upper()
                price = float(o.get("filled_avg_price") or 0)
                qty   = int(o.get("filled_qty") or 0)
                side  = o.get("side","")
                ts    = o.get("filled_at","")
                if side == "buy":
                    buys.setdefault(sym, []).append((qty, price, ts))
                else:
                    sells.setdefault(sym, []).append((qty, price, ts))

            # Get existing today's trade symbols to avoid duplicates
            existing = set()
            for t in self._portfolio._trades:
                et = (t.exit_time or "")[:10]
                if et == today:
                    existing.add(t.symbol.upper())

            injected = 0
            for sym in sells:
                if sym not in buys:
                    continue
                if sym in existing:
                    continue

                b_list = buys[sym]
                s_list = sells[sym]
                avg_buy  = sum(p*q for q,p,_ in b_list) / sum(q for q,p,_ in b_list)
                avg_sell = sum(p*q for q,p,_ in s_list) / sum(q for q,p,_ in s_list)
                qty_sold = sum(q for q,p,_ in s_list)
                pnl      = (avg_sell - avg_buy) * qty_sold
                entry_ts = min(t for _,_,t in b_list)
                exit_ts  = max(t for _,_,t in s_list)

                trade = ClosedTrade(
                    symbol      = sym,
                    entry_price = round(avg_buy, 4),
                    exit_price  = round(avg_sell, 4),
                    qty         = qty_sold,
                    entry_time  = entry_ts,
                    exit_time   = exit_ts,
                    pnl         = round(pnl, 2),
                    pnl_pct     = round((avg_sell - avg_buy) / avg_buy, 4) if avg_buy > 0 else 0,
                    exit_reason = "Recovered from Alpaca",
                    approach    = "Profit Maximizer",
                )
                self._portfolio.record_trade(trade)
                injected += 1
                logger.info(f"[SyncAlpaca] Injected {sym}: ${pnl:+.2f}")

                # Update ticker cooldown counts so session ban reflects real history
                if hasattr(self, '_ticker_cd'):
                    if pnl >= 0:
                        self._ticker_cd.record_win(sym)
                    else:
                        self._ticker_cd.record_loss(sym)

            # Rebuild ticker losses from ALL today's recorded trades
            # This ensures session ban reflects real history after restart
            if hasattr(self, '_ticker_cd'):
                # Reset counts first to avoid double-counting
                self._ticker_cd._ticker_losses = {}
                self._ticker_cd._ticker_cooldown = {}
                for t in sorted(self._portfolio._trades,
                                 key=lambda x: x.exit_time or ""):
                    et = (t.exit_time or "")[:10]
                    if et != today:
                        continue
                    sym = t.symbol.upper()
                    if t.pnl < 0:
                        self._ticker_cd.record_loss(sym)
                    else:
                        self._ticker_cd.record_win(sym)
                logger.info(f"[SyncAlpaca] Rebuilt ticker losses: {self._ticker_cd._ticker_losses}")

            if injected:
                logger.info(f"[SyncAlpaca] Injected {injected} missing trades for {today}")
            else:
                logger.info(f"[SyncAlpaca] All today's trades already recorded — {len(existing)} found")

        except Exception as e:
            import traceback
            logger.warning(f"[SyncAlpaca] Sync failed: {e}")
            logger.debug(traceback.format_exc())

    def _scan_cycle(self, scan_type: str = 'EOD'):
        """One complete scan: fetch → analyse → decide → (execute in Layer 5)."""
        self._cycle_count    += 1
        self._bounce_scan_idx += 1
        scan_start = datetime.now(timezone.utc)
        logger.info(f"[Agent] Cycle #{self._cycle_count} ({scan_type}) starting — {self.config.watchlist}")
        # Fully sync _open_positions from Alpaca every cycle
        # This removes closed positions and adds new ones — keeps count accurate
        try:
            self._executor.update_positions()
            confirmed = set(self._executor.open_positions.keys())
            # Remove from pending_buys anything already confirmed in Alpaca
            self._pending_buys -= confirmed
            # Replace _open_positions entirely with current Alpaca state
            self._open_positions = {
                sym: {"symbol": sym, "qty": getattr(pos,"qty",0),
                      "entry_price": getattr(pos,"entry_price",0), "max_loss": 0}
                for sym, pos in self._executor.open_positions.items()
            }
        except Exception as _pe:
            logger.warning(f"[Agent] Position sync ERROR: {_pe}")
            import traceback
            logger.warning(traceback.format_exc())

        # Fetch market data
        start = scan_start - timedelta(days=365)
        watchlist_data    : Dict[str, pd.DataFrame]   = {}
        strategy_reports  : Dict                      = {}

        # Phase C: At market open, check if overnight-held positions gapped up
        # Champion evaluation — runs at EOD only
        if scan_type == "EOD":
            try:
                self._evaluate_champion()
            except Exception as _ce:
                logger.warning(f"[Champion] Eval error: {_ce}")

        # Champion evaluation — runs at EOD only
        if scan_type == "EOD":
            try:
                self._evaluate_champion()
            except Exception as _ce:
                logger.warning(f"[Champion] Eval error: {_ce}")

        if scan_type in ("STARTUP", "INTRADAY") and self._hold_overnight:
            from datetime import datetime as _dt2, timezone as _tz2
            _now_et = _dt2.now(_tz2.utc)
            _hour   = _now_et.hour - 4  # rough ET (EDT)
            if 9 <= _hour <= 10:  # only in first hour — sell gap and re-enter
                logger.info("[Agent] Morning startup — checking gap open exits")
                self._check_gap_open_exits()

        # Fetch 1-min bars for Micro Momentum mode
        micro_data = {}
        _approach_val = getattr(self.config, 'approach', '')
        _approach_str = _approach_val.value if hasattr(_approach_val, 'value') else str(_approach_val)
        _is_micro = _approach_str.lower() in ('micro momentum', 'micro_momentum')
        if _is_micro:
            try:
                from datetime import datetime as _dt3, timedelta as _td3, timezone as _tz3
                import pandas as _pd2
                _start1 = _dt3.now(_tz3.utc) - _td3(hours=2)  # last 2 hours of 1-min bars
                for _sym in self.config.watchlist:
                    try:
                        _df1 = self._data_manager.get_bars_df(_sym, "1Min", start=_start1, limit=120)
                        if _df1 is not None and len(_df1) >= 5:
                            micro_data[_sym] = _df1
                    except Exception:
                        pass
                if micro_data:
                    logger.info(f"[Agent] Micro 1-min bars: {len(micro_data)} symbols")
            except Exception as _me:
                logger.debug(f"[Agent] Micro fetch failed: {_me}")

        # Fetch 15-min intraday bars + VWAP directly (inline, no dependency on fetcher module)
        intraday_data = {}
        try:
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            import pandas as _pd
            _start = _dt.now(_tz.utc) - _td(hours=7)
            _fetched = 0
            for _sym in self.config.watchlist:
                try:
                    _df = self._data_manager.get_bars_df(_sym, "15Min", start=_start, limit=30)
                    if _df is not None and len(_df) >= 2:
                        # Calculate VWAP inline
                        _h = _df["high"]   if "high"   in _df.columns else _df["close"]
                        _l = _df["low"]    if "low"    in _df.columns else _df["close"]
                        _c = _df["close"]
                        _v = _df["volume"] if "volume" in _df.columns else _pd.Series([1]*len(_c), index=_c.index)
                        _tp = (_h + _l + _c) / 3
                        _df = _df.copy()
                        _df["vwap"] = (_tp * _v).cumsum() / _v.cumsum().replace(0, float("nan"))
                        intraday_data[_sym] = _df
                        _fetched += 1
                except Exception:
                    pass
            if _fetched > 0:
                logger.info(f"[Agent] Intraday 15-min bars fetched for {_fetched} symbols")
            self._last_intraday_data = intraday_data
        except Exception as _ie:
            logger.debug(f"[Agent] Intraday fetch failed: {_ie}")

        # Rally detection — find stocks having significant intraday moves
        rally_signals = {}
        try:
            if self._rally_detector:
                rally_signals = self._rally_detector.scan(self.config.watchlist)
        except Exception as _re:
            logger.debug(f"[Agent] Rally scan failed: {_re}")

        # Pre-market heat scoring — reorder watchlist by momentum score
        scan_watchlist = list(self.config.watchlist)
        try:
            if self._premarket_scanner:
                scores = self._premarket_scanner.scan(scan_watchlist, top_n=len(scan_watchlist))
                if scores:
                    scored_syms = [s.symbol for s in scores]
                    # Put top-scored symbols first, keep rest in original order
                    remaining = [s for s in scan_watchlist if s not in scored_syms]
                    scan_watchlist = scored_syms + remaining
                    top3 = scores[:3]
                    logger.info(
                        f"[Agent] Pre-market top picks: "
                        + ", ".join(f"{s.symbol}({s.heat_score:.1f} heat, {s.reason})" for s in top3)
                    )
        except Exception as _pme:
            logger.debug(f"[Agent] Premarket scoring skipped: {_pme}")

        # ── Continuous bounce pre-activation ──────────────────────────
        # Every scan cycle: check all tickers for intraday weakness.
        # Trigger: dropped >=1% from session high AND RSI < 45
        # Max 4 tickers at once to avoid overexposure on broad selloffs.
        # Catches weakness at open AND mid-session dips.
        if intraday_data:
            try:
                MAX_BOUNCE_PREACT = 4
                _current_preact   = sum(
                    1 for bt in self._bounce_tickers.values()
                    if bt.get("reason") in ("bar2_preactivate", "session_dip")
                )
                _preact_count = 0
                for _sym, _df_b2 in intraday_data.items():
                    if _current_preact + _preact_count >= MAX_BOUNCE_PREACT:
                        break
                    if _sym in self._bounce_tickers:
                        continue
                    if _sym in self._open_positions:
                        continue
                    if len(_df_b2) < 5:
                        continue
                    _sess_high = float(_df_b2["high"].max()) if "high" in _df_b2.columns                                  else float(_df_b2["close"].max())
                    _cur_price = float(_df_b2["close"].iloc[-1])
                    _drop      = (_sess_high - _cur_price) / _sess_high if _sess_high > 0 else 0
                    _closes = _df_b2["close"].values
                    if len(_closes) >= 15:
                        _dlts  = [_closes[i]-_closes[i-1] for i in range(1,len(_closes))]
                        _gains = [max(d,0) for d in _dlts[-14:]]
                        _loss  = [max(-d,0) for d in _dlts[-14:]]
                        _ag = sum(_gains)/14; _al = sum(_loss)/14
                        _rsi = 100 - 100/(1+_ag/max(_al,1e-9))
                    else:
                        _rsi = 50.0
                    if _drop >= 0.010 and _rsi < 45:
                        self._bounce_tickers[_sym] = {
                            "active":          True,
                            "consec_losses":   0,
                            "next_sl":         0.003,
                            "pause_until_bar": 0,
                            "reason":          "session_dip",
                        }
                        _preact_count += 1
                        logger.info(
                            f"[BounceMode] {_sym} PRE-ACTIVATED (session dip) "
                            f"drop={_drop*100:.1f}% RSI={_rsi:.1f} "
                            f"high=${_sess_high:.2f} now=${_cur_price:.2f} "
                            f"— PM blocked, bounce enabled"
                        )
                if _preact_count:
                    logger.info(
                        f"[BounceMode] Session-dip pre-activation: "
                        f"{_preact_count} tickers (total: "
                        f"{_current_preact + _preact_count}/{MAX_BOUNCE_PREACT})"
                    )
            except Exception as _b2e:
                logger.debug(f"[Agent] Session-dip pre-activation failed: {_b2e}")

        for symbol in scan_watchlist:
            try:
                df = self._data_manager.get_bars_df(
                    symbol, self.config.trading_timeframe, start=start
                )
                if len(df) < 30:
                    logger.warning(f"[Agent] {symbol}: insufficient data ({len(df)} bars)")
                    continue
                watchlist_data[symbol] = df
            except Exception as exc:
                logger.warning(f"[Agent] Data fetch failed for {symbol}: {exc}")

        # Run indicators + strategies (with intraday data attached)
        for symbol, df in watchlist_data.items():
            try:
                summary = self._ind_engine.analyze(symbol, df)
                # Attach 15-min intraday df to summary for VWAP strategy
                if intraday_data.get(symbol) is not None:
                    summary.intraday_df = intraday_data[symbol]
                else:
                    summary.intraday_df = None
                # Attach 1-min df to summary for Micro Momentum strategy
                summary.micro_df = micro_data.get(symbol)
                report  = self._str_engine.evaluate(symbol, df, summary)
                strategy_reports[symbol] = report
            except Exception as exc:
                logger.warning(f"[Agent] Analysis failed for {symbol}: {exc}")

        # Update portfolio state
        self._dec_engine.update_portfolio_state(
            daily_pnl       = self._daily_pnl,
            open_positions  = self._open_positions,
            portfolio_value = self._portfolio_value,
            market_regime   = getattr(self._dec_engine._current_regime, 'regime', 'UNKNOWN') if hasattr(self._dec_engine, '_current_regime') and self._dec_engine._current_regime else 'UNKNOWN',
        )

        # Make decisions
        decisions = self._dec_engine.scan_watchlist(
            watchlist_data, strategy_reports, self._portfolio_value
        )

        # ── EarningsMomentum Peer Halo (Fix 3) ──────────────────────────────
        # If any watchlist symbol fired EarningsMomentum BUY with gap > 10%,
        # boost conviction of same-sector peers by +0.5 for this cycle only.
        try:
            SECTOR_PEERS = {
                'AMD':  ['MU','NVDA','INTC','QCOM','AMAT','AVGO','SNDK'],
                'MU':   ['AMD','NVDA','INTC','QCOM','AMAT','AVGO','SNDK'],
                'NVDA': ['AMD','MU','INTC','QCOM','AMAT','AVGO'],
                'INTC': ['AMD','MU','NVDA','QCOM','AMAT','AVGO','SNDK'],
                'QCOM': ['AMD','MU','NVDA','INTC','AMAT','AVGO'],
                'AMAT': ['AMD','MU','NVDA','INTC','QCOM','AVGO'],
                'AVGO': ['AMD','MU','NVDA','INTC','QCOM','AMAT'],
                'SNDK': ['MU','INTC','AMAT'],
                'ORCL': ['MSFT','META','GOOGL','AMZN'],
                'MSFT': ['ORCL','META','GOOGL','AMZN'],
            }
            EARNINGS_HALO = 0.5   # conviction boost for sector peers
            GAP_THRESHOLD = 0.08  # 8% gap = meaningful earnings catalyst
            
            catalyst_symbols = set()
            for sym, report in strategy_reports.items():
                for sig in report.signals:
                    if (sig.strategy == 'EarningsMomentum' and
                        str(sig.action).upper() in ('BUY', 'TradeAction.BUY') and
                        sig.confidence >= 0.70):
                        catalyst_symbols.add(sym)
                        logger.info(f"[PeerHalo] {sym} is earnings catalyst — boosting sector peers")
            
            if catalyst_symbols:
                peers_to_boost = set()
                for cat in catalyst_symbols:
                    peers_to_boost.update(SECTOR_PEERS.get(cat, []))
                peers_to_boost -= catalyst_symbols  # don't double-boost the catalyst itself
                
                for decision in decisions:
                    if decision.symbol in peers_to_boost and decision.action in ('BUY', 'HOLD'):
                        decision.conviction_score = round(decision.conviction_score + EARNINGS_HALO, 3)
                        logger.info(
                            f"[PeerHalo] {decision.symbol} +{EARNINGS_HALO} conviction "
                            f"(sector peer of {catalyst_symbols}) → {decision.conviction_score:.2f}"
                        )
        except Exception as _halo_ex:
            logger.debug(f"[PeerHalo] Failed: {_halo_ex}")

        # ── Smart Exit Check ─────────────────────────────────────────────
        # Run trailing stop + smart exit manager on every scan cycle
        if self._executor and self._executor.open_positions:
            try:
                # Build price map — use last close from bars, fall back to live price
                current_prices = {}
                for sym, df in watchlist_data.items():
                    try:
                        current_prices[sym] = float(df.iloc[-1]["close"])
                    except Exception:
                        pass
                # Also include current prices from executor for positions not in watchlist_data
                for sym, pos in self._executor.open_positions.items():
                    if sym not in current_prices and pos.current_price:
                        current_prices[sym] = float(pos.current_price)

                # Stop levels are set at config stop_loss_pct — never override with ATR
                # ATR override was removed: it widened stops beyond configured 1%, defeating risk management

                # Collect candlestick pattern signals from strategy reports
                candle_signals = {}
                for sym, report in strategy_reports.items():
                    patterns = getattr(report, "candle_patterns", [])
                    if patterns:
                        candle_signals[sym] = patterns

                exit_signals = self._trailing_mgr.update_and_check(
                    positions        = self._executor.open_positions,
                    current_prices   = current_prices,
                    strategy_reports = strategy_reports,
                    candle_signals   = candle_signals,
                )

                if exit_signals:
                    logger.info(f"[Agent] {len(exit_signals)} exit signal(s) triggered this cycle")

                for sig in exit_signals:
                    logger.info(f"[Agent] EXIT SIGNAL: {sig.symbol} {sig.action} — {sig.reason}")
                    try:
                        # Snapshot position BEFORE close for P&L calculation
                        pos = self._executor.open_positions.get(sig.symbol)
                        entry_price = pos.entry_price if pos else 0
                        entry_qty   = abs(pos.qty)    if pos else 0  # abs() prevents negative qty inflating P&L
                        entry_time  = getattr(pos, "entry_time", None) or scan_start.isoformat()

                        if sig.action == "SELL":
                            class _ExitDecision:
                                def __init__(self, sym):
                                    self.symbol = sym
                                    self.action = "SELL"
                            order = self._executor._close_position(_ExitDecision(sig.symbol))
                            self._trailing_mgr.remove_position(sig.symbol)
                            # Fix 1: Mark stop-loss exits with 2hr cooldown to prevent re-entry
                            if "stop" in (sig.reason or "").lower() or "Stop" in (sig.reason or ""):
                                self._scheduler.mark_stopped_out(sig.symbol, cooldown_minutes=120)
                                # D1+Adaptive: stop-out → activate bounce mode for rest of session
                                self._activate_bounce_mode(sig.symbol, reason="PM_LOSS")

                            # Record completed trade in portfolio tracker
                            if order and entry_price > 0:
                                from execution.portfolio_tracker import ClosedTrade
                                exit_price = getattr(order, "filled_avg_price", None) or sig.price or entry_price
                                pnl        = (exit_price - entry_price) * entry_qty
                                pnl_pct    = (exit_price - entry_price) / entry_price if entry_price else 0
                                trade = ClosedTrade(
                                    symbol      = sig.symbol,
                                    entry_price = round(entry_price, 4),
                                    exit_price  = round(float(exit_price), 4),
                                    qty         = entry_qty,
                                    entry_time  = str(entry_time),
                                    exit_time   = scan_start.isoformat(),
                                    pnl         = round(pnl, 2),
                                    pnl_pct     = round(pnl_pct, 4),
                                    exit_reason = sig.reason[:40] if sig.reason else "exit",
                                    approach    = (self.config.approach.value if hasattr(self.config.approach, "value") else self.config.approach),
                                )
                                self._portfolio.record_trade(trade)
                                # Record result for re-entry logic
                                self._scheduler.record_trade_result(sig.symbol, pnl >= 0)
                                # Update strategy ranker
                                try:
                                    if hasattr(self._strategy_ranker, 'record_trade'):
                                        self._strategy_ranker.record_trade(
                                            sig.symbol,
                                            getattr(sig, 'strategy', ''),
                                            is_win=(pnl >= 0)
                                        )
                                except Exception as _sre:
                                    logger.debug(f"[Agent] StrategyRanker update skipped: {_sre}")
                                # Update discipline engine
                                if hasattr(self, '_discipline'):
                                    self._discipline.record_trade_result(pnl_pct=pnl_pct)
                                # Per-ticker cooldown recording
                                if hasattr(self, '_ticker_cd'):
                                    if pnl >= 0:
                                        self._ticker_cd.record_win(symbol)
                                    else:
                                        self._ticker_cd.record_loss(symbol)
                                # D1+Adaptive: record bounce exit → tightens adaptive stop
                                if getattr(sig, 'bounce_entry', False):
                                    self._record_bounce_exit(symbol, pnl)
                                # D1+Adaptive: PM loss → bounce mode for rest of session
                                if pnl < 0:
                                    self._activate_bounce_mode(symbol, reason="PM_LOSS")
                                else:
                                    # PM win — clear any stale bounce state
                                    self._bounce_tickers.pop(symbol, None)

                        elif sig.action == "PARTIAL_SELL":
                            order = self._executor._close_partial(sig.symbol, sig.shares)

                            # Record partial trade
                            if order and entry_price > 0:
                                from execution.portfolio_tracker import ClosedTrade
                                exit_price = getattr(order, "filled_avg_price", None) or sig.price or entry_price
                                pnl        = (exit_price - entry_price) * sig.shares
                                pnl_pct    = (exit_price - entry_price) / entry_price if entry_price else 0
                                trade = ClosedTrade(
                                    symbol      = sig.symbol,
                                    entry_price = round(entry_price, 4),
                                    exit_price  = round(float(exit_price), 4),
                                    qty         = sig.shares,
                                    entry_time  = str(entry_time),
                                    exit_time   = scan_start.isoformat(),
                                    pnl         = round(pnl, 2),
                                    pnl_pct     = round(pnl_pct, 4),
                                    exit_reason = "partial_profit",
                                    approach    = (self.config.approach.value if hasattr(self.config.approach, "value") else self.config.approach),
                                )
                                self._portfolio.record_trade(trade)

                    except Exception as ex:
                        logger.warning(f"[Agent] Exit execution failed for {sig.symbol}: {ex}")
                else:
                    logger.debug(f"[Agent] Exit check: no exits triggered on {len(self._executor.open_positions)} positions")
            except Exception as ex:
                logger.warning(f"[Agent] Exit check failed: {ex}")
        # ─────────────────────────────────────────────────────────────────

        # Record portfolio snapshot every cycle (feeds equity curve)
        try:
            # Always get live equity from Alpaca so curve reflects real P&L
            try:
                _live_acct = self._executor.get_account() if self._executor else {}
                if _live_acct and _live_acct.get("equity"):
                    self._portfolio_value = float(_live_acct["equity"])
            except Exception:
                pass  # keep last known value
            self._portfolio.record_snapshot(
                portfolio_value = self._portfolio_value,
                cash            = getattr(self._executor, "_cash", self._portfolio_value),
                open_positions  = len(self._executor.open_positions) if self._executor else 0,
                daily_pnl       = self._daily_pnl,
            )
        except Exception as ex:
            logger.debug(f"[Agent] Snapshot record failed: {ex}")

        # Strategy ranker: learn from all completed trades
        try:
            self._strategy_ranker.learn_from_trades(self._portfolio._trades)
        except Exception as ex:
            logger.debug(f"[StrategyRanker] Update failed: {ex}")

        # Phase 3: Adaptive threshold learning — re-analyse every 5 new trades
        try:
            trades = self._portfolio._trades
            if self._adaptive.should_update(len(trades)):
                rec = self._adaptive.analyse(trades)
                if rec.confidence >= 0.4:
                    old_conv = self.config.min_conviction_score
                    old_strats = self.config.min_strategies_agree
                    # For Micro Momentum: cap adaptive learning — never override scalping settings
                    _approach_str = self.config.approach.value if hasattr(self.config.approach, 'value') else str(self.config.approach)
                    if _approach_str == 'Micro Momentum':
                        self.config.min_conviction_score = min(rec.conviction_floor, 1.5)
                        self.config.min_strategies_agree = 1  # always 1 for Micro Momentum
                    else:
                        self.config.min_conviction_score = max(1.5, min(rec.conviction_floor, 2.5))
                        self.config.min_strategies_agree = rec.min_strategies
                    if old_conv != rec.conviction_floor or old_strats != rec.min_strategies:
                        logger.info(
                            f"[Adaptive] Thresholds updated: "
                            f"conviction {old_conv:.1f}→{rec.conviction_floor:.1f} | "
                            f"min_strats {old_strats}→{rec.min_strategies} | "
                            f"{rec.summary}"
                        )
        except Exception as ex:
            logger.debug(f"[Adaptive] Learning failed: {ex}")

        # Store + notify
        self._decisions_today.extend(decisions)
        self._last_scan = scan_start

        # Auto-reset daily guards on new trading day
        from datetime import date as _date
        today_date = _date.today()
        if not hasattr(self, '_last_trade_date') or self._last_trade_date != today_date:
            self._last_trade_date = today_date
            self._scheduler.reset_daily_guards()
            logger.info(f"[Agent] New day {today_date} — guards reset")
            self._reset_bounce_tickers_for_new_day()

        for d in decisions:
            if self._on_decision:
                self._on_decision(d)

            if d.approved and d.action in ("BUY", "SELL"):
                # Already in this position — never double up
                # Check both in-memory AND executor positions for safety
                # Triple-layer guard against duplicate buys
                _in_executor  = d.symbol in self._executor.open_positions
                _in_internal  = d.symbol in (self._open_positions or {})
                # Also refresh executor positions if both are empty (post-restart gap)
                if d.action == "BUY" and not _in_executor and not _in_internal:
                    try:
                        self._executor.update_positions()
                        _in_executor = d.symbol in self._executor.open_positions
                    except Exception:
                        pass
                _already_open = _in_executor or _in_internal
                if d.action == "BUY" and _already_open:
                    logger.info(f"[Agent] {d.symbol} already in open position — skipping")
                    continue

                # ── Bounce mode gate ─────────────────────────────────────
                if d.action == "BUY":
                    _bt = self._bounce_tickers.get(d.symbol)
                    if _bt and _bt.get('active'):
                        # Paused after 3 consecutive bounce losses
                        if self._bounce_scan_idx < _bt.get('pause_until_bar', 0):
                            logger.info(f"[Agent] {d.symbol} bounce paused — skipping")
                            continue
                        # Only bounce entries allowed — PM signal skipped
                        if not getattr(d, 'bounce_entry', False):
                            logger.info(
                                f"[Agent] {d.symbol} in bounce mode — "
                                f"PM signal skipped, waiting for exhaustion")
                            continue

                # ── Scheduler stop-out cooldown gate ─────────────────────
                if d.action == "BUY" and hasattr(self, '_scheduler'):
                    if self._scheduler.is_in_stop_cooldown(d.symbol):
                        logger.info(f"[Agent] {d.symbol} in stop-out cooldown — skipping")
                        continue

                # ── TickerCooldown gate — per-symbol loss cooling ─────────
                if d.action == "BUY" and hasattr(self, '_ticker_cd'):
                    _regime = getattr(self._dec_engine, '_current_regime', None)
                    _regime_str = getattr(_regime, 'regime', 'BULL') if _regime else 'BULL'
                    _mtf_score = 0.0
                    try:
                        _mtf_score = self._dec_engine._mtf_scores.get(d.symbol, 0.0) if hasattr(self._dec_engine, '_mtf_scores') else 0.0
                    except Exception:
                        pass

                    # ── Check cooldown ───────────────────────────────────────
                    _cd_ok, _cd_reason = self._ticker_cd.can_trade(d.symbol, regime=_regime_str, mtf_score=_mtf_score)
                    if not _cd_ok:
                        logger.warning(f"[TickerCooldown] {d.symbol} BLOCKED — {_cd_reason}")
                        continue
                # ── EOD Entry Gate ───────────────────────────────────────
                # Block new BUY entries after 12:00 PM PST (3:00 PM ET) unless
                # a legitimate catalyst justifies the late entry.
                if d.action == "BUY":
                    import datetime as _dt
                    import zoneinfo as _zi
                    _ET  = _zi.ZoneInfo('America/New_York')
                    _now_et = _dt.datetime.now(_ET)
                    _eod_gate_active = (_now_et.hour > 15) or (_now_et.hour == 15 and _now_et.minute >= 0)
                    if _eod_gate_active:
                        # Exception 1 — Earnings catalyst fired today (earnings_gap > 8%)
                        _has_earnings = False
                        try:
                            _rep = self._strategy_reports.get(d.symbol)
                            if _rep:
                                for _sr in (_rep.strategy_results if hasattr(_rep, 'strategy_results') else []):
                                    if 'Earnings' in getattr(_sr, 'strategy_name', '') and getattr(_sr, 'signal', '') == 'BUY':
                                        _has_earnings = d.conviction_score >= 3.0
                        except Exception:
                            pass

                        # Exception 2 — Strong bull run (up >2% today, RSI 60-80, vol >1.2x, conv >=3.5)
                        _has_bull_run = False
                        try:
                            _rally = rally_signals.get(d.symbol)
                            if _rally:
                                _day_gain = getattr(_rally, 'intraday_pct', 0) / 100
                                _vol_ok   = getattr(_rally, 'vol_ratio', 0) >= 1.2
                                _rsi_ok   = False
                                _smry = self._analysis_summaries.get(d.symbol)
                                if _smry:
                                    _rsi_val = getattr(_smry, 'rsi', 50)
                                    _rsi_ok  = 60 <= _rsi_val <= 80
                                _has_bull_run = (_day_gain > 0.02 and _vol_ok and _rsi_ok
                                                 and d.conviction_score >= 3.5)
                        except Exception:
                            pass

                        # Exception 3 — Sector surge / PeerHalo active this session
                        _has_sector_surge = False
                        try:
                            _has_sector_surge = (
                                hasattr(self, '_peer_halo_active') and
                                self._peer_halo_active and
                                d.symbol in getattr(self, '_peer_halo_symbols', set()) and
                                d.conviction_score >= 3.0
                            )
                        except Exception:
                            pass

                        if not (_has_earnings or _has_bull_run or _has_sector_surge):
                            logger.info(
                                f"[EODGate] {d.symbol} BLOCKED — after 3PM ET, "
                                f"no earnings/bull-run/sector-surge catalyst "
                                f"(conv={d.conviction_score:.2f})"
                            )
                            continue

                # Apply rally conviction bonus — boost entries on rallying stocks
                if d.action == "BUY" and rally_signals.get(d.symbol):
                    bonus = self._rally_detector.get_conviction_bonus(d.symbol)
                    if bonus > 0:
                        sig = rally_signals[d.symbol]
                        logger.info(
                            f"[Rally] {d.symbol} conviction bonus +{bonus:.1f} "
                            f"({sig.intraday_pct:+.1f}% today, {sig.vol_ratio:.1f}x vol)"
                        )
                        d.conviction_score = d.conviction_score + bonus

                # Kelly sizing: override position dollar amount based on conviction + regime
                if d.action == "BUY":
                    try:
                        stats     = self._portfolio.stats
                        # Use cash (not buying_power) to avoid PDT margin issues
                        # buying_power = 0 when daytrading_buying_power = 0 (PDT rule)
                        # cash is always available for non-day-trade purchases
                        _buying_power = 0.0
                        try:
                            _bp_acct = self._executor.get_account() if self._executor else {}
                            # Prefer cash over buying_power — avoids PDT daytrading restriction
                            _cash = float(_bp_acct.get("cash", 0) or 0)
                            _equity = float(_bp_acct.get("equity", 0) or 0)
                            # Use actual cash (never borrowed) — true no-margin sizing
                            _buying_power = max(_cash, 0)
                            if _buying_power <= 0:
                                # Fallback to equity if cash is zero
                                _buying_power = max(_equity * 0.95, 0)
                        except Exception:
                            pass

                        # Use per-symbol stats if available, else fall back to overall
                        _sym_stats = {}
                        try:
                            _sym_stats = self._portfolio.symbol_stats(d.symbol)
                        except Exception:
                            pass
                        _win_rate = _sym_stats.get('win_rate') or stats.get('win_rate', 0.5) or 0.5
                        _avg_win  = _sym_stats.get('avg_win')  or stats.get('avg_win', 10.0) or 10.0
                        _avg_loss = _sym_stats.get('avg_loss') or abs(stats.get('avg_loss', 10.0) or 10.0)
                        if _sym_stats.get('count', 0) > 0:
                            logger.debug(f"[Kelly] {d.symbol}: using {_sym_stats['count']} trades history "
                                         f"(win={_win_rate:.1%} avg_win=${_avg_win:.0f} avg_loss=${_avg_loss:.0f})")

                        kelly_res = self._kelly_sizer.size(
                            symbol           = d.symbol,
                            portfolio_value  = self._portfolio_value,
                            conviction_score = d.conviction_score if hasattr(d, 'conviction_score') else 2.5,
                            regime           = getattr(self._dec_engine._current_regime, 'regime', 'RANGING')
                                               if hasattr(self._dec_engine, '_current_regime') and
                                               self._dec_engine._current_regime else 'RANGING',
                            win_rate         = _win_rate,
                            avg_win          = _avg_win,
                            avg_loss         = _avg_loss,
                            max_pct          = self.config.max_position_pct,
                            available_cash   = _buying_power,
                        )
                        d.dollar_amount = kelly_res.dollar_amount
                        logger.info(
                            f"[KellyDebug] {d.symbol}: kelly_res.dollar=${kelly_res.dollar_amount:,.2f} "
                            f"kelly_f={kelly_res.kelly_f:.4f} conv_mult={kelly_res.conviction_mult:.2f} "
                            f"regime_mult={kelly_res.regime_mult:.2f} fraction={kelly_res.fraction:.4f} "
                            f"buying_power=${_buying_power:,.2f} "
                            f"win_rate={_win_rate:.2f} avg_win={_avg_win:.2f} avg_loss={_avg_loss:.2f}"
                        )

                        # ── Recalculate shares from Kelly dollar_amount ────────
                        # engine.py sets shares based on old portfolio_value logic
                        # We override here with the cash-safe dollar_amount
                        try:
                            _price = getattr(d, 'entry_price', None) or getattr(d, 'current_price', None)
                            if not _price and hasattr(self._dec_engine, '_last_prices'):
                                _price = self._dec_engine._last_prices.get(d.symbol)
                            if _price and _price > 0 and d.dollar_amount > 0:
                                _safe_shares = max(1, int(d.dollar_amount / _price))
                                d.shares = _safe_shares
                                logger.info(
                                    f"[Kelly] {d.symbol}: {_safe_shares} shares @ ${_price:.2f} "
                                    f"= ${_safe_shares * _price:,.0f} [NO MARGIN]"
                                )
                        except Exception:
                            pass  # keep original shares if price lookup fails

                        # ── Hard cash check — block trade if not enough cash ──
                        _order_cost = (d.shares or 1) * getattr(d, 'entry_price', 0) or d.dollar_amount
                        if _buying_power > 0 and _order_cost > _buying_power * 0.95:
                            logger.warning(
                                f"[CashGuard] {d.symbol} BLOCKED — order ${_order_cost:,.0f} "
                                f"exceeds 95% of buying_power ${_buying_power:,.0f}. No margin."
                            )
                            continue

                        # ── Session loss guard — if same symbol lost 2+ times today, ban it ──
                        if hasattr(self, '_ticker_cd'):
                            _sym_losses = self._ticker_cd._ticker_losses.get(d.symbol.upper(), 0)
                            if _sym_losses >= 2:
                                logger.warning(
                                    f"[SessionGuard] {d.symbol} BANNED — {_sym_losses} losses today. "
                                    f"Not re-entering this symbol again today."
                                )
                                continue
                        logger.info(
                            f"[Kelly] {d.symbol}: {kelly_res.reason}"
                        )
                    except Exception as kex:
                        logger.debug(f"[Kelly] Sizing failed for {d.symbol}: {kex}")
                logger.info(f"[Agent] ACTION: {d}")
                self._scheduler.mark_traded(d.symbol)
                if self._executor:
                    order = self._executor.execute(d)
                    if order:
                        logger.info(f"[Agent] Order result: {order}")

        if self._on_scan_complete:
            self._on_scan_complete(decisions)

        elapsed = (datetime.now(timezone.utc) - scan_start).total_seconds()
        logger.info(
            f"[Agent] Cycle #{self._cycle_count} done in {elapsed:.1f}s — "
            f"{sum(1 for d in decisions if d.action in ('BUY','SELL'))} actions"
        )

    def _notify_status(self):
        if self._on_status_change:
            self._on_status_change(self.status)

    def discipline_status(self) -> dict:
        """Return discipline engine status for dashboard."""
        if hasattr(self, '_discipline'):
            return self._discipline.get_status()
        return {}

    @property
    def _news_cache(self) -> dict:
        """News sentiment cache accessible to conviction engine."""
        return getattr(self, '_cached_news', {})

    def update_news_cache(self, news_data: dict):
        """Update news sentiment cache from news fetcher."""
        self._cached_news = news_data

    def last_conviction_breakdown(self) -> dict:
        """Return last conviction breakdown for dashboard."""
        return getattr(self, '_last_breakdown', {})
