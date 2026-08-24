"""Tests for premarket-only best opportunities (أفضل الفرص)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from models.premarket_opportunity import PremarketOpportunitySignal, PremarketScanResult
from services.best_opportunities_service import (
    PREMARKET_EMPTY_SUB,
    PREMARKET_EMPTY_TITLE,
    build_premarket_opportunities_response,
    get_best_opportunities_premarket,
    premarket_to_stock_opportunity,
    build_opportunities_from_scans,
)


def _confirmed_signal(**kwargs) -> PremarketOpportunitySignal:
    defaults = dict(
        symbol="PMI",
        current_price=4.91,
        premarket_change_percent=45.0,
        premarket_volume=3_400_000,
        trigger_type="LONG_BREAKOUT",
        status="CONFIRMED_ENTRY",
        entry=4.91,
        stop_loss=4.68,
        tp1=5.20,
        tp2=5.50,
        risk_reward=2.1,
        vwap=4.75,
        premarket_high=5.11,
        spread_percent=0.8,
        volume_acceleration=2.2,
        reason="Premarket high breakout with volume acceleration above VWAP",
    )
    defaults.update(kwargs)
    return PremarketOpportunitySignal(**defaults)


def _early_signal(**kwargs) -> PremarketOpportunitySignal:
    defaults = dict(
        symbol="PMI",
        current_price=4.69,
        premarket_change_percent=46.0,
        premarket_volume=3_400_000,
        trigger_type="EARLY_MOMENTUM",
        status="EARLY_MOMENTUM",
        early_entry_zone=4.69,
        invalidation_level=4.50,
        vwap=4.75,
        premarket_high=5.11,
        distance_to_premarket_high=8.2,
        spread_percent=0.8,
        volume_acceleration=1.4,
        relative_volume=1.5,
        reason="تسارع مبكر في السعر والسيولة + Gap قوي + حجم مرتفع + اقتراب من VWAP/القمة",
    )
    defaults.update(kwargs)
    return PremarketOpportunitySignal(**defaults)


def _watch_signal(**kwargs) -> PremarketOpportunitySignal:
    defaults = dict(
        symbol="PMI",
        current_price=4.69,
        premarket_change_percent=46.0,
        premarket_volume=3_400_000,
        status="WATCH",
        reason="Price has not broken premarket high",
    )
    defaults.update(kwargs)
    return PremarketOpportunitySignal(**defaults)


def test_premarket_response_includes_confirmed_and_early():
    scan = PremarketScanResult(
        status="CONFIRMED_ENTRY",
        opportunities=[_confirmed_signal(), _early_signal(symbol="EARLY1")],
        watches=[_watch_signal()],
        top_opportunity=_confirmed_signal(),
        top_early=_early_signal(symbol="EARLY1"),
    )
    resp = build_premarket_opportunities_response(scan, limit=20)
    assert len(resp.opportunities) == 2
    symbols = {o.symbol for o in resp.opportunities}
    assert symbols == {"PMI", "EARLY1"}
    confirmed = next(o for o in resp.opportunities if o.symbol == "PMI")
    assert confirmed.status == "شراء"
    assert "دخول: 4.91" in confirmed.status_reason_ar
    early = next(o for o in resp.opportunities if o.symbol == "EARLY1")
    assert early.status == "انتظار"
    assert early.ai_signal == "EARLY_MOMENTUM"
    assert resp.watchlist_candidates == []


def test_premarket_shows_early_momentum_without_confirmed():
    scan = PremarketScanResult(
        status="EARLY_MOMENTUM",
        opportunities=[_early_signal()],
        top_early=_early_signal(),
    )
    resp = build_premarket_opportunities_response(scan)
    assert len(resp.opportunities) == 1
    assert resp.opportunities[0].symbol == "PMI"
    assert resp.opportunities[0].ai_signal == "EARLY_MOMENTUM"
    assert "منطقة مبكرة" in resp.opportunities[0].status_reason_ar


def test_premarket_empty_state_no_legacy_fallback():
    scan = PremarketScanResult(
        status="WATCH",
        watches=[_watch_signal()],
        top_watch=_watch_signal(),
    )
    resp = build_premarket_opportunities_response(scan)
    assert resp.opportunities == []
    assert resp.watchlist_candidates == []
    assert PREMARKET_EMPTY_TITLE in resp.no_signal_reason
    assert PREMARKET_EMPTY_SUB in resp.no_signal_reason


def test_premarket_to_stock_opportunity_confirmed_fields():
    pm = _confirmed_signal()
    opp = premarket_to_stock_opportunity(pm, name="Picard Medical")
    assert opp.symbol == "PMI"
    assert opp.name == "Picard Medical"
    assert opp.price == 4.91
    assert opp.change_percent == 45.0
    assert opp.ai_signal == "CONFIRMED_ENTRY"
    assert "R:R: 2.1" in opp.status_reason_ar


def test_opportunities_endpoint_uses_premarket_scanner_during_premarket(
    client: TestClient,
    auth_headers: dict,
):
    legacy_opp = SimpleNamespace(
        symbol="BFLY",
        name="BFLY",
        price=3.5,
        change_percent=5.0,
        ai_score=95,
        recommendation="Wait",
        confidence=80.0,
        confirmed_factors=10,
        total_factors=17,
        safety_passed=True,
        status_reason_ar="",
        rejection_reason="",
    )
    mock_state = SimpleNamespace(
        market_status="PRE_MARKET",
        top_opportunities=[legacy_opp],
        watchlist_candidates=[legacy_opp],
        snapshots=[],
        explanation="legacy",
        no_signal_reason="legacy reason",
        debug=None,
    )
    empty_scan = PremarketScanResult(
        status="WATCH",
        watches=[_watch_signal()],
        top_watch=_watch_signal(),
    )

    with patch("main.market_scanner.get_state", return_value=mock_state):
        with patch(
            "services.best_opportunities_service.sync_pre_move_scan",
        ) as mock_pm:
            from models.pre_move import PreMoveScanResult
            mock_pm.return_value = PreMoveScanResult()
            with patch(
                "services.best_opportunities_service.sync_premarket_scanner",
                return_value=empty_scan,
            ):
                resp = client.get("/stocks/opportunities?limit=20", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["market_status"] == "PRE_MARKET"
    assert body["opportunities"] == []
    assert body["watchlist_candidates"] == []
    assert PREMARKET_EMPTY_TITLE in body["no_signal_reason"]
    symbols = [o["symbol"] for o in body["opportunities"]]
    assert "BFLY" not in symbols
    assert "BDTX" not in symbols


def test_opportunities_endpoint_shows_premarket_confirmed(client: TestClient, auth_headers: dict):
    mock_state = SimpleNamespace(
        market_status="PRE_MARKET",
        top_opportunities=[],
        watchlist_candidates=[],
        snapshots=[],
        explanation="",
        no_signal_reason="",
        debug=None,
    )
    scan = PremarketScanResult(
        status="CONFIRMED_ENTRY",
        opportunities=[_confirmed_signal()],
        top_opportunity=_confirmed_signal(),
    )

    built = build_premarket_opportunities_response(scan, limit=20, state=mock_state, session="PRE_MARKET")
    import time
    from services import snapshot_cache_service as scs

    scs._cached = scs.CachedOpportunities(
        response=built,
        generated_mono=time.monotonic(),
        generated_at_iso="2026-01-01T00:00:00Z",
        scan_id="test",
        session="PRE_MARKET",
    )

    with patch("main.market_scanner.get_state", return_value=mock_state):
        with patch("services.best_opportunities_service.sync_pre_move_scan") as mock_prem:
            with patch(
                "services.best_opportunities_service.sync_premarket_scanner",
            ) as mock_pm:
                resp = client.get("/stocks/opportunities?limit=20", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    mock_prem.assert_not_called()
    mock_pm.assert_not_called()
    assert len(body["opportunities"]) == 1
    assert body["opportunities"][0]["symbol"] == "PMI"
    assert body["opportunities"][0]["ai_signal"] == "CONFIRMED_ENTRY"
    assert body.get("cache_hit") is True


def test_get_best_opportunities_premarket_uses_cache_not_sync_scan():
    import time
    from services import snapshot_cache_service as scs
    from services.best_opportunities_service import build_premarket_opportunities_response

    scan = PremarketScanResult(message="empty")
    built = build_premarket_opportunities_response(scan, limit=5, state=None, session="PRE_MARKET")
    scs._cached = scs.CachedOpportunities(
        response=built,
        generated_mono=time.monotonic(),
        generated_at_iso="t",
        scan_id="t",
        session="PRE_MARKET",
    )
    with patch("services.best_opportunities_service.sync_pre_move_scan") as mock_scan:
        with patch("services.best_opportunities_service.sync_premarket_scanner"):
            resp = get_best_opportunities_premarket(limit=5, state=None)
    mock_scan.assert_not_called()
    assert resp.opportunities == []
    assert resp.cache_hit is True
