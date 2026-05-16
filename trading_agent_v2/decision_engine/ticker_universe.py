# -*- coding: utf-8 -*-
"""
TickerUniverse — Dynamic 60+ ticker pool across 6 market domains
----------------------------------------------------------------
Scores every ticker every refresh on:
  - Momentum       40%  (price change vs 5/20 day avg)
  - Volume surge   25%  (current vs 20-day avg volume)
  - Win streak     20%  (agent's own trade history on this ticker)
  - Regime align   15%  (does the ticker's sector match market regime?)

Claude reads these scores and picks the active watchlist dynamically.
Leveraged ETFs are tagged separately — Claude activates them only when
regime is bullish and win rate is above the threshold it deems appropriate.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SEC = 4 * 3600   # rescore every 4 hours (or on-demand)


# ── Full ticker universe ──────────────────────────────────────────────────────

UNIVERSE: Dict[str, Dict] = {
    # ── TECH ─────────────────────────────────────────────────────────────────
    "NVDA":  {"domain": "tech",    "levered": False, "desc": "NVIDIA — AI chips"},
    "AMD":   {"domain": "tech",    "levered": False, "desc": "AMD — CPUs/GPUs"},
    "TSLA":  {"domain": "tech",    "levered": False, "desc": "Tesla — EV/AI"},
    "MSFT":  {"domain": "tech",    "levered": False, "desc": "Microsoft"},
    "AAPL":  {"domain": "tech",    "levered": False, "desc": "Apple"},
    "META":  {"domain": "tech",    "levered": False, "desc": "Meta Platforms"},
    "GOOGL": {"domain": "tech",    "levered": False, "desc": "Alphabet"},
    "AMZN":  {"domain": "tech",    "levered": False, "desc": "Amazon"},
    "AVGO":  {"domain": "tech",    "levered": False, "desc": "Broadcom"},
    "ARM":   {"domain": "tech",    "levered": False, "desc": "Arm Holdings"},
    "SMCI":  {"domain": "tech",    "levered": False, "desc": "Super Micro"},
    "MU":    {"domain": "tech",    "levered": False, "desc": "Micron"},
    "ORCL":  {"domain": "tech",    "levered": False, "desc": "Oracle"},
    "CRM":   {"domain": "tech",    "levered": False, "desc": "Salesforce"},
    "QCOM":  {"domain": "tech",    "levered": False, "desc": "Qualcomm"},
    "INTC":  {"domain": "tech",    "levered": False, "desc": "Intel"},
    # ── FINANCE ──────────────────────────────────────────────────────────────
    "JPM":   {"domain": "finance", "levered": False, "desc": "JPMorgan"},
    "GS":    {"domain": "finance", "levered": False, "desc": "Goldman Sachs"},
    "BAC":   {"domain": "finance", "levered": False, "desc": "Bank of America"},
    "MS":    {"domain": "finance", "levered": False, "desc": "Morgan Stanley"},
    "V":     {"domain": "finance", "levered": False, "desc": "Visa"},
    "MA":    {"domain": "finance", "levered": False, "desc": "Mastercard"},
    "COIN":  {"domain": "finance", "levered": False, "desc": "Coinbase"},
    "HOOD":  {"domain": "finance", "levered": False, "desc": "Robinhood"},
    "PYPL":  {"domain": "finance", "levered": False, "desc": "PayPal"},
    "SQ":    {"domain": "finance", "levered": False, "desc": "Block (Square)"},
    "NU":    {"domain": "finance", "levered": False, "desc": "Nubank"},
    "SOFI":  {"domain": "finance", "levered": False, "desc": "SoFi"},
    # ── ENERGY ───────────────────────────────────────────────────────────────
    "XOM":   {"domain": "energy",  "levered": False, "desc": "ExxonMobil"},
    "CVX":   {"domain": "energy",  "levered": False, "desc": "Chevron"},
    "OXY":   {"domain": "energy",  "levered": False, "desc": "Occidental"},
    "DVN":   {"domain": "energy",  "levered": False, "desc": "Devon Energy"},
    "NEE":   {"domain": "energy",  "levered": False, "desc": "NextEra Energy"},
    "FSLR":  {"domain": "energy",  "levered": False, "desc": "First Solar"},
    "SMR":   {"domain": "energy",  "levered": False, "desc": "NuScale Power"},
    "CEG":   {"domain": "energy",  "levered": False, "desc": "Constellation Energy"},
    "VST":   {"domain": "energy",  "levered": False, "desc": "Vistra"},
    "NRG":   {"domain": "energy",  "levered": False, "desc": "NRG Energy"},
    # ── BIOTECH ──────────────────────────────────────────────────────────────
    "LLY":   {"domain": "biotech", "levered": False, "desc": "Eli Lilly"},
    "NVO":   {"domain": "biotech", "levered": False, "desc": "Novo Nordisk"},
    "MRNA":  {"domain": "biotech", "levered": False, "desc": "Moderna"},
    "BNTX":  {"domain": "biotech", "levered": False, "desc": "BioNTech"},
    "REGN":  {"domain": "biotech", "levered": False, "desc": "Regeneron"},
    "VRTX":  {"domain": "biotech", "levered": False, "desc": "Vertex Pharma"},
    "HIMS":  {"domain": "biotech", "levered": False, "desc": "Hims & Hers"},
    "CELH":  {"domain": "biotech", "levered": False, "desc": "Celsius Holdings"},
    "CRSP":  {"domain": "biotech", "levered": False, "desc": "CRISPR Therapeutics"},
    # ── MACRO / DEFENSE / INFRA ───────────────────────────────────────────────
    "LMT":   {"domain": "macro",   "levered": False, "desc": "Lockheed Martin"},
    "RTX":   {"domain": "macro",   "levered": False, "desc": "Raytheon"},
    "NOC":   {"domain": "macro",   "levered": False, "desc": "Northrop Grumman"},
    "BA":    {"domain": "macro",   "levered": False, "desc": "Boeing"},
    "CAT":   {"domain": "macro",   "levered": False, "desc": "Caterpillar"},
    "DE":    {"domain": "macro",   "levered": False, "desc": "John Deere"},
    "URI":   {"domain": "macro",   "levered": False, "desc": "United Rentals"},
    "PWR":   {"domain": "macro",   "levered": False, "desc": "Quanta Services"},
    "AXON":  {"domain": "macro",   "levered": False, "desc": "Axon Enterprise"},
    "PLTR":  {"domain": "macro",   "levered": False, "desc": "Palantir"},
    # ── LEVERAGED ETFs ───────────────────────────────────────────────────────
    "TQQQ":  {"domain": "etf_lev", "levered": True,  "desc": "3x Nasdaq"},
    "SOXL":  {"domain": "etf_lev", "levered": True,  "desc": "3x Semis"},
    "SPXL":  {"domain": "etf_lev", "levered": True,  "desc": "3x S&P500"},
    "LABU":  {"domain": "etf_lev", "levered": True,  "desc": "3x Biotech"},
    "FAS":   {"domain": "etf_lev", "levered": True,  "desc": "3x Financials"},
    "TECL":  {"domain": "etf_lev", "levered": True,  "desc": "3x Tech"},
    "SOXS":  {"domain": "etf_lev", "levered": True,  "desc": "3x Semis inverse"},
    "TQQQ":  {"domain": "etf_lev", "levered": True,  "desc": "3x Nasdaq"},
    "XLF":   {"domain": "etf_lev", "levered": False, "desc": "Financials ETF"},
    "XLE":   {"domain": "etf_lev", "levered": False, "desc": "Energy ETF"},
    "XLK":   {"domain": "etf_lev", "levered": False, "desc": "Tech ETF"},
    "ARKK":  {"domain": "etf_lev", "levered": False, "desc": "ARK Innovation"},
}


@dataclass
class TickerScore:
    symbol:        str
    domain:        str
    levered:       bool
    score:         float          # 0 – 10 composite
    momentum_score: float
    volume_score:  float
    streak_score:  float
    regime_score:  float
    streak:        int            # +N wins, -N losses from agent history
    price:         float = 0.0
    volume_ratio:  float = 1.0
    last_updated:  str   = ""


class TickerUniverse:
    """
    Maintains live streak scores for all 60+ tickers.
    Provides ranked list to AIConfigurator every scan cycle.
    """

    def __init__(self, data_manager=None, portfolio=None):
        self._data_manager = data_manager
        self._portfolio    = portfolio
        self._scores: Dict[str, TickerScore] = {}
        self._lock         = threading.Lock()
        self._last_refresh = 0.0
        self._regime       = "UNKNOWN"
        self._spy_rsi      = 50.0

        logger.info(f"[Universe] Initialized with {len(UNIVERSE)} tickers across 6 domains")

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, regime: str = "UNKNOWN", spy_rsi: float = 50.0, force: bool = False):
        """
        Score all tickers. Called at market open, on regime shifts,
        and every 4 hours. Thread-safe.
        """
        now = time.time()
        if not force and (now - self._last_refresh) < REFRESH_INTERVAL_SEC:
            return
        self._regime  = regime
        self._spy_rsi = spy_rsi

        logger.info(f"[Universe] Scoring {len(UNIVERSE)} tickers (regime={regime})")
        trade_history = self._build_trade_history()

        new_scores = {}
        for symbol, meta in UNIVERSE.items():
            try:
                score = self._score_ticker(symbol, meta, trade_history, regime, spy_rsi)
                new_scores[symbol] = score
            except Exception as e:
                logger.debug(f"[Universe] Score failed for {symbol}: {e}")

        with self._lock:
            self._scores = new_scores
            self._last_refresh = now

        top5 = sorted(new_scores.values(), key=lambda x: -x.score)[:5]
        logger.info(
            f"[Universe] Refresh done. Top 5: "
            + ", ".join(f"{t.symbol}={t.score:.1f}(streak={t.streak:+d})" for t in top5)
        )

    def get_scores(self) -> List[Dict]:
        """Return all scores sorted by composite score, highest first."""
        with self._lock:
            return [
                {
                    "symbol":   s.symbol,
                    "domain":   s.domain,
                    "levered":  s.levered,
                    "score":    round(s.score, 2),
                    "streak":   s.streak,
                    "momentum": round(s.momentum_score, 2),
                    "volume":   round(s.volume_score, 2),
                    "regime_align": round(s.regime_score, 2),
                    "price":    s.price,
                    "vol_ratio": round(s.volume_ratio, 2),
                }
                for s in sorted(self._scores.values(), key=lambda x: -x.score)
            ]

    def get_top_n(self, n: int, exclude_levered: bool = False) -> List[str]:
        """Return top N symbols by score."""
        scores = self.get_scores()
        if exclude_levered:
            scores = [s for s in scores if not s["levered"]]
        return [s["symbol"] for s in scores[:n]]

    def get_domain_leaders(self) -> Dict[str, str]:
        """Return the top-scoring ticker per domain."""
        leaders = {}
        with self._lock:
            by_domain: Dict[str, TickerScore] = {}
            for s in self._scores.values():
                if s.domain not in by_domain or s.score > by_domain[s.domain].score:
                    by_domain[s.domain] = s
        return {d: s.symbol for d, s in by_domain.items()}

    # ── Scoring logic ─────────────────────────────────────────────────────────

    def _score_ticker(
        self,
        symbol: str,
        meta: Dict,
        trade_history: Dict[str, int],
        regime: str,
        spy_rsi: float,
    ) -> TickerScore:
        momentum_score = self._momentum_score(symbol)
        volume_score   = self._volume_score(symbol)
        streak_score, streak = self._streak_score(symbol, trade_history)
        regime_score   = self._regime_align_score(meta["domain"], meta["levered"], regime, spy_rsi)

        composite = (
            momentum_score * 0.40
            + volume_score * 0.25
            + streak_score * 0.20
            + regime_score * 0.15
        )
        # Levered ETF penalty in non-bullish regimes
        if meta["levered"] and regime not in ("BULL", "STRONG_BULL", "TRENDING_UP"):
            composite *= 0.5

        return TickerScore(
            symbol         = symbol,
            domain         = meta["domain"],
            levered        = meta["levered"],
            score          = min(10.0, max(0.0, composite)),
            momentum_score = momentum_score,
            volume_score   = volume_score,
            streak_score   = streak_score,
            regime_score   = regime_score,
            streak         = streak,
            last_updated   = datetime.now(timezone.utc).isoformat(),
        )

    def _momentum_score(self, symbol: str) -> float:
        """Fetch recent bars and compute momentum. Returns 0-10."""
        if not self._data_manager:
            return 5.0  # neutral default when no data manager
        try:
            from datetime import timedelta
            bars = self._data_manager.get_bars_df(
                symbol, "15Min",
                start=datetime.now(timezone.utc) - timedelta(days=5),
                limit=50,
            )
            if bars is None or len(bars) < 10:
                return 5.0

            close = bars["close"]
            price_now  = float(close.iloc[-1])
            price_5ago = float(close.iloc[-5])
            price_20ago = float(close.iloc[0]) if len(close) >= 20 else price_5ago

            chg_5  = (price_now - price_5ago)  / price_5ago  if price_5ago  > 0 else 0
            chg_20 = (price_now - price_20ago) / price_20ago if price_20ago > 0 else 0

            # RSI proxy
            gains  = close.diff().clip(lower=0).tail(14).mean()
            losses = (-close.diff().clip(upper=0)).tail(14).mean()
            rsi    = 100 - 100 / (1 + gains / losses) if losses > 0 else 50

            # Score: strong upward momentum = high score
            raw = 5.0
            raw += chg_5  * 100   # +1pt per 1% 5-bar gain
            raw += chg_20 * 50    # +0.5pt per 1% 20-bar gain
            raw += (rsi - 50) / 10  # RSI above 50 boosts score
            return min(10.0, max(0.0, raw))
        except Exception:
            return 5.0

    def _volume_score(self, symbol: str) -> float:
        """Volume surge vs 20-bar average. Returns 0-10."""
        if not self._data_manager:
            return 5.0
        try:
            from datetime import timedelta
            bars = self._data_manager.get_bars_df(
                symbol, "15Min",
                start=datetime.now(timezone.utc) - timedelta(days=5),
                limit=50,
            )
            if bars is None or len(bars) < 5 or "volume" not in bars.columns:
                return 5.0
            avg_vol = float(bars["volume"].tail(20).mean())
            cur_vol = float(bars["volume"].iloc[-1])
            if avg_vol <= 0:
                return 5.0
            ratio = cur_vol / avg_vol
            # 1x = 5, 2x = 7.5, 3x+ = 10, below 0.5x = 2.5
            return min(10.0, max(0.0, 2.5 + ratio * 2.5))
        except Exception:
            return 5.0

    def _streak_score(self, symbol: str, trade_history: Dict[str, int]) -> tuple:
        """Agent's own win/loss streak on this ticker. Returns (score 0-10, streak int)."""
        streak = trade_history.get(symbol, 0)
        if streak >= 5:
            return 10.0, streak
        elif streak >= 3:
            return 8.0, streak
        elif streak >= 1:
            return 6.5, streak
        elif streak == 0:
            return 5.0, streak
        elif streak >= -2:
            return 3.0, streak
        else:
            return 0.0, streak  # 3+ consecutive losses — bench it

    def _regime_align_score(
        self, domain: str, levered: bool, regime: str, spy_rsi: float
    ) -> float:
        """How well does this ticker/domain align with current market regime?"""
        bullish = regime in ("BULL", "STRONG_BULL", "TRENDING_UP", "RECOVERY")
        bearish = regime in ("BEAR", "EXTREME_BEAR", "CRASH", "BREAKDOWN")
        neutral = not bullish and not bearish

        scores = {
            "tech":    9.0 if bullish else (3.0 if bearish else 6.0),
            "finance": 8.0 if bullish else (4.0 if bearish else 6.0),
            "energy":  7.0 if bullish else (5.0 if bearish else 6.0),  # energy more defensive
            "biotech": 7.0 if bullish else (3.0 if bearish else 5.5),
            "macro":   6.0 if bullish else (7.0 if bearish else 6.0),  # defense holds in bear
            "etf_lev": 9.0 if bullish else (1.0 if bearish else 4.0),
        }
        base = scores.get(domain, 5.0)

        # Adjust for RSI overbought/oversold
        if spy_rsi > 75 and bullish:
            base *= 0.85   # slight caution — market stretched
        elif spy_rsi < 35 and bearish:
            base *= 0.80   # deep bear, extra penalty

        return min(10.0, max(0.0, base))

    # ── Trade history ─────────────────────────────────────────────────────────

    def _build_trade_history(self) -> Dict[str, int]:
        """
        Build per-symbol win streak from portfolio trade history.
        Returns {symbol: consecutive_wins_or_negative_losses}
        e.g. +3 = 3 wins in a row, -2 = 2 losses in a row
        """
        if not self._portfolio:
            return {}
        try:
            trades = self._portfolio.all_trades
            if not trades:
                return {}

            # Group by symbol, keep chronological order
            by_symbol: Dict[str, list] = {}
            for t in trades:
                sym = t.get("symbol", "")
                if sym:
                    by_symbol.setdefault(sym, []).append(t.get("pnl", 0))

            streaks = {}
            for sym, pnls in by_symbol.items():
                streak = 0
                for pnl in reversed(pnls):   # most recent first
                    if pnl > 0:
                        if streak >= 0:
                            streak += 1
                        else:
                            break   # streak broken
                    else:
                        if streak <= 0:
                            streak -= 1
                        else:
                            break
                streaks[sym] = streak
            return streaks
        except Exception as e:
            logger.debug(f"[Universe] Trade history error: {e}")
            return {}
