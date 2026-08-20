"""Provider interfaces for Market Pulse."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawNewsItem:
    provider_id: str
    headline: str
    url: str = ""
    published_at: datetime | None = None
    symbols: list[str] = field(default_factory=list)
    body: str = ""


@dataclass
class TradeTick:
    symbol: str
    price: float
    size: int
    timestamp_ms: int
    conditions: list[int] = field(default_factory=list)


@dataclass
class QuoteTick:
    symbol: str
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    timestamp_ms: int


@dataclass
class AggregateMinute:
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    timestamp_ms: int


@dataclass
class LuldEvent:
    symbol: str
    halt: bool
    reason: str = ""
    timestamp_ms: int = 0


class FilingProvider(ABC):
    """Interface for future SEC filing integration."""

    @abstractmethod
    async def fetch_recent_filings(self, symbol: str, limit: int = 10) -> list[dict]:
        """Return recent SEC filings for a symbol."""
