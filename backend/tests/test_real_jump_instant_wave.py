"""Instant-wave REAL_JUMP_ALERT — moment-based, not session/day change."""

from __future__ import annotations

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from analysis.early_upward_surge import RealJumpWaveSnapshot, evaluate_real_jump_alert
from config import STAGE_EE_MAX_EXTENSION_PCT
from services.real_jump_alert_layer import RealJumpWaveTracker, evaluate_premove_real_jump, real_jump_wave_tracker
from tests.test_real_jump_alert_layer import _real_jump_signal

ET = ZoneInfo("America/New_York")


def _bars_from_closes(closes: list[float]) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(closes):
        rows.append({
            "timestamp": pd.Timestamp(f"2026-08-27 10:{i:02d}:00", tz=ET),
            "open": c * 0.998,
            "high": c * 1.012,
            "low": c * 0.995,
            "close": c,
            "volume": 1000 + i * 500,
        })
    return pd.DataFrame(rows)


def _strong_wave_kwargs(**overrides):
    base = dict(
        current_price=5.5,
        change_pct=5.0,
        price_volume_response=0.55,
        micro_higher_lows=True,
        breakout_pressure=48.0,
        resistance_distance_pct=1.0,
        trigger_price=5.2,
        movement_start_price=5.0,
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
    )
    for k, v in overrides.items():
        setattr(wave, k, v)
    return wave


@pytest.fixture(autouse=True)
def _reset_tracker():
    real_jump_wave_tracker.reset()
    yield
    real_jump_wave_tracker.reset()


def test_daily_up_70_stagnant_no_real_jump():
    """+70% session move but flat now — no REAL_JUMP_ALERT."""
    stagnant = _bars_from_closes([16.0, 16.01, 16.0, 16.01, 16.0, 16.02])
    wave = real_jump_wave_tracker.update("STAG", current_price=16.02, bars=stagnant)
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(current_price=16.02, change_pct=70.0),
        bars=stagnant,
        wave=wave,
    )
    assert v.confirmed is False
    assert v.reject_reason in ("no_active_wave", "wave_ended", "flat_or_down")


def test_daily_up_5_instant_wave_yes_real_jump():
    """+5% session but strong new instant wave — REAL_JUMP_ALERT allowed."""
    surge = _bars_from_closes([4.80, 4.85, 4.92, 5.02, 5.15, 5.28])
    wave = real_jump_wave_tracker.update("SURGE", current_price=5.28, bars=surge)
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(current_price=5.28, change_pct=5.0, movement_start_price=4.80),
        bars=surge,
        wave=wave,
    )
    assert v.confirmed is True
    assert v.wave is not None
    assert v.wave.current_move_pct > 0
    assert v.wave.wave_active is True


def test_wave_ended_clears_real_jump():
    tracker = RealJumpWaveTracker()
    active = _bars_from_closes([5.0, 5.1, 5.25, 5.45, 5.62])
    wave_active = tracker.update("W1", current_price=5.62, bars=active)
    v_on = evaluate_real_jump_alert(
        **_strong_wave_kwargs(current_price=5.62, movement_start_price=5.0),
        bars=active,
        wave=wave_active,
    )
    assert v_on.confirmed is True

    flat = _bars_from_closes([5.0, 5.1, 5.25, 5.45, 5.62, 5.61, 5.60, 5.61])
    wave_flat = tracker.update("W1", current_price=5.61, bars=flat)
    v_off = evaluate_real_jump_alert(
        **_strong_wave_kwargs(current_price=5.61, movement_start_price=5.0),
        bars=flat,
        wave=wave_flat,
    )
    assert v_off.confirmed is False
    assert v_off.reject_reason in ("wave_ended", "no_active_wave")


def test_reacceleration_new_instant_wave():
    tracker = RealJumpWaveTracker()
    first = _bars_from_closes([3.0, 3.08, 3.12, 3.18, 3.22])
    w1 = tracker.update("R1", current_price=3.22, bars=first)
    v1 = evaluate_real_jump_alert(
        **_strong_wave_kwargs(
            current_price=3.22,
            change_pct=40.0,
            movement_start_price=0,
            trigger_price=3.15,
        ),
        bars=first,
        wave=w1,
    )
    assert v1.confirmed is True

    pause = _bars_from_closes([3.0, 3.08, 3.18, 3.32, 3.50, 3.49, 3.48, 3.49])
    tracker.update("R1", current_price=3.49, bars=pause)
    tracker.update("R1", current_price=3.48, bars=pause)
    w_pause = tracker.update("R1", current_price=3.49, bars=pause)
    assert w_pause.wave_active is False or w_pause.wave_ended

    second = _bars_from_closes([3.0, 3.08, 3.18, 3.32, 3.50, 3.49, 3.48, 3.49, 3.55, 3.68, 3.85])
    w2 = tracker.update("R1", current_price=3.85, bars=second)
    v2 = evaluate_real_jump_alert(
        **_strong_wave_kwargs(
            current_price=3.85,
            change_pct=55.0,
            movement_start_price=w2.move_start_price or 3.48,
            trigger_price=3.55,
        ),
        bars=second,
        wave=w2,
    )
    assert v2.confirmed is True
    assert w2.is_new_wave or w2.wave_active


def test_premove_layer_uses_instant_wave_not_day_change():
    for p in [5.1, 5.25, 5.38, 5.5]:
        real_jump_wave_tracker.update("RJ", current_price=p)
    sig = _real_jump_signal(change_percent=5.0)
    verdict = evaluate_premove_real_jump(sig)
    assert verdict.confirmed is True
    assert verdict.wave is not None
    assert verdict.wave.wave_active


def test_day_change_ignored_when_no_wave():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(change_pct=80.0),
        wave=RealJumpWaveSnapshot(wave_active=False, current_move_pct=0.0),
    )
    assert v.confirmed is False


def test_too_late_uses_wave_extension_not_day_change():
    v = evaluate_real_jump_alert(
        **_strong_wave_kwargs(change_pct=5.0, movement_start_price=0),
        wave=_active_wave(current_move_pct=STAGE_EE_MAX_EXTENSION_PCT + 3),
        late_guard=True,
    )
    assert v.confirmed is False
    assert v.reject_reason in ("too_late_to_chase", "wave_too_extended")


def test_false_positives_zero_instant_patterns():
    negatives = [
        _bars_from_closes([2.0, 2.05, 2.08, 2.10]),
        _bars_from_closes([5.0, 5.02, 5.01, 5.03]),
        _bars_from_closes([3.0, 2.95, 2.98, 3.02, 3.01]),
    ]
    fp = 0
    for bars in negatives:
        price = float(bars["close"].iloc[-1])
        wave = real_jump_wave_tracker.update("NEG", current_price=price, bars=bars)
        v = evaluate_real_jump_alert(
            current_price=price,
            change_pct=3.0,
            price_volume_response=0.12,
            volume_acceleration_1m=1.5,
            rvol_same_time=0.9,
            liquidity_score=60.0,
            spread_pct=2.0,
            bars=bars,
            wave=wave,
        )
        if v.confirmed:
            fp += 1
    assert fp == 0
