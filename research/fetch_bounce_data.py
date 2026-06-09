#!/usr/bin/env python3
"""
fetch_bounce_data.py  —  RUN THIS ON YOUR MAC (not in the chat sandbox)

Pulls ~30 trading days of 1-minute OHLCV for a wide set of tickers that had a
rough June 5, plus warmup. Writes ONE csv per symbol into ./bounce_data/.
The backtest harness reads everything in that folder — you don't have to name
days or label regimes; the harness auto-classifies each symbol-day by its move.

USAGE:
    cd ~/Desktop/trading_system/trading_agent
    python3 fetch_bounce_data.py

Then upload the whole ./bounce_data/ folder's CSVs to the chat (or zip it).

NOTE: paper keys are fine for market data. Rotate them after, per the security
note — they've been exposed in chat.
"""

import os
import time
import pandas as pd

# ── Uses YOUR existing provider so creds/config match production exactly ──
from data_layer import DataManager, AlpacaProvider

# ----------------------------------------------------------------------------
# CONFIG — edit if you like
# ----------------------------------------------------------------------------
API_KEY    = "PKUPVN2TBTLKAUHOQLIMWGK4BM"          # V1 paper key (rotate after!)
SECRET_KEY = "3Y1FwQmVvL7uzWkFELzUGJeXJZ5a8qoboFcWPD1mcn1Q"

# Wide set: mega-cap tech + semis + names that sold off hard June 5.
# More tickers = more behavior observed. Trim if any aren't tradable.
SYMBOLS = [
    "MSFT", "AVGO", "MU", "NVDA", "AMD", "TSLA", "AAPL", "AMZN", "GOOGL",
    "META", "QCOM", "INTC", "NFLX", "CRM", "ADBE", "ORCL", "PLTR", "SMCI",
    "ARM", "DELL", "TSM", "ASML", "LRCX", "KLAC", "MRVL",
]

# ~30 trading days back from June 5 + a couple warmup days before the window.
# Calendar window generously covers ~30 sessions (weekends/holidays excluded by
# the data feed automatically). Adjust START earlier if you want more.
START = "2026-04-21T00:00:00Z"   # ~7 weeks back -> ~30 trading days
END   = "2026-06-06T00:00:00Z"   # through June 5 close

TIMEFRAME = "1Min"
OUT_DIR   = "bounce_data"
BAR_LIMIT = 60000   # plenty for 30 days of 1-min (~11.7k bars/symbol)
# ----------------------------------------------------------------------------


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    provider = AlpacaProvider(api_key=API_KEY, secret_key=SECRET_KEY, paper=True)
    dm = DataManager(provider=provider, bar_cache_size=5000)
    dm.connect()

    ok, fail = [], []
    for sym in SYMBOLS:
        try:
            df = dm.get_bars_df(sym, TIMEFRAME, start=START, limit=BAR_LIMIT)
            if df is None or len(df) == 0:
                fail.append((sym, "no bars"))
                print(f"  {sym}: NO DATA")
                continue
            cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
            df = df[cols].copy().reset_index()
            df.rename(columns={df.columns[0]: "t"}, inplace=True)
            df["t"] = df["t"].astype(str)
            # keep only through END
            df = df[df["t"] < END]
            path = os.path.join(OUT_DIR, f"{sym}_1min.csv")
            df.to_csv(path, index=False)
            ndays = pd.to_datetime(df["t"]).dt.date.nunique()
            ok.append((sym, len(df), ndays))
            print(f"  {sym}: {len(df):>6} bars across {ndays} sessions -> {path}")
            time.sleep(0.3)  # be gentle on the API
        except Exception as e:
            fail.append((sym, str(e)[:80]))
            print(f"  {sym}: ERROR {e}")

    print("\n" + "=" * 60)
    print(f"DONE. {len(ok)} symbols written to ./{OUT_DIR}/")
    if fail:
        print(f"{len(fail)} failed: {[f[0] for f in fail]}")
    print(f"\nUpload the CSVs in ./{OUT_DIR}/ to the chat (zip the folder if easier).")


if __name__ == "__main__":
    main()
