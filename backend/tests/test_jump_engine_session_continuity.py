"""Jump Engine 24/7 — session transitions must not stop or reset state."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models.pre_move_stage import PreMoveStageProgressionMetrics, StageSnapshot
from services.extended_hours_gap_detector import ExtendedGapDetection, extended_gap_registry
from services.jump_alert_registry import JumpAlertRegistry
from services.jump_engine_monitor import JumpEngineMonitor, _resolve_jump_engine_status
from services.live_price_registry import live_price_registry
from services.opportunity_now_service import _collect_jump_alerts
from services.pre_move_stage_store import get_or_create_state, reset_store, update_stage_state
from services.session_price import ensure_session_cache_valid
from tests.test_jump_alert_registry import _make_signal


def _now_ns() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)


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
def _clean():
    reset_store()
    extended_gap_registry.reset()
    live_price_registry.clear_execution_prices()
    import services.session_price as sp_mod

    sp_mod._last_known_session = None
    yield
    reset_store()
    extended_gap_registry.reset()
    live_price_registry.clear_execution_prices()
    sp_mod._last_known_session = None


def test_session_chain_preserves_stage_and_ws():
    """PRE_MARKET → REGULAR → AFTER_HOURS → CLOSED → PRE_MARKET."""
    import services.session_price as sp_mod

    sym = "CRE"
    session_date = "2026-08-26"
    snap = StageSnapshot(
        timestamp="2026-08-26T08:45:00-04:00",
        price=2.07,
        change_pct=12.0,
        pre_move_score=68,
        trigger_price=2.12,
    )
    state = update_stage_state(sym, session_date, snap, "EARLY_ENTRY", _stage_metrics())
    state.minutes_in_stage = 18.0
    before_stage = state.current_stage
    before_snaps = len(state.snapshots)

    chain = ["PRE_MARKET", "REGULAR", "AFTER_HOURS", "CLOSED", "PRE_MARKET"]
    sp_mod._last_known_session = chain[0]
    live_price_registry.ingest_trade(sym, 2.15, exchange_ts_ns=_now_ns())

    for prev, current in zip(chain, chain[1:]):
        sp_mod._last_known_session = prev
        with patch("services.session_price.get_us_market_session", return_value=current):
            ensure_session_cache_valid()
        sp_mod._last_known_session = current

    after = get_or_create_state(sym, session_date)
    assert after.current_stage == before_stage
    assert len(after.snapshots) == before_snaps
    assert live_price_registry.get_tick(sym) is not None


def test_regular_jump_alert_reaches_opportunity_now():
    """REGULAR qualified jump must appear in opportunity-now jump_alerts."""
    reg = JumpAlertRegistry()
    sig = _make_signal("REG1", score=88, price=3.5)
    alert = reg.create_from_signal(sig)
    assert alert is not None

    with patch("services.opportunity_now_service.jump_alert_registry", reg):
        with patch("services.opportunity_now_service.sync_engine_from_scanner"):
            with patch("services.opportunity_now_service.get_us_market_session", return_value="REGULAR"):
                with patch("services.opportunity_now_service.market_scanner") as mock_scanner:
                    mock_scanner.get_state.return_value = None
                    mock_scanner._rank_pool = []
                    mock_scanner._snapshots = {}
                    mock_scanner._candidate_symbols = []
                    jumps = _collect_jump_alerts("REGULAR")

    assert len(jumps) == 1
    assert jumps[0].symbol == "REG1"
    assert jumps[0].jump_qualified is True
    assert jumps[0].status == "NOW"


def test_no_live_data_when_ws_disconnected_in_regular():
    status = _resolve_jump_engine_status(
        websocket_connected=False,
        last_ws_message_time="",
        session="REGULAR",
    )
    assert status == "NO_LIVE_DATA"


def test_armed_when_ws_connected_any_session():
    for session in ("PRE_MARKET", "REGULAR", "AFTER_HOURS", "CLOSED"):
        assert _resolve_jump_engine_status(
            websocket_connected=True,
            last_ws_message_time="",
            session=session,
        ) == "ARMED"


def test_extended_registry_survives_regular_transition():
    det = ExtendedGapDetection(
        symbol="AH1",
        name="AH1",
        session="AFTER_HOURS",
        previous_close=2.0,
        extended_price=2.5,
        extended_gap_pct=25.0,
        extended_volume=80_000,
        relative_volume=2.0,
        detection_stage="EXPLOSIVE",
        catalyst_type="NEWS",
        catalyst_title_ar="خبر",
        catalyst_source="news",
        catalyst_published_at="",
        has_confirmed_news=True,
    )
    extended_gap_registry.register(det)

    with patch("services.extended_hours_gap_detector.get_us_market_session", return_value="REGULAR"):
        from services.extended_hours_gap_detector import sync_extended_gap_detector

        kept = sync_extended_gap_detector()

    assert extended_gap_registry.get("AH1") is not None
    assert len(kept) == 1


def test_jump_engine_monitor_records_no_live_data():
    mon = JumpEngineMonitor()
    with patch("services.jump_engine_monitor.get_us_market_session", return_value="REGULAR"):
        mon.tick_started(
            scanner_task_alive=True,
            websocket_connected=False,
            last_ws_message_time="",
            reconnect_count=0,
            refresh_in_progress=False,
            refresh_skipped=0,
        )
    snap = mon.get_snapshot()
    assert snap.status == "RUNNING"
    assert snap.jump_engine_status == "NO_LIVE_DATA"
