"""Tests for live confirmation engine — 3 confirmations, chase prevention, WS fallback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from analysis.professional_decision import REQUIRED_INSTITUTIONAL_FACTORS
from services import live_confirmation_engine as eng
from services.live_confirmation_engine import (
    CandidateState,
    ConfirmationReading,
    LIVE_MONITOR_POOL,
    NOW_TTL_SECONDS,
    REQUIRED_CONFIRMATIONS,
    live_confirmation_engine,
)
from services import opportunity_now_service as svc


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _snap(**kwargs):
    now = _utcnow().isoformat()
    price = kwargs.get("price", 5.0)
    factor_scores = {k: 80.0 for k in REQUIRED_INSTITUTIONAL_FACTORS}
    defaults = dict(
        symbol="LIVE",
        name="Live Co",
        price=price,
        change_percent=8.0,
        volume=1_200_000,
        last_updated=now,
        news=[],
        smc=SimpleNamespace(bos=True, liquidity_sweep=True, fair_value_gaps=[1], order_blocks=[1]),
        volume_engine=SimpleNamespace(relative_volume=3.5, session_rvol=3.5),
        trend_analysis=SimpleNamespace(vwap=price * 0.998, direction="bullish"),
        volume_liquidity=SimpleNamespace(vwap=price * 0.998, relative_volume=3.5),
        news_intelligence=SimpleNamespace(overall_sentiment="neutral", confidence_adjustment=0, summary=""),
        indicators=SimpleNamespace(resistance=price * 1.0004, support=price * 0.9996),
        trade_decision=SimpleNamespace(factor_scores=factor_scores),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _reset_engine():
    live_confirmation_engine.reset()
    yield
    live_confirmation_engine.reset()


def _add_passed_readings(state: CandidateState, count: int, *, gap: int = 10) -> None:
    base = _utcnow() - timedelta(seconds=gap * count)
    for i in range(count):
        state.readings.append(
            ConfirmationReading(
                timestamp=base + timedelta(seconds=i * gap),
                price=state.last_price or 5.0,
                micro_count=4,
                micro_hits=["تسارع الحجم", "زخم صاعد", "فوق VWAP"],
                passed=True,
            )
        )
    state.consecutive_confirmations = live_confirmation_engine._count_confirmations(state)


def test_no_now_before_three_confirmations():
    snap = _snap(symbol="AAPL")
    live_confirmation_engine.set_monitor_symbols(["AAPL"])
    live_confirmation_engine.ingest_snapshot(snap)
    state = live_confirmation_engine._candidates["AAPL"]
    state.consecutive_confirmations = 2
    state.score = 85
    state.confirmed_factors = 14
    state.risk_reward_ratio = 2.5
    live_confirmation_engine.ingest_snapshot(snap)
    assert state.status != "NOW"


def test_now_after_three_confirmations():
    snap = _snap(symbol="BETA")
    live_confirmation_engine.set_monitor_symbols(["BETA"])
    with patch.object(live_confirmation_engine, "_evaluate_micro", return_value=(4, ["a", "b", "c", "d"])):
        live_confirmation_engine.ingest_snapshot(snap)
    state = live_confirmation_engine._candidates["BETA"]
    assert state.score >= 80, f"score too low: {state.score}"
    _add_passed_readings(state, REQUIRED_CONFIRMATIONS)
    with patch.object(live_confirmation_engine, "_evaluate_micro", return_value=(4, ["a", "b", "c", "d"])):
        live_confirmation_engine.ingest_snapshot(snap)
    assert live_confirmation_engine._candidates["BETA"].status == "NOW"


def test_chase_prevention_vwap_extension():
    snap = _snap(symbol="CHASE", price=6.0)
    live_confirmation_engine.set_monitor_symbols(["CHASE"])
    live_confirmation_engine.ingest_snapshot(snap)
    state = live_confirmation_engine._candidates["CHASE"]
    state.status = "NOW"
    state.vwap = 5.0
    state.now_started_at = _utcnow()
    state.entry_zone_high = 6.1
    snap.price = 6.5  # far above vwap
    live_confirmation_engine.ingest_snapshot(snap)
    assert state.status == "CANCELLED"
    assert state.cancellation_reasons


def test_rejects_stale_data_and_high_spread():
    old = (_utcnow() - timedelta(minutes=5)).isoformat()
    snap = _snap(last_updated=old)
    live_confirmation_engine.set_monitor_symbols(["LIVE"])
    live_confirmation_engine.ingest_snapshot(snap)
    state = live_confirmation_engine._candidates["LIVE"]
    assert state.status == "WATCH"
    assert state.data_age_seconds > 90

    snap2 = _snap()
    with patch.object(live_confirmation_engine, "_spread_pct", return_value=1.5):
        live_confirmation_engine.ingest_snapshot(snap2)
    assert live_confirmation_engine._candidates["LIVE"].status == "WATCH"


def test_cancel_after_breakout_failure():
    snap = _snap(symbol="BRK", price=4.0)
    live_confirmation_engine.set_monitor_symbols(["BRK"])
    live_confirmation_engine.ingest_snapshot(snap)
    state = live_confirmation_engine._candidates["BRK"]
    state.status = "NOW"
    state.breakout_active = True
    state.day_high = 4.2
    state.now_started_at = _utcnow()
    state.vwap = 3.9
    snap.price = 4.0
    live_confirmation_engine.ingest_snapshot(snap)
    assert state.status == "CANCELLED"


def test_cancel_after_90_second_ttl():
    snap = _snap(symbol="TTL")
    live_confirmation_engine.set_monitor_symbols(["TTL"])
    live_confirmation_engine.ingest_snapshot(snap)
    state = live_confirmation_engine._candidates["TTL"]
    state.status = "NOW"
    state.now_started_at = _utcnow() - timedelta(seconds=NOW_TTL_SECONDS + 5)
    state.vwap = snap.price * 0.98
    state.entry_zone_high = snap.price * 1.01
    live_confirmation_engine.ingest_snapshot(snap)
    assert state.status == "CANCELLED"
    assert any("90" in r for r in state.cancellation_reasons)


def test_get_opportunity_now_returns_none_without_exception():
    with patch("services.opportunity_now_service.live_data_gate") as mock_gate:
        mock_gate.live_feed_valid = False
        mock_gate.jump_engine_status = "DATA_UNAVAILABLE"
        with patch.object(svc.market_scanner, "get_state", return_value=None):
            with patch.object(svc.market_scanner, "_rank_pool", []):
                resp = svc.get_opportunity_now()
    assert resp.status == "NONE"
    assert resp.top_signal is None
    assert resp.message == "DATA_UNAVAILABLE"
    assert resp.jump_engine_status == "DATA_UNAVAILABLE"


def test_ws_fallback_does_not_crash_engine():
    live_confirmation_engine.set_ws_status(connected=False, fallback=True, error="1008 policy")
    resp = svc.get_opportunity_now()
    assert resp.status == "NONE"
    assert resp.live_source == "DATA_UNAVAILABLE"
    assert resp.ws_connected is False


def test_monitor_pool_is_100():
    assert LIVE_MONITOR_POOL == 100
