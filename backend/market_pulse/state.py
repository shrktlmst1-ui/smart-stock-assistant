"""Per-symbol market state for pulse metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from market_pulse.providers.base import AggregateMinute, LuldEvent, QuoteTick, RawNewsItem, TradeTick


@dataclass
class LinkedNews:
    item: RawNewsItem
    linked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    news_age_seconds: float = 0.0
    classification_sentiment: str = "neutral"
    trigger_type: str = ""
    risk_flags: list[str] = field(default_factory=list)
    catalyst_score: float = 0.0


@dataclass
class SymbolPulseState:
    symbol: str
    trades: list[TradeTick] = field(default_factory=list)
    last_quote: QuoteTick | None = None
    minute_bars: list[AggregateMinute] = field(default_factory=list)
    luld: LuldEvent | None = None
    linked_news: LinkedNews | None = None
    session_volume: int = 0
    baseline_minute_volume: float = 1000.0
    day_high: float = 0.0
    last_price: float = 0.0
    subscribed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    alert_created_at: datetime | None = None
    max_trades_kept: int = 500

    def add_trade(self, tick: TradeTick) -> None:
        self.trades.append(tick)
        if len(self.trades) > self.max_trades_kept:
            self.trades = self.trades[-self.max_trades_kept :]
        self.last_price = tick.price
        self.session_volume += tick.size
        if tick.price > self.day_high:
            self.day_high = tick.price

    def add_minute_bar(self, bar: AggregateMinute) -> None:
        self.minute_bars.append(bar)
        if len(self.minute_bars) > 120:
            self.minute_bars = self.minute_bars[-120:]
        self.last_price = bar.close
        if bar.high > self.day_high:
            self.day_high = bar.high

    def latest_timestamp_ms(self) -> int | None:
        candidates: list[int] = []
        if self.trades:
            candidates.append(self.trades[-1].timestamp_ms)
        if self.last_quote:
            candidates.append(self.last_quote.timestamp_ms)
        if self.minute_bars:
            candidates.append(self.minute_bars[-1].timestamp_ms)
        return max(candidates) if candidates else None
