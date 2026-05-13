# -*- coding: utf-8 -*-
"""
Bollinger Bands
---------------
A volatility indicator: a middle SMA band with upper/lower bands
placed 2 standard deviations away (default).

Signals:
  BUY  (STRONG)   : Price touches/breaks BELOW lower band (oversold)
  BUY  (MODERATE) : Price bouncing up from lower band area
  SELL (STRONG)   : Price touches/breaks ABOVE upper band (overbought)
  SELL (MODERATE) : Price pulling back from upper band area
  NEUTRAL         : Price within bands, bandwidth normal
  
  SQUEEZE detected: Bands tightening -- big move incoming (direction unknown)
"""

import pandas as pd
from .base import Signal, SignalDirection, SignalStrength


def calculate_bollinger_bands(
    df:       pd.DataFrame,
    period:   int   = 20,
    std_dev:  float = 2.0,
) -> pd.DataFrame:
    """
    Compute Bollinger Bands.

    Returns:
        DataFrame with columns: upper, middle, lower, bandwidth, pct_b
    """
    middle = df["close"].rolling(window=period).mean()
    std    = df["close"].rolling(window=period).std()

    upper     = middle + (std * std_dev)
    lower     = middle - (std * std_dev)
    bandwidth = (upper - lower) / middle                     # volatility measure
    pct_b     = (df["close"] - lower) / (upper - lower)     # 0=lower band, 1=upper band

    return pd.DataFrame({
        "upper":     upper,
        "middle":    middle,
        "lower":     lower,
        "bandwidth": bandwidth,
        "pct_b":     pct_b,
    }, index=df.index)


def bollinger_signal(
    symbol:   str,
    df:       pd.DataFrame,
    period:   int   = 20,
    std_dev:  float = 2.0,
) -> Signal:
    """
    Generate a trading signal from Bollinger Bands position.

    Args:
        symbol:  Ticker symbol
        df:      OHLCV DataFrame from DataManager.get_bars_df()
        period:  SMA period (default 20)
        std_dev: Standard deviations for band width (default 2.0)

    Returns:
        Signal with direction BUY / SELL / NEUTRAL
    """
    if len(df) < period + 5:
        raise ValueError(f"Need at least {period + 5} bars, got {len(df)}")

    bb        = calculate_bollinger_bands(df, period, std_dev)
    timestamp = df.index[-1].to_pydatetime()

    price      = float(df["close"].iloc[-1])
    prev_price = float(df["close"].iloc[-2])
    upper      = float(bb["upper"].iloc[-1])
    middle     = float(bb["middle"].iloc[-1])
    lower      = float(bb["lower"].iloc[-1])
    pct_b      = float(bb["pct_b"].iloc[-1])
    bandwidth  = float(bb["bandwidth"].iloc[-1])
    prev_bw    = float(bb["bandwidth"].iloc[-2])

    # Squeeze: bands tightening (volatility compression before big move)
    squeeze = bandwidth < bb["bandwidth"].rolling(20).mean().iloc[-1] * 0.8

    if price <= lower:
        direction = SignalDirection.BUY
        strength  = SignalStrength.STRONG
        reason    = f"Price {price:.2f} at/below lower band {lower:.2f}"
    elif pct_b < 0.2 and price > prev_price:
        direction = SignalDirection.BUY
        strength  = SignalStrength.MODERATE
        reason    = f"Price bouncing up from lower band area (pct_b={pct_b:.2f})"
    elif price >= upper:
        direction = SignalDirection.SELL
        strength  = SignalStrength.STRONG
        reason    = f"Price {price:.2f} at/above upper band {upper:.2f}"
    elif pct_b > 0.8 and price < prev_price:
        direction = SignalDirection.SELL
        strength  = SignalStrength.MODERATE
        reason    = f"Price pulling back from upper band (pct_b={pct_b:.2f})"
    else:
        direction = SignalDirection.NEUTRAL
        strength  = SignalStrength.NONE
        reason    = f"Price within bands (pct_b={pct_b:.2f})"
        if squeeze:
            reason += " -- SQUEEZE detected, big move incoming"

    return Signal(
        indicator = "BB",
        symbol    = symbol,
        timestamp = timestamp,
        direction = direction,
        strength  = strength,
        value     = pct_b,
        reason    = reason,
        details   = {
            "price":     price,
            "upper":     upper,
            "middle":    middle,
            "lower":     lower,
            "pct_b":     pct_b,
            "bandwidth": bandwidth,
            "squeeze":   squeeze,
        },
    )
