"""News deduplication for Market Pulse."""

from __future__ import annotations

import hashlib

from market_pulse.providers.base import RawNewsItem


def _title_hash(headline: str) -> str:
    normalized = " ".join(headline.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def dedupe_key(item: RawNewsItem) -> str:
    if item.provider_id:
        return f"id:{item.provider_id}"
    if item.url:
        return f"url:{item.url.strip().lower()}"
    return f"hash:{_title_hash(item.headline)}"


def dedupe_news(items: list[RawNewsItem]) -> list[RawNewsItem]:
    seen: set[str] = set()
    out: list[RawNewsItem] = []
    for item in items:
        key = dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
