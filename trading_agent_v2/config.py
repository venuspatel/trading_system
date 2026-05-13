"""
config.py — central configuration for the trading agent
--------------------------------------------------------
All settings live here. Values are read from environment variables
(or a .env file) so secrets never touch source code.

Usage:
    from trading_agent.config import cfg
    print(cfg.alpaca_api_key)
"""

import os
from dataclasses import dataclass, field
from typing import List

# Load .env file if python-dotenv is available (optional but recommended)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Config:

    # ------------------------------------------------------------------
    # Active provider  ("alpaca" | "ibkr" | "binance")
    # ------------------------------------------------------------------
    active_provider: str = field(
        default_factory=lambda: os.getenv("ACTIVE_PROVIDER", "alpaca")
    )

    # ------------------------------------------------------------------
    # Alpaca
    # ------------------------------------------------------------------
    alpaca_api_key:    str  = field(default_factory=lambda: os.getenv("ALPACA_API_KEY",    ""))
    alpaca_secret_key: str  = field(default_factory=lambda: os.getenv("ALPACA_SECRET_KEY", ""))
    alpaca_paper:      bool = field(default_factory=lambda: os.getenv("ALPACA_PAPER", "true").lower() != "false")

    # ------------------------------------------------------------------
    # IBKR  (stub — fill in when ready)
    # ------------------------------------------------------------------
    ibkr_host:      str = field(default_factory=lambda: os.getenv("IBKR_HOST",      "127.0.0.1"))
    ibkr_port:      int = field(default_factory=lambda: int(os.getenv("IBKR_PORT",  "7497")))
    ibkr_client_id: int = field(default_factory=lambda: int(os.getenv("IBKR_CLIENT_ID", "1")))

    # ------------------------------------------------------------------
    # Binance  (stub — fill in when ready)
    # ------------------------------------------------------------------
    binance_api_key:    str  = field(default_factory=lambda: os.getenv("BINANCE_API_KEY",    ""))
    binance_secret_key: str  = field(default_factory=lambda: os.getenv("BINANCE_SECRET_KEY", ""))
    binance_testnet:    bool = field(default_factory=lambda: os.getenv("BINANCE_TESTNET", "true").lower() != "false")

    # ------------------------------------------------------------------
    # Watchlist — symbols the agent monitors
    # ------------------------------------------------------------------
    watchlist: List[str] = field(default_factory=lambda: [
        sym.strip()
        for sym in os.getenv("WATCHLIST", "AAPL,TSLA,NVDA,MSFT,AMZN").split(",")
        if sym.strip()
    ])

    # ------------------------------------------------------------------
    # Data layer settings
    # ------------------------------------------------------------------
    default_timeframe:   str = field(default_factory=lambda: os.getenv("DEFAULT_TIMEFRAME", "1Day"))
    bar_cache_size:      int = field(default_factory=lambda: int(os.getenv("BAR_CACHE_SIZE", "500")))
    warmup_lookback_days: int = field(default_factory=lambda: int(os.getenv("WARMUP_DAYS", "60")))

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # ------------------------------------------------------------------
    # Anthropic API — for AI trade reviewer (optional)
    # ------------------------------------------------------------------
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))


# Singleton — import `cfg` anywhere in the project
cfg = Config()
