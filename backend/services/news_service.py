"""Market news service via Polygon.io."""

from __future__ import annotations

from datetime import datetime, timezone

from models.stock import NewsItem
from services.polygon_client import PolygonClient


async def fetch_stock_news(client: PolygonClient, symbol: str, limit: int = 3) -> list[NewsItem]:
    try:
        results = await client.get_news(symbol, limit=limit)
    except Exception:
        return []

    items: list[NewsItem] = []
    for article in results:
        published = article.get("published_utc", "")
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            published_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            published_str = published

        items.append(
            NewsItem(
                id=str(article.get("id", published)),
                title=article.get("title", "بدون عنوان"),
                source=article.get("publisher", {}).get("name", "Polygon"),
                published_at=published_str,
                url=article.get("article_url", ""),
                symbols=article.get("tickers", [symbol]),
            )
        )
    return items
