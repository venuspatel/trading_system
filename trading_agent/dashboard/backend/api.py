# -*- coding: utf-8 -*-
"""
Dashboard Backend — FastAPI
Run: uvicorn dashboard.backend.api:app --reload --port 8000
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load .env file for Alpaca keys and configuration
_env_file = os.environ.get("ENV_FILE", ".env")
try:
    from dotenv import load_dotenv as _load_dotenv
    # Resolve absolute path: dashboard/backend/api.py -> up 2 levels -> trading_agent root
    _root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    _dotenv_path = os.path.join(_root, _env_file)
    if os.path.exists(_dotenv_path):
        _load_dotenv(_dotenv_path, override=True)
except Exception:
    pass

import asyncio, json, logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import cfg as app_cfg
import os as _os
# Set anthropic key in environment so AIReviewer can find it
if app_cfg.anthropic_api_key:
    _os.environ["ANTHROPIC_API_KEY"] = app_cfg.anthropic_api_key
from decision_engine import AgentConfig, Approach, SizingMethod, TradingAgent, AgentStatus, TrailingStopManager
from execution import AlpacaExecutor, PortfolioTracker
from performance import PerformanceAnalyzer, StrategyRanker, DailyReportGenerator
from decision_engine.decision_logger import DecisionLogger
from news import NewsFetcher, SentimentEngine, SymbolSentiment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

app = FastAPI(title="TradeAgent Dashboard", version="1.0")



@app.get("/")
def root():
    return {"status": "ok", "service": "TradeAgent V1"}

# ── Push notification support ──
_push_tokens: set = set()

@app.post("/api/notify/register")
async def register_push_token(request: Request):
    try:
        body  = await request.json()
        token = body.get("token", "")
        if token:
            _push_tokens.add(token)
            logger.info(f"[Notify] Registered token: {token[:20]}...")
            return {"status": "registered", "tokens": len(_push_tokens)}
        return {"status": "error", "message": "no token"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/notify/send")
async def send_notification(request: Request):
    try:
        body    = await request.json()
        title   = body.get("title", "TradeAgent")
        message = body.get("message", "")
        if _push_tokens:
            import httpx
            messages = [{"to": t, "title": title, "body": message, "sound": "default"}
                       for t in _push_tokens]
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://exp.host/--/api/v2/push/send",
                    json=messages, timeout=5
                )
            logger.info(f"[Notify] Sent to {len(_push_tokens)} devices: {title}")
            return {"status": "sent", "devices": len(_push_tokens)}
        return {"status": "no_tokens", "message": "No devices registered"}
    except Exception as e:
        logger.warning(f"[Notify] Send failed: {e}")
        return {"status": "error", "message": str(e)}
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def auto_restore_and_start():
    """Auto-load saved config + auto-start agent on every backend launch."""
    import asyncio, logging
    _log = logging.getLogger(__name__)
    await asyncio.sleep(2.0)  # wait for full initialisation
    global _config, _agent
    try:
        if _config is None:
            restored = _load_config_from_disk()
            if restored:
                _config = restored
                _log.info(f"[API] Config restored: {getattr(restored, 'approach', 'unknown')}")
        if _config is not None and _agent is None:
            _agent = TradingAgent(_config)
        if _agent is not None and str(_agent.status).lower() == "idle":
            _agent.start()
            _log.info("[API] Agent auto-started from saved config ✓")
            # Enable intraday mode using config interval
            import time as _time, threading as _th
            def _auto_intraday_restore():
                _time.sleep(3)
                try:
                    interval = getattr(_config, 'intraday_interval_min', 2) if _config else 2
                    if _agent and hasattr(_agent, '_scheduler'):
                        _agent._scheduler.set_intraday_mode(True, interval)
                        _log.info(f"[API] Intraday mode AUTO-ON on restore ✓ ({interval} min)")
                except Exception as _e:
                    _log.warning(f"[API] Intraday auto-on (restore) failed: {_e}")
            _th.Thread(target=_auto_intraday_restore, daemon=True).start()
    except Exception as e:
        _log.warning(f"[API] Auto-restore failed: {e}")

_config   = None
SAVE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "saved_config.json"))

def _save_config_to_disk(cfg: "AgentConfig"):
    """Persist current config so it survives restarts."""
    import json as _json, logging, os as _os
    _log = logging.getLogger(__name__)
    try:
        data = cfg.to_dict() if hasattr(cfg, "to_dict") else {}
        # Ensure directory exists
        _os.makedirs(_os.path.dirname(SAVE_PATH), exist_ok=True)
        with open(SAVE_PATH, "w") as f:
            _json.dump(data, f, indent=2)
        _log.info(f"[API] Config saved to {SAVE_PATH}")
    except Exception as e:
        # Try fallback path in same dir as this file
        try:
            fallback = _os.path.join(_os.path.dirname(__file__), "..", "..", "saved_config.json")
            fallback = _os.path.abspath(fallback)
            data = cfg.to_dict() if hasattr(cfg, "to_dict") else {}
            with open(fallback, "w") as f:
                _json.dump(data, f, indent=2)
            _log.info(f"[API] Config saved (fallback) to {fallback}")
        except Exception as e2:
            _log.error(f"[API] Config save FAILED: primary={e} fallback={e2} path={SAVE_PATH}")

def _load_config_from_disk() -> "Optional[AgentConfig]":
    """Load last saved config from disk."""
    try:
        import json as _json
        if not os.path.exists(SAVE_PATH):
            return None
        with open(SAVE_PATH) as f:
            data = _json.load(f)
        cfg = AgentConfig()
        approach = data.get("approach", "Profit Maximizer")
        {
            "Conservative":    cfg.apply_conservative,
            "Balanced":        cfg.apply_balanced,
            "Aggressive":      cfg.apply_aggressive,
            "Profit Maximizer":cfg.apply_profit_maximizer,
            "Long Term":       cfg.apply_long_term,
            "Micro Momentum":  cfg.apply_micro_momentum,
        }.get(approach, cfg.apply_profit_maximizer)()
        cfg.approach = approach  # always restore the exact saved approach string
        # Restore key settings
        for attr in ["max_open_positions","stop_loss_pct","take_profit_pct",
                     "confidence_threshold","min_strategies_agree","paper_trading",
                     "market_hours_only","earnings_blackout_days","trailing_stop",
                     "max_trades_per_day","max_hold_days","watchlist",
                     "min_conviction_score","intraday_mode","intraday_interval_min",
                     "trailing_stop","max_trades_per_symbol","trade_cooldown_minutes"]:
            if attr in data:
                try: setattr(cfg, attr, data[attr])
                except Exception: pass
        # Restore feature_flags — merge saved flags on top of preset defaults
        if "feature_flags" in data and data["feature_flags"]:
            existing = cfg.feature_flags or {}
            existing.update(data["feature_flags"])
            cfg.feature_flags = existing
        import logging; logging.getLogger(__name__).info(f"[API] Config restored: {approach}")
        return cfg
    except Exception as e:
        import logging; logging.getLogger(__name__).warning(f"Config load failed: {e}")
        return None
_agent    = None
_executor = None
_portfolio = PortfolioTracker()
_analyzer  = PerformanceAnalyzer()
_ranker    = StrategyRanker()
_d_logger  = DecisionLogger()
_news_fetcher  = None
_sentiment_eng = None
_news_cache: dict = {}

class ConnectionManager:
    def __init__(self): self.active = []
    async def connect(self, ws):
        await ws.accept(); self.active.append(ws)
    def disconnect(self, ws):
        if ws in self.active: self.active.remove(ws)
    async def broadcast(self, data):
        dead = []
        for ws in self.active:
            try: await ws.send_json(data)
            except: dead.append(ws)
        for ws in dead: self.active.remove(ws)

ws_manager = ConnectionManager()

class ConfigPayload(BaseModel):
    approach: str = "Balanced"
    sizing_method: str = "Confidence-Scaled"
    max_portfolio_risk_pct: float = 5.0
    max_open_positions: int = 3
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    daily_loss_limit_pct: float = 3.0
    min_strategies_agree: int = 3
    confidence_threshold: float = 0.65
    min_conviction_score: float = 2.0
    paper_trading: bool = True
    market_hours_only: bool = True
    earnings_blackout_days: int = 3
    regime_filter: bool = True
    watchlist: List[str] = ["AAPL","TSLA","NVDA","MSFT","AMZN"]
    trailing_stop: bool = False
    candle_exit:   bool = False
    momentum_exit: bool = False
    max_hold_days: int  = 0
    scan_frequency_minutes:  int   = 60
    max_trades_per_day:      int   = 5
    max_consecutive_losses:  int   = 3
    cooldown_minutes:        int   = 60
    profit_lock_pct:         float = 3.0
    weekly_loss_limit_pct:   float = 8.0
    feature_flags: dict = None   # e.g. {"trail_activation": true, ...}

def _build_config(p: ConfigPayload) -> AgentConfig:
    cfg = AgentConfig()
    {
        "Conservative":    cfg.apply_conservative,
        "Balanced":        cfg.apply_balanced,
        "Aggressive":      cfg.apply_aggressive,
        "Profit Maximizer":cfg.apply_profit_maximizer,
        "Long Term":       cfg.apply_long_term,
        "Micro Momentum":  cfg.apply_micro_momentum,
    }.get(p.approach, cfg.apply_balanced)()
    cfg.approach = p.approach  # always preserve the exact approach string

    # Apply ALL user overrides AFTER preset — so manual sliders always win
    cfg.max_portfolio_risk_pct = p.max_portfolio_risk_pct / 100
    cfg.max_open_positions = p.max_open_positions
    cfg.stop_loss_pct = p.stop_loss_pct / 100
    cfg.take_profit_pct = p.take_profit_pct / 100
    cfg.daily_loss_limit_pct = p.daily_loss_limit_pct / 100
    cfg.min_strategies_agree = p.min_strategies_agree
    cfg.confidence_threshold = p.confidence_threshold
    cfg.min_conviction_score = p.min_conviction_score

    # Sanity guard: take_profit must always be > stop_loss (basic risk management)
    if cfg.take_profit_pct <= cfg.stop_loss_pct:
        import logging
        logging.getLogger(__name__).warning(
            f"[API] take_profit ({cfg.take_profit_pct:.1%}) <= stop_loss ({cfg.stop_loss_pct:.1%}) — "
            f"auto-correcting take_profit to {cfg.stop_loss_pct * 2:.1%}"
        )
        cfg.take_profit_pct = cfg.stop_loss_pct * 2

    # Sanity guard: min_strategies_agree must be at least 2 for Profit Maximizer
    if p.approach == "Profit Maximizer" and cfg.min_strategies_agree < 2:
        cfg.min_strategies_agree = 2
        import logging
        logging.getLogger(__name__).warning("[API] min_strategies_agree < 2 for PM — auto-corrected to 2")
    cfg.paper_trading = p.paper_trading
    cfg.market_hours_only = p.market_hours_only
    cfg.earnings_blackout_days = p.earnings_blackout_days
    cfg.regime_filter = p.regime_filter
    cfg.watchlist = p.watchlist
    cfg.sizing_method = {"Kelly Criterion": SizingMethod.KELLY, "Fixed Fractional": SizingMethod.FIXED, "Confidence-Scaled": SizingMethod.CONFIDENCE}.get(p.sizing_method, SizingMethod.CONFIDENCE)

    # Apply trailing stop overrides if passed
    if hasattr(p, 'trailing_stop'):    cfg.trailing_stop    = p.trailing_stop
    if hasattr(p, 'candle_exit'):      cfg.candle_exit      = p.candle_exit
    if hasattr(p, 'momentum_exit'):    cfg.momentum_exit    = p.momentum_exit

    # Apply feature flags — merge with existing defaults so unset flags stay OFF
    if p.feature_flags:
        existing = cfg.feature_flags or {}
        existing.update(p.feature_flags)
        cfg.feature_flags = existing
    if hasattr(p, 'max_hold_days'):    cfg.max_hold_days    = p.max_hold_days
    if hasattr(p, 'scan_frequency_minutes'): cfg.scan_frequency_minutes = p.scan_frequency_minutes
    if hasattr(p, 'max_trades_per_day'):     cfg.max_trades_per_day     = p.max_trades_per_day
    if hasattr(p, 'max_consecutive_losses'): cfg.max_consecutive_losses = p.max_consecutive_losses
    if hasattr(p, 'cooldown_minutes'):       cfg.cooldown_minutes       = p.cooldown_minutes
    if hasattr(p, 'profit_lock_pct'):        cfg.profit_lock_pct        = p.profit_lock_pct / 100
    if hasattr(p, 'weekly_loss_limit_pct'):  cfg.weekly_loss_limit_pct  = p.weekly_loss_limit_pct / 100

    return cfg


# In-memory cache of Alpaca assets — loaded once, searched instantly
_ticker_cache: list = []
_ticker_cache_loaded: bool = False

async def _load_ticker_cache():
    """Load all Alpaca US equity assets into memory — tries alpaca-py then urllib fallback."""
    global _ticker_cache, _ticker_cache_loaded
    if _ticker_cache_loaded:
        return
    try:
        import os as _os, logging, asyncio, json
        _log = logging.getLogger(__name__)
        api_key    = _os.getenv("ALPACA_API_KEY", _os.getenv("APCA_API_KEY_ID", ""))
        api_secret = _os.getenv("ALPACA_SECRET_KEY", _os.getenv("APCA_API_SECRET_KEY", ""))
        if not api_key:
            _log.warning("[API] No Alpaca key found — using local ticker list")
            return

        def _fetch_sync():
            # Try alpaca-py first
            try:
                from alpaca.trading import TradingClient
                from alpaca.trading.requests import GetAssetsRequest
                from alpaca.trading.enums import AssetClass, AssetStatus
                client = TradingClient(api_key, api_secret, paper=True)
                req = GetAssetsRequest(asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE)
                assets = client.get_all_assets(req)
                return [{"symbol": str(a.symbol), "name": str(a.name or ""), 
                         "exchange": str(a.exchange or ""), "tradable": getattr(a,"tradable",False)}
                        for a in assets]
            except Exception:
                pass

            # Fallback: urllib (zero dependencies)
            import urllib.request as _ur
            url = "https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity"
            req = _ur.Request(url, headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
                "Accept": "application/json"
            })
            with _ur.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())

        loop   = asyncio.get_event_loop()
        raw    = await loop.run_in_executor(None, _fetch_sync)

        cache = []
        for a in raw:
            sym  = str(a.get("symbol",""))
            name = str(a.get("name","")) or sym
            exch = str(a.get("exchange",""))
            if not a.get("tradable", False): continue
            if not sym or len(sym) > 6: continue
            if "." in sym or "/" in sym: continue
            cache.append((sym, name.upper(), name, exch))

        _ticker_cache = cache
        _ticker_cache_loaded = True
        import logging
        logging.getLogger(__name__).info(f"[API] Ticker cache: {len(cache)} assets loaded")

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[API] Ticker cache failed: {e}")

def _build_reporting_stats(stats: dict, agent) -> dict:
    """Build clean professional reporting metrics for the dashboard."""
    try:
        acct = agent._executor.get_account() if agent and agent._executor else {}
        equity      = float(acct.get("equity",       0))
        buying_power= float(acct.get("buying_power", 0))
        positions   = agent._executor.open_positions if agent and agent._executor else {}
        total_invested = sum(
            float(p.get("qty",0)) * float(p.get("avg_entry_price", p.get("entry_price",0)))
            for p in (positions.values() if isinstance(positions, dict) else [])
        )
        unrealised_pnl = sum(
            float(p.get("unrealized_pl", p.get("pnl", 0)))
            for p in (positions.values() if isinstance(positions, dict) else [])
        )
    except Exception:
        equity = buying_power = total_invested = unrealised_pnl = 0

    return {
        # Capital
        "total_invested":     round(total_invested, 2),
        "remaining_liquid":   round(buying_power, 2),
        "unrealised_pnl":     round(unrealised_pnl, 2),
        "account_equity":     round(equity, 2),
        # Session (since last restart)
        "session_pnl":        stats.get("session_pnl", 0),
        "session_trades":     stats.get("session_trades", 0),
        # Day
        "day_pnl":            stats.get("day_pnl", 0),
        "day_trades":         stats.get("day_trades", 0),
        "day_win_rate":       stats.get("day_win_rate", 0),
        # Week / Month
        "week_pnl":           stats.get("week_pnl", 0),
        "month_pnl":          stats.get("month_pnl", 0),
        # All-time closed
        "total_closed_pnl":   stats.get("total_pnl", 0),
        "twrr":               stats.get("twrr", 0),
        "win_rate":           stats.get("win_rate", 0),
        "profit_factor":      stats.get("profit_factor", 0),
        "expectancy":         stats.get("expectancy", 0),
        "reward_risk":        stats.get("reward_risk", 0),
        "sharpe":             stats.get("sharpe", 0),
        "max_drawdown":       stats.get("max_drawdown", 0),
        "max_consec_losses":  stats.get("max_consec_losses", 0),
    }



@app.get("/api/tickers/search")
async def search_tickers(q: str = "", limit: int = 10):
    """
    Fast ticker search — loads Alpaca assets into memory cache on first call,
    then searches 10,000+ stocks instantly by symbol OR company name.
    """
    q = q.upper().strip()
    if not q:
        return {"results": []}

    # Try to load cache if not yet loaded
    await _load_ticker_cache()

    if _ticker_cache:
        exact_prefix, name_match = [], []
        for sym, name_upper, name_orig, exch in _ticker_cache:
            if sym.startswith(q):
                exact_prefix.append({"symbol": sym, "name": name_orig, "exchange": exch})
            elif len(q) >= 2 and q in name_upper:
                name_match.append({"symbol": sym, "name": name_orig, "exchange": exch})
            if len(exact_prefix) >= limit and len(name_match) >= limit * 2:
                break
        results = exact_prefix + name_match
        # Sort exact prefix by symbol length (shorter = more relevant)
        results[:len(exact_prefix)] = sorted(exact_prefix, key=lambda x: len(x["symbol"]))
        return {"results": results[:limit], "source": "alpaca_cache", "total": len(results)}

    # Local fallback
    LOCAL = [
        ("AAPL","Apple Inc","NASDAQ"),("TSLA","Tesla Inc","NASDAQ"),("NVDA","NVIDIA Corp","NASDAQ"),
        ("MSFT","Microsoft Corp","NASDAQ"),("AMZN","Amazon.com Inc","NASDAQ"),("GOOGL","Alphabet Inc","NASDAQ"),
        ("META","Meta Platforms","NASDAQ"),("NFLX","Netflix Inc","NASDAQ"),("AMD","Advanced Micro Devices","NASDAQ"),
        ("INTC","Intel Corp","NASDAQ"),("AVGO","Broadcom Inc","NASDAQ"),("ORCL","Oracle Corp","NYSE"),
        ("JPM","JPMorgan Chase","NYSE"),("BAC","Bank of America","NYSE"),("GS","Goldman Sachs","NYSE"),
        ("V","Visa Inc","NYSE"),("MA","Mastercard Inc","NYSE"),("PYPL","PayPal Holdings","NASDAQ"),
        ("COIN","Coinbase Global","NASDAQ"),("HOOD","Robinhood Markets","NASDAQ"),
        ("SOFI","SoFi Technologies","NASDAQ"),("PLTR","Palantir Technologies","NYSE"),
        ("SNAP","Snap Inc","NYSE"),("MU","Micron Technology","NASDAQ"),("MSTR","MicroStrategy","NASDAQ"),
        ("MARA","Marathon Digital","NASDAQ"),("RKLB","Rocket Lab USA","NASDAQ"),
        ("IONQ","IonQ Inc","NYSE"),("QBTS","D-Wave Quantum","NYSE"),
        ("SPY","SPDR S&P 500 ETF","NYSE"),("QQQ","Invesco QQQ Trust","NASDAQ"),
        ("TSLA","Tesla Inc","NASDAQ"),("SMCI","Super Micro Computer","NASDAQ"),
        ("ARM","Arm Holdings","NASDAQ"),("TSM","Taiwan Semiconductor","NYSE"),
        ("SAND","Sandstorm Gold","NYSE"),("SAN","Banco Santander","NYSE"),
        ("SANM","Sanmina Corp","NASDAQ"),("SNDK","SanDisk Corp","NASDAQ"),
        ("AAL","American Airlines","NASDAQ"),("SMR","NuScale Power","NYSE"),
        ("BMNR","Bitmine Immersion","NASDAQ"),("HIMS","Hims & Hers Health","NYSE"),
        ("PANW","Palo Alto Networks","NASDAQ"),("CRWD","CrowdStrike Holdings","NASDAQ"),
        ("SNOW","Snowflake Inc","NYSE"),("DDOG","Datadog Inc","NASDAQ"),
        ("NET","Cloudflare Inc","NYSE"),("SHOP","Shopify Inc","NYSE"),
        ("ABNB","Airbnb Inc","NASDAQ"),("UBER","Uber Technologies","NYSE"),
    ]
    exact = [{"symbol":s,"name":n,"exchange":e} for s,n,e in LOCAL if s.startswith(q)]
    names = [{"symbol":s,"name":n,"exchange":e} for s,n,e in LOCAL if q in n.upper() and not s.startswith(q)]
    return {"results": (exact+names)[:limit], "source": "local"}

@app.get("/api/champion")
async def get_champion():
    """Return champion eval status + current champion config."""
    import json as _json, os as _os
    BASE_DIR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    eval_path  = _os.path.join(BASE_DIR, "logs", "champion_eval.json")
    champ_path = _os.path.join(BASE_DIR, "logs", "pm_champion.json")
    prev_path  = _os.path.join(BASE_DIR, "logs", "pm_champion_prev.json")

    eval_data  = {}
    champ_data = {}
    prev_data  = {}

    if _os.path.exists(eval_path):
        with open(eval_path) as f:
            eval_data = _json.load(f)
    if _os.path.exists(champ_path):
        with open(champ_path) as f:
            champ_data = _json.load(f)
    if _os.path.exists(prev_path):
        with open(prev_path) as f:
            prev_data = _json.load(f)

    return {
        "eval":     eval_data,
        "champion": champ_data,
        "previous": prev_data,
        "has_champion": bool(champ_data),
        "promote_ready": eval_data.get("promote_ready", False),
    }


@app.post("/api/promote")
async def promote_champion():
    """
    Promote current saved_config.json to pm_champion.json.
    Backs up existing champion to pm_champion_prev.json first.
    Called manually from dashboard when user clicks 'Promote to Default'.
    """
    import json as _json, os as _os, shutil
    BASE_DIR   = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    saved_path = _os.path.join(BASE_DIR, "saved_config.json")
    champ_path = _os.path.join(BASE_DIR, "logs", "pm_champion.json")
    prev_path  = _os.path.join(BASE_DIR, "logs", "pm_champion_prev.json")
    eval_path  = _os.path.join(BASE_DIR, "logs", "champion_eval.json")

    try:
        # Load current saved config
        with open(saved_path) as f:
            saved = _json.load(f)

        # Load eval data for performance stats
        eval_data = {}
        if _os.path.exists(eval_path):
            with open(eval_path) as f:
                eval_data = _json.load(f)

        # Backup existing champion
        if _os.path.exists(champ_path):
            shutil.copy2(champ_path, prev_path)

        # Write new champion
        champion = {
            "promoted_at":   datetime.now(timezone.utc).isoformat(),
            "promoted_from": "saved_config.json",
            "performance":   eval_data.get("today", {}),
            "history":       eval_data.get("history", []),
            "consecutive":   eval_data.get("consecutive", 0),
            "config":        saved,
        }
        _os.makedirs(_os.path.dirname(champ_path), exist_ok=True)
        with open(champ_path, 'w') as f:
            _json.dump(champion, f, indent=2)

        import logging
        logging.getLogger(__name__).info(
            f"[Champion] 🏆 Promoted to champion: "
            f"win={eval_data.get('today',{}).get('win_rate',0):.0%} "
            f"pnl=${eval_data.get('today',{}).get('day_pnl',0):+.0f}"
        )
        return {"status": "promoted", "champion": champion}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/revert")
async def revert_champion():
    """
    Revert to previous champion config.
    Copies pm_champion_prev.json → saved_config.json and reconfigures agent.
    """
    import json as _json, os as _os
    BASE_DIR   = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
    saved_path = _os.path.join(BASE_DIR, "saved_config.json")
    prev_path  = _os.path.join(BASE_DIR, "logs", "pm_champion_prev.json")

    if not _os.path.exists(prev_path):
        return {"status": "error", "message": "No previous champion to revert to"}

    try:
        with open(prev_path) as f:
            prev = _json.load(f)

        prev_config = prev.get("config", {})
        if not prev_config:
            return {"status": "error", "message": "Previous champion has no config"}

        # Write back to saved_config.json
        with open(saved_path, 'w') as f:
            _json.dump(prev_config, f, indent=2)

        # Reconfigure live agent
        if _agent:
            cfg = _load_config_from_disk()
            if cfg:
                _agent.reconfigure(cfg)

        import logging
        logging.getLogger(__name__).info("[Champion] Reverted to previous champion config")
        return {"status": "reverted", "config": prev_config}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/health")
def health(): return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


def _get_market_regime() -> dict:
    """Get current market regime from decision engine."""
    try:
        if _agent and hasattr(_agent, '_dec_engine'):
            regime = _agent._dec_engine._current_regime
            if regime:
                return {
                    "regime":       regime.regime,
                    "spy_trend":    regime.spy_trend,
                    "spy_rsi":      regime.spy_rsi,
                    "vix_est":      regime.vix_level,
                    "momentum":     regime.spy_momentum,
                    "conviction_threshold": regime.thresholds.conviction,
                    "confidence_threshold": regime.thresholds.confidence,
                    "reason":       regime.reason,
                }
    except Exception:
        pass
    return {"regime": "UNKNOWN", "reason": "Not yet detected", "overrides": []}


def _get_strategy_vote_distribution(decisions: list) -> list:
    """
    Aggregate strategy votes across all symbols.
    Returns list of {strategy, role, buys:[], sells:[], holds:[]} 
    so dashboard can show which strategies are helping vs cancelling.
    """
    if not decisions:
        return []
    
    # Strategy name → role mapping (known roles)
    role_map = {
        "Momentum":          "Trend",
        "Breakout":          "Trend",
        "TrendStrength":     "Trend",
        "EarningsMomentum":  "Trend",
        "MeanReversion":     "Counter-trend",
        "Fibonacci":         "Counter-trend",
        "CandleReversal":    "Neutral",
        "CandleContinuation":"Neutral",
        "Divergence":        "Neutral",
        "VolumeConfirmation":"Neutral",
        "MultiTimeframe":    "Neutral",
        "TrendRegime":       "Neutral",
    }
    
    agg = {}
    for dec in decisions:
        for sig in dec.get("strategy_signals", []):
            name = sig.get("strategy", "Unknown")
            action = sig.get("action", "HOLD")
            sym = dec.get("symbol", "")
            if name not in agg:
                agg[name] = {"strategy": name, "role": role_map.get(name, "Neutral"),
                             "buys": [], "sells": [], "holds": []}
            if action == "BUY":
                agg[name]["buys"].append(sym)
            elif action == "SELL":
                agg[name]["sells"].append(sym)
            else:
                agg[name]["holds"].append(sym)
    
    return sorted(agg.values(), key=lambda x: -len(x["buys"]))

@app.get("/api/trades")
async def get_all_trades():
    """Return ALL closed trades for full P&L audit."""
    global _agent
    live_portfolio = _agent._portfolio if _agent and hasattr(_agent, "_portfolio") else None
    if not live_portfolio:
        return {"trades": [], "count": 0, "total_pnl": 0}
    all_t = live_portfolio.all_trades
    total_pnl = sum(t.get("pnl", 0) for t in all_t)
    winners   = sum(1 for t in all_t if t.get("pnl", 0) > 0)
    return {
        "trades":    all_t,
        "count":     len(all_t),
        "total_pnl": round(total_pnl, 2),
        "winners":   winners,
        "losers":    len(all_t) - winners,
        "win_rate":  round(winners / len(all_t), 4) if all_t else 0
    }


@app.get("/api/state")
def get_state():
    global _agent, _executor, _config

    # Safe account fetch — try both executor and agent executor
    account = {}
    positions = {}
    # Get the best available executor
    _exec = _executor
    if (not _exec or not getattr(_exec, '_connected', False)) and _agent:
        _exec = getattr(_agent, '_executor', _exec)
    if _exec and getattr(_exec, '_connected', False):
        try:
            account = _exec.get_account()
        except Exception as e:
            logger.warning(f"Account fetch error: {e}")
        try:
            # Refresh positions from Alpaca (safely — don't crash if executor not ready)
            try:
                _exec.update_positions()
            except Exception as _upe:
                pass  # use stale positions if refresh fails
            positions = {
                sym: {
                    "qty": p.qty,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "pnl": p.unrealised_pnl,
                    "pnl_pct": p.unrealised_pnl_pct,
                    # Pull stop/TP from TrailingStopManager — Alpaca doesn't store these
                    "stop_loss": (
                        getattr(_agent._trailing_mgr._states.get(sym), "current_stop", None)
                        if _agent and hasattr(_agent, "_trailing_mgr")
                        else getattr(p, "stop_loss", None)
                    ),
                    "take_profit": (
                        getattr(_agent._trailing_mgr._states.get(sym), "take_profit", None)
                        if _agent and hasattr(_agent, "_trailing_mgr")
                        else p.take_profit
                    ),
                }
                for sym, p in _exec.open_positions.items()
            }
        except Exception as e:
            logger.warning(f"Positions fetch error: {e}")

    # Always use the live agent's portfolio instance so trade history is current
    live_portfolio = (getattr(_agent, "_portfolio", None) or _portfolio) if _agent else _portfolio

    # Build perf_dict directly from portfolio stats — no analyzer needed
    try:
        stats = live_portfolio.stats
        trades = live_portfolio._trades
        perf_dict = {
            "win_rate":      stats.get("win_rate", 0),
            "profit_factor": stats.get("profit_factor", 0),
            "sharpe_ratio":  0,
            "max_drawdown":  stats.get("max_drawdown", 0),
            "total_pnl":     stats.get("total_pnl", 0),
            "grade":         "N/A",
            "pnl_7d":        0,
            "pnl_30d":       0,
            "total_trades":  stats.get("total_trades", 0),
            "winners":       stats.get("winners", 0),
            "losers":        stats.get("losers", 0),
            "avg_win":       stats.get("avg_win", 0),
            "avg_loss":      stats.get("avg_loss", 0),
            "best_trade":    stats.get("best_trade"),
            "worst_trade":   stats.get("worst_trade"),
        }
        # Try to get grade from analyzer — non-blocking
        try:
            perf = _analyzer.analyze(trades, live_portfolio._snapshots, live_portfolio._starting_value or 100000)
            perf_dict["grade"] = perf.grade
            perf_dict["sharpe_ratio"] = perf.sharpe_ratio
            perf_dict["pnl_7d"] = perf.pnl_7d
            perf_dict["pnl_30d"] = perf.pnl_30d
        except Exception:
            pass
    except Exception as e:
        import logging; logging.getLogger(__name__).warning(f"perf_dict build failed: {e}")
        perf_dict = {"win_rate":0,"profit_factor":0,"sharpe_ratio":0,"max_drawdown":0,"total_pnl":0,
                     "grade":"N/A","pnl_7d":0,"pnl_30d":0,"total_trades":0,"winners":0,"losers":0,
                     "avg_win":0,"avg_loss":0}

    # Safe decisions — read directly from log file so restarts don't lose history
    try:
        recent = []
        for r in _d_logger.recent(20):
            d = vars(r)
            # Include AI verdict fields if present
            recent.append(d)
        today = _d_logger.today_summary()
    except Exception:
        recent, today = [], {}

    # Fallback: read JSONL log file directly if in-memory logger is empty
    if not recent:
        try:
            import json as _json
            log_path = _config.log_path if _config else "logs/decisions.jsonl"
            if os.path.exists(log_path):
                with open(log_path) as lf:
                    lines = [l.strip() for l in lf.readlines() if l.strip()]
                recent = [_json.loads(l) for l in lines[-20:]]
                recent.reverse()
        except Exception as e:
            logger.warning(f"Log file read error: {e}")

    agent_state = {}
    try:
        agent_state = _agent.state if _agent else {}
    except Exception:
        pass

    # Expose per-symbol trend states from engine
    trend_states = {}
    try:
        if _agent and hasattr(_agent, '_dec_engine') and hasattr(_agent._dec_engine, '_trend_states'):
            trend_states = _agent._dec_engine._trend_states
    except Exception:
        pass

    return {
        "agent_status":    str(_agent.status if _agent else "idle"),
        "last_error":      getattr(_agent, '_last_scan_error', None) if _agent else None,
        "error_trace":     getattr(_agent, '_last_scan_traceback', None) if _agent else None,
        "config":          _config.to_dict() if _config else {},
        "account":         account,
        "positions":       positions,
        "portfolio":       live_portfolio.stats,
        "reporting":       _build_reporting_stats(live_portfolio.stats, _agent),
            "ticker_cooldowns":_agent._ticker_cd.get_status() if _agent and hasattr(_agent,'_ticker_cd') else {},
        "equity_curve":    live_portfolio.equity_curve,
        "synthetic_curve": live_portfolio.synthetic_curve,
        "recent_trades":   live_portfolio.recent_trades,
            "all_trades":      live_portfolio.all_trades,
            "trade_count":     live_portfolio.trade_count,
        "performance":     perf_dict,
        "decisions_today": today,
        "recent_decisions": recent,
        "strategy_vote_dist": _get_strategy_vote_distribution(recent),
        "market_regime": _get_market_regime(),
        "trend_states":    trend_states,
        "rally_signals":   agent_state.get("rally_signals", {}),
        "intraday_mode":   getattr(_agent._scheduler, "_intraday_mode", False) if _agent and hasattr(_agent, "_scheduler") else False,
        "intraday_interval_min": getattr(_agent._scheduler, "_intraday_interval", 2) if _agent and hasattr(_agent, "_scheduler") else 2,
        "hold_overnight":  agent_state.get("hold_overnight", {}),
        "intraday_vwap":   agent_state.get("intraday_vwap", {}),
        "watchlist":       _config.watchlist if _config else [],
        "cycle_count":     getattr(_agent, "_cycle_count", agent_state.get("cycle_count", 0)) if _agent else 0,
        "news_sentiment":  _news_cache,
        "discipline":      _agent.discipline_status() if _agent and hasattr(_agent, 'discipline_status') else {},
        "conviction_breakdown": _agent.last_conviction_breakdown() if _agent and hasattr(_agent, 'last_conviction_breakdown') else {},
    }

@app.post("/api/configure")
async def configure(payload: ConfigPayload):
    global _config, _agent, _executor
    _config = _build_config(payload)
    _save_config_to_disk(_config)
    if _executor is None:
        try:
            _executor = AlpacaExecutor(api_key=app_cfg.alpaca_api_key, secret_key=app_cfg.alpaca_secret_key, paper=_config.paper_trading)
            _executor.connect()
        except Exception as e:
            logger.error(f"Executor error: {e}"); _executor = None
    if _agent: _agent.reconfigure(_config)
    _config.save()

    # Init news fetcher
    global _news_fetcher, _sentiment_eng
    if _news_fetcher is None:
        _news_fetcher = NewsFetcher(
            alpaca_api_key    = app_cfg.alpaca_api_key,
            alpaca_secret_key = app_cfg.alpaca_secret_key,
        )
        _sentiment_eng = SentimentEngine(api_key=app_cfg.anthropic_api_key)

    await ws_manager.broadcast({"type": "config_updated", "config": _config.to_dict()})
    return {"status": "configured", "approach": (_config.approach.value if hasattr(_config.approach, "value") else _config.approach)}

@app.post("/api/agent/start")
async def start_agent():
    global _agent, _config
    if not _config: return {"error": "Configure first"}
    if _agent and _agent.status == AgentStatus.RUNNING: return {"status": "already_running"}
    # Ensure approach is always a proper Enum before creating agent
    try:
        from decision_engine.agent_config import Approach
        if isinstance(_config.approach, str):
            _config.approach = Approach(_config.approach)
    except Exception:
        pass
    _agent = TradingAgent(_config)
    # Get the running event loop so background threads can safely call it
    loop = asyncio.get_event_loop()

    def on_dec(d):
        data = {"type": "decision", "symbol": d.symbol, "action": d.action,
                "conviction": d.conviction_score,
                "reason": d.top_reasons[0] if d.top_reasons else "",
                "shares": d.shares, "approved": d.approved}
        loop.call_soon_threadsafe(asyncio.ensure_future, ws_manager.broadcast(data))

    def on_st(s):
        loop.call_soon_threadsafe(asyncio.ensure_future, ws_manager.broadcast({"type": "status", "status": str(s)}))

    _agent.on_decision(on_dec)
    _agent.on_status_change(on_st)
    _agent.start()
    # Always activate intraday mode immediately after agent starts
    import threading as _th, time as _time
    def _auto_intraday():
        _time.sleep(2)  # let agent thread fully initialize
        try:
            if _agent and hasattr(_agent, '_scheduler'):
                interval = getattr(_config, 'intraday_interval_min', 2) if _config else 2
                _agent._scheduler.set_intraday_mode(True, interval)
                logger.info(f"[API] Intraday mode AUTO-ON ✓ ({interval} min)")
        except Exception as _e:
            logger.warning(f"[API] Intraday auto-on failed: {_e}")
    _th.Thread(target=_auto_intraday, daemon=True).start()
    if not os.path.exists(SAVE_PATH): _save_config_to_disk(_config)  # only create file if missing — never overwrite on start
    await ws_manager.broadcast({"type": "status", "status": "running"})
    return {"status": "started"}

@app.post("/api/agent/pause")
async def pause_agent():
    if _agent: _agent.pause()
    await ws_manager.broadcast({"type": "status", "status": "paused"})
    return {"status": "paused"}

@app.post("/api/agent/resume")
async def resume_agent():
    if _agent: _agent.resume()
    await ws_manager.broadcast({"type": "status", "status": "running"})
    return {"status": "resumed"}

@app.post("/api/agent/stop")
async def stop_agent():
    if _agent: _agent.stop()
    await ws_manager.broadcast({"type": "status", "status": "stopped"})
    return {"status": "stopped"}

@app.post("/api/agent/scan")
async def force_scan():
    if _agent: _agent.force_scan(); return {"status": "triggered"}
    return {"error": "Agent not running"}

@app.get("/api/decisions")
def get_decisions(limit: int = 50): return {"decisions": [vars(r) for r in _d_logger.recent(limit)]}

@app.get("/api/premarket")
def get_premarket_scores():
    """Get pre-market heat scores for all watchlist symbols."""
    try:
        if not _agent or not getattr(_agent, '_premarket_scanner', None):
            return {"error": "Pre-market scanner not available"}
        watchlist = _config.watchlist if _config else []
        scores = _agent._premarket_scanner.scan(watchlist, top_n=len(watchlist))
        return {
            "scores": [
                {
                    "symbol":     s.symbol,
                    "heat_score": s.heat_score,
                    "gap_pct":    s.gap_pct,
                    "vol_ratio":  s.vol_ratio,
                    "rsi":        s.rsi,
                    "above_ma5":  s.above_ma5,
                    "above_ma20": s.above_ma20,
                    "reason":     s.reason,
                }
                for s in scores
            ],
            "top_pick": scores[0].symbol if scores else None,
            "time_et":  datetime.now(ET).strftime("%H:%M ET") if "ET" in dir() else "N/A"
        }
    except Exception as e:
        logger.error(f"Premarket scan error: {e}")
        return {"error": str(e)}


@app.post("/api/intraday_mode")
def set_intraday_mode(body: dict = {}):
    """Enable/disable intraday fast-scan mode (2-min intervals + auto-close 3:45 PM)."""
    try:
        enabled  = body.get("enabled", False)
        interval = int(body.get("interval_minutes", 2))
        if _agent and hasattr(_agent, "_scheduler"):
            _agent._scheduler.set_intraday_mode(enabled, interval)
            # Persist to config so it survives restarts
            if _config:
                _config.intraday_mode = enabled
                _config.intraday_interval_min = interval
                _save_config_to_disk(_config)
            return {"success": True, "intraday_mode": enabled, "interval_minutes": interval}
        return {"error": "Agent not running"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/close_all")
def close_all_positions():
    """Close all open positions immediately."""
    try:
        if not _agent:
            return {"error": "Agent not running"}
        _agent._close_all_positions("Manual close-all from dashboard")
        return {"success": True, "message": "All positions closed"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/debug_intraday")
def debug_intraday():
    """Test 15-min bar fetch via DataManager — shows exact error."""
    try:
        from datetime import datetime, timedelta, timezone
        if not _agent:
            return {"error": "Agent not initialized — wait 10s and retry"}
        dm = getattr(_agent, "_data_manager", None)
        if not dm:
            return {"error": "No _data_manager on agent"}
        start = datetime.now(timezone.utc) - timedelta(hours=7)
        df = dm.get_bars_df("AAPL", "15Min", start=start, limit=30)
        if df is None:
            return {"success": False, "error": "get_bars_df returned None"}
        return {
            "success":  True,
            "symbol":   "AAPL",
            "bars":     len(df),
            "columns":  list(df.columns),
            "latest":   {
                "close":  round(float(df["close"].iloc[-1]), 2),
                "volume": int(df["volume"].iloc[-1]) if "volume" in df.columns else None,
            } if len(df) > 0 else {}
        }
    except Exception as e:
        return {"success": False, "error": str(e), "type": type(e).__name__}


@app.post("/api/clean_trades")
def clean_trades():
    """Remove corrupted trades without wiping all history."""
    try:
        live_p = (getattr(_agent, "_portfolio", None) or _portfolio) if _agent else _portfolio
        removed = live_p.clean_bad_trades(max_single_pnl=500.0)
        stats = live_p.stats
        return {"removed": removed, "remaining": stats.get("total_trades", 0), "message": f"Cleaned {removed} bad trades"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/scan_stocks")
def scan_stocks(top_n: int = 15):
    """Run the stock scanner and return top candidates."""
    try:
        if not _agent:
            return {"error": "Agent not running"}
        if not getattr(_agent, '_scanner', None):
            return {"error": "Scanner not available — restart agent"}
        pinned = _config.watchlist[:8] if _config else []
        candidates = _agent._scanner.scan(top_n=top_n, pinned=pinned)
        return {
            "candidates": [
                {
                    "symbol":       c.symbol,
                    "score":        c.score,
                    "rsi":          c.rsi,
                    "adx":          c.adx,
                    "vol_ratio":    c.vol_ratio,
                    "momentum_pct": c.momentum_pct,
                    "above_ma20":   c.above_ma20,
                    "reason":       c.reason,
                }
                for c in candidates
            ]
        }
    except Exception as e:
        logger.error(f"Scanner error: {e}")
        return {"error": str(e)}


@app.post("/api/apply_scan_results")
def apply_scan_results(body: dict):
    """Add scanner results to the watchlist."""
    try:
        symbols = body.get("symbols", [])
        if not _config or not symbols:
            return {"error": "No config or symbols"}
        current = list(_config.watchlist)
        added = []
        for s in symbols:
            s = s.upper()
            if s not in current:
                current.append(s)
                added.append(s)
        _config.watchlist = current
        if _agent:
            _agent.config.watchlist = current
        return {"added": added, "watchlist": current}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/performance")
def get_performance():
    try:
        live_p = (getattr(_agent, "_portfolio", None) or _portfolio) if _agent else _portfolio
        report = _analyzer.analyze(live_p._trades, live_p._snapshots, live_p._starting_value or 100000)
        ranks  = _ranker.rank(live_p._trades) if live_p._trades else []
        return {"report": vars(report), "rankings": [vars(r) for r in ranks], "trades": live_p.all_trades, "equity": live_p.equity_curve}
    except Exception as e:
        logger.error(f"[Performance] Error: {e}")
        return {"report": {}, "rankings": [], "trades": [], "equity": []}

@app.get("/api/news")
def get_news(symbol: str = ""):
    """Return cached news and sentiment for all watchlist symbols or one symbol."""
    if symbol:
        return _news_cache.get(symbol, {"symbol": symbol, "articles": [], "sources_hit": []})
    return {"news": _news_cache}

@app.post("/api/news/refresh")
async def refresh_news():
    """Manually trigger a news fetch for the full watchlist."""
    import threading
    def _fetch():
        global _news_cache
        if not _news_fetcher or not _config:
            return
        watchlist = _config.watchlist or []
        news_map  = _news_fetcher.fetch_watchlist(watchlist)
        scores    = _sentiment_eng.score_watchlist(news_map)
        _news_cache = {sym: s.to_dict() for sym, s in scores.items()}
        logger.info(f"[News] Refreshed {len(_news_cache)} symbols")
    threading.Thread(target=_fetch, daemon=True).start()
    return {"status": "refreshing"}

@app.get("/api/top_movers")
async def get_top_movers(approach: str = "Balanced"):
    """
    Returns top momentum stocks for the given approach.
    Fetches real-time data from Yahoo Finance screener.
    Falls back to curated defaults if fetch fails.
    """
    import threading, urllib.request, json as _json

    DEFAULTS = {
        "Profit Maximizer": ["TSLA","NVDA","AMD","MU","AVGO","META","AMZN","ORCL"],
        "Aggressive":        ["TSLA","COIN","NVDA","AMD","PLTR","MSTR","SNAP"],
        "Balanced":          ["AAPL","NVDA","MSFT","AMZN","META","GOOGL","JPM"],
        "Conservative":      ["AAPL","MSFT","GOOGL","JPM","WMT","SPY"],
        "Long Term":         ["AAPL","NVDA","MSFT","AMZN","META","GOOGL","AVGO"],
    }

    try:
        # Try Yahoo Finance most active / gainers
        url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds=most_actives&count=20"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read().decode())

        quotes = data.get("finance",{}).get("result",[{}])[0].get("quotes",[])

        # Filter: price > $5, volume > 5M, positive change
        symbols = []
        for q in quotes:
            sym    = q.get("symbol","")
            price  = q.get("regularMarketPrice", 0)
            vol    = q.get("regularMarketVolume", 0)
            change = q.get("regularMarketChangePercent", 0)
            # Only large-cap tradeable symbols for paper trading
            if (price > 5 and vol > 5_000_000 and
                len(sym) <= 5 and "." not in sym):
                symbols.append(sym)

        if approach == "Profit Maximizer":
            # Sort by volume — want highest momentum
            symbols = symbols[:10]
        else:
            symbols = symbols[:8]

        if symbols:
            return {"symbols": symbols, "source": "live", "approach": approach}
    except Exception as e:
        logger.debug(f"[TopMovers] Live fetch failed: {e}")

    # Fallback to curated defaults
    return {"symbols": DEFAULTS.get(approach, DEFAULTS["Balanced"]), "source": "default", "approach": approach}

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({"type": "connected", "state": get_state()})
        while True:
            data = await websocket.receive_text()
            if data == "ping": await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect: ws_manager.disconnect(websocket)

frontend_build = os.path.join(os.path.dirname(__file__), "..", "frontend", "build")
if os.path.exists(frontend_build):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_build, "static")), name="static")
    @app.get("/{full_path:path}")
    def serve_react(full_path: str): return FileResponse(os.path.join(frontend_build, "index.html"))

# ── DEV: file reader endpoint (Claude access) ──────────────────────────
@app.get("/api/dev/file")
async def read_file(path: str):
    """Read any file relative to trading_agent root. Dev use only."""
    import os
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    full = os.path.abspath(os.path.join(base, path))
    if not full.startswith(base):
        return {"error": "path outside project"}
    try:
        with open(full) as f:
            return {"path": path, "content": f.read()}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/dev/write")
async def write_file(payload: dict):
    """Write content to a file relative to trading_agent root. Dev use only."""
    import os
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    full = os.path.abspath(os.path.join(base, payload.get("path", "")))
    if not full.startswith(base):
        return {"error": "path outside project"}
    try:
        with open(full, "w") as f:
            f.write(payload.get("content", ""))
        return {"ok": True, "path": payload["path"]}
    except Exception as e:
        return {"error": str(e)}
