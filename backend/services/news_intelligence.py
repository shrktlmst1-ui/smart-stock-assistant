"""News Intelligence — Benzinga ready + Polygon fallback with sentiment."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from config import BENZINGA_API_KEY, BENZINGA_ENABLED
from models.stock import NewsItem
from models.trading import NewsIntelligence, NewsSentiment
from services.polygon_client import PolygonClient

logger = logging.getLogger(__name__)

BULLISH_WORDS = {
    "surge", "rally", "beat", "upgrade", "growth", "record", "profit", "bullish",
    "outperform", "buy", "strong", "soar", "jump", "gain", "positive", "breakout",
    "ارتفاع", "صعود", "أرباح", "نمو", "تجاوز", "قوي",
}
BEARISH_WORDS = {
    "fall", "drop", "miss", "downgrade", "loss", "bearish", "underperform", "sell",
    "weak", "plunge", "decline", "cut", "negative", "lawsuit", "warning", "crash",
    "انخفاض", "هبوط", "خسارة", "ضعف", "تحذير", "دعوى",
}


def _sentiment_score(text: str) -> tuple[str, float]:
    text_lower = text.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in text_lower)
    bear = sum(1 for w in BEARISH_WORDS if w in text_lower)
    if bull > bear:
        return "bullish", min(1.0, (bull - bear) * 0.2)
    if bear > bull:
        return "bearish", max(-1.0, (bull - bear) * 0.2)
    return "neutral", 0.0


def _price_correlation(sentiment: str, change_pct: float) -> str:
    if sentiment == "bullish" and change_pct > 0.3:
        return "aligned"
    if sentiment == "bearish" and change_pct < -0.3:
        return "aligned"
    if sentiment == "bullish" and change_pct < -0.5:
        return "divergent"
    if sentiment == "bearish" and change_pct > 0.5:
        return "divergent"
    return "neutral"


async def fetch_benzinga_news(symbol: str, limit: int = 5) -> list[dict]:
    if not BENZINGA_ENABLED or not BENZINGA_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.benzinga.com/api/v2/news",
                params={
                    "token": BENZINGA_API_KEY,
                    "tickers": symbol,
                    "pageSize": limit,
                    "displayOutput": "headline",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("news", [])
    except Exception as e:
        logger.warning("Benzinga fetch failed: %s", e)
        return []


async def analyze_news(
    symbol: str,
    client: PolygonClient,
    change_pct: float,
    limit: int = 5,
) -> tuple[list[NewsItem], NewsIntelligence]:
    items: list[NewsItem] = []
    sentiments: list[NewsSentiment] = []

    # Try Benzinga first
    bz_news = await fetch_benzinga_news(symbol, limit)
    source = "benzinga" if bz_news else "polygon"

    if bz_news:
        for article in bz_news[:limit]:
            title = article.get("title", article.get("headline", ""))
            if not title:
                continue
            sent, score = _sentiment_score(title)
            corr = _price_correlation(sent, change_pct)
            impact = score * 10
            if corr == "aligned":
                impact += 3
            elif corr == "divergent":
                impact -= 5
            sentiments.append(NewsSentiment(
                headline=title, sentiment=sent, score=score,
                price_correlation=corr, confidence_impact=round(impact, 1),
            ))
            items.append(NewsItem(
                id=str(article.get("id", title[:20])),
                title=title,
                source="Benzinga",
                published_at=article.get("created", datetime.now(timezone.utc).isoformat()),
                url=article.get("url", ""),
                symbols=[symbol],
            ))
    else:
        from services.news_service import fetch_stock_news
        items = await fetch_stock_news(client, symbol, limit)
        for n in items:
            sent, score = _sentiment_score(n.title)
            corr = _price_correlation(sent, change_pct)
            impact = score * 10
            sentiments.append(NewsSentiment(
                headline=n.title, sentiment=sent, score=score,
                price_correlation=corr, confidence_impact=round(impact, 1),
            ))

    total_impact = sum(s.confidence_impact for s in sentiments)
    total_impact = max(-20, min(20, total_impact))

    bull_count = sum(1 for s in sentiments if s.sentiment == "bullish")
    bear_count = sum(1 for s in sentiments if s.sentiment == "bearish")
    if bull_count > bear_count:
        overall = "bullish"
    elif bear_count > bull_count:
        overall = "bearish"
    else:
        overall = "neutral"

    intelligence = NewsIntelligence(
        items=sentiments,
        overall_sentiment=overall,
        confidence_adjustment=round(total_impact, 1),
        source=source,
    )
    return items, intelligence
