"""Tests for Jump Alert Registry — real jumps only in jump_alerts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from models.pre_move import (
    PreMoveBreakoutMetrics,
    PreMoveCompressionMetrics,
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveNewsMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from models.scanner import OpportunitiesResponse
from models.stock import StockOpportunity
from services.jump_alert_registry import JumpAlertRegistry


def _make_signal(
    symbol: str = "BTCT",
    *,
    score: int = 85,
    price: float = 4.25,
    status: str = "EARLY_ENTRY",
    lifecycle: str = "EARLY_ENTRY",
    validated: bool = True,
    too_late: bool = False,
) -> PreMoveSignal:
    return PreMoveSignal(
        signal_id=f"{symbol}:2026-08-26",
        symbol=symbol,
        name=symbol,
        current_price=price,
        change_percent=12.5,
        pre_move_score=score,
        status=status,
        lifecycle=lifecycle,
        entry_low=price,
        entry_high=price * 1.01,
        stop_loss=price * 0.95,
        tp1=price * 1.05,
        tp2=price * 1.10,
        trigger_price=price * 1.02,
        risk_reward=2.0,
        stage_progression=PreMoveStageProgressionMetrics(
            stage_lifecycle=lifecycle,
            stage_progression_score=float(score),
            persistence_minutes=12,
        ),
        volume=PreMoveVolumeMetrics(rvol=2.5, volume_acceleration_1m=1.8),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=70),
        late_move=PreMoveLateMoveMetrics(is_too_late=too_late),
        vwap=PreMoveVwapMetrics(),
        breakout=PreMoveBreakoutMetrics(),
        news=PreMoveNewsMetrics(),
        compression=PreMoveCompressionMetrics(),
        early_activity=PreMoveEarlyActivityMetrics(),
        validated=validated,
        reason="test setup",
    )


@pytest.fixture
def registry() -> JumpAlertRegistry:
    reg = JumpAlertRegistry()
    reg.reset()
    return reg


def test_jump_alert_created_and_logged(registry: JumpAlertRegistry, caplog):
    sig = _make_signal()
    with caplog.at_level("INFO"):
        alert = registry.create_from_signal(sig)

    assert alert is not None
    assert alert.alert_id
    assert alert.symbol == "BTCT"
    assert alert.status == "ACTIVE"
    assert alert.jump_qualified is True
    assert alert.jump_alert_created is True
    assert any("JUMP_ALERT_CREATED" in r.message for r in caplog.records)


def test_merge_returns_jump_alerts_not_opportunities(registry: JumpAlertRegistry):
    sig = _make_signal("DNUT", score=76, price=3.49)
    registry.create_from_signal(sig)

    scan = OpportunitiesResponse(
        market_status="REGULAR",
        opportunities=[
            StockOpportunity(
                symbol="OTHER",
                name="Other",
                price=1.0,
                change_percent=5.0,
                score=50,
                trend="صاعد",
                risk_level="متوسط",
                status="انتظار",
                ai_signal="Wait",
                confidence=0.0,
            )
        ],
        api_status="OK",
    )

    merged = registry.merge_into_response(scan, limit=20)

    assert len(merged.jump_alerts) == 1
    assert merged.jump_alerts[0].symbol == "DNUT"
    assert all(o.symbol != "DNUT" or not o.is_sticky_jump_alert for o in merged.opportunities)


def test_max_three_displayed_sorted_by_score(registry: JumpAlertRegistry):
    for sym, score in [("A", 70), ("B", 90), ("C", 80), ("D", 95)]:
        registry.create_from_signal(_make_signal(sym, score=score, price=2.0 + score / 100))

    merged = registry.merge_into_response(
        OpportunitiesResponse(market_status="REGULAR", opportunities=[]),
        limit=20,
    )
    assert len(merged.jump_alerts) == 3
    assert [a.symbol for a in merged.jump_alerts] == ["D", "B", "C"]


def test_early_watch_not_in_display(registry: JumpAlertRegistry):
    sig = _make_signal("EW", status="EARLY_WATCH", lifecycle="EARLY_WATCH")
    assert registry.create_from_signal(sig) is None
    merged = registry.merge_into_response(
        OpportunitiesResponse(market_status="REGULAR", opportunities=[]),
        limit=20,
    )
    assert merged.jump_alerts == []


def test_too_late_not_in_display(registry: JumpAlertRegistry):
    sig = _make_signal("LATE", too_late=True)
    assert registry.create_from_signal(sig) is None


def test_expired_alert_removed_with_reason(registry: JumpAlertRegistry, caplog):
    sig = _make_signal("XPON", score=80)
    alert = registry.create_from_signal(sig)
    assert alert is not None

    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    with registry._lock:
        stored = registry._alerts[alert.alert_id]
        stored.expires_at = past.isoformat()

    with caplog.at_level("INFO"):
        registry.purge_expired()

    assert registry.get_qualified_alerts() == []


def test_counts_qualified_and_created(registry: JumpAlertRegistry):
    registry.create_from_signal(_make_signal("Q1", score=88))
    registry.create_from_signal(_make_signal("Q2", score=77))
    assert registry.count_jump_qualified() == 2
    assert registry.count_jump_alert_created() == 2
