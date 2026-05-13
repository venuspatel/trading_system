# -*- coding: utf-8 -*-
"""
RSI - Relative Strength Index
------------------------------
Measures momentum by comparing average gains vs average losses
over a rolling window (default 14 periods).

Signals:
  BUY  (STRONG)   : RSI < 30  -- oversold, likely reversal up
  BUY  (MODERATE) : RSI 30-40 -- recovering from oversold
  SELL (STRONG)   : RSI > 70  -- overbought, likely reversal down
  SELL (MODERATE) : RSI 60-70 -- approaching overbought
  NEUTRAL         : RSI 40-60 -- no clear signal
"""

from datetime import timezone
import pandas as pd
from .base import Signal, SignalDirection, SignalStrength


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute RSI for a price DataFrame.

    Args:
        df:     DataFrame with a 'close' column (from DataManager)
        period: Lookback window, default 14

    Returns:
        pd.Series of RSI values (0-100), same index as df
    """
    delta  = df["close"].diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs  = avg_gain / avg_loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    return rsi.rename("rsi")


def rsi_signal(
    symbol: str,
    df:     pd.DataFrame,
    period: int = 14,
    oversold:   float = 30.0,
    overbought: float = 70.0,
) -> Signal:
    """
    Generate a trading signal from the latest RSI value.

    Args:
        symbol:     Ticker symbol
        df:         OHLCV DataFrame from DataManager.get_bars_df()
        period:     RSI period (default 14)
        oversold:   RSI level considered oversold (default 30)
        overbought: RSI level considered overbought (default 70)

    Returns:
        Signal with direction BUY / SELL / NEUTRAL
    """
    if len(df) < period + 1:
        raise ValueError(f"Need at least {period + 1} bars, got {len(df)}")

    rsi_series = calculate_rsi(df, period)
    rsi_val    = float(rsi_series.iloc[-1])
    prev_rsi   = float(rsi_series.iloc[-2])
    timestamp  = df.index[-1].to_pydatetime()

    # Determine direction + strength
    if rsi_val < oversold:
        direction = SignalDirection.BUY
        strength  = SignalStrength.STRONG
        reason    = f"RSI {rsi_val:.1f} is oversold (< {oversold})"
    elif rsi_val < oversold + 10:
        direction = SignalDirection.BUY
        strength  = SignalStrength.MODERATE
        reason    = f"RSI {rsi_val:.1f} recovering from oversold"
    elif rsi_val > overbought:
        direction = SignalDirection.SELL
        strength  = SignalStrength.STRONG
        reason    = f"RSI {rsi_val:.1f} is overbought (> {overbought})"
    elif rsi_val > overbought - 10:
        direction = SignalDirection.SELL
        strength  = SignalStrength.MODERATE
        reason    = f"RSI {rsi_val:.1f} approaching overbought"
    else:
        direction = SignalDirection.NEUTRAL
        strength  = SignalStrength.NONE
        reason    = f"RSI {rsi_val:.1f} in neutral zone"

    return Signal(
        indicator = "RSI",
        symbol    = symbol,
        timestamp = timestamp,
        direction = direction,
        strength  = strength,
        value     = rsi_val,
        reason    = reason,
        details   = {
            "rsi":         rsi_val,
            "prev_rsi":    prev_rsi,
            "period":      period,
            "oversold":    oversold,
            "overbought":  overbought,
            "trending_up": rsi_val > prev_rsi,
        },
    )
