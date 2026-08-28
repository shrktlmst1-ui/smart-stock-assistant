"""Rank symbols from live WS trade activity — feeds rank_pool without REST-only deadlock."""

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_trade_dollar: dict[str, float] = defaultdict(float)
_trade_count: dict[str, int] = defaultdict(int)


def note_live_trade(symbol: str, price: float, size: int = 0) -> None:
    sym = symbol.upper()
    if not sym or price <= 0:
        return
    dollars = price * max(size, 1)
    with _lock:
        _trade_dollar[sym] += dollars
        _trade_count[sym] += 1


def top_live_symbols(limit: int = 50) -> list[str]:
    with _lock:
        if not _trade_dollar:
            return []
        ranked = sorted(_trade_dollar.items(), key=lambda x: (x[1], _trade_count[x[0]]), reverse=True)
    return [s for s, _ in ranked[:limit]]


def reset_live_ranks() -> None:
    with _lock:
        _trade_dollar.clear()
        _trade_count.clear()
