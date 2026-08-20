"""Symbol subscription manager — no market-wide wildcards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TrackedSymbol:
    symbol: str
    source: str  # news | watchlist
    subscribed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SubscriptionManager:
    """Track up to max_symbols with TTL eviction — never T.* or Q.*."""

    WILDCARD_PATTERNS = ("T.*", "Q.*", "A.*", "AM.*", "LULD.*")

    def __init__(self, max_symbols: int = 50, ttl_seconds: int = 3600):
        self.max_symbols = max_symbols
        self.ttl_seconds = ttl_seconds
        self._symbols: dict[str, TrackedSymbol] = {}

    def _is_wildcard(self, symbol_or_channel: str) -> bool:
        upper = symbol_or_channel.upper().strip()
        if upper.endswith(".*") or upper in ("*", "ALL"):
            return True
        return upper in self.WILDCARD_PATTERNS

    def add(self, symbol: str, source: str = "news") -> bool:
        sym = symbol.strip().upper()
        if not sym or self._is_wildcard(sym):
            return False
        self.evict_stale()
        if sym in self._symbols:
            return True
        if len(self._symbols) >= self.max_symbols:
            oldest = min(self._symbols.values(), key=lambda t: t.subscribed_at)
            del self._symbols[oldest.symbol]
        self._symbols[sym] = TrackedSymbol(symbol=sym, source=source)
        return True

    def add_many(self, symbols: list[str], source: str = "news") -> list[str]:
        added: list[str] = []
        for s in symbols:
            if self.add(s, source=source):
                added.append(s.strip().upper())
        return added

    def remove(self, symbol: str) -> None:
        self._symbols.pop(symbol.upper(), None)

    def evict_stale(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        evicted: list[str] = []
        for sym, tracked in list(self._symbols.items()):
            age = (now - tracked.subscribed_at).total_seconds()
            if age > self.ttl_seconds:
                del self._symbols[sym]
                evicted.append(sym)
        return evicted

    def symbols(self) -> list[str]:
        self.evict_stale()
        return sorted(self._symbols.keys())

    def count(self) -> int:
        return len(self.symbols())

    def build_ws_subscriptions(self) -> list[str]:
        """Per-symbol feeds only — A, AM, T, Q, LULD — no wildcards."""
        subs: list[str] = []
        for sym in self.symbols():
            subs.extend([
                f"A.{sym}",
                f"AM.{sym}",
                f"T.{sym}",
                f"Q.{sym}",
                f"LULD.{sym}",
            ])
        return subs

    def contains_wildcard(self, subscriptions: list[str]) -> bool:
        for sub in subscriptions:
            upper = sub.upper()
            if upper.endswith(".*"):
                return True
            parts = upper.split(".", 1)
            if len(parts) == 2 and parts[1] in ("*", "ALL"):
                return True
            if upper in self.WILDCARD_PATTERNS:
                return True
        return False
