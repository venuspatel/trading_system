# -*- coding: utf-8 -*-
"""
NewsFetcher — Multi-source financial news aggregator
------------------------------------------------------
Fetches headlines from 3 free sources (no API keys needed):
  1. Alpaca News API   — real-time, already connected
  2. Yahoo Finance     — earnings, analyst ratings, headlines
  3. Finviz            — aggregated news with sentiment tags

Falls back gracefully if any source fails.
Results are cached per symbol for 15 minutes to avoid hammering APIs.
"""

import json
import logging
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 900   # 15 minutes


@dataclass
class NewsArticle:
    """One news article from any source."""
    headline:   str
    source:     str          # "Alpaca" | "Yahoo" | "Finviz"
    url:        str          = ""
    published:  str          = ""   # ISO timestamp
    summary:    str          = ""
    symbol:     str          = ""
    raw_sentiment: float     = 0.0  # pre-scored if source provides it (-1 to +1)

    @property
    def age_hours(self) -> float:
        if not self.published:
            return 99.0
        try:
            pub = datetime.fromisoformat(self.published.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - pub).total_seconds() / 3600
        except Exception:
            return 99.0


@dataclass
class SymbolNews:
    """Aggregated news for one symbol across all sources."""
    symbol:         str
    articles:       List[NewsArticle]   = field(default_factory=list)
    sources_hit:    List[str]           = field(default_factory=list)
    fetched_at:     float               = field(default_factory=time.time)
    error:          Optional[str]       = None

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.fetched_at) > CACHE_TTL_SECONDS

    @property
    def article_count(self) -> int:
        return len(self.articles)


class NewsFetcher:
    """
    Fetches news from multiple free sources for a list of symbols.
    Results are cached to avoid redundant API calls within a scan cycle.

    Usage:
        fetcher = NewsFetcher(alpaca_api_key="...", alpaca_secret_key="...")
        news    = fetcher.fetch("AAPL")
        for article in news.articles:
            print(article.headline)
    """

    def __init__(
        self,
        alpaca_api_key:    str = "",
        alpaca_secret_key: str = "",
        max_articles:      int = 10,
        max_age_hours:     int = 24,
    ):
        self.alpaca_key    = alpaca_api_key
        self.alpaca_secret = alpaca_secret_key
        self.max_articles  = max_articles
        self.max_age_hours = max_age_hours
        self._cache: Dict[str, SymbolNews] = {}

    def fetch(self, symbol: str, force: bool = False) -> SymbolNews:
        """Fetch news for one symbol. Returns cached result if fresh."""
        if not force and symbol in self._cache and not self._cache[symbol].is_stale:
            return self._cache[symbol]

        articles    = []
        sources_hit = []
        errors      = []

        # Source 1: Alpaca News API
        try:
            alpaca_articles = self._fetch_alpaca(symbol)
            if alpaca_articles:
                articles.extend(alpaca_articles)
                sources_hit.append("Alpaca")
        except Exception as e:
            errors.append(f"Alpaca: {e}")
            logger.debug(f"[News] Alpaca failed for {symbol}: {e}")

        # Source 2: Yahoo Finance
        try:
            yahoo_articles = self._fetch_yahoo(symbol)
            if yahoo_articles:
                articles.extend(yahoo_articles)
                sources_hit.append("Yahoo")
        except Exception as e:
            errors.append(f"Yahoo: {e}")
            logger.debug(f"[News] Yahoo failed for {symbol}: {e}")

        # Source 3: Finviz
        try:
            finviz_articles = self._fetch_finviz(symbol)
            if finviz_articles:
                articles.extend(finviz_articles)
                sources_hit.append("Finviz")
        except Exception as e:
            errors.append(f"Finviz: {e}")
            logger.debug(f"[News] Finviz failed for {symbol}: {e}")

        # Deduplicate by headline similarity and sort by recency
        articles = self._deduplicate(articles)
        articles = sorted(articles, key=lambda a: a.age_hours)
        articles = [a for a in articles if a.age_hours <= self.max_age_hours]
        articles = articles[:self.max_articles]

        result = SymbolNews(
            symbol      = symbol,
            articles    = articles,
            sources_hit = sources_hit,
            error       = " | ".join(errors) if errors and not articles else None,
        )

        self._cache[symbol] = result
        logger.info(
            f"[News] {symbol}: {len(articles)} articles from "
            f"{', '.join(sources_hit) if sources_hit else 'no sources'}"
        )
        return result

    def fetch_watchlist(self, symbols: List[str]) -> Dict[str, SymbolNews]:
        """Fetch news for all symbols. Returns dict keyed by symbol."""
        results = {}
        for sym in symbols:
            try:
                results[sym] = self.fetch(sym)
            except Exception as e:
                logger.warning(f"[News] Failed to fetch {sym}: {e}")
                results[sym] = SymbolNews(symbol=sym, error=str(e))
        return results

    # ------------------------------------------------------------------
    # Source implementations
    # ------------------------------------------------------------------

    def _fetch_alpaca(self, symbol: str) -> List[NewsArticle]:
        """Fetch from Alpaca News API (requires Alpaca keys)."""
        if not self.alpaca_key:
            return []

        url = (
            f"https://data.alpaca.markets/v1beta1/news"
            f"?symbols={symbol}&limit=10&sort=desc"
        )
        req = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID":     self.alpaca_key,
                "APCA-API-SECRET-KEY": self.alpaca_secret,
                "Accept":              "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        articles = []
        for item in data.get("news", []):
            articles.append(NewsArticle(
                headline  = item.get("headline", ""),
                source    = "Alpaca",
                url       = item.get("url", ""),
                published = item.get("created_at", ""),
                summary   = item.get("summary", ""),
                symbol    = symbol,
            ))
        return articles

    def _fetch_yahoo(self, symbol: str) -> List[NewsArticle]:
        """Fetch from Yahoo Finance via their public API endpoint."""
        url = (
            f"https://query1.finance.yahoo.com/v1/finance/search"
            f"?q={symbol}&newsCount=8&enableFuzzyQuery=false"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; TradingAgent/1.0)",
                "Accept":     "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        articles = []
        for item in data.get("news", []):
            pub_ts = item.get("providerPublishTime", 0)
            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc).isoformat() if pub_ts else ""
            articles.append(NewsArticle(
                headline  = item.get("title", ""),
                source    = "Yahoo",
                url       = item.get("link", ""),
                published = pub_dt,
                summary   = "",
                symbol    = symbol,
            ))
        return articles

    def _fetch_finviz(self, symbol: str) -> List[NewsArticle]:
        """Fetch from Finviz news table (HTML scrape, no key needed)."""
        url = f"https://finviz.com/quote.ashx?t={symbol}&p=d"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept":     "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        articles = []
        # Parse news table rows — Finviz uses a consistent table structure
        import re
        pattern = r'class="news-link-left"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?class="news-link-right"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html)

        for url_match, headline, source_date in matches[:8]:
            articles.append(NewsArticle(
                headline  = headline.strip(),
                source    = "Finviz",
                url       = url_match,
                published = "",
                symbol    = symbol,
            ))
        return articles

    def _deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Remove near-duplicate headlines."""
        seen = []
        unique = []
        for article in articles:
            if not article.headline:
                continue
            # Simple dedup: check if any existing headline shares 60%+ words
            words = set(article.headline.lower().split())
            is_dup = False
            for s in seen:
                overlap = len(words & s) / max(len(words), 1)
                if overlap > 0.6:
                    is_dup = True
                    break
            if not is_dup:
                seen.append(words)
                unique.append(article)
        return unique
