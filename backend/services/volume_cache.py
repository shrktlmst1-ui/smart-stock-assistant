"""Cached 30-day average daily volume (ADV30) from Polygon daily bars."""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

ADV30_CACHE_TTL_SECONDS = 86400
_adv30_cache: dict[str, tuple[float, float]] = {}


def get_cached_adv30(symbol: str) -> float:
    sym = symbol.upper()
    row = _adv30_cache.get(sym)
    if not row:
        return 0.0
    adv, ts = row
    if time.monotonic() - ts > ADV30_CACHE_TTL_SECONDS:
        return 0.0
    return adv


def set_cached_adv30(symbol: str, adv30: float) -> None:
    if adv30 > 0:
        _adv30_cache[symbol.upper()] = (adv30, time.monotonic())


async def compute_adv30(client, symbol: str) -> float:
    """Mean daily volume over the last 30 completed trading days."""
    cached = get_cached_adv30(symbol)
    if cached > 0:
        return cached
    try:
        df = await client.get_daily_bars(symbol, limit=30)
        if df.empty or "volume" not in df.columns:
            return 0.0
        adv = float(df["volume"].tail(30).mean())
        if adv > 0:
            set_cached_adv30(symbol, adv)
        return adv
    except Exception as e:
        logger.debug("ADV30 %s: %s", symbol, e)
        return 0.0


async def enrich_adv30_batch(
    client,
    symbols: list[str],
    *,
    max_symbols: int = 400,
    concurrency: int = 12,
) -> None:
    """Populate ADV30 cache for off-hours liquidity filtering."""
    pending = [
        s.upper()
        for s in symbols
        if get_cached_adv30(s) <= 0
    ][:max_symbols]
    if not pending:
        return

    sem = asyncio.Semaphore(concurrency)

    async def one(sym: str) -> None:
        async with sem:
            await compute_adv30(client, sym)

    await asyncio.gather(*(one(s) for s in pending))
    logger.info("ADV30 cache enriched for %d symbols (cache size=%d)", len(pending), len(_adv30_cache))
