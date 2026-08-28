"""Live data gate — suppress live alerts when WebSocket feed is invalid or stale."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from services.market_session import JUMP_ARMED_SESSIONS, get_us_market_session
from services.ws_feed_state import DATA_UNAVAILABLE, LIVE, LIVE_DATA_UNAVAILABLE

MAX_AGG_AGE_SECONDS = 5.0
MAX_TRADE_AGE_SECONDS = 15.0
MIN_AGG_MESSAGES_PER_MIN = 100


@dataclass
class FeedMetrics:
    ws_connected: bool = False
    ws_authenticated: bool = False
    last_aggregate_mono: float = 0.0
    last_trade_mono: float = 0.0
    aggregate_count_window: int = 0
    window_start_mono: float = field(default_factory=time.monotonic)
    dropped_messages: int = 0
    queue_size: int = 0
    reconnect_count: int = 0
    aggregates_subscribed: bool = False
    session: str = "CLOSED"

    def note_aggregate(self) -> None:
        now = time.monotonic()
        if now - self.window_start_mono >= 60.0:
            self.aggregate_count_window = 0
            self.window_start_mono = now
        self.aggregate_count_window += 1
        self.last_aggregate_mono = now

    def note_trade(self) -> None:
        self.last_trade_mono = time.monotonic()

    @property
    def aggregate_age_seconds(self) -> float:
        if self.last_aggregate_mono <= 0:
            return 9999.0
        return time.monotonic() - self.last_aggregate_mono

    @property
    def is_valid(self) -> bool:
        session = get_us_market_session()
        if session not in JUMP_ARMED_SESSIONS:
            return False
        if not self.ws_connected or not self.ws_authenticated:
            return False
        if not self.aggregates_subscribed:
            return False
        if self.aggregate_age_seconds > MAX_AGG_AGE_SECONDS:
            return False
        if self.aggregate_count_window < MIN_AGG_MESSAGES_PER_MIN and self.aggregate_age_seconds > 30:
            return False
        return True

    @property
    def status(self) -> str:
        from services.live_price_registry import live_price_registry

        state = live_price_registry.feed_state()
        if state == LIVE and self.is_valid:
            return LIVE
        if state in (LIVE, "SUBSCRIBED", "AUTHENTICATED", "CONNECTING", "STALE"):
            return state
        return LIVE_DATA_UNAVAILABLE

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "live_feed_valid": self.is_valid,
            "ws_connected": self.ws_connected,
            "aggregate_age_seconds": round(self.aggregate_age_seconds, 2),
            "aggregate_count_60s": self.aggregate_count_window,
            "dropped_messages": self.dropped_messages,
            "queue_size": self.queue_size,
            "reconnect_count": self.reconnect_count,
            "session": get_us_market_session(),
        }


class LiveDataGate:
    """When invalid — block JUMP/STRONG_BUY; never surface REST/cache as live opportunity."""

    def __init__(self) -> None:
        self.metrics = FeedMetrics()

    def reset_window(self) -> None:
        self.metrics.window_start_mono = time.monotonic()
        self.metrics.aggregate_count_window = 0

    def set_ws_health(self, *, connected: bool, authenticated: bool, aggregates_subscribed: bool) -> None:
        self.metrics.ws_connected = connected
        self.metrics.ws_authenticated = authenticated
        self.metrics.aggregates_subscribed = aggregates_subscribed
        self.metrics.session = get_us_market_session()

    def note_queue(self, *, size: int, dropped: int) -> None:
        self.metrics.queue_size = size
        self.metrics.dropped_messages = dropped

    def note_reconnect(self) -> None:
        self.metrics.reconnect_count += 1

    @property
    def live_feed_valid(self) -> bool:
        from services.live_price_registry import live_price_registry

        return live_price_registry.feed_state() == LIVE and self.metrics.is_valid

    @property
    def jump_engine_status(self) -> str:
        from services.live_price_registry import live_price_registry

        return live_price_registry.feed_state()


live_data_gate = LiveDataGate()
