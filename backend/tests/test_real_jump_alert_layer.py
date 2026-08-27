"""REAL_JUMP_ALERT — independent layer above existing display signals."""

from __future__ import annotations

from analysis.early_upward_surge import DISPLAY_REAL_JUMP_ALERT, RealJumpEarlyDetectionKPI, RealJumpWaveSnapshot, evaluate_real_jump_alert
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
    evaluate_premove_display,
)
from services.real_jump_alert_layer import (
    REAL_JUMP_EXPLOSIVE_WAVE_PCT,
    REAL_JUMP_SECTION_MIN_WAVE_PCT,
    RealJumpAlertRegistry,
    apply_real_jump_display,
    eligible_for_price_jump_section,
    evaluate_premove_real_jump,
    is_explosive_wave,
    real_jump_wave_tracker,
    reset_real_jump_state,
)


def _real_jump_signal(**overrides) -> PreMoveSignal:
    base = PreMoveSignal(
        signal_id="RJ:1",
        symbol="RJ",
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
            volume_acceleration_1m=2.8,
            volume_acceleration_slope=1.18,
            rvol=2.2,
            rvol_same_time=2.1,
        ),
        early_activity=PreMoveEarlyActivityMetrics(
            trade_count_growth=0.22,
            trade_velocity=15.0,
            dollar_volume_growth=0.35,
            breakout_pressure_score=48.0,
            micro_higher_lows=True,
            price_volume_response=0.55,
            resistance_distance_pct=1.0,
            range_compression_3m=0.55,
        ),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=65.0, spread_percent=1.8),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(
            stage_lifecycle="EARLY_ENTRY",
            persistence_minutes=3,
            move_from_base_pct=8.5,
        ),
    )
    data = base.model_dump()
    data.update(overrides)
    return PreMoveSignal(**data)


