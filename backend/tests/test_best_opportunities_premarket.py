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
)


def _opp_signal(**kwargs) -> PremarketOpportunitySignal:
    defaults = dict(
        symbol="PMI",
        current_price=4.91,
        premarket_change_percent=45.0,
        premarket_volume=3_400_000,
        trigger_type="LONG_BREAKOUT",
        status="OPPORTUNITY",
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


def _watch_signal(**kwargs) -> PremarketOpportunitySignal:
    defaults = dict(
        symbol="PMI",
        current_price=4.69,
        premarket_change_percent=46.0,
        premarket_volume=3_400_000,
        trigger_type="",
        status="WATCH",
        reason="Price has not broken premarket high",
    )
    defaults.update(kwargs)
    return PremarketOpportunitySignal(**defaults)


def test_premarket_response_includes_only_opportunity_status():
    scan = PremarketScanResult(
        status="OPPORTUNITY",
        opportunities=[_opp_signal(), _watch_signal(symbol="BFLY", status="WATCH")],
        watches=[_watch_signal()],
        top_opportunity=_opp_signal(),
    )
    resp = build_premarket_opportunities_response(scan, limit=20)
    assert len(resp.opportunities) == 1
    assert resp.opportunities[0].symbol == "PMI"
    assert resp.opportunities[0].score == 0
    assert "دخول: 4.91" in resp.opportunities[0].status_reason_ar
    assert resp.watchlist_candidates == []


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


def test_premarket_to_stock_opportunity_fields():
    pm = _opp_signal()
    opp = premarket_to_stock_opportunity(pm, name="Picard Medical")
    assert opp.symbol == "PMI"
    assert opp.name == "Picard Medical"
    assert opp.price == 4.91
    assert opp.change_percent == 45.0
    assert opp.ai_signal == "LONG_BREAKOUT"
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


def test_opportunities_endpoint_shows_premarket_trigger(client: TestClient, auth_headers: dict):
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
        status="OPPORTUNITY",
        opportunities=[_opp_signal()],
        top_opportunity=_opp_signal(),
    )

    with patch("main.market_scanner.get_state", return_value=mock_state):
        with patch(
            "services.best_opportunities_service.sync_premarket_scanner",
            return_value=scan,
        ):
            resp = client.get("/stocks/opportunities?limit=20", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["opportunities"]) == 1
    assert body["opportunities"][0]["symbol"] == "PMI"
    assert body["opportunities"][0]["ai_signal"] == "LONG_BREAKOUT"


def test_get_best_opportunities_premarket_invokes_scanner():
    with patch(
        "services.best_opportunities_service.sync_premarket_scanner",
        return_value=PremarketScanResult(message="empty"),
    ) as mock_scan:
        resp = get_best_opportunities_premarket(limit=5, state=None)
    mock_scan.assert_called_once()
    assert resp.opportunities == []
