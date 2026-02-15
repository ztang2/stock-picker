"""News sentiment analysis using yfinance news and keyword matching."""

import logging
import time
from typing import Dict, List, Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)

POSITIVE_WORDS = {"beat", "surge", "growth", "upgrade", "buy", "profit", "record", "strong",
                  "bullish", "outperform", "raise", "exceed", "positive", "gain", "rally"}
NEGATIVE_WORDS = {"miss", "decline", "downgrade", "sell", "loss", "weak", "cut", "warning",
                  "lawsuit", "recall", "bearish", "underperform", "drop", "fall", "negative"}

_sentiment_cache: Dict[str, Tuple[float, dict]] = {}
CACHE_TTL = 3600  # 1 hour


def analyze_sentiment(ticker: str) -> dict:
    """Fetch news headlines for ticker and compute keyword sentiment.

    Returns dict with score (-1 to +1), headline_count, headlines list.
    """
    now = time.time()
    if ticker in _sentiment_cache:
        ts, cached = _sentiment_cache[ticker]
        if now - ts < CACHE_TTL:
            return cached

    result = {"score": 0.0, "headline_count": 0, "headlines": [], "positive_count": 0, "negative_count": 0}

    try:
        t = yf.Ticker(ticker)
        news = t.news if hasattr(t, 'news') else []
        if not news:
            _sentiment_cache[ticker] = (now, result)
            return result

        headlines: List[str] = []
        for item in news[:20]:
            title = item.get("title", "")
            if title:
                headlines.append(title)

        pos_count = 0
        neg_count = 0
        for h in headlines:
            words = set(h.lower().split())
            pos_count += len(words & POSITIVE_WORDS)
            neg_count += len(words & NEGATIVE_WORDS)

        total = pos_count + neg_count
        score = (pos_count - neg_count) / total if total > 0 else 0.0
        score = max(-1.0, min(1.0, score))

        result = {
            "score": round(score, 3),
            "headline_count": len(headlines),
            "headlines": headlines[:10],
            "positive_count": pos_count,
            "negative_count": neg_count,
        }
    except Exception:
        logger.warning("Failed to get sentiment for %s", ticker, exc_info=True)

    _sentiment_cache[ticker] = (now, result)
    return result