def _volume_only_signal(**overrides) -> PreMoveSignal:
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
        volume=PreMoveVolumeMetrics(
            volume_acceleration_1m=3.5,
            volume_acceleration_slope=1.25,
            rvol=4.0,
            rvol_same_time=4.2,
        ),
        early_activity=PreMoveEarlyActivityMetrics(
            trade_count_growth=0.05,
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


def test_real_jump_qualifies_for_real_jump_alert_layer():
    reset_real_jump_state()
    for p in [5.1, 5.25, 5.38, 5.5]:
        real_jump_wave_tracker.update("RJ", current_price=p)
    verdict = evaluate_premove_real_jump(_real_jump_signal())
    assert verdict.confirmed is True
    assert verdict.explosion_confluence_score >= 0.58


def test_volume_only_no_real_jump_alert():
    verdict = evaluate_premove_real_jump(_volume_only_signal())
    assert verdict.confirmed is False


def test_existing_display_unchanged_for_volume_only():
    sig = _volume_only_signal()
    display = evaluate_premove_display(sig)
    assert display.show is True
    assert display.display_type == DISPLAY_JUMP_ALERT


def test_existing_strong_buy_unchanged():
    sig = _volume_only_signal(display_type=DISPLAY_STRONG_BUY_WATCH)
    display = evaluate_premove_display(sig)
    assert display.show is True
    assert display.display_type == DISPLAY_STRONG_BUY_WATCH


def test_real_jump_applies_real_jump_alert_display_type():
    sig = _real_jump_signal()
    verdict = evaluate_premove_real_jump(sig)
    out = apply_real_jump_display(
        OpportunityNowSignal(symbol=sig.symbol, price=sig.current_price, change_percent=sig.change_percent, score=72),
        verdict,
    )
    assert out.display_type == DISPLAY_REAL_JUMP_ALERT
    assert out.status_ar == "REAL_JUMP_ALERT"
    assert out.real_jump_move_start_price >= 0
    assert out.real_jump_first_detected_time or out.real_jump_move_start_time


def test_flat_or_down_rejected():
    v = evaluate_real_jump_alert(
        current_price=5.0,
        change_pct=-1.0,
        price_volume_response=0.5,
        wave=RealJumpWaveSnapshot(wave_active=False, current_move_pct=-1.0),
    )
    assert v.confirmed is False


def test_reacceleration_allows_real_jump_alert():
    v = evaluate_real_jump_alert(
        current_price=6.2,
        change_pct=8.0,
        price_volume_response=0.55,
        micro_higher_lows=True,
        breakout_pressure=48.0,
        resistance_distance_pct=1.0,
        trigger_price=6.0,
        movement_start_price=5.8,
        volume_acceleration_1m=2.8,
        volume_acceleration_slope=1.18,
        trade_velocity_growth=0.22,
        trade_velocity=12.0,
        dollar_volume_growth=0.35,
        rvol=2.2,
        rvol_same_time=2.1,
        liquidity_score=65.0,
        spread_pct=1.8,
        persistence_minutes=3,
        move_from_base_pct=8.0,
        range_compression_3m=0.5,
        reacceleration=True,
        wave=RealJumpWaveSnapshot(
            move_start_price=5.8,
            current_move_pct=6.9,
            price_acceleration_1m=0.2,
            price_acceleration_3m=0.35,
            price_acceleration_5m=0.4,
            wave_active=True,
            is_new_wave=True,
        ),
    )
    assert v.confirmed is True


def test_kpi_wave_peak_move_from_move_start_not_prev_close():
    registry = RealJumpAlertRegistry()
    wave = RealJumpWaveSnapshot(
        move_start_price=2.0,
        first_detected_price=2.5,
        wave_peak_price=4.5,
        wave_active=True,
    )
    from analysis.early_upward_surge import RealPriceJumpVerdict

    kpi = registry._build_kpi(
        wave,
        RealPriceJumpVerdict(confirmed=True, explosion_confluence_score=0.7),
        timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        current_price=4.5,
    )
    assert kpi.first_detected_pct == 25.0
    assert kpi.wave_peak_move_pct == 125.0
    assert kpi.peak_after_detection_pct == 80.0
    assert eligible_for_price_jump_section(kpi, current_move_pct=125.0) is True


def test_price_jump_section_blocked_below_100pct_wave():
    assert eligible_for_price_jump_section(None, current_move_pct=50.0) is False
    assert eligible_for_price_jump_section(None, current_move_pct=100.0) is True
    assert is_explosive_wave(150.0) is True


def test_explosive_badge_at_150pct_wave():
    from analysis.early_upward_surge import RealPriceJumpVerdict

    wave = RealJumpWaveSnapshot(move_start_price=1.0, wave_peak_price=2.6, wave_active=True)
    registry = RealJumpAlertRegistry()
    kpi = registry._build_kpi(
        wave,
        RealPriceJumpVerdict(confirmed=True, explosion_confluence_score=0.8),
        timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        current_price=2.6,
    )
    assert kpi.wave_peak_move_pct >= 150.0
    out = apply_real_jump_display(
        OpportunityNowSignal(symbol="X", price=2.6, change_percent=160, score=90),
        RealPriceJumpVerdict(confirmed=True, wave=wave, kpi=kpi),
    )
    wave.current_move_pct = 155.0
    out2 = apply_real_jump_display(
        OpportunityNowSignal(symbol="X", price=2.6, change_percent=160, score=90),
        RealPriceJumpVerdict(confirmed=True, wave=wave, kpi=kpi),
    )
    assert out2.detection_stage == "EXPLOSIVE"


def test_real_jump_layer_sorts_above_existing_cards():
    real = OpportunityNowSignal(
        symbol="REAL",
        price=5.5,
        change_percent=9.0,
        score=72,
        display_type=DISPLAY_REAL_JUMP_ALERT,
        buy_pressure_score=10.0,
    )
    watch = OpportunityNowSignal(
        symbol="VOL",
        price=4.2,
        change_percent=2.5,
        score=58,
        display_type=DISPLAY_STRONG_BUY_WATCH,
        buy_pressure_score=99.0,
    )
    combined = [real, watch]
    assert combined[0].display_type == DISPLAY_REAL_JUMP_ALERT
    assert combined[1].display_type == DISPLAY_STRONG_BUY_WATCH
