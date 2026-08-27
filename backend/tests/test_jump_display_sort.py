"""Jump section — real price jump vs volume-only classification and sort order."""

from __future__ import annotations

from models.opportunity_now import OpportunityNowSignal
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
    display_sort_key,
    evaluate_jump_alert_display,
    evaluate_premove_display,
)


def _real_jump_premove(**overrides) -> PreMoveSignal:
    base = PreMoveSignal(
        signal_id="JUMP:1",
        symbol="JUMP",
        current_price=5.5,
        change_percent=9.0,
        pre_move_score=72,
        status="EARLY_ENTRY",
        lifecycle="EARLY_ENTRY",
        validated=True,
        first_detected_price=5.1,
        trigger_price=5.45,
        display_confirmed=True,
        display_type=DISPLAY_JUMP_ALERT,
        buy_pressure_score=18.0,
        confluence_count=7,
        volume=PreMoveVolumeMetrics(
            volume_acceleration_1m=2.4,
            volume_acceleration_slope=1.15,
            rvol=2.2,
            rvol_same_time=2.5,
        ),
        early_activity=PreMoveEarlyActivityMetrics(
            trade_count_growth=0.22,
            dollar_volume_growth=0.35,
            breakout_pressure_score=48.0,
            micro_higher_lows=True,
            price_volume_response=0.55,
            resistance_distance_pct=1.0,
        ),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=65.0, spread_percent=1.8),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(
            stage_lifecycle="EARLY_ENTRY",
            persistence_minutes=3,
        ),
    )
    data = base.model_dump()
    data.update(overrides)
    return PreMoveSignal(**data)


def _volume_only_premove(**overrides) -> PreMoveSignal:
    base = PreMoveSignal(
        signal_id="VOL:1",
        symbol="VOL",
        current_price=4.2,
        change_percent=2.5,
        pre_move_score=58,
        status="EARLY_WATCH",
        lifecycle="EARLY_WATCH",
        validated=True,
        display_confirmed=True,
        display_type=DISPLAY_JUMP_ALERT,
        buy_pressure_score=22.0,
        confluence_count=6,
        volume=PreMoveVolumeMetrics(
            volume_acceleration_1m=3.5,
            volume_acceleration_slope=1.25,
            rvol=4.0,
            rvol_same_time=4.2,
        ),
        early_activity=PreMoveEarlyActivityMetrics(
            trade_count_growth=0.35,
            price_volume_response=0.08,
            micro_higher_lows=False,
            resistance_distance_pct=8.0,
            breakout_pressure_score=15.0,
        ),
        vwap=PreMoveVwapMetrics(),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=60.0, spread_percent=2.0),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(stage_lifecycle="EARLY_WATCH"),
    )
    data = base.model_dump()
    data.update(overrides)
    return PreMoveSignal(**data)


def test_real_price_jump_stays_jump_alert():
    verdict = evaluate_premove_display(_real_jump_premove())
    assert verdict.show is True
    assert verdict.display_type == DISPLAY_JUMP_ALERT


def test_volume_only_downgraded_to_strong_buy_watch():
    verdict = evaluate_premove_display(_volume_only_premove())
    assert verdict.show is True
    assert verdict.display_type == DISPLAY_STRONG_BUY_WATCH


def test_confirmed_jump_sorts_above_volume_watch():
    jump_sig = OpportunityNowSignal(
        symbol="JUMP",
        price=5.5,
        change_percent=9.0,
        score=72,
        display_type=DISPLAY_JUMP_ALERT,
        buy_pressure_score=18.0,
        confluence_count=7,
    )
    vol_sig = OpportunityNowSignal(
        symbol="VOL",
        price=4.2,
        change_percent=2.5,
        score=58,
        display_type=DISPLAY_STRONG_BUY_WATCH,
        buy_pressure_score=22.0,
        confluence_count=6,
    )
    ordered = sorted([vol_sig, jump_sig], key=display_sort_key)
    assert ordered[0].symbol == "JUMP"
    assert ordered[0].display_type == DISPLAY_JUMP_ALERT
    assert ordered[1].display_type == DISPLAY_STRONG_BUY_WATCH


def test_jump_alert_registry_real_jump_vs_volume_only():
    real = OpportunityNowSignal(
        symbol="REAL",
        price=3.2,
        change_percent=8.5,
        score=80,
        entry_zone_low=2.9,
        entry_zone_high=3.1,
        entry_zone=3.0,
        rvol=2.0,
        volume_acceleration=2.1,
        consecutive_confirmations=3,
        jump_qualified=True,
        jump_alert_created=True,
    )
    vol_only = OpportunityNowSignal(
        symbol="LIQ",
        price=2.1,
        change_percent=1.8,
        score=70,
        entry_zone_low=2.05,
        entry_zone_high=2.08,
        entry_zone=2.06,
        rvol=5.0,
        volume_acceleration=4.0,
        consecutive_confirmations=0,
        jump_qualified=True,
        jump_alert_created=True,
    )
    real_verdict = evaluate_jump_alert_display(real)
    vol_verdict = evaluate_jump_alert_display(vol_only)
    assert real_verdict.display_type == DISPLAY_JUMP_ALERT
    assert vol_verdict.show is True
    assert vol_verdict.display_type == DISPLAY_STRONG_BUY_WATCH

    ordered = sorted(
        [
            OpportunityNowSignal(
                symbol="LIQ",
                price=2.1,
                change_percent=1.8,
                score=70,
                display_type=vol_verdict.display_type,
                buy_pressure_score=25.0,
            ),
            OpportunityNowSignal(
                symbol="REAL",
                price=3.2,
                change_percent=8.5,
                score=80,
                display_type=real_verdict.display_type,
                buy_pressure_score=15.0,
            ),
        ],
        key=display_sort_key,
    )
    assert ordered[0].symbol == "REAL"
