"""Tests for Extended Hours News-Gap Detector — SUGP mandatory case."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from analysis.extended_catalyst_classifier import classify_extended_catalyst
from services.extended_hours_gap_detector import (
    apply_detection_to_engine,
    compute_extended_gap_pct,
    evaluate_gap,
    extended_gap_registry,
    merge_monitor_pool,
    sync_extended_gap_detector,
)
from services.live_confirmation_engine import live_confirmation_engine

ET = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def _reset():
    extended_gap_registry.reset()
    live_confirmation_engine.reset()
    yield
    extended_gap_registry.reset()
    live_confirmation_engine.reset()


def test_compute_extended_gap_pct_sugp():
    gap = compute_extended_gap_pct(3.99, 2.775)
    assert abs(gap - 43.78) < 0.1


def test_sugp_nasdaq_compliance_not_earnings():
    result = classify_extended_catalyst(
        headline="SUGP regained Nasdaq minimum bid compliance",
        published_at=datetime.now(timezone.utc).isoformat(),
    )
    assert result.catalyst_type == "NASDAQ_COMPLIANCE"
    assert result.catalyst_type != "EARNINGS"


def test_sugp_full_detection():
    now = datetime.now(timezone.utc).isoformat()
    det = evaluate_gap(
        symbol="SUGP",
        name="Su Group Holdings",
        session="PRE_MARKET",
        previous_close=2.775,
        extended_price=3.99,
        extended_volume=7_200_000,
        relative_volume=5.0,
        news_headline="SUGP regained Nasdaq minimum bid compliance",
        news_published_at=now,
    )
    assert det is not None
    assert det.symbol == "SUGP"
    assert abs(det.extended_gap_pct - 43.78) < 0.1
    assert det.detection_stage == "EXPLOSIVE"
    assert det.catalyst_type == "NASDAQ_COMPLIANCE"
    assert det.has_confirmed_news is True
    assert det.is_late_chase is True


def test_sugp_monitor_pool_and_cancelled_status():
    now = datetime.now(timezone.utc).isoformat()
    det = evaluate_gap(
        symbol="SUGP",
        name="Su Group Holdings",
        session="PRE_MARKET",
        previous_close=2.775,
        extended_price=3.99,
        extended_volume=7_200_000,
        relative_volume=5.0,
        news_headline="regained Nasdaq minimum bid compliance",
        news_published_at=now,
    )
    assert det is not None

    merged = merge_monitor_pool(["SUGP"], ["AAA", "BBB"])
    assert "SUGP" in merged
    live_confirmation_engine.set_monitor_symbols(merged)
    assert "SUGP" in live_confirmation_engine._monitor_symbols

    extended_gap_registry.register(det)
    apply_detection_to_engine(det)

    state = live_confirmation_engine._candidates["SUGP"]
    assert state.status == "CANCELLED"
    assert any("مطاردة" in r for r in state.cancellation_reasons)
    assert any("لا تطارد" in r for r in state.cancellation_reasons)


def test_sugp_appears_in_opportunity_now_response():
    from services import opportunity_now_service as svc

    now = datetime.now(timezone.utc).isoformat()
    det = evaluate_gap(
        symbol="SUGP",
        session="PRE_MARKET",
        previous_close=2.775,
        extended_price=3.99,
        extended_volume=7_000_000,
        relative_volume=4.0,
        news_headline="regained Nasdaq minimum bid compliance",
        news_published_at=now,
    )
    assert det is not None
    live_confirmation_engine.set_monitor_symbols(["SUGP"])
    extended_gap_registry.register(det)
    apply_detection_to_engine(det)

    pre_market_dt = datetime(2026, 6, 30, 8, 0, tzinfo=ET)
    with patch("services.opportunity_now_service.sync_engine_from_scanner"):
        with patch("services.opportunity_now_service.get_us_market_session", return_value="PRE_MARKET"):
            with patch("services.opportunity_now_service.is_regular_session", return_value=False):
                resp = svc.get_opportunity_now()

    sug_signals = [s for s in resp.signals if s.symbol == "SUGP"]
    assert sug_signals, "SUGP must appear in signals"
    sig = sug_signals[0]
    assert abs(sig.extended_gap_pct - 43.78) < 0.1
    assert sig.detection_stage == "EXPLOSIVE"
    assert sig.catalyst_type == "NASDAQ_COMPLIANCE"
    assert sig.status == "CANCELLED"
    assert resp.top_signal is not None
    assert resp.top_signal.symbol == "SUGP"


def test_detection_stages_progression():
    base = dict(
        symbol="TEST",
        session="PRE_MARKET",
        previous_close=5.0,
        extended_volume=60_000,
    )
    watch = evaluate_gap(**base, extended_price=5.22, relative_volume=1.0)
    assert watch is not None
    assert watch.detection_stage == "WATCH"

    active = evaluate_gap(
        **base,
        extended_price=5.40,
        relative_volume=2.5,
        news_headline="contract award",
        news_published_at=datetime.now(timezone.utc).isoformat(),
    )
    assert active is not None
    assert active.detection_stage == "ACTIVE"

    explosive = evaluate_gap(**base, extended_price=6.10)
    assert explosive is not None
    assert explosive.detection_stage == "EXPLOSIVE"


def test_sync_skips_regular_session():
    with patch("services.extended_hours_gap_detector.get_us_market_session", return_value="REGULAR"):
        result = sync_extended_gap_detector()
    assert result == []
