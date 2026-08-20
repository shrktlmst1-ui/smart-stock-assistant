"""Benzinga news provider via Massive API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import BENZINGA_NEWS_URL, get_polygon_api_key
from market_pulse.news_dedup import dedupe_news
from market_pulse.providers.base import RawNewsItem

logger = logging.getLogger(__name__)


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
    for key in ("tickers", "symbols", "stocks"):
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


class BenzingaNewsProvider:
    """Fetch Benzinga news through Massive REST — key stays server-side only."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BENZINGA_NEWS_URL,
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
        params = {"limit": limit, "apiKey": self._api_key}
        resp = await client.get(self._base_url, params=params)
        resp.raise_for_status()
        payload = resp.json()

        rows: list[dict] = []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("results") or payload.get("news") or payload.get("data") or []

        items: list[RawNewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            headline = str(row.get("title") or row.get("headline") or "").strip()
            if not headline:
                continue
            provider_id = str(row.get("id") or row.get("benzinga_id") or row.get("article_id") or "")
            url = str(row.get("url") or row.get("link") or "")
            published = _parse_datetime(
                row.get("published") or row.get("published_at") or row.get("created")
            )
            symbols = _extract_symbols(row)
            body = str(row.get("body") or row.get("teaser") or row.get("summary") or "")
            items.append(
                RawNewsItem(
                    provider_id=provider_id,
                    headline=headline,
                    url=url,
                    published_at=published,
                    symbols=symbols,
                    body=body,
                )
            )

        self.last_fetch_at = datetime.now(timezone.utc)
        return dedupe_news(items)
