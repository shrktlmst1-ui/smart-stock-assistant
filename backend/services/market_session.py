"""US equity market session detection (Eastern Time)."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

MarketSession = Literal["PRE_MARKET", "REGULAR", "AFTER_HOURS", "CLOSED"]

ET = ZoneInfo("America/New_York")

# US market holidays are not modeled; session windows follow standard NYSE hours.
PRE_MARKET_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
AFTER_HOURS_CLOSE = time(20, 0)

SESSION_EXPLANATIONS: dict[MarketSession, str] = {
    "PRE_MARKET": (
        "Market is currently in Pre-Market. "
        "Live liquidity filters are disabled. "
        "Showing the highest-quality watchlist candidates based on completed market data."
    ),
    "AFTER_HOURS": (
        "Market is currently in After-Hours. "
        "Live liquidity filters are disabled. "
        "Showing the highest-quality watchlist candidates based on completed market data."
    ),
    "CLOSED": (
        "Market is currently Closed. "
        "Live liquidity filters are disabled. "
        "Showing the highest-quality watchlist candidates based on completed market data."
    ),
    "REGULAR": "",
}


def get_us_market_session(when: datetime | None = None) -> MarketSession:
    """Return the current US market session in Eastern Time."""
    now_et = (when or datetime.now(timezone.utc)).astimezone(ET) if when else datetime.now(ET)
    if now_et.weekday() >= 5:
        return "CLOSED"

    t = now_et.time()
    if PRE_MARKET_OPEN <= t < REGULAR_OPEN:
        return "PRE_MARKET"
    if REGULAR_OPEN <= t < REGULAR_CLOSE:
        return "REGULAR"
    if REGULAR_CLOSE <= t < AFTER_HOURS_CLOSE:
        return "AFTER_HOURS"
    return "CLOSED"


def is_regular_session(session: MarketSession | None = None) -> bool:
    return (session or get_us_market_session()) == "REGULAR"


def session_explanation(session: MarketSession | None = None) -> str:
    return SESSION_EXPLANATIONS.get(session or get_us_market_session(), "")
