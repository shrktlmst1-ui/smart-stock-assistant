"""Integration tests: Jump Engine continuity across PRE_MARKET → REGULAR."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models.pre_move_stage import PreMoveStageProgressionMetrics, StageSnapshot
from services.live_price_registry import live_price_registry
from services.pre_move_stage_store import get_or_create_state, reset_store, update_stage_state
from services.session_price import (
    STALE_PRICE_STATUS,
    resolve_jump_execution_price,
)


def _now_ns() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)


def _stale_premarket_item() -> dict:
    from tests.test_session_price import _btct_stale_premarket_item

    return _btct_stale_premarket_item()


def _stage_metrics() -> PreMoveStageProgressionMetrics:
    return PreMoveStageProgressionMetrics(
        stage_lifecycle="EARLY_ENTRY",
        previous_lifecycle="PRE_BREAKOUT",
        stage_progression_score=72.0,
        momentum_persistence_score=65.0,
        persistence_minutes=18,
        trigger_readiness_score=80.0,
    )


@pytest.fixture(autouse=True)
def _clean_state():
    reset_store()
    live_price_registry.clear_execution_prices()
    import services.session_price as sp_mod

    sp_mod._last_known_session = None
    yield
    reset_store()
    live_price_registry.clear_execution_prices()
    sp_mod._last_known_session = None


def test_premarket_to_regular_preserves_fresh_ws_price():
    """Fresh WS tick must survive session switch — REST alone would be STALE."""
    import services.session_price as sp_mod

    sym = "BTCT"
    item = _stale_premarket_item()
    ws_price = 2.15

    sp_mod._last_known_session = "PRE_MARKET"
    with patch("services.live_price_registry.get_us_market_session", return_value="REGULAR"):
        live_price_registry.ingest_trade(sym, ws_price, exchange_ts_ns=_now_ns())

    with patch("services.session_price.get_us_market_session", return_value="REGULAR"):
        sp_mod.ensure_session_cache_valid()

    with patch("services.session_price.get_us_market_session", return_value="REGULAR"):
        sp, diag = resolve_jump_execution_price(item, symbol=sym, session="REGULAR")

    assert live_price_registry.get_tick(sym) is not None
    assert not sp.is_stale, f"STALE after transition: {diag}"
    assert sp.price == pytest.approx(ws_price, rel=1e-3)
    assert sp.source in ("last_trade", "live_trade")
    assert diag["STALE_PRICE"] is False


def test_premarket_to_regular_without_fix_would_stale():
    """Control: clearing WS on transition reproduces session-switch STALE."""
    from tests.test_session_price import _ns_ago

    sym = "BTCT"
    item = _stale_premarket_item()
    item["updated"] = _ns_ago(120)
    item["day"] = {"c": 0, "v": 0, "o": 0, "h": 0, "l": 0}
    item["min"] = {"c": 0, "v": 0, "t": 0}

    with patch("services.live_price_registry.get_us_market_session", return_value="REGULAR"):
        live_price_registry.ingest_trade(sym, 2.15, exchange_ts_ns=_now_ns())
    live_price_registry.clear_execution_prices()

    with patch("services.session_price.get_us_market_session", return_value="REGULAR"):
        sp, _diag = resolve_jump_execution_price(item, symbol=sym, session="REGULAR")

    assert sp.is_stale
    assert sp.stale_reason == STALE_PRICE_STATUS


def test_premarket_to_regular_preserves_stage_progression_fields():
    """Stage store + first_detected_* / persistence must not reset on transition."""
    import services.session_price as sp_mod

    sym = "BTCT"
    session_date = "2026-08-26"
    snap = StageSnapshot(
        timestamp="2026-08-26T08:45:00-04:00",
        price=2.07,
        change_pct=12.0,
        pre_move_score=68,
        trigger_price=2.12,
    )
    metrics = _stage_metrics()

    state = update_stage_state(sym, session_date, snap, "EARLY_ENTRY", metrics)
    state.minutes_in_stage = 18.0
    state.peak_stage = "EARLY_ENTRY"
    state.peak_progression_score = 72.0

    before = {
        "current_stage": state.current_stage,
        "first_detected_at": state.first_detected_at,
        "first_detected_price": state.first_detected_price,
        "minutes_in_stage": state.minutes_in_stage,
        "peak_stage": state.peak_stage,
        "peak_progression_score": state.peak_progression_score,
        "snapshots_len": len(state.snapshots),
    }

    sp_mod._last_known_session = "PRE_MARKET"
    with patch("services.session_price.get_us_market_session", return_value="REGULAR"):
        sp_mod.ensure_session_cache_valid()

    after_state = get_or_create_state(sym, session_date)
    assert after_state.current_stage == before["current_stage"]
    assert after_state.first_detected_at == before["first_detected_at"]
    assert after_state.first_detected_price == before["first_detected_price"]
    assert after_state.minutes_in_stage == before["minutes_in_stage"]
    assert after_state.peak_stage == before["peak_stage"]
    assert after_state.peak_progression_score == before["peak_progression_score"]
    assert len(after_state.snapshots) == before["snapshots_len"]


def test_premarket_to_regular_rejection_is_trading_not_session_cache():
    """If gate rejects after transition, reason must not be STALE_PRICE when WS is fresh."""
    import services.session_price as sp_mod

    sym = "BTCT"
    item = _stale_premarket_item()

    sp_mod._last_known_session = "PRE_MARKET"
    with patch("services.live_price_registry.get_us_market_session", return_value="REGULAR"):
        live_price_registry.ingest_trade(sym, 2.15, exchange_ts_ns=_now_ns())

    with patch("services.session_price.get_us_market_session", return_value="REGULAR"):
        sp_mod.ensure_session_cache_valid()
        sp, diag = resolve_jump_execution_price(item, symbol=sym, session="REGULAR")

    assert not sp.is_stale
    assert diag["STALE_PRICE"] is False
    assert sp.stale_reason != STALE_PRICE_STATUS
