"""US equity market session detection — America/New_York source, Asia/Riyadh display."""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from services.market_calendar import is_nyse_holiday, regular_close_for_day

logger = logging.getLogger(__name__)

MarketSession = Literal["PRE_MARKET", "REGULAR", "AFTER_HOURS", "CLOSED"]
MarketClosedReason = Literal["MARKET_CLOSED", "NO_LIVE_DATA", ""]

# Primary clock — never hardcode Saudi hours; convert via zoneinfo for DST.
ET = ZoneInfo("America/New_York")
RIYADH = ZoneInfo("Asia/Riyadh")

PRE_MARKET_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
AFTER_HOURS_CLOSE = time(20, 0)

JUMP_ARMED_SESSIONS = frozenset({"PRE_MARKET", "REGULAR", "AFTER_HOURS"})

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


def to_et(when: datetime | None = None) -> datetime:
    """Timezone-aware Eastern Time."""
    if when is None:
        return datetime.now(ET)
    if when.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return when.astimezone(ET)


def to_riyadh(when: datetime | None = None) -> datetime:
    """Display clock — derived from ET, handles DST on both zones."""
    return to_et(when).astimezone(RIYADH)


def trading_session_date_et(when: datetime | None = None) -> str:
    """ET calendar date for stage store / jump registry keys."""
    return to_et(when).strftime("%Y-%m-%d")


def is_weekend_et(when: datetime | None = None) -> bool:
    return to_et(when).weekday() >= 5


def get_market_closed_reason(when: datetime | None = None) -> MarketClosedReason:
    """Why the market is not in an active live session."""
    now_et = to_et(when)
    if is_weekend_et(now_et):
        return "MARKET_CLOSED"
    if is_nyse_holiday(now_et.date()):
        return "MARKET_CLOSED"
    t = now_et.time()
    if t >= AFTER_HOURS_CLOSE or t < PRE_MARKET_OPEN:
        return "NO_LIVE_DATA"
    return ""


def get_regular_close_et(when: datetime | None = None) -> time:
    """Regular close for the ET day — respects early-close calendar."""
    return regular_close_for_day(to_et(when).date())


def get_us_market_session(when: datetime | None = None) -> MarketSession:
    """Return US market session from America/New_York clock (DST-aware)."""
    now_et = to_et(when)
    if is_weekend_et(now_et) or is_nyse_holiday(now_et.date()):
        return "CLOSED"

    t = now_et.time()
    reg_close = get_regular_close_et(now_et)

    if PRE_MARKET_OPEN <= t < REGULAR_OPEN:
        return "PRE_MARKET"
    if REGULAR_OPEN <= t < reg_close:
        return "REGULAR"
    if reg_close <= t < AFTER_HOURS_CLOSE:
        return "AFTER_HOURS"
    return "CLOSED"


def is_regular_session(session: MarketSession | None = None) -> bool:
    return (session or get_us_market_session()) == "REGULAR"


def is_jump_engine_armed_session(session: MarketSession | None = None) -> bool:
    return (session or get_us_market_session()) in JUMP_ARMED_SESSIONS


def session_explanation(session: MarketSession | None = None) -> str:
    return SESSION_EXPLANATIONS.get(session or get_us_market_session(), "")


def session_clock_context(when: datetime | None = None) -> dict[str, str]:
    """UTC + New York + Riyadh clocks for logging and UI."""
    utc = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ny = utc.astimezone(ET)
    ry = utc.astimezone(RIYADH)
    session = get_us_market_session(utc)
    return {
        "utc_time": utc.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "new_york_time": ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "riyadh_time": ry.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "session": session,
        "closed_reason": get_market_closed_reason(utc),
        "jump_engine_armed": str(is_jump_engine_armed_session(session)),
    }


def log_session_transition(
    *,
    old_session: MarketSession,
    new_session: MarketSession,
    ws_connected: bool = False,
    subscribed_symbols: int = 0,
    last_trade_age: float | None = None,
    last_quote_age: float | None = None,
    when: datetime | None = None,
) -> None:
    """Structured log on every session boundary — no engine reset."""
    ctx = session_clock_context(when)
    logger.info(
        "SESSION_TRANSITION UTC_TIME=%s NEW_YORK_TIME=%s RIYADH_TIME=%s "
        "OLD_SESSION=%s NEW_SESSION=%s CLOSED_REASON=%s JUMP_ENGINE_ARMED=%s "
        "WS_CONNECTED=%s SUBSCRIBED_SYMBOLS=%d LAST_TRADE_AGE=%s LAST_QUOTE_AGE=%s",
        ctx["utc_time"],
        ctx["new_york_time"],
        ctx["riyadh_time"],
        old_session,
        new_session,
        ctx["closed_reason"] or "none",
        ctx["jump_engine_armed"],
        ws_connected,
        subscribed_symbols,
        f"{last_trade_age:.1f}s" if last_trade_age is not None else "none",
        f"{last_quote_age:.1f}s" if last_quote_age is not None else "none",
    )


def session_window_table() -> list[dict[str, str]]:
    """Reference table ET + Riyadh for a representative summer weekday (EDT)."""
    # Use a fixed EDT summer date for documentation — actual Riyadh offset varies with DST.
    sample = datetime(2026, 8, 26, 12, 0, tzinfo=ET)
    rows = [
        ("PRE_MARKET", PRE_MARKET_OPEN, REGULAR_OPEN),
        ("REGULAR", REGULAR_OPEN, REGULAR_CLOSE),
        ("AFTER_HOURS", REGULAR_CLOSE, AFTER_HOURS_CLOSE),
        ("CLOSED / NO_LIVE_DATA", AFTER_HOURS_CLOSE, PRE_MARKET_OPEN),
    ]
    out: list[dict[str, str]] = []
    for name, start, end in rows:
        start_et = datetime.combine(sample.date(), start, tzinfo=ET)
        end_et = datetime.combine(sample.date(), end, tzinfo=ET) if end > start else None
        out.append({
            "session": name,
            "et_start": start.strftime("%H:%M"),
            "et_end": end.strftime("%H:%M") if end > start else "04:00 (next)",
            "riyadh_start": start_et.astimezone(RIYADH).strftime("%H:%M"),
            "riyadh_end": end_et.astimezone(RIYADH).strftime("%H:%M") if end_et else "—",
        })
    return out
