# -*- coding: utf-8 -*-
"""
IntradayVWAP — 15-minute bar + VWAP intraday strategy
------------------------------------------------------
VWAP (Volume Weighted Average Price) is the single most important
intraday indicator used by professional day traders and institutions.

Rules:
  BUY  — price crosses ABOVE VWAP on a 15-min bar with volume confirmation
  SELL — price crosses BELOW VWAP or momentum fades

Why this catches AMD-style moves:
  - AMD at 9:30 opens below VWAP (choppy first minutes)
  - By 9:45 AM AMD crosses above VWAP with 2x volume
  - This strategy fires a BUY at 9:45 AM
  - Daily RSI is 81 but that doesn't matter here — VWAP says it's going

Additional signals layered in:
  - Opening range breakout (first 15-min high/low)
  - VWAP slope (is VWAP itself rising?)
  - Price vs VWAP distance (don't chase if too far extended)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from .base import BaseStrategy, StrategyRole, TradeAction, TradeSignal

logger = logging.getLogger(__name__)


class IntradayVWAPStrategy(BaseStrategy):
    """
    15-minute VWAP crossover strategy for intraday momentum.
    Requires intraday bar data — fetched fresh each scan cycle.
    """

    def __init__(
        self,
        vwap_cross_min_vol: float = 1.3,   # volume must be 1.3x avg to confirm cross
        max_vwap_distance:  float = 0.025,  # don't chase if price >2.5% above VWAP
        min_bars:           int   = 4,      # need at least 4 bars of intraday data
    ):
        self.vwap_cross_min_vol = vwap_cross_min_vol
        self.max_vwap_distance  = max_vwap_distance
        self.min_bars           = min_bars

    @property
    def name(self) -> str:
        return "IntradayVWAP"

    @property
    def description(self) -> str:
        return "15-min VWAP crossover — enters when price crosses above VWAP with volume"

    @property
    def role(self) -> str:
        return StrategyRole.INTRADAY

    def generate_signal(self, symbol: str, df: pd.DataFrame, summary) -> TradeSignal:
        """
        df here is the DAILY bar df (standard input).
        We fetch 15-min bars ourselves from the data manager.
        """
        # Get intraday df from summary extras if provided
        intraday_df = getattr(summary, 'intraday_df', None)

        if intraday_df is None or len(intraday_df) < self.min_bars:
            return self._hold(symbol, df, "No intraday data available")

        try:
            return self._evaluate_vwap(symbol, df, intraday_df)
        except Exception as ex:
            logger.debug(f"[IntradayVWAP] {symbol} failed: {ex}")
            return self._hold(symbol, df, f"VWAP calc error: {ex}")

    def _evaluate_vwap(
        self, symbol: str, daily_df: pd.DataFrame, intra_df: pd.DataFrame
    ) -> TradeSignal:
        """Core VWAP logic on 15-min bars."""
        close  = intra_df["close"]
        volume = intra_df["volume"] if "volume" in intra_df.columns else pd.Series([1]*len(close))
        high   = intra_df["high"]   if "high"   in intra_df.columns else close
        low    = intra_df["low"]    if "low"    in intra_df.columns else close

        price   = float(close.iloc[-1])
        prev    = float(close.iloc[-2]) if len(close) > 1 else price
        timestamp = daily_df.index[-1].to_pydatetime() if len(daily_df) > 0 else datetime.now(timezone.utc)

        # ── Calculate VWAP ────────────────────────────────────────────
        typical = (high + low + close) / 3
        cum_vol  = volume.cumsum()
        cum_tpv  = (typical * volume).cumsum()
        vwap_series = cum_tpv / cum_vol.replace(0, float('nan'))
        vwap    = float(vwap_series.iloc[-1])
        vwap_prev = float(vwap_series.iloc[-2]) if len(vwap_series) > 1 else vwap

        # ── Volume check ──────────────────────────────────────────────
        avg_vol  = float(volume.rolling(10).mean().iloc[-1]) if len(volume) >= 10 else float(volume.mean())
        curr_vol = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        # ── Opening range (first 2 bars = first 30 min) ───────────────
        or_high = float(high.iloc[:2].max()) if len(high) >= 2 else float(high.max())
        or_low  = float(low.iloc[:2].min())  if len(low)  >= 2 else float(low.min())

        # ── VWAP distance ─────────────────────────────────────────────
        vwap_dist = (price - vwap) / vwap if vwap > 0 else 0.0

        # Fix 10: VWAP reclaim + 2-bar confirmation + ATR stops

        # ── ATR for adaptive stops ────────────────────────────────────
        try:
            hi_d, lo_d, cl_d = daily_df["high"], daily_df["low"], daily_df["close"]
            tr_d  = pd.concat([hi_d-lo_d, (hi_d-cl_d.shift(1)).abs(),
                               (lo_d-cl_d.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr_d.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── Signal logic ──────────────────────────────────────────────
        vwap_cross_up = prev <= vwap_prev and price > vwap
        above_vwap    = price > vwap
        vwap_rising   = vwap > vwap_prev
        or_breakout   = price > or_high and len(high) > 2

        # Fix 10a: 2-bar confirmation — need 2 consecutive closes above VWAP
        # Single bar above VWAP is noise, 2 bars = confirmed hold
        if len(close) >= 3:
            two_bar_confirm = (float(close.iloc[-1]) > float(vwap_series.iloc[-1]) and
                               float(close.iloc[-2]) > float(vwap_series.iloc[-2]))
        else:
            two_bar_confirm = above_vwap

        # Fix 10b: VWAP reclaim pattern — strongest VWAP signal
        # Price dips below VWAP then reclaims it = institutions defending VWAP
        if len(close) >= 4:
            dipped_below = any(float(close.iloc[i]) < float(vwap_series.iloc[i])
                               for i in range(-3, -1))
            vwap_reclaim = dipped_below and price > vwap and vwap_rising
        else:
            vwap_reclaim = False

        # ── BUY: VWAP reclaim (strongest signal) ─────────────────────
        if vwap_reclaim and vol_ratio >= self.vwap_cross_min_vol:
            if abs(vwap_dist) > self.max_vwap_distance:
                return self._hold(symbol, daily_df,
                    f"VWAP reclaim but too extended ({vwap_dist:+.1%})")
            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)
            confidence = min(0.92, 0.78 + (vol_ratio - 1.3) * 0.10)
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = round(confidence, 3),
                reason     = (f"VWAP reclaim ↑ price={price:.2f} VWAP={vwap:.2f} "
                              f"vol={vol_ratio:.1f}x (institutions defending VWAP)"),
                strategy   = self.name,
                stop_loss  = round(stop, 2),
                take_profit= round(tp, 2),
                details    = {"vwap": round(vwap,2), "vwap_dist": round(vwap_dist,4),
                              "vol_ratio": round(vol_ratio,2), "signal": "reclaim"},
            )

        # ── BUY: fresh VWAP cross with 2-bar confirmation ────────────
        if vwap_cross_up and two_bar_confirm and vol_ratio >= self.vwap_cross_min_vol:
            if abs(vwap_dist) > self.max_vwap_distance:
                return self._hold(symbol, daily_df,
                    f"VWAP cross but too extended ({vwap_dist:+.1%})")
            stop = price - (1.5 * atr14)
            tp   = price + (3.0 * atr14)
            confidence = min(0.90, 0.70 + (vol_ratio - 1.3) * 0.12)
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = round(confidence, 3),
                reason     = (f"VWAP cross ↑ confirmed price={price:.2f} "
                              f"VWAP={vwap:.2f} vol={vol_ratio:.1f}x (2-bar)"),
                strategy   = self.name,
                stop_loss  = round(stop, 2),
                take_profit= round(tp, 2),
                details    = {"vwap": round(vwap,2), "vwap_dist": round(vwap_dist,4),
                              "vol_ratio": round(vol_ratio,2), "signal": "cross"},
            )

        # ── BUY: OR breakout above VWAP ───────────────────────────────
        if or_breakout and above_vwap and vwap_rising and vol_ratio >= self.vwap_cross_min_vol:
            if abs(vwap_dist) > self.max_vwap_distance:
                return self._hold(symbol, daily_df,
                    f"OR breakout too extended ({vwap_dist:+.1%})")
            stop = price - (1.5 * atr14)
            tp   = price + (2.0 * atr14)
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.BUY,
                confidence = 0.74,
                reason     = (f"OR breakout + VWAP={vwap:.2f} vol={vol_ratio:.1f}x "
                              f"dist={vwap_dist:+.1%}"),
                strategy   = self.name,
                stop_loss  = round(stop, 2),
                take_profit= round(tp, 2),
                details    = {"vwap": round(vwap,2), "or_high": round(or_high,2),
                              "signal": "or_breakout"},
            )

        # ── SELL: price dropped below VWAP ────────────────────────────
        if not above_vwap and prev > vwap_prev:
            stop = price + (1.5 * atr14)
            tp   = price - (2.0 * atr14)
            return TradeSignal(
                symbol     = symbol,
                timestamp  = timestamp,
                action     = TradeAction.SELL,
                confidence = 0.68,
                reason     = f"VWAP cross ↓ price={price:.2f} VWAP={vwap:.2f}",
                strategy   = self.name,
                stop_loss  = round(stop, 2),
                take_profit= round(tp, 2),
                details    = {"vwap": round(vwap,2), "signal": "cross_down"},
            )

        return self._hold(
            symbol, daily_df,
            f"VWAP={vwap:.2f} price={price:.2f} dist={vwap_dist:+.1%} "
            f"vol={vol_ratio:.1f}x 2bar={two_bar_confirm}"
        )
