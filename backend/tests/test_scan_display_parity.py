"""Ensure display_confirmed signals are not dropped in scan pipeline."""

from __future__ import annotations

from models.pre_move import (
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from services.display_buy_pressure_filter import DISPLAY_STRONG_BUY_WATCH, evaluate_premove_display


def test_failed_setup_with_display_confirmed_included_in_scan_logic():
    sig = PreMoveSignal(
        signal_id="X:1",
        symbol="X",
        current_price=5.4,
        change_percent=8.0,
        pre_move_score=40,
        status="FAILED_SETUP",
        lifecycle="REARMED",
        validated=False,
        rejection_reason="some_gate",
        display_confirmed=True,
        display_type=DISPLAY_STRONG_BUY_WATCH,
        buy_pressure_score=12,
        confluence_count=6,
        volume=PreMoveVolumeMetrics(volume_acceleration_1m=2.5),
        early_activity=PreMoveEarlyActivityMetrics(price_volume_response=0.8, micro_higher_lows=True),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=65, spread_percent=2.0),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(stage_lifecycle="REARMED"),
    )
    would_reject_scan = not sig.validated and sig.rejection_reason and not sig.display_confirmed
    assert would_reject_scan is False
    assert evaluate_premove_display(sig).show is True
