# -*- coding: utf-8 -*-
"""
SentimentEngine — Multi-source sentiment scorer
-------------------------------------------------
Scores news articles using:
  1. Claude AI     — deep contextual analysis (if API key available)
  2. Keyword rules — fast fallback, financial-domain vocabulary

Final sentiment per symbol:
  - Score: -1.0 (very negative) to +1.0 (very positive)
  - Confidence: 0.0 to 1.0 (higher = more sources agree)
  - Grade: STRONGLY_POSITIVE | POSITIVE | NEUTRAL | NEGATIVE | STRONGLY_NEGATIVE
  - Signal: BUY_BOOST | HOLD | SELL_SIGNAL (how to adjust the trade decision)
"""

import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .fetcher import NewsArticle, SymbolNews

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-sonnet-4-6"

# Keyword-based fallback scorer
POSITIVE_WORDS = {
    "beats": 0.4, "beat": 0.4, "exceeded": 0.4, "record": 0.35,
    "upgrade": 0.5, "upgraded": 0.5, "buy": 0.3, "outperform": 0.4,
    "raises": 0.3, "raised": 0.3, "growth": 0.25, "profit": 0.25,
    "gains": 0.25, "surge": 0.4, "soars": 0.4, "rally": 0.3,
    "strong": 0.2, "positive": 0.3, "bullish": 0.4, "expansion": 0.25,
    "dividend": 0.2, "buyback": 0.3, "innovation": 0.15, "partnership": 0.2,
}
NEGATIVE_WORDS = {
    "misses": 0.4, "miss": 0.4, "missed": 0.4, "below": 0.25,
    "downgrade": 0.5, "downgraded": 0.5, "sell": 0.3, "underperform": 0.4,
    "cuts": 0.3, "cut": 0.3, "loss": 0.35, "losses": 0.35,
    "decline": 0.3, "drops": 0.3, "falls": 0.25, "slump": 0.35,
    "investigation": 0.5, "lawsuit": 0.4, "fraud": 0.6, "recall": 0.5,
    "layoffs": 0.4, "restructuring": 0.3, "warning": 0.35, "concerns": 0.2,
    "weak": 0.25, "bearish": 0.4, "disappointing": 0.35, "miss": 0.4,
    "antitrust": 0.5, "fine": 0.3, "penalty": 0.4, "violation": 0.45,
}


@dataclass
class ArticleSentiment:
    """Sentiment for one article."""
    headline:   str
    score:      float        # -1.0 to +1.0
    grade:      str          # STRONGLY_POSITIVE | POSITIVE | NEUTRAL | NEGATIVE | STRONGLY_NEGATIVE
    method:     str          # "claude" | "keyword"
    reasoning:  str          = ""


@dataclass
class SymbolSentiment:
    """Aggregated sentiment for one symbol."""
    symbol:          str
    score:           float        # weighted average -1.0 to +1.0
    confidence:      float        # 0.0 to 1.0
    grade:           str
    signal:          str          # BUY_BOOST | HOLD | SELL_SIGNAL
    article_scores:  List[ArticleSentiment] = field(default_factory=list)
    ai_summary:      str          = ""
    sources_count:   int          = 0
    article_count:   int          = 0
    top_positive:    str          = ""
    top_negative:    str          = ""

    def to_dict(self) -> dict:
        return {
            "symbol":        self.symbol,
            "score":         round(self.score, 3),
            "confidence":    round(self.confidence, 3),
            "grade":         self.grade,
            "signal":        self.signal,
            "ai_summary":    self.ai_summary,
            "sources_count": self.sources_count,
            "article_count": self.article_count,
            "top_positive":  self.top_positive,
            "top_negative":  self.top_negative,
            "articles": [
                {
                    "headline": a.headline,
                    "score":    round(a.score, 3),
                    "grade":    a.grade,
                    "method":   a.method,
                }
                for a in self.article_scores
            ],
        }


