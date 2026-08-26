"""Market session boundaries — America/New_York, DST, holidays, transitions."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from services.market_session import (
    AFTER_HOURS_CLOSE,
    ET,
    PRE_MARKET_OPEN,
    REGULAR_CLOSE,
    REGULAR_OPEN,
    RIYADH,
    get_market_closed_reason,
    get_us_market_session,
    is_jump_engine_armed_session,
    is_weekend_et,
    log_session_transition,
    session_clock_context,
    to_riyadh,
    trading_session_date_et,
)
from services.market_calendar import is_nyse_holiday


def _et(y, mo, d, h, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def test_boundary_0359_closed_0400_premarket():
    assert get_us_market_session(_et(2026, 8, 26, 3, 59)) == "CLOSED"
    assert get_us_market_session(_et(2026, 8, 26, 4, 0)) == "PRE_MARKET"


def test_boundary_0929_premarket_0930_regular():
    assert get_us_market_session(_et(2026, 8, 26, 9, 29)) == "PRE_MARKET"
    assert get_us_market_session(_et(2026, 8, 26, 9, 30)) == "REGULAR"


def test_boundary_1559_regular_1600_afterhours():
    assert get_us_market_session(_et(2026, 8, 26, 15, 59)) == "REGULAR"
    assert get_us_market_session(_et(2026, 8, 26, 16, 0)) == "AFTER_HOURS"


def test_boundary_1959_afterhours_2000_closed():
    assert get_us_market_session(_et(2026, 8, 26, 19, 59)) == "AFTER_HOURS"
    assert get_us_market_session(_et(2026, 8, 26, 20, 0)) == "CLOSED"
    assert get_market_closed_reason(_et(2026, 8, 26, 20, 0)) == "NO_LIVE_DATA"


def test_weekend_market_closed():
    # Saturday 2026-08-29
    sat = _et(2026, 8, 29, 12, 0)
    assert is_weekend_et(sat)
    assert get_us_market_session(sat) == "CLOSED"
    assert get_market_closed_reason(sat) == "MARKET_CLOSED"


def test_nyse_holiday_closed():
    christmas = _et(2026, 12, 25, 12, 0)
    assert is_nyse_holiday(christmas.date())
    assert get_us_market_session(christmas) == "CLOSED"
    assert get_market_closed_reason(christmas) == "MARKET_CLOSED"


def test_dst_summer_riyadh_offset():
    """EDT day — Riyadh ~7h ahead of New York (not hardcoded, from zoneinfo)."""
    ny = _et(2026, 8, 26, 9, 30)
    ry = to_riyadh(ny)
    assert ry.hour == 16
    assert ry.minute == 30


def test_dst_winter_riyadh_offset():
    """EST day — Riyadh ~8h ahead of New York."""
    ny = datetime(2026, 1, 15, 9, 30, tzinfo=ET)
    ry = to_riyadh(ny)
    assert ry.hour == 17
    assert ry.minute == 30


def test_midnight_riyadh_still_et_session():
    """00:30 Riyadh on Wed → still Tue evening ET (AFTER_HOURS or CLOSED)."""
    ry = datetime(2026, 8, 27, 0, 30, tzinfo=RIYADH)
    session = get_us_market_session(ry.astimezone(timezone.utc))
    assert session in ("AFTER_HOURS", "CLOSED", "PRE_MARKET")


def test_trading_session_date_uses_et_not_utc():
    # 2026-08-27 02:00 UTC = 2026-08-26 22:00 ET (still same ET trading day)
    utc = datetime(2026, 8, 27, 2, 0, tzinfo=timezone.utc)
    assert trading_session_date_et(utc) == "2026-08-26"


def test_jump_armed_only_active_sessions():
    assert is_jump_engine_armed_session("PRE_MARKET")
    assert is_jump_engine_armed_session("REGULAR")
    assert is_jump_engine_armed_session("AFTER_HOURS")
    assert not is_jump_engine_armed_session("CLOSED")


def test_premarket_to_regular_transition_logging(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="services.market_session")
    log_session_transition(
        old_session="PRE_MARKET",
        new_session="REGULAR",
        ws_connected=True,
        subscribed_symbols=42,
        last_trade_age=1.2,
        last_quote_age=0.8,
        when=_et(2026, 8, 26, 9, 30),
    )
    assert any("SESSION_TRANSITION" in r.message for r in caplog.records)
    assert any("OLD_SESSION=PRE_MARKET" in r.message for r in caplog.records)
    assert any("NEW_SESSION=REGULAR" in r.message for r in caplog.records)


def test_premarket_to_regular_preserves_stage_and_ws():
    """PRE_MARKET → REGULAR must not reset stage store or WS ticks."""
    from unittest.mock import patch

    from services.live_price_registry import live_price_registry
    from services.pre_move_stage_store import get_or_create_state, reset_store, update_stage_state
    from services.session_price import ensure_session_cache_valid
    from models.pre_move_stage import PreMoveStageProgressionMetrics, StageSnapshot
    import services.session_price as sp_mod

    reset_store()
    live_price_registry.clear_execution_prices()
    sp_mod._last_known_session = "PRE_MARKET"

    sym = "JMP1"
    session_date = trading_session_date_et(_et(2026, 8, 26, 8, 0))
    snap = StageSnapshot(
        timestamp="2026-08-26T08:45:00-04:00",
        price=2.07,
        change_pct=12.0,
        pre_move_score=68,
        trigger_price=2.12,
    )
    metrics = PreMoveStageProgressionMetrics(
        stage_lifecycle="EARLY_ENTRY",
        previous_lifecycle="PRE_BREAKOUT",
        stage_progression_score=72.0,
        momentum_persistence_score=65.0,
        persistence_minutes=18,
        trigger_readiness_score=80.0,
    )
    update_stage_state(sym, session_date, snap, "EARLY_ENTRY", metrics)
    live_price_registry.ingest_trade(sym, 2.15, exchange_ts_ns=int(_et(2026, 8, 26, 9, 29).timestamp() * 1e9))

    with patch("services.session_price.get_us_market_session", return_value="REGULAR"):
        ensure_session_cache_valid()

    after = get_or_create_state(sym, session_date)
    assert after.current_stage == "EARLY_ENTRY"
    assert live_price_registry.get_tick(sym) is not None

    reset_store()
    live_price_registry.clear_execution_prices()
    sp_mod._last_known_session = None


def test_session_clock_context_has_three_zones():
    ctx = session_clock_context(_et(2026, 8, 26, 9, 30))
    assert "utc_time" in ctx
    assert "new_york_time" in ctx
    assert "riyadh_time" in ctx
    assert ctx["session"] == "REGULAR"
