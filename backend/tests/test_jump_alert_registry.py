"""Tests for Jump Alert Registry — sticky alerts across refresh cycles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from models.pre_move import (
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveLiquidityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveVwapMetrics,
    PreMoveBreakoutMetrics,
    PreMoveNewsMetrics,
    PreMoveCompressionMetrics,
    PreMoveEarlyActivityMetrics,
)
from models.scanner import OpportunitiesResponse
from services.jump_alert_registry import JumpAlertRegistry


def _make_signal(
    symbol: str = "BTCT",
    *,
    score: int = 85,
    price: float = 4.25,
    status: str = "EARLY_ENTRY",
    lifecycle: str = "EARLY_ENTRY",
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
        stage_progression=PreMoveStageProgressionMetrics(
            stage_lifecycle=lifecycle,
            stage_progression_score=float(score),
        ),
        volume=PreMoveVolumeMetrics(),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=70),
        late_move=PreMoveLateMoveMetrics(),
        vwap=PreMoveVwapMetrics(),
        breakout=PreMoveBreakoutMetrics(),
        news=PreMoveNewsMetrics(),
        compression=PreMoveCompressionMetrics(),
        early_activity=PreMoveEarlyActivityMetrics(),
        validated=True,
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

    assert alert.alert_id
    assert alert.symbol == "BTCT"
    assert alert.status == "ACTIVE"
    assert any("JUMP_ALERT_CREATED" in r.message for r in caplog.records)
    assert registry.get_active_alerts()[0].alert_id == alert.alert_id


def test_merge_keeps_alert_when_scan_empty(registry: JumpAlertRegistry, caplog):
    sig = _make_signal("DNUT", score=76, price=3.49)
    registry.create_from_signal(sig)

    empty = OpportunitiesResponse(
        market_status="REGULAR",
        opportunities=[],
        api_status="NO_OPPORTUNITIES",
    )

    with caplog.at_level("INFO"):
        merged = registry.merge_into_response(empty, limit=20)

    assert len(merged.opportunities) == 1
    assert merged.opportunities[0].symbol == "DNUT"
    assert merged.opportunities[0].is_sticky_jump_alert is True
    assert merged.opportunities[0].jump_alert_id
    assert len(merged.jump_alerts) == 1
    assert merged.api_status == "OK"
    assert any("JUMP_ALERT_STATUS" in r.message for r in caplog.records)


def test_alert_survives_multiple_refresh_cycles(registry: JumpAlertRegistry):
    sig = _make_signal("MSTZ", score=82, price=6.10)
    alert = registry.create_from_signal(sig)

    for cycle in range(3):
        empty = OpportunitiesResponse(
            market_status="REGULAR",
            opportunities=[],
            api_status="NO_OPPORTUNITIES",
        )
        merged = registry.merge_into_response(empty, limit=20)
        assert any(o.symbol == "MSTZ" for o in merged.opportunities), f"cycle {cycle + 1}"
        registry.log_refresh_cycle(
            scan_opportunity_symbols=set(),
            merged_symbols={"MSTZ"},
        )

    active = registry.get_active_alerts()
    assert len(active) == 1
    assert active[0].alert_id == alert.alert_id


def test_expired_alert_removed_with_reason(registry: JumpAlertRegistry, caplog, monkeypatch):
    sig = _make_signal("XPON", score=80)
    alert = registry.create_from_signal(sig)

    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    with registry._lock:
        stored = registry._alerts[alert.alert_id]
        stored.expires_at = past.isoformat()

    with caplog.at_level("INFO"):
        registry.purge_expired()

    assert registry.get_active_alerts() == []
    assert any(
        "JUMP_ALERT_STATUS" in r.message and "removal_reason=EXPIRED" in r.message
        for r in caplog.records
    )


def test_full_pipeline_created_stored_api_displayed(registry: JumpAlertRegistry):
    """CREATED → STORED → API RETURNED → still present after refresh."""
    sig = _make_signal("TESTJ", score=90, price=2.50)
    created = registry.create_from_signal(sig)

    assert created.alert_id in registry._alerts

    scan_with_other = OpportunitiesResponse(
        market_status="REGULAR",
        opportunities=[],
        api_status="NO_OPPORTUNITIES",
    )
    api1 = registry.merge_into_response(scan_with_other, limit=20)
    assert api1.opportunities[0].symbol == "TESTJ"
    assert api1.opportunities[0].jump_alert_id == created.alert_id

    scan_overwrite = OpportunitiesResponse(
        market_status="REGULAR",
        opportunities=[],
        api_status="NO_OPPORTUNITIES",
    )
    api2 = registry.merge_into_response(scan_overwrite, limit=20)
    assert any(o.symbol == "TESTJ" for o in api2.opportunities)
    assert api2.jump_alerts[0].status == "ACTIVE"
