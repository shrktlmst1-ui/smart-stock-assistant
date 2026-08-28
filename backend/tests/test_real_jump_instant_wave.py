"""REAL_JUMP_ALERT gate tests — snapshot/logic only, no synthetic market bars."""

from __future__ import annotations

import pytest

from analysis.early_upward_surge import RealJumpWaveSnapshot, evaluate_real_jump_alert
from config import STAGE_EE_MAX_EXTENSION_PCT
from services.real_jump_alert_layer import (
    RealJumpAlertRegistry,
    RealJumpWaveTracker,
    evaluate_premove_real_jump,
    real_jump_alert_registry,
    real_jump_wave_tracker,
    reset_real_jump_state,
)
from tests.test_real_jump_alert_layer import _real_jump_signal


def _strong_wave_kwargs(**overrides):
    base = dict(
        current_price=5.5,
        change_pct=5.0,
        price_volume_response=0.55,
        micro_higher_lows=True,
        breakout_pressure=48.0,
        resistance_distance_pct=1.0,
        trigger_price=5.2,
        movement_start_price=0,
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
        range_compression_3m=0.55,
    )
    base.update(overrides)
    return base


def _active_wave(**overrides) -> RealJumpWaveSnapshot:
    wave = RealJumpWaveSnapshot(
        move_start_price=5.0,
        current_move_pct=10.0,
        price_acceleration_1m=0.18,
        price_acceleration_3m=0.32,
        price_acceleration_5m=0.41,
        wave_active=True,
        wave_peak_price=5.5,
    )
    for k, v in overrides.items():
        setattr(wave, k, v)
    return wave


@pytest.fixture(autouse=True)
def _reset():
    reset_real_jump_state()
    yield
    reset_real_jump_state()


def test_daily_up_70_stagnant_no_real_jump():
    wave = RealJumpWaveSnapshot(wave_active=False, wave_ended=False, current_move_pct=0.0)
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(current_price=16.02, change_pct=70.0),
        wave=wave,
    )
    assert v.confirmed is False
    assert v.reject_reason in ("no_active_wave", "wave_ended", "flat_or_down", "hard_gate")


def test_rvol_only_without_price_acceleration_rejected():
    v = evaluate_real_jump_alert(
        current_price=4.2,
        change_pct=3.0,
        price_volume_response=0.08,
        volume_acceleration_1m=0.5,
        rvol_same_time=4.5,
        rvol=4.0,
        liquidity_score=60.0,
        spread_pct=2.0,
        wave=RealJumpWaveSnapshot(
            wave_active=True,
            current_move_pct=3.0,
            price_acceleration_1m=0.05,
            price_acceleration_3m=0.08,
            move_start_price=4.0,
        ),
    )
    assert v.confirmed is False


def test_volume_spike_only_rejected():
    v = evaluate_real_jump_alert(
        current_price=4.02,
        change_pct=0.5,
        price_volume_response=0.05,
        volume_acceleration_1m=3.5,
        volume_acceleration_slope=1.3,
        rvol_same_time=0.8,
        liquidity_score=60.0,
        spread_pct=2.0,
        wave=RealJumpWaveSnapshot(
            wave_active=True,
            current_move_pct=0.5,
            price_acceleration_1m=0.02,
            move_start_price=4.0,
        ),
    )
    assert v.confirmed is False


def test_down_move_rejected():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(current_price=4.8, change_pct=-2.0),
        wave=RealJumpWaveSnapshot(wave_active=True, current_move_pct=-1.5, move_start_price=5.0),
    )
    assert v.confirmed is False


def test_wide_spread_weak_liquidity_rejected():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(spread_pct=9.0, liquidity_score=20.0),
        wave=_active_wave(),
    )
    assert v.confirmed is False


def test_news_only_does_not_create_alert():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(price_volume_response=0.1),
        wave=RealJumpWaveSnapshot(wave_active=True, current_move_pct=4.0, move_start_price=5.0),
        news_catalyst_score=85.0,
    )
    assert v.confirmed is False


def test_active_wave_with_confluence_passes():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(),
        wave=_active_wave(),
    )
    assert v.confirmed is True
    assert v.explosion_confluence_score >= 0.58


def test_wave_ended_rejects():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(),
        wave=RealJumpWaveSnapshot(
            wave_active=False,
            wave_ended=True,
            current_move_pct=8.0,
            move_start_price=5.0,
        ),
    )
    assert v.confirmed is False
    assert v.reject_reason in ("wave_ended", "no_active_wave")


def test_premove_layer_uses_instant_wave_not_day_change():
    for p in [5.1, 5.25, 5.38, 5.5]:
        real_jump_wave_tracker.update("RJ", current_price=p)
    sig = _real_jump_signal(change_percent=5.0)
    verdict = evaluate_premove_real_jump(sig)
    assert verdict.confirmed is True
    assert verdict.wave is not None
    assert verdict.wave.wave_active


def test_duplicate_alert_blocked_for_same_wave():
    registry = RealJumpAlertRegistry()
    wave = _active_wave(wave_id="TEST:5.0:2026")
    v1 = evaluate_real_jump_alert(**_strong_wave_kwargs(), wave=wave)
    live = dict(
        price_volume_response=0.55,
        trade_velocity_growth=0.22,
        trade_velocity=12.0,
        volume_acceleration_1m=2.8,
        spread_pct=1.8,
        liquidity_score=65.0,
    )
    r1 = registry.process("TEST", v1, wave=wave, current_price=5.5, **live)
    r2 = registry.process("TEST", v1, wave=wave, current_price=5.52, **live)
    assert r1.emit is True
    assert r1.update_existing is False
    assert r2.emit is True
    assert r2.update_existing is True
    assert registry.get("TEST") is not None
    assert registry.get("TEST").alert_id == r1.alert.alert_id


def test_new_wave_after_end_allows_new_alert():
    registry = RealJumpAlertRegistry()
    w1 = _active_wave(wave_id="T:5.0:A", is_new_wave=False)
    v1 = evaluate_real_jump_alert(**_strong_wave_kwargs(), wave=w1)
    registry.process("T", v1, wave=w1, current_price=5.5)

    ended = RealJumpWaveSnapshot(
        wave_active=False,
        wave_ended=True,
        wave_id="T:5.0:A",
        move_start_price=5.0,
        current_move_pct=6.0,
    )
    v_end = evaluate_real_jump_alert(**_strong_wave_kwargs(), wave=ended)
    registry.process("T", v_end, wave=ended, current_price=5.4)

    w2 = _active_wave(
        wave_id="T:5.35:B",
        is_new_wave=True,
        move_start_price=5.35,
        current_move_pct=5.0,
    )
    v2 = evaluate_real_jump_alert(**_strong_wave_kwargs(current_price=5.62), wave=w2)
    r2 = registry.process("T", v2, wave=w2, current_price=5.62)
    assert r2.emit is True
    assert r2.update_existing is False
    assert registry.get("T").wave_id == "T:5.35:B"


def test_too_late_uses_wave_extension_not_day_change():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(change_pct=5.0),
        wave=_active_wave(current_move_pct=STAGE_EE_MAX_EXTENSION_PCT + 3),
        late_guard=True,
    )
    assert v.confirmed is False