def _score_to_grade(score: float) -> str:
    if score >= 0.6:  return "STRONGLY_POSITIVE"
    if score >= 0.25: return "POSITIVE"
    if score >= -0.25:return "NEUTRAL"
    if score >= -0.6: return "NEGATIVE"
    return "STRONGLY_NEGATIVE"


def _score_to_signal(score: float, confidence: float) -> str:
    if score >= 0.4 and confidence >= 0.5:  return "BUY_BOOST"
    if score <= -0.4 and confidence >= 0.5: return "SELL_SIGNAL"
    return "HOLD"


class SentimentEngine:
    """
    Scores news articles and produces per-symbol sentiment signals.

    Usage:
        engine    = SentimentEngine(api_key="sk-ant-...")
        sentiment = engine.score(symbol_news)
        print(sentiment.score, sentiment.signal)
    """

    def __init__(self, api_key: str = ""):
        self.api_key  = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._use_ai  = bool(self.api_key)
        if self._use_ai:
            logger.info("[Sentiment] Claude AI scoring enabled")
        else:
            logger.info("[Sentiment] Using keyword fallback scorer")

    def score(self, news: SymbolNews) -> SymbolSentiment:
        """Score all articles for one symbol and return aggregated sentiment."""
        if not news.articles:
            return SymbolSentiment(
                symbol     = news.symbol,
                score      = 0.0,
                confidence = 0.0,
                grade      = "NEUTRAL",
                signal     = "HOLD",
                ai_summary = "No news found for this symbol.",
            )

        # Score each article
        article_scores = []
        for article in news.articles:
            scored = self._score_article(article)
            article_scores.append(scored)

        # Weighted average — recent articles count more
        total_weight = 0.0
        weighted_sum = 0.0
        for i, scored in enumerate(article_scores):
            # More recent = higher weight (index 0 is most recent)
            weight = 1.0 / (1 + i * 0.3)
            weighted_sum += scored.score * weight
            total_weight += weight

        avg_score = weighted_sum / total_weight if total_weight > 0 else 0.0
        avg_score = max(-1.0, min(1.0, avg_score))

        # Confidence: higher when sources agree and more articles exist
        scores = [a.score for a in article_scores]
        if len(scores) > 1:
            variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
            agreement = max(0.0, 1.0 - variance)
        else:
            agreement = 0.5

        source_bonus = min(len(news.sources_hit) / 3, 1.0)
        volume_bonus  = min(len(news.articles) / 5, 1.0)
        confidence    = (agreement * 0.5 + source_bonus * 0.3 + volume_bonus * 0.2)
        confidence    = round(min(1.0, confidence), 3)

        # Find top positive and negative
        pos_articles = [a for a in article_scores if a.score > 0.2]
        neg_articles = [a for a in article_scores if a.score < -0.2]
        top_positive = max(pos_articles, key=lambda a: a.score).headline if pos_articles else ""
        top_negative = min(neg_articles, key=lambda a: a.score).headline if neg_articles else ""

        # AI summary
        ai_summary = ""
        if self._use_ai and news.articles:
            try:
                ai_summary = self._get_ai_summary(news.symbol, news.articles, avg_score)
            except Exception as e:
                logger.debug(f"[Sentiment] AI summary failed: {e}")
                ai_summary = self._keyword_summary(avg_score, len(news.articles), news.sources_hit)
        else:
            ai_summary = self._keyword_summary(avg_score, len(news.articles), news.sources_hit)

        grade  = _score_to_grade(avg_score)
        signal = _score_to_signal(avg_score, confidence)

        result = SymbolSentiment(
            symbol         = news.symbol,
            score          = round(avg_score, 3),
            confidence     = confidence,
            grade          = grade,
            signal         = signal,
            article_scores = article_scores,
            ai_summary     = ai_summary,
            sources_count  = len(news.sources_hit),
            article_count  = len(news.articles),
            top_positive   = top_positive,
            top_negative   = top_negative,
        )

        logger.info(
            f"[Sentiment] {news.symbol}: score={avg_score:+.2f} "
            f"conf={confidence:.0%} grade={grade} signal={signal}"
        )
        return result

    def score_watchlist(self, news_map: Dict[str, SymbolNews]) -> Dict[str, SymbolSentiment]:
        """Score all symbols in the watchlist."""
        return {sym: self.score(news) for sym, news in news_map.items()}

    # ------------------------------------------------------------------
    # Article scoring
    # ------------------------------------------------------------------

    def _score_article(self, article: NewsArticle) -> ArticleSentiment:
        """Score one article. Uses AI if available, keyword fallback otherwise."""
        if self._use_ai:
            try:
                return self._score_with_ai(article)
            except Exception:
                pass
        return self._score_with_keywords(article)

    def _score_with_keywords(self, article: NewsArticle) -> ArticleSentiment:
        """Fast keyword-based scoring."""
        text = (article.headline + " " + article.summary).lower()
        words = re.findall(r'\b\w+\b', text)

        pos_score = sum(POSITIVE_WORDS.get(w, 0) for w in words)
        neg_score = sum(NEGATIVE_WORDS.get(w, 0) for w in words)

        raw = (pos_score - neg_score) / max(pos_score + neg_score, 1)
        score = max(-1.0, min(1.0, raw))

        return ArticleSentiment(
            headline  = article.headline,
            score     = round(score, 3),
            grade     = _score_to_grade(score),
            method    = "keyword",
        )

    def _score_with_ai(self, article: NewsArticle) -> ArticleSentiment:
        """Score one article using Claude."""
        prompt = f"""Rate the sentiment of this financial news headline for stock {article.symbol}.
Respond with JSON only — no other text:
{{"score": -1.0 to 1.0, "grade": "STRONGLY_POSITIVE|POSITIVE|NEUTRAL|NEGATIVE|STRONGLY_NEGATIVE", "reasoning": "one sentence"}}

Headline: {article.headline}"""

        payload = json.dumps({
            "model":      MODEL,
            "max_tokens": 100,
            "messages":   [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            ANTHROPIC_API_URL, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key":    self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        text = data["content"][0]["text"].strip()
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL).strip()
        parsed = json.loads(text)

        return ArticleSentiment(
            headline  = article.headline,
            score     = float(parsed.get("score", 0)),
            grade     = parsed.get("grade", "NEUTRAL"),
            method    = "claude",
            reasoning = parsed.get("reasoning", ""),
        )

    def _get_ai_summary(self, symbol: str, articles: List[NewsArticle], avg_score: float) -> str:
        """Get Claude's plain-English summary of all news for a symbol."""
        headlines = "\n".join(f"- {a.headline}" for a in articles[:6])
        prompt = f"""Summarize the news sentiment for {symbol} in 2 sentences for a trader.
Be direct about whether the news supports or undermines a trade.

Headlines:
{headlines}

Overall score: {avg_score:+.2f}

Respond with just the 2-sentence summary — no JSON, no preamble."""

        payload = json.dumps({
            "model":      MODEL,
            "max_tokens": 120,
            "messages":   [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            ANTHROPIC_API_URL, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key":    self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        return data["content"][0]["text"].strip()

    def _keyword_summary(self, score: float, count: int, sources: List[str]) -> str:
        grade = _score_to_grade(score)
        src   = ", ".join(sources) if sources else "available sources"
        desc  = {
            "STRONGLY_POSITIVE": "strongly positive",
            "POSITIVE":          "generally positive",
            "NEUTRAL":           "mixed or neutral",
            "NEGATIVE":          "generally negative",
            "STRONGLY_NEGATIVE": "strongly negative",
        }.get(grade, "neutral")
        return (
            f"News sentiment is {desc} based on {count} articles from {src}. "
            f"AI analysis active — refresh to update sentiment."
        )
