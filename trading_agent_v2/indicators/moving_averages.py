# -*- coding: utf-8 -*-
"""
Moving Averages - Trend Direction
-----------------------------------
Tracks SMA 20, 50, and 200 to determine short, medium, and long-term trend.

Signals:
  BUY  (STRONG)   : Golden Cross -- SMA50 crosses above SMA200
  BUY  (MODERATE) : Price above SMA20 and SMA50; SMA50 > SMA200
  SELL (STRONG)   : Death Cross  -- SMA50 crosses below SMA200
  SELL (MODERATE) : Price below SMA20 and SMA50; SMA50 < SMA200
  NEUTRAL         : Mixed signals or price between MAs
"""

import pandas as pd
from .base import Signal, SignalDirection, SignalStrength


def calculate_moving_averages(
    df: pd.DataFrame,
    periods: list = None,
) -> pd.DataFrame:
    """
    Compute multiple SMAs and EMAs.

    Returns:
        DataFrame with sma_20, sma_50, sma_200, ema_9, ema_21
    """
    if periods is None:
        periods = [20, 50, 200]

    result = {}
    for p in periods:
        result[f"sma_{p}"] = df["close"].rolling(window=p).mean()

    result["ema_9"]  = df["close"].ewm(span=9,  adjust=False).mean()
    result["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()

    return pd.DataFrame(result, index=df.index)


def moving_average_signal(
    symbol: str,
    df:     pd.DataFrame,
) -> Signal:
    """
    Generate a trend signal from moving average relationships.

    Args:
        symbol: Ticker symbol
        df:     OHLCV DataFrame from DataManager.get_bars_df()
                (needs at least 200 bars for full signal, 50 for partial)

    Returns:
        Signal with direction BUY / SELL / NEUTRAL
    """
    if len(df) < 52:
        raise ValueError(f"Need at least 52 bars for MA signal, got {len(df)}")

    has_200 = len(df) >= 202

    mas       = calculate_moving_averages(df)
    timestamp = df.index[-1].to_pydatetime()
    price     = float(df["close"].iloc[-1])

    sma20      = float(mas["sma_20"].iloc[-1])
    sma50      = float(mas["sma_50"].iloc[-1])
    prev_sma50 = float(mas["sma_50"].iloc[-2])

    sma200     = float(mas["sma_200"].iloc[-1]) if has_200 else None
    prev_sma200= float(mas["sma_200"].iloc[-2]) if has_200 else None

    ema9       = float(mas["ema_9"].iloc[-1])
    ema21      = float(mas["ema_21"].iloc[-1])

    # Golden / Death Cross (SMA50 vs SMA200)
    golden_cross = has_200 and prev_sma50 <= prev_sma200 and sma50 > sma200
    death_cross  = has_200 and prev_sma50 >= prev_sma200 and sma50 < sma200

    # Trend alignment
    bullish_alignment = (
        price > sma20 > sma50 and
        (not has_200 or sma50 > sma200) and
        ema9 > ema21
    )
    bearish_alignment = (
        price < sma20 < sma50 and
        (not has_200 or sma50 < sma200) and
        ema9 < ema21
    )

    if golden_cross:
        direction = SignalDirection.BUY
        strength  = SignalStrength.STRONG
        reason    = f"Golden Cross: SMA50 ({sma50:.2f}) crossed above SMA200 ({sma200:.2f})"
    elif death_cross:
        direction = SignalDirection.SELL
        strength  = SignalStrength.STRONG
        reason    = f"Death Cross: SMA50 ({sma50:.2f}) crossed below SMA200 ({sma200:.2f})"
    elif bullish_alignment:
        direction = SignalDirection.BUY
        strength  = SignalStrength.MODERATE
        reason    = f"Bullish alignment: price {price:.2f} > SMA20 {sma20:.2f} > SMA50 {sma50:.2f}"
    elif bearish_alignment:
        direction = SignalDirection.SELL
        strength  = SignalStrength.MODERATE
        reason    = f"Bearish alignment: price {price:.2f} < SMA20 {sma20:.2f} < SMA50 {sma50:.2f}"
    else:
        direction = SignalDirection.NEUTRAL
        strength  = SignalStrength.NONE
        reason    = f"Mixed MA signals (price={price:.2f}, SMA20={sma20:.2f}, SMA50={sma50:.2f})"

    return Signal(
        indicator = "MA",
        symbol    = symbol,
        timestamp = timestamp,
        direction = direction,
        strength  = strength,
        value     = price / sma50,     # price-to-SMA50 ratio
        reason    = reason,
        details   = {
            "price":        price,
            "sma_20":       sma20,
            "sma_50":       sma50,
            "sma_200":      sma200,
            "ema_9":        ema9,
            "ema_21":       ema21,
            "golden_cross": golden_cross,
            "death_cross":  death_cross,
            "above_sma20":  price > sma20,
            "above_sma50":  price > sma50,
            "above_sma200": price > sma200 if has_200 else None,
        },
    )
