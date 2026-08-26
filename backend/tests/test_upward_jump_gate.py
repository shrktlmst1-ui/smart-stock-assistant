"""Tests for upward-only jump gate."""

from __future__ import annotations

from analysis.upward_jump_gate import evaluate_upward_jump, upward_stage_label
from models.pre_move import (
    PreMoveBreakoutMetrics,
    PreMoveCompressionMetrics,
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)


def _bullish_signal(**overrides) -> PreMoveSignal:
    base = PreMoveSignal(
        signal_id="TEST:2026-08-26",
        symbol="BTCT",
        name="BTCT",
        current_price=2.10,
        change_percent=4.5,
        pre_move_score=72,
        status="EARLY_ENTRY",
        trigger_price=2.05,
        volume=PreMoveVolumeMetrics(
            rvol=2.0,
            volume_acceleration_1m=1.4,
            volume_acceleration=1.3,
        ),
        early_activity=PreMoveEarlyActivityMetrics(
            micro_higher_lows=True,
            breakout_pressure_score=55.0,
            trade_velocity=80.0,
        ),
        compression=PreMoveCompressionMetrics(higher_lows_score=0.5),
        vwap=PreMoveVwapMetrics(vwap_hold=True, distance_from_vwap_pct=0.8),
        breakout=PreMoveBreakoutMetrics(distance_to_breakout_pct=2.0),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=65),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(
            stage_lifecycle="EARLY_ENTRY",
            regression_signals=[],
        ),
        validated=True,
    )
    data = base.model_dump()
    data.update(overrides)
    return PreMoveSignal(**data)


def test_upward_jump_passes_bullish_setup():
    ok, reason = evaluate_upward_jump(_bullish_signal())
    assert ok is True
    assert reason == ""


def test_negative_momentum_not_jump():
    ok, reason = evaluate_upward_jump(_bullish_signal(change_percent=-5.0))
    assert ok is False
    assert reason == "NOT_JUMP_NEGATIVE_MOMENTUM"


def test_support_break_not_jump():
    ok, reason = evaluate_upward_jump(
        _bullish_signal(
            stage_progression=PreMoveStageProgressionMetrics(
                regression_signals=["higher_lows_broken"],
            ),
        ),
    )
    assert ok is False
    assert reason == "NOT_JUMP_SUPPORT_BREAK"


def test_insufficient_up_evidence_not_jump():
    ok, reason = evaluate_upward_jump(
        _bullish_signal(
            change_percent=0.5,
            volume=PreMoveVolumeMetrics(rvol=0.5, volume_acceleration_1m=0.5),
            early_activity=PreMoveEarlyActivityMetrics(
                micro_higher_lows=False,
                breakout_pressure_score=10.0,
                trade_velocity=-1.0,
            ),
            vwap=PreMoveVwapMetrics(vwap_hold=False, distance_from_vwap_pct=-5.0),
            compression=PreMoveCompressionMetrics(higher_lows_score=0.0),
        ),
    )
    assert ok is False
    assert reason == "NOT_JUMP_INSUFFICIENT_UP_EVIDENCE"


def test_upward_stage_label_suffix():
    assert upward_stage_label("EARLY_WATCH") == "EARLY_WATCH_UP"
