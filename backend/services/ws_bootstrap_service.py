"""Fetch REST snapshot and bootstrap WS symbol subscriptions before rank_pool exists."""

from __future__ import annotations

import logging

from services.live_price_registry import live_price_registry
from services.universe_manager import universe_manager
from services.ws_bootstrap_symbols import BOOTSTRAP_LIMIT, bootstrap_symbols_from_snapshot

logger = logging.getLogger(__name__)


async def fetch_bootstrap_symbols(
    *,
    limit: int = BOOTSTRAP_LIMIT,
) -> tuple[list[str], int, dict[str, dict]]:
    """Pull full market snapshot from REST — independent of rank_pool/liquid."""
    from services.polygon_client import PolygonClient

    await universe_manager.ensure_loaded()
    client = PolygonClient()
    try:
        raw_list = await client.get_full_market_snapshot()
        snapshot_count = len(raw_list)
        snapshot_raw = {
            (i.get("ticker") or "").upper(): i for i in raw_list if i.get("ticker")
        }
        symbol_set = universe_manager.symbol_set or set(snapshot_raw.keys())
        symbols = bootstrap_symbols_from_snapshot(
            snapshot_raw, symbol_set, limit=limit,
        )
        if not symbols and snapshot_raw:
            symbols = bootstrap_symbols_from_snapshot(
                snapshot_raw, set(snapshot_raw.keys()), limit=limit,
            )
        live_price_registry.set_bootstrap_metrics(
            snapshot_count=snapshot_count,
            symbols_count=len(symbols),
        )
        logger.info(
            "[WS_BOOTSTRAP] fetch_complete bootstrap_snapshot_count=%d "
            "bootstrap_symbols_count=%d sample=%s",
            snapshot_count,
            len(symbols),
            symbols[:8],
        )
        return symbols, snapshot_count, snapshot_raw
    finally:
        await client.close()
