"""WebSocket feed lifecycle states — connect → auth → subscribe → live market data."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Literal

from services.market_session import is_jump_engine_armed_session

FeedState = Literal[
    "CONNECTING",
    "AUTHENTICATED",
    "SUBSCRIBED",
    "LIVE",
    "STALE",
    "DATA_UNAVAILABLE",
]

CONNECTING: FeedState = "CONNECTING"
AUTHENTICATED: FeedState = "AUTHENTICATED"
SUBSCRIBED: FeedState = "SUBSCRIBED"
LIVE: FeedState = "LIVE"
STALE: FeedState = "STALE"
DATA_UNAVAILABLE: FeedState = "DATA_UNAVAILABLE"

# Alias used by opportunity-now / live_data_gate consumers.
LIVE_DATA_UNAVAILABLE = DATA_UNAVAILABLE

WS_STALE_MESSAGE_SECONDS: float = float(
    __import__("os").getenv("WS_STALE_MESSAGE_SECONDS", "15")
)


def resolve_feed_state(
    *,
    session: str,
    hub_running: bool,
    connected: bool,
    authenticated: bool,
    subscribed: bool,
    last_message_at: datetime | None,
    subscribed_at_mono: float | None = None,
    stale_failure_count: int = 0,
    max_stale_failures: int = 3,
) -> FeedState:
    """Resolve feed state — LIVE only after a real market-data payload (not status)."""
    if stale_failure_count >= max_stale_failures:
        return DATA_UNAVAILABLE
    if not is_jump_engine_armed_session(session):  # type: ignore[arg-type]
        return DATA_UNAVAILABLE
    if not hub_running:
        return DATA_UNAVAILABLE
    stale_threshold = WS_STALE_MESSAGE_SECONDS
    if not connected or not authenticated:
        return CONNECTING
    if not subscribed:
        return AUTHENTICATED
    if last_message_at is not None:
        age = (datetime.now(timezone.utc) - last_message_at).total_seconds()
        if age <= stale_threshold:
            return LIVE
        return STALE
    if subscribed_at_mono is not None:
        since_sub = time.monotonic() - subscribed_at_mono
        if since_sub >= stale_threshold:
            return STALE
    return SUBSCRIBED


def message_age_seconds(last_message_at: datetime | None) -> float | None:
    if last_message_at is None:
        return None
    return (datetime.now(timezone.utc) - last_message_at).total_seconds()
