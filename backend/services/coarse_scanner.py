"""Threaded coarse scan — score thousands of tickers in parallel."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import SCANNER_WORKER_THREADS
from analysis.institutional_score import compute_coarse_institutional_score
from services.market_session import MarketSession, get_us_market_session
from services.scanner_filters import TickerMetrics, parse_snapshot_item, passes_liquidity_filter
from services.universe_manager import UniverseManager, UniverseMember

logger = logging.getLogger(__name__)


def _score_one(
    item: dict,
    member: UniverseMember | None,
    in_universe: bool,
    session: MarketSession,
) -> tuple[str, TickerMetrics, float] | None:
    if not in_universe:
        return None
    meta = None
    if member:
        meta = {
            "name": member.name,
            "market_cap": member.market_cap,
            "float_shares": member.float_shares,
        }
    m = parse_snapshot_item(item, meta)
    if not m or not passes_liquidity_filter(m, session):
        return None
    coarse = compute_coarse_institutional_score(m, item)
    return m.symbol, m, coarse


def coarse_scan_threaded(
    snapshot_items: list[dict],
    universe: UniverseManager,
    max_workers: int | None = None,
    session: MarketSession | None = None,
) -> list[tuple[TickerMetrics, float]]:
    """Score all liquid universe tickers using a thread pool."""
    workers = max_workers or SCANNER_WORKER_THREADS
    market_session = session or get_us_market_session()
    symbol_set = universe.symbol_set
    members = universe.members

    results: list[tuple[TickerMetrics, float]] = []
    chunk_size = 400
    chunks = [snapshot_items[i : i + chunk_size] for i in range(0, len(snapshot_items), chunk_size)]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for chunk in chunks:
            for item in chunk:
                sym = (item.get("ticker") or "").upper()
                futures.append(
                    pool.submit(
                        _score_one,
                        item,
                        members.get(sym),
                        sym in symbol_set,
                        market_session,
                    )
                )
        for fut in as_completed(futures):
            try:
                row = fut.result()
                if row:
                    _, metrics, coarse = row
                    metrics.composite_score = coarse
                    results.append((metrics, coarse))
            except Exception as e:
                logger.debug("coarse score error: %s", e)

    results.sort(key=lambda x: x[1], reverse=True)
    logger.info(
        "Coarse scan scored %d liquid tickers (workers=%d, session=%s)",
        len(results), workers, market_session,
    )
    return results
