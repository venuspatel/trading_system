"""
Layer 1 quick-start example
----------------------------
Run this script to verify your Alpaca connection is working.

Before running:
    1. pip install alpaca-py pandas python-dotenv
    2. Copy .env.example to .env and fill in your Alpaca keys
    3. python examples/layer1_quickstart.py

Expected output:
    [DataManager] Connected via Alpaca
    Market open: False  (or True during market hours)
    Fetched 30 bars for AAPL
                           open    high     low   close      volume
    timestamp
    2024-...              182.15  183.90  181.60  183.42  54321000.0
    ...

    Latest AAPL bar: Bar(symbol='AAPL', timestamp=..., close=183.42)
    Streaming quotes for 60 seconds...  (Ctrl+C to stop)
"""

import logging
import time
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import cfg
from data_layer import AlpacaProvider, DataManager

# ── Logging setup ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=cfg.log_level,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("layer1_quickstart")


# ── 1. Build the provider and data manager ─────────────────────────────────
provider = AlpacaProvider(
    api_key    = cfg.alpaca_api_key,
    secret_key = cfg.alpaca_secret_key,
    paper      = cfg.alpaca_paper,
)

manager = DataManager(provider=provider, bar_cache_size=cfg.bar_cache_size)
manager.connect()


# ── 2. Check market status ─────────────────────────────────────────────────
print(f"\nMarket open: {manager.is_market_open()}")


# ── 3. Fetch 30 days of daily bars ────────────────────────────────────────
symbol = "AAPL"
start  = datetime(2024, 1, 1, tzinfo=timezone.utc)

print(f"\nFetching daily bars for {symbol}...")
df = manager.get_bars_df(symbol, "1Day", start=start, limit=30)
print(f"Fetched {len(df)} bars\n")
print(df.tail(5).to_string())


# ── 4. Latest bar ──────────────────────────────────────────────────────────
latest = manager.get_latest_bar(symbol)
print(f"\nLatest {symbol} bar: {latest}")


# ── 5. Warm the cache for all watchlist symbols ────────────────────────────
print(f"\nWarming cache for watchlist: {cfg.watchlist}")
manager.warm_cache(cfg.watchlist, "1Day", lookback_days=cfg.warmup_lookback_days)


# ── 6. Stream live quotes (only meaningful during market hours) ───────────
def on_quote(q):
    print(f"  QUOTE  {q.symbol:6s}  bid={q.bid:.4f}  ask={q.ask:.4f}  "
          f"spread={q.spread:.4f}  mid={q.mid:.4f}")

def on_bar(b):
    print(f"  BAR    {b.symbol:6s}  close={b.close:.4f}  vol={b.volume:,.0f}")

if manager.is_market_open():
    print(f"\nStreaming live quotes + bars for {cfg.watchlist[:2]} (60 sec)...")
    print("(Press Ctrl+C to stop early)\n")
    manager.subscribe_quotes(cfg.watchlist[:2], callback=on_quote)
    manager.subscribe_bars(cfg.watchlist[:2], callback=on_bar)
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        print("\nStopped by user.")
else:
    print("\nMarket is closed -- skipping live stream.")
    print("To test streaming, run again Mon-Fri between 9:30am-4:00pm Eastern Time.")

manager.disconnect()
print("\nLayer 1 complete. Ready for Layer 2!")
