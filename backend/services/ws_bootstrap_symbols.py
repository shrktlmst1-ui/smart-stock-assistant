"""Bootstrap WS T/Q subscriptions from REST snapshot — breaks rank_pool=0 deadlock."""

from __future__ import annotations

import logging

from config import SCANNER_MAX_PRICE, SCANNER_MAX_SPREAD_PCT, SCANNER_MIN_PRICE
from services.session_price import resolve_session_price

logger = logging.getLogger(__name__)

BOOTSTRAP_MIN_VOLUME = int(__import__("os").getenv("WS_BOOTSTRAP_MIN_VOLUME", "50000"))
BOOTSTRAP_LIMIT = int(__import__("os").getenv("WS_BOOTSTRAP_SYMBOL_LIMIT", "50"))


def bootstrap_symbols_from_snapshot(
    snapshot_raw: dict[str, dict],
    symbol_set: set[str],
    *,
    limit: int = BOOTSTRAP_LIMIT,
    min_volume: int = BOOTSTRAP_MIN_VOLUME,
) -> list[str]:
    """Rank universe tickers by dollar volume + intraday volume — no rank_pool dependency."""
    ranked: list[tuple[str, float, int]] = []
    for sym, item in snapshot_raw.items():
        if sym not in symbol_set:
            continue
        sp = resolve_session_price(item)
        if not sp.is_valid:
            continue
        price = sp.price
        if price < SCANNER_MIN_PRICE or price > SCANNER_MAX_PRICE:
            continue
        vol = int(sp.volume or 0)
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
            "[WS_BOOTSTRAP] snapshot bootstrap symbols=%d top=%s dollar_vol_top=%.0f",
            len(symbols),
            symbols[:5],
            ranked[0][1] if ranked else 0,
        )
    return symbols
