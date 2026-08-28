"""Unified US eligible price band — config-driven, price-neutral."""

from __future__ import annotations

from config import SCANNER_MAX_PRICE, SCANNER_MIN_PRICE


def passes_universe_price(price: float) -> bool:
    """Penny stocks through $10 — same rules for scanner, jumps, and opportunity layers."""
    return price >= SCANNER_MIN_PRICE and price <= SCANNER_MAX_PRICE


def price_universe_reject_reason(price: float) -> str | None:
    if price <= 0:
        return "invalid_price"
    if price < SCANNER_MIN_PRICE:
        return "below_min_price"
    if price > SCANNER_MAX_PRICE:
        return "above_max_price"
    return None
