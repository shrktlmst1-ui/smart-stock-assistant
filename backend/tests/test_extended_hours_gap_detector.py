"""Tests for Extended Hours News-Gap Detector — SUGP mandatory case."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from analysis.extended_catalyst_classifier import classify_extended_catalyst
from services.extended_hours_gap_detector import (
    ExtendedQuoteExtract,
    apply_detection_to_engine,
    compute_extended_gap_pct,
    evaluate_gap,
    extended_gap_registry,
    is_eligible_extended_gap_symbol,
    merge_monitor_pool,
    scan_snapshot_raw,
    sync_extended_gap_detector,
    _extract_extended_quote,
)
from services.live_confirmation_engine import CandidateState, live_confirmation_engine
from services.market_scanner_service import MarketScannerService

ET = ZoneInfo("America/New_York")


def _sugp_snapshot_item(*, premarket_v=None, last_trade_p=4.28) -> dict:
    now_ns = int(datetime.now(ET).timestamp() * 1_000_000_000)
    return {
        "ticker": "SUGP",
        "prevDay": {"c": 2.775, "v": 8_231_278},
        "preMarket": {"c": None, "v": premarket_v},
        "day": {"c": 0, "v": 0},
        "lastTrade": {"p": last_trade_p, "t": now_ns},
        "min": {"c": last_trade_p},
        "type": "CS",
        "primary_exchange": "XNAS",
    }


@pytest.fixture(autouse=True)
def _reset():
    extended_gap_registry.reset()
    live_confirmation_engine.reset()
    yield
    extended_gap_registry.reset()
    live_confirmation_engine.reset()


def test_compute_extended_gap_pct_sugp():
    gap = compute_extended_gap_pct(4.28, 2.775)
    assert abs(gap - 54.23) < 0.1


def test_sugp_nasdaq_compliance_not_earnings():
    result = classify_extended_catalyst(
        headline="SUGP regained Nasdaq minimum bid compliance",
        published_at=datetime.now(timezone.utc).isoformat(),
    )
    assert result.catalyst_type == "NASDAQ_COMPLIANCE"
    assert result.catalyst_type != "EARNINGS"


def test_sugp_extract_quote_unknown_volume():
    pre_market_dt = datetime(2026, 6, 30, 8, 0, tzinfo=ET)
    item = _sugp_snapshot_item(premarket_v=None)
    with patch("services.extended_hours_gap_detector._is_trade_in_extended_session", return_value=True):
        with patch("services.extended_hours_gap_detector._is_trade_fresh", return_value=True):
            quote = _extract_extended_quote(item, "PRE_MARKET")
    assert quote is not None
    assert quote.extended_price == 4.28
    assert quote.volume_status == "UNKNOWN"
    assert quote.extended_volume == 0


def test_sugp_bulk_snapshot_not_in_reference_universe():
    item = _sugp_snapshot_item(premarket_v=None)
    assert is_eligible_extended_gap_symbol("SUGP", item) is True
    now = datetime.now(timezone.utc).isoformat()
    news = {
        "SUGP": [
            {
                "title": "SUGP regained Nasdaq minimum bid compliance",
                "published_utc": now,
                "publisher": "news",
            }
        ]
    }
    with patch("services.extended_hours_gap_detector._is_trade_in_extended_session", return_value=True):
        with patch("services.extended_hours_gap_detector._is_trade_fresh", return_value=True):
            dets = scan_snapshot_raw({"SUGP": item}, session="PRE_MARKET", news_by_symbol=news)
    assert len(dets) == 1
    det = dets[0]
    assert det.symbol == "SUGP"
    assert abs(det.extended_gap_pct - 54.23) < 0.1
    assert det.detection_stage == "EXPLOSIVE"
    assert det.catalyst_type == "NASDAQ_COMPLIANCE"
    assert det.volume_status == "UNKNOWN"
    assert det.is_late_chase is True


def test_sugp_with_enriched_volume():
    item = _sugp_snapshot_item(premarket_v=None)
    now = datetime.now(timezone.utc).isoformat()
    news = {
        "SUGP": [
            {
                "title": "SUGP regained Nasdaq minimum bid compliance",
                "published_utc": now,
                "publisher": "news",
            }
        ]
    }
    with patch("services.extended_hours_gap_detector._is_trade_in_extended_session", return_value=True):
        with patch("services.extended_hours_gap_detector._is_trade_fresh", return_value=True):
            dets = scan_snapshot_raw(
                {"SUGP": item},
                session="PRE_MARKET",
                news_by_symbol=news,
                volume_overrides={"SUGP": 9_140_000},
            )
    assert dets[0].extended_volume == 9_140_000
    assert dets[0].volume_status == "KNOWN"


def test_sugp_monitor_pool_and_cancelled_status():
    now = datetime.now(timezone.utc).isoformat()
    det = evaluate_gap(
        symbol="SUGP",
        name="Su Group Holdings",
        session="PRE_MARKET",
        previous_close=2.775,
        extended_price=4.28,
        extended_volume=9_140_000,
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


def test_sugp_extended_alert_separate_from_top_signal():
    from services import opportunity_now_service as svc

    now = datetime.now(timezone.utc).isoformat()
    det = evaluate_gap(
        symbol="SUGP",
        session="PRE_MARKET",
        previous_close=2.775,
        extended_price=4.28,
        extended_volume=9_140_000,
        relative_volume=4.0,
        news_headline="regained Nasdaq minimum bid compliance",
        news_published_at=now,
    )
    assert det is not None
    extended_gap_registry.register(det)
    apply_detection_to_engine(det)

    live_confirmation_engine._candidates["BTCT"] = CandidateState(
        symbol="BTCT",
        name="BTCT",
        last_price=3.5,
        change_percent=2.0,
        score=72.0,
        status="WATCH",
        last_updated=now,
    )
    live_confirmation_engine.set_monitor_symbols(["SUGP", "BTCT"])

    from models.premarket_opportunity import PremarketScanResult

    with patch("services.opportunity_now_service.sync_engine_from_scanner"):
        with patch(
            "services.premarket_opportunity_scanner.get_last_premarket_scan",
            return_value=PremarketScanResult(message="لا توجد فرصة فعلية الآن"),
        ):
            with patch("services.opportunity_now_service.get_us_market_session", return_value="PRE_MARKET"):
                with patch("services.opportunity_now_service.is_regular_session", return_value=False):
                    resp = svc.get_opportunity_now()

    assert resp.extended_alert is not None
    assert resp.extended_alert.symbol == "SUGP"
    assert abs(resp.extended_alert.extended_gap_pct - 54.23) < 0.1
    assert resp.extended_alert.detection_stage == "EXPLOSIVE"
    assert resp.extended_alert.catalyst_type == "NASDAQ_COMPLIANCE"
    assert resp.extended_alert.status == "CANCELLED"
    assert resp.top_signal is None


def test_sugp_unknown_volume_still_in_extended_alert():
    from services import opportunity_now_service as svc

    now = datetime.now(timezone.utc).isoformat()
    det = evaluate_gap(
        symbol="SUGP",
        session="PRE_MARKET",
        previous_close=2.775,
        extended_price=4.28,
        extended_volume=0,
        volume_status="UNKNOWN",
        trade_is_fresh=True,
        news_headline="regained Nasdaq minimum bid compliance",
        news_published_at=now,
    )
    assert det is not None
    extended_gap_registry.register(det)
    apply_detection_to_engine(det)

    with patch("services.opportunity_now_service.sync_engine_from_scanner"):
        with patch("services.opportunity_now_service.get_us_market_session", return_value="PRE_MARKET"):
            with patch("services.opportunity_now_service.is_regular_session", return_value=False):
                resp = svc.get_opportunity_now()

    assert resp.extended_alert is not None
    assert resp.extended_alert.symbol == "SUGP"
    assert resp.extended_alert.volume_status == "UNKNOWN"


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


def test_market_coverage_pct_capped():
    overlap = MarketScannerService._snapshot_universe_overlap({"AAA": {}, "BBB": {}})
    assert overlap >= 0
    counts = MarketScannerService._build_stage_counts(
        "PRE_MARKET",
        symbols_scanned=5000,
        universe_symbols=1000,
        passed_liquidity=100,
        phase2_count=50,
        analyzed=[],
        passed_safety=0,
        last_full_scan_at="",
    )
    assert counts.market_coverage_pct <= 100.0


def test_sync_preserves_registry_regular_session():
    """REGULAR must not reset extended gap registry — engine stays armed."""
    from services.extended_hours_gap_detector import ExtendedGapDetection, extended_gap_registry

    det = ExtendedGapDetection(
        symbol="DNUT",
        name="DNUT",
        session="AFTER_HOURS",
        previous_close=1.0,
        extended_price=1.25,
        extended_gap_pct=25.0,
        extended_volume=100_000,
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
        result = sync_extended_gap_detector()

    assert len(result) == 1
    assert result[0].symbol == "DNUT"
    assert extended_gap_registry.get("DNUT") is not None
