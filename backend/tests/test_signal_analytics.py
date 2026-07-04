"""Unit tests for Professional Signal Analytics."""

from __future__ import annotations

import pytest

from database.signal_analytics_db import init_signal_analytics_db, insert_signal_record
from services.signal_analytics_service import (
    build_explanation,
    classify_failure,
    compute_trade_quality,
    get_analytics_dashboard,
    get_performance_report,
    get_ranked_signals,
    update_analytics_tracks,
)


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_file = tmp_path / "signals.db"
    monkeypatch.setattr(
        "database.signal_analytics_db.DB_PATH",
        db_file,
    )
    init_signal_analytics_db()
    yield


def _insert(**overrides):
    base = {
        "symbol": "AAPL",
        "signal": "Buy",
        "signal_date": "2026-07-02",
        "signal_time": "14:30:00",
        "timeframe": "live",
        "ai_score": 78.0,
        "confidence_score": 82.0,
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "target_1": 104.0,
        "target_2": 106.0,
        "target_3": 108.0,
        "trend_direction": "long",
        "market_status": "REGULAR",
        "sector": "stocks",
        "industry": "Consumer Electronics",
        "track_status": "Waiting",
        "trade_quality_stars": 4,
        "trade_quality_label": "Very Good",
        "explanation": [{"label": "Trend Alignment", "passed": True}],
        "factor_scores": {"trend": 70, "relative_volume": 55, "bos": 60},
        "filters_passed": ["trend", "bos"],
        "filters_failed": [],
        "trend_strength": 72.0,
        "relative_volume": 55.0,
    }
    base.update(overrides)
    return insert_signal_record(base)


def test_compute_trade_quality_tiers():
    stars, label = compute_trade_quality(90, 88, 80, 75)
    assert stars == 5
    assert label == "Excellent"

    stars, label = compute_trade_quality(40, 40, 40, 40)
    assert stars == 1
    assert label == "Weak"


def test_build_explanation_pass_fail():
    factors = {
        "trend": 70,
        "bos": 50,
        "choch": 30,
        "order_blocks": 60,
        "fair_value_gaps": 55,
        "liquidity_sweep": 48,
        "relative_volume": 62,
        "vwap": 58,
        "ema20": 50,
        "ema50": 50,
        "ema200": 50,
    }
    items = build_explanation(factors, ["trend", "order_blocks"], ["choch"])
    by_label = {i["label"]: i["passed"] for i in items}
    assert by_label["Trend Alignment"] is True
    assert by_label["CHOCH Confirmed"] is False
    assert by_label["EMA Alignment"] is True


def test_classify_failure_weak_volume():
    reason = classify_failure("Buy", {"relative_volume": 30, "trend": 60})
    assert reason == "Weak Volume"


def test_classify_failure_news():
    reason = classify_failure(
        "Buy",
        {"relative_volume": 60, "news_impact": 80},
        news_risk=70,
    )
    assert reason == "News Event"


def test_update_tracks_target_hit():
    _insert(track_status="Active", entry_price=100.0, stop_loss=98.0,
            target_1=104.0, target_2=106.0, target_3=108.0)
    updated = update_analytics_tracks("AAPL", 104.5)
    assert updated >= 1
    ranked = get_ranked_signals(limit=5)
    assert ranked.signals[0].track_status == "Target 1 Hit"
    assert ranked.signals[0].profit_pct > 0


def test_update_tracks_stop_loss():
    _insert(track_status="Active")
    update_analytics_tracks("AAPL", 97.5)
    ranked = get_ranked_signals(limit=5)
    assert ranked.signals[0].track_status == "Stop Loss Hit"
    assert ranked.signals[0].failure_reason is not None


def test_dashboard_and_performance_from_data():
    _insert(track_status="Target 2 Hit", profit_pct=6.0)
    _insert(symbol="MSFT", track_status="Stop Loss Hit", profit_pct=-2.0,
            signal="Sell", entry_price=200.0, stop_loss=205.0,
            target_1=190.0, target_2=185.0, target_3=180.0)

    dashboard = get_analytics_dashboard()
    assert dashboard.total_signals == 2
    assert dashboard.winning_signals == 1
    assert dashboard.losing_signals == 1
    assert dashboard.win_rate_pct == 50.0

    report = get_performance_report()
    assert report.overall_total == 2
    assert report.wins == 1
    assert report.losses == 1


def test_ranking_order():
    _insert(symbol="LOW", confidence_score=60, ai_score=70, trend_strength=50, relative_volume=40)
    _insert(symbol="HIGH", confidence_score=90, ai_score=85, trend_strength=80, relative_volume=70)

    ranked = get_ranked_signals(limit=10)
    assert ranked.signals[0].symbol == "HIGH"
    assert ranked.signals[0].confidence_score >= ranked.signals[1].confidence_score
