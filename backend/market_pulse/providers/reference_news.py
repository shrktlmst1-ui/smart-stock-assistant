"""Massive/Polygon reference news provider — included with Stocks subscription."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import POLYGON_BASE_URL, get_polygon_api_key
from market_pulse.news_dedup import dedupe_news
from market_pulse.providers.base import RawNewsItem

logger = logging.getLogger(__name__)

REFERENCE_NEWS_PATH = "/v2/reference/news"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_symbols(raw: dict[str, Any]) -> list[str]:
    symbols: list[str] = []
    tickers = raw.get("tickers")
    if isinstance(tickers, list):
        for ticker in tickers:
            if isinstance(ticker, str) and ticker.strip():
                symbols.append(ticker.strip().upper())
    for key in ("symbols", "stocks"):
        val = raw.get(key)
        if isinstance(val, list):
            for s in val:
                if isinstance(s, str) and s.strip():
                    symbols.append(s.strip().upper())
                elif isinstance(s, dict):
                    t = s.get("name") or s.get("symbol") or s.get("ticker")
                    if t:
                        symbols.append(str(t).upper())
    return list(dict.fromkeys(symbols))


def _row_to_item(row: dict[str, Any]) -> RawNewsItem | None:
    headline = str(row.get("title") or row.get("headline") or "").strip()
    if not headline:
        return None
    provider_id = str(row.get("id") or row.get("article_id") or "")
    url = str(row.get("article_url") or row.get("url") or row.get("link") or "")
    published = _parse_datetime(
        row.get("published_utc") or row.get("published") or row.get("published_at") or row.get("created")
    )
    symbols = _extract_symbols(row)
    body = str(row.get("description") or row.get("body") or row.get("teaser") or row.get("summary") or "")
    return RawNewsItem(
        provider_id=provider_id,
        headline=headline,
        url=url,
        published_at=published,
        symbols=symbols,
        body=body,
    )


class ReferenceNewsProvider:
    """Fetch latest stock news via Polygon/Massive /v2/reference/news."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = POLYGON_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = (api_key or get_polygon_api_key()).strip()
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._owns_client = client is None
        self.last_fetch_at: datetime | None = None

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_news(self, limit: int = 50) -> list[RawNewsItem]:
        if not self._api_key:
            return []

        client = await self._get_client()
        url = f"{self._base_url}{REFERENCE_NEWS_PATH}"
        params = {
            "limit": limit,
            "sort": "published_utc",
            "order": "desc",
            "apiKey": self._api_key,
        }

        try:
            resp = await client.get(url, params=params)
        except httpx.TimeoutException:
            logger.warning("Reference news fetch timed out")
            return []
        except httpx.RequestError as exc:
            logger.warning("Reference news request failed: %s", type(exc).__name__)
            return []

        if resp.status_code in (401, 403, 429):
            logger.warning("Reference news fetch returned HTTP %s", resp.status_code)
            return []
        if resp.status_code >= 400:
            logger.warning("Reference news fetch failed with HTTP %s", resp.status_code)
            return []

        try:
            payload = resp.json()
        except ValueError:
            logger.warning("Reference news response was not valid JSON")
            return []

        rows: list[dict] = []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("results") or payload.get("news") or payload.get("data") or []

        items: list[RawNewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _row_to_item(row)
            if item is not None:
                items.append(item)

        self.last_fetch_at = datetime.now(timezone.utc)
        return dedupe_news(items)


# Backward-compatible alias for existing imports/tests being migrated.
BenzingaNewsProvider = ReferenceNewsProvider
