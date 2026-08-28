"""Bootstrap WS T/Q subscriptions from REST snapshot — breaks rank_pool=0 deadlock."""

from __future__ import annotations

import logging

from config import SCANNER_MAX_PRICE, SCANNER_MAX_SPREAD_PCT, SCANNER_MIN_PRICE
from services.session_price import resolve_session_price

logger = logging.getLogger(__name__)

BOOTSTRAP_MIN_VOLUME = int(__import__("os").getenv("WS_BOOTSTRAP_MIN_VOLUME", "50000"))
BOOTSTRAP_LIMIT = int(__import__("os").getenv("WS_BOOTSTRAP_SYMBOL_LIMIT", "50"))


def _day_bar_metrics(item: dict) -> tuple[float, int] | None:
    """REST coarse metrics — day bar first, avoids strict live freshness gates."""
    day = item.get("day") or {}
    prev = item.get("prevDay") or {}
    price = float(day.get("c") or day.get("o") or prev.get("c") or 0)
    vol = int(day.get("v") or 0)
    if price <= 0:
        return None
    return price, vol


def _item_price_volume(item: dict) -> tuple[float, int] | None:
    sp = resolve_session_price(item)
    if sp.is_valid and sp.price > 0:
        return sp.price, int(sp.volume or 0)
    return _day_bar_metrics(item)


def bootstrap_symbols_from_snapshot(
    snapshot_raw: dict[str, dict],
    symbol_set: set[str],
    *,
    limit: int = BOOTSTRAP_LIMIT,
    min_volume: int = BOOTSTRAP_MIN_VOLUME,
) -> list[str]:
    """Rank tickers by dollar volume — no rank_pool or liquid dependency."""
    ranked: list[tuple[str, float, int]] = []
    for sym, item in snapshot_raw.items():
        if symbol_set and sym not in symbol_set:
            continue
        metrics = _item_price_volume(item)
        if not metrics:
            continue
        price, vol = metrics
        if price < SCANNER_MIN_PRICE or price > SCANNER_MAX_PRICE:
            continue
        if vol < min_volume:
            continue
        day = item.get("day") or {}
        high = float(day.get("h") or price)
        low = float(day.get("l") or price)
        spread_pct = ((high - low) / price * 100) if price > 0 else 99.0
        if spread_pct > SCANNER_MAX_SPREAD_PCT * 3:
            continue
        dollar_vol = price * vol
        ranked.append((sym.upper(), dollar_vol, vol))

    ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)
    symbols = [s for s, _, _ in ranked[:limit]]
    if symbols:
        logger.info(
            "[WS_BOOTSTRAP] ranked bootstrap_symbols_count=%d top=%s dollar_vol_top=%.0f",
            len(symbols),
            symbols[:5],
            ranked[0][1],
        )
    else:
        logger.warning(
            "[WS_BOOTSTRAP] ranked bootstrap_symbols_count=0 from snapshot_items=%d",
            len(snapshot_raw),
        )
    return symbols
