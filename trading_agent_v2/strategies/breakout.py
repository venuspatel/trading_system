# -*- coding: utf-8 -*-
"""
Strategy 3: Breakout
---------------------
Detects when price breaks through key support/resistance
with volume confirmation — signals the start of a new move.

Entry BUY:
  - Price breaks above resistance level
  - Volume >= 1.5x average (confirms institutional participation)
  - Bollinger squeeze was detected (energy buildup before break)

Entry SELL:
  - Price breaks below support level
  - Volume confirms the breakdown
"""

import pandas as pd
from .base import BaseStrategy, TradeAction, TradeSignal, StrategyRole


class BreakoutStrategy(BaseStrategy):

    def __init__(self, volume_factor=1.5, proximity=0.015):
        self.volume_factor = volume_factor
        self.proximity     = proximity     # within 1.5% of level = near it

    @property
    def name(self) -> str:
        return "Breakout"

    @property
    def description(self) -> str:
        return "Trades price breakouts above resistance or below support with volume"

    @property
    def role(self) -> str:
        return StrategyRole.TREND

    def generate_signal(self, symbol, df, summary) -> TradeSignal:
        # Fix 7: Base quality + extension cap + base-low stop + RS filter + ATR stops
        if len(df) < 30:
            return self._hold(symbol, df, "Not enough bars")

        price     = float(df["close"].iloc[-1])
        prev      = float(df["close"].iloc[-2])
        timestamp = df.index[-1].to_pydatetime()

        sr_sig = summary.signals.get("SR")
        bb_sig = summary.signals.get("BB")

        if not sr_sig:
            return self._hold(symbol, df, "No S/R data")

        resistances = sr_sig.details.get("resistance_levels", [])
        supports    = sr_sig.details.get("support_levels", [])
        squeeze     = bb_sig.details.get("squeeze", False) if bb_sig else False

        avg_vol   = float(df["volume"].rolling(20).mean().iloc[-1])
        curr_vol  = float(df["volume"].iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
        vol_ok    = vol_ratio >= self.volume_factor

        # ── Fix 7a: ATR for adaptive stops ───────────────────────────────
        try:
            hi, lo, cl = df["high"], df["low"], df["close"]
            tr    = pd.concat([hi-lo, (hi-cl.shift(1)).abs(),
                               (lo-cl.shift(1)).abs()], axis=1).max(axis=1)
            atr14 = float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            atr14 = price * 0.01

        # ── Fix 7b: Base quality — tight consolidation before breakout ────
        # Look at last 10 bars before current — tight base = low StdDev
        if len(df) >= 12:
            base_closes  = df["close"].iloc[-12:-1]
            base_std_pct = float(base_closes.std() / base_closes.mean())
            tight_base   = base_std_pct < 0.03   # StdDev < 3% = tight base
            base_low     = float(base_closes.min())
        else:
            tight_base = False
            base_low   = price * 0.97

        # ── Fix 7c: RS vs SPY — don't buy breakouts while SPY is tanking ─
        spy_df   = getattr(summary, "spy_df", None)
        spy_ok   = True
        spy_note = ""
        if spy_df is not None and len(spy_df) >= 3:
            try:
                spy_chg = (float(spy_df["close"].iloc[-1]) -
                           float(spy_df["close"].iloc[-3])) / float(spy_df["close"].iloc[-3])
                spy_ok  = spy_chg > -0.015   # SPY down >1.5% in 3 bars = avoid breakouts
                spy_note = f" SPY={spy_chg:+.1%}"
            except Exception:
                spy_ok = True

        confirmations = []

        # ── BUY breakout ─────────────────────────────────────────────────
        broken_resistance = [r for r in resistances
                             if prev <= r * (1 + self.proximity) and price > r]

        if broken_resistance:
            level = broken_resistance[-1]

            # Fix 7d: Extension cap — don't chase extended breakouts
            extension = (price - level) / level
            if extension > 0.03:
                return self._hold(symbol, df,
                    f"Breakout too extended: {extension:.1%} above ${level:.2f} — chasing")

            # SPY filter
            if not spy_ok:
                return self._hold(symbol, df,
                    f"Breakout blocked: SPY tanking{spy_note} — avoid false breakouts")

            confirmations.append(f"broke resistance ${level:.2f} (+{extension:.1%})")
            if vol_ok:    confirmations.append(f"volume {vol_ratio:.1f}x avg")
            if squeeze:   confirmations.append("BB squeeze released")
            if tight_base:confirmations.append(f"tight base (std={base_std_pct:.1%})")

            # Confidence: base + vol + squeeze + tight base
            confidence = (0.55
                + (0.12 if vol_ok    else 0)
                + (0.08 if squeeze   else 0)
                + (0.07 if tight_base else 0)
                - (0.05 if not tight_base else 0))  # loose base = penalty

            # Fix 7e: Stop below base low (not just below level)
            stop = min(level * 0.985, base_low * 0.99)
            tp   = price + (price - stop) * 2   # 2:1 R:R from actual stop

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.BUY,
                confidence    = round(min(confidence, 0.92), 3),
                reason        = (f"Breakout ${level:.2f} ext={extension:.1%} "
                                 f"vol={vol_ratio:.1f}x tight={tight_base}{spy_note}"),
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {
                    "broken_level":  level,
                    "extension_pct": round(extension*100, 2),
                    "volume_ratio":  round(vol_ratio, 2),
                    "tight_base":    tight_base,
                    "base_std_pct":  round(base_std_pct*100, 2) if len(df) >= 12 else None,
                    "atr14":         round(atr14, 3),
                },
            )

        # ── SELL breakdown ────────────────────────────────────────────────
        broken_support = [s for s in supports
                          if prev >= s * (1 - self.proximity) and price < s]

        if broken_support:
            level      = broken_support[0]
            extension  = (level - price) / level
            if extension > 0.03:
                return self._hold(symbol, df,
                    f"Breakdown too extended: {extension:.1%} below ${level:.2f}")

            confirmations.append(f"broke support ${level:.2f}")
            if vol_ok: confirmations.append(f"volume {vol_ratio:.1f}x avg")

            stop = level * 1.015
            tp   = price - (stop - price) * 2

            return TradeSignal(
                strategy      = self.name,
                symbol        = symbol,
                timestamp     = timestamp,
                action        = TradeAction.SELL,
                confidence    = round(min(0.55 + (0.12 if vol_ok else 0), 0.88), 3),
                reason        = f"Breakdown ${level:.2f} vol={vol_ratio:.1f}x",
                confirmations = confirmations,
                stop_loss     = round(stop, 2),
                take_profit   = round(tp, 2),
                details       = {"broken_level": level, "volume_ratio": round(vol_ratio, 2)},
            )

        return self._hold(symbol, df,
            f"No breakout: {len(resistances)} resistance levels checked")
