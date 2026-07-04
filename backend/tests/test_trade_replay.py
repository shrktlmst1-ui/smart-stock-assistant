"""Unit tests for Trade Replay & Post-Trade Analytics."""

from __future__ import annotations

import pytest

from database.signal_analytics_db import init_signal_analytics_db, insert_signal_record
from database.trade_replay_db import init_trade_replay_db
from services.trade_replay_service import (
    compute_post_trade_quality,
    get_trade_replay_detail,
    init_trade_replay,
    observe_trade_price,
    on_track_status_change,
)
from datetime import datetime, timezone


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    db_file = tmp_path / "signals.db"
    monkeypatch.setattr("database.signal_analytics_db.DB_PATH", db_file)
    monkeypatch.setattr("database.trade_replay_db.DB_PATH", db_file)
    init_signal_analytics_db()
    init_trade_replay_db()
    yield


def _insert_signal(**overrides):
    base = {
        "symbol": "NVDA",
        "signal": "Buy",
        "signal_date": "2026-07-02",
        "signal_time": "09:35:00",
        "timeframe": "live",
        "ai_score": 80.0,
        "confidence_score": 85.0,
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "target_1": 104.0,
        "target_2": 106.0,
        "target_3": 108.0,
        "trend_direction": "long",
        "market_status": "REGULAR",
        "track_status": "Active",
        "trade_quality_stars": 4,
        "trade_quality_label": "Very Good",
        "explanation": [],
        "factor_scores": {},
        "filters_passed": [],
        "filters_failed": [],
        "trend_strength": 70.0,
        "relative_volume": 60.0,
        "created_at": "2026-07-02T09:35:00+00:00",
    }
    base.update(overrides)
    return insert_signal_record(base)


def test_init_replay_creates_timeline():
    sid = _insert_signal()
    init_trade_replay(
        sid,
        symbol="NVDA",
        entry_price=100.0,
        ai_score=80,
        confidence=85,
        risk_reward_ratio=2.5,
        created_at="2026-07-02T09:35:00+00:00",
        signal_time="09:35",
    )
    detail = get_trade_replay_detail(sid)
    assert detail is not None
    assert detail.timeline[0].event_label == "Signal Generated"
    assert detail.entry_quality_score > 0


def test_observe_price_updates_excursions():
    sid = _insert_signal(track_status="Active")
    init_trade_replay(
        sid, symbol="NVDA", entry_price=100.0, ai_score=80, confidence=85,
        risk_reward_ratio=2.0, created_at="2026-07-02T09:35:00+00:00", signal_time="09:35",
    )
    now = datetime(2026, 7, 2, 10, 6, tzinfo=timezone.utc)
    track = {
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "target_1": 104.0,
        "target_2": 106.0,
        "target_3": 108.0,
        "signal": "Buy",
        "created_at": "2026-07-02T09:41:00+00:00",
        "activated_at": "2026-07-02T09:41:00+00:00",
        "ai_score": 80,
        "confidence_score": 85,
    }
    observe_trade_price(
        sid, price=105.0, track=track, old_status="Active", new_status="Active",
        activated_at=track["activated_at"], now=now,
    )
    detail = get_trade_replay_detail(sid)
    assert detail is not None
    assert detail.live_max_profit_pct > 0


def test_finalize_post_trade_on_close():
    sid = _insert_signal(track_status="Target 2 Hit", profit_pct=6.0)
    init_trade_replay(
        sid, symbol="NVDA", entry_price=100.0, ai_score=82, confidence=88,
        risk_reward_ratio=3.0, created_at="2026-07-02T09:35:00+00:00", signal_time="09:35",
    )
    now = datetime(2026, 7, 2, 11, 17, tzinfo=timezone.utc)
    track = {
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "target_1": 104.0,
        "target_2": 106.0,
        "target_3": 108.0,
        "signal": "Buy",
        "ai_score": 82,
        "confidence_score": 88,
        "exit_price": 106.0,
        "created_at": "2026-07-02T09:35:00+00:00",
        "activated_at": "2026-07-02T09:41:00+00:00",
        "holding_seconds": 5760,
    }
    on_track_status_change(
        sid, track=track, old_status="Active", new_status="Target 2 Hit",
        activated_at=track["activated_at"], closed_at=now.isoformat(),
        profit_pct=6.0, now=now,
    )
    detail = get_trade_replay_detail(sid)
    assert detail is not None
    assert detail.post_trade is not None
    assert detail.post_trade.final_result == "WIN"
    assert detail.post_trade.post_trade_quality in ("Excellent", "Very Good", "Good", "Average", "Poor")
    labels = [e.event_label for e in detail.timeline]
    assert "Target 2 Hit" in labels
    assert "Trade Closed" in labels


def test_post_trade_quality_tiers():
    assert compute_post_trade_quality(90, 90, 3.0, 1.0, 8.0, "WIN") == "Excellent"
    assert compute_post_trade_quality(40, 40, 1.0, 8.0, 1.0, "LOSS") == "Poor"
