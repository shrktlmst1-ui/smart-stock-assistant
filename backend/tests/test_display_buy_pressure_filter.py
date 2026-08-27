"""Display filter — strong real buying only (no engine changes)."""

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
from services.display_buy_pressure_filter import (
    DISPLAY_JUMP_ALERT,
    DISPLAY_STRONG_BUY_WATCH,
    evaluate_premove_display,
    evaluate_jump_alert_display,
)
from models.opportunity_now import OpportunityNowSignal


def _cre_style_signal(**overrides) -> PreMoveSignal:
    base = PreMoveSignal(
        signal_id="CRE:2026",
        symbol="CRE",
        current_price=1.15,
        change_percent=10.0,
        pre_move_score=68,
        status="EARLY_WATCH",
        lifecycle="EARLY_WATCH",
        validated=True,
        volume=PreMoveVolumeMetrics(
            volume_acceleration_1m=1.35,
            volume_acceleration_slope=1.12,
            rvol=2.1,
            rvol_same_time=2.4,
        ),
        early_activity=PreMoveEarlyActivityMetrics(
            trade_count_growth=0.28,
            dollar_volume_growth=0.3,
            breakout_pressure_score=45.0,
            micro_higher_lows=True,
            price_volume_response=0.45,
            resistance_distance_pct=2.0,
        ),
        vwap=PreMoveVwapMetrics(vwap_hold=True, vwap_reclaim=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=55.0, spread_percent=1.5),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(stage_lifecycle="EARLY_WATCH"),
    )
    data = base.model_dump()
    data.update(overrides)
    return PreMoveSignal(**data)


def test_cre_style_passes_strong_buy_watch():
    verdict = evaluate_premove_display(_cre_style_signal())
    assert verdict.show is True
    assert verdict.display_type == DISPLAY_STRONG_BUY_WATCH
    assert verdict.confluence_count >= 5


def test_too_late_rejected():
    sig = _cre_style_signal(
        status="TOO_LATE_TO_CHASE",
        change_percent=80.0,
        late_move=PreMoveLateMoveMetrics(is_too_late=True),
    )
    assert evaluate_premove_display(sig).show is False


def test_score_only_without_surge_rejected():
    sig = _cre_style_signal(
        volume=PreMoveVolumeMetrics(volume_acceleration_1m=1.0, rvol=1.0),
        early_activity=PreMoveEarlyActivityMetrics(trade_count_growth=0.0),
    )
    assert evaluate_premove_display(sig).show is False


def test_early_entry_is_jump_alert():
    sig = _cre_style_signal(status="EARLY_ENTRY", lifecycle="EARLY_ENTRY")
    verdict = evaluate_premove_display(sig)
    assert verdict.show is True
    assert verdict.display_type == DISPLAY_JUMP_ALERT


def test_jump_alert_signal_display():
    sig = OpportunityNowSignal(
        symbol="BTCT",
        price=2.5,
        change_percent=8.0,
        score=85,
        entry_zone_low=2.2,
        entry_zone_high=2.45,
        entry_zone=2.35,
        rvol=2.5,
        volume_acceleration=2.0,
        consecutive_confirmations=3,
        jump_alert_id="abc",
        jump_qualified=True,
        jump_alert_created=True,
    )
    verdict = evaluate_jump_alert_display(sig)
    assert verdict.show is True
    assert verdict.display_type == DISPLAY_JUMP_ALERT
