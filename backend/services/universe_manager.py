"""Universe Manager — NYSE, NASDAQ, AMEX, ETFs from Polygon reference API."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from config import (
    SCANNER_MAX_PRICE,
    SCANNER_MIN_AVG_VOLUME,
    SCANNER_MIN_MARKET_CAP,
    SCANNER_MIN_PRICE,
    UNIVERSE_CACHE_SECONDS,
)
from services.polygon_client import PolygonClient

logger = logging.getLogger(__name__)

EXCHANGE_MAP = {
    "XNYS": "NYSE",
    "XNAS": "NASDAQ",
    "XASE": "AMEX",
}


@dataclass
class UniverseMember:
    symbol: str
    name: str
    exchange: str
    market_cap: float = 0.0
    float_shares: float = 0.0
    avg_volume: float = 0.0


@dataclass
class UniverseState:
    members: dict[str, UniverseMember] = field(default_factory=dict)
    by_exchange: dict[str, int] = field(default_factory=dict)
    updated_at: float = 0.0


class UniverseManager:
    def __init__(self) -> None:
        self.client = PolygonClient()
        self._state = UniverseState()
        self._loading = False

    @property
    def symbol_set(self) -> set[str]:
        return set(self._state.members.keys())

    @property
    def members(self) -> dict[str, UniverseMember]:
        return self._state.members

    def get_member(self, symbol: str) -> UniverseMember | None:
        return self._state.members.get(symbol.upper())

    def stats(self) -> dict:
        return {
            "total": len(self._state.members),
            "by_exchange": dict(self._state.by_exchange),
            "updated_at": self._state.updated_at,
        }

    def is_stale(self) -> bool:
        if not self._state.members:
            return True
        return time.monotonic() - self._state.updated_at > UNIVERSE_CACHE_SECONDS

    async def ensure_loaded(self) -> UniverseState:
        if not self.is_stale():
            return self._state
        if self._loading:
            return self._state
        self._loading = True
        try:
            await self._load_universe()
        finally:
            self._loading = False
        return self._state

    async def _load_universe(self) -> None:
        t0 = time.monotonic()
        members: dict[str, UniverseMember] = {}
        counts: dict[str, int] = {v: 0 for v in EXCHANGE_MAP.values()}
        counts["ETF"] = 0

        for mic, label in EXCHANGE_MAP.items():
            tickers = await self.client.list_reference_tickers(exchange=mic)
            for t in tickers:
                sym = (t.get("ticker") or "").upper()
                if not sym or sym in members:
                    continue
                members[sym] = UniverseMember(
                    symbol=sym,
                    name=str(t.get("name") or sym),
                    exchange=label,
                    market_cap=float(t.get("market_cap") or 0),
                    float_shares=float(
                        t.get("share_class_shares_outstanding")
                        or t.get("weighted_shares_outstanding")
                        or 0
                    ),
                )
                counts[label] += 1

        etfs = await self.client.list_reference_tickers(ticker_type="ETF")
        for t in etfs:
            sym = (t.get("ticker") or "").upper()
            if not sym:
                continue
            if sym not in members:
                members[sym] = UniverseMember(
                    symbol=sym,
                    name=str(t.get("name") or sym),
                    exchange="ETF",
                    market_cap=float(t.get("market_cap") or 0),
                    float_shares=float(
                        t.get("share_class_shares_outstanding") or 0
                    ),
                )
                counts["ETF"] += 1
            else:
                members[sym].exchange = members[sym].exchange + "+ETF"

        self._state = UniverseState(
            members=members,
            by_exchange=counts,
            updated_at=time.monotonic(),
        )
        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "Universe loaded: %d symbols NYSE=%d NASDAQ=%d AMEX=%d ETF=%d (%.0fms)",
            len(members), counts["NYSE"], counts["NASDAQ"], counts["AMEX"], counts["ETF"], elapsed,
        )

    def passes_universe_filters(
        self,
        symbol: str,
        price: float,
        day_volume: int,
        prev_volume: int,
        market_cap: float = 0,
        float_shares: float = 0,
    ) -> bool:
        if symbol.upper() not in self._state.members:
            return False
        if price < SCANNER_MIN_PRICE or price > SCANNER_MAX_PRICE:
            return False
        avg_vol = prev_volume or day_volume
        if avg_vol < SCANNER_MIN_AVG_VOLUME:
            return False
        mcap = market_cap or self._state.members[symbol.upper()].market_cap
        if mcap > 0 and mcap < SCANNER_MIN_MARKET_CAP:
            return False
        member = self._state.members[symbol.upper()]
        if float_shares > 0 and float_shares < 1_000_000:
            return False
        if member.float_shares > 0 and member.float_shares < 1_000_000:
            return False
        return True


universe_manager = UniverseManager()
