"""قفزة سعرية مميزة — live wave >= 50% from move_start only."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analysis.early_upward_surge import (
    WAVE_STATE_ACTIVE_UPWARD,
    WAVE_STATE_ENDED_LABEL,
    RealJumpEarlyDetectionKPI,
    RealJumpWaveSnapshot,
    RealPriceJumpVerdict,
)
from models.opportunity_now import OpportunityNowSignal
from services.real_jump_alert_layer import (
    DISTINGUISHED_JUMP_MIN_WAVE_PCT,
    DISPLAY_DISTINGUISHED_PRICE_JUMP,
    _live_wave_move_pct,
    apply_distinguished_jump_display,
    eligible_for_distinguished_jump_section,
)


def _active_wave(**overrides) -> RealJumpWaveSnapshot:
    wave = RealJumpWaveSnapshot(
        move_start_price=2.0,
        current_price=3.2,
        current_move_pct=60.0,
        wave_peak_price=3.3,
        price_acceleration_1m=0.12,
        price_acceleration_3m=0.18,
        price_acceleration_5m=0.22,
        wave_active=True,
        wave_ended=False,
        wave_state=WAVE_STATE_ACTIVE_UPWARD,
        move_start_time=datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc),
        first_detected_time=datetime(2026, 8, 28, 14, 2, tzinfo=timezone.utc),
        first_detected_price=2.4,
    )
    for k, v in overrides.items():
        setattr(wave, k, v)
    return wave


def _base_signal(**overrides) -> OpportunityNowSignal:
    data = OpportunityNowSignal(
        symbol="SYM",
        name="SYM",
        price=3.2,
        change_percent=80.0,
    ).model_dump()
    data.update(overrides)
    return OpportunityNowSignal(**data)


def _verdict(wave: RealJumpWaveSnapshot) -> RealPriceJumpVerdict:
    kpi = RealJumpEarlyDetectionKPI(
        move_start_price=wave.move_start_price,
        first_detected_price=wave.first_detected_price,
        first_detected_time=wave.first_detected_time,
        wave_peak_price=wave.wave_peak_price,
    )
    return RealPriceJumpVerdict(confirmed=False, wave=wave, kpi=kpi)


def test_live_move_pct_from_move_start_only():
    assert _live_wave_move_pct(2.0, 3.0) == pytest.approx(50.0)
    assert _live_wave_move_pct(2.0, 4.0) == pytest.approx(100.0)


def test_eligible_when_live_wave_at_least_50():
    wave = _active_wave(move_start_price=2.0, current_price=3.2)
    assert eligible_for_distinguished_jump_section(wave, current_price=3.2) is True


def test_daily_50_percent_but_live_wave_under_50_excluded():
    """change_percent 80% must not qualify if live wave from move_start is < 50%."""
    wave = _active_wave(
        move_start_price=2.0,
        current_price=2.8,
        current_move_pct=40.0,
    )
    assert eligible_for_distinguished_jump_section(wave, current_price=2.8) is False


def test_ended_wave_excluded_even_if_prior_peak_was_high():
    wave = _active_wave(
        wave_active=False,
        wave_ended=True,
        wave_state=WAVE_STATE_ENDED_LABEL,
        current_move_pct=65.0,
        current_price=3.3,
    )
    assert eligible_for_distinguished_jump_section(wave, current_price=3.3) is False


def test_collapsed_from_peak_excluded():
    wave = _active_wave(
        wave_peak_price=4.0,
        current_price=2.4,
        price_acceleration_1m=-0.05,
        price_acceleration_3m=-0.1,
        price_acceleration_5m=-0.08,
        current_move_pct=20.0,
    )
    assert eligible_for_distinguished_jump_section(wave, current_price=2.4) is False


def test_new_wave_uses_fresh_move_start_not_combined():
    wave1 = _active_wave(
        move_start_price=2.0,
        current_price=3.2,
        move_start_time=datetime(2026, 8, 28, 13, 0, tzinfo=timezone.utc),
    )
    live1 = _live_wave_move_pct(wave1.move_start_price, 3.2)
    assert live1 == pytest.approx(60.0)

    wave2 = _active_wave(
        move_start_price=3.0,
        current_price=4.65,
        is_new_wave=True,
        move_start_time=datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc),
    )
    live2 = _live_wave_move_pct(wave2.move_start_price, 4.65)
    assert live2 == pytest.approx(55.0)
    assert live2 != live1


def test_all_matching_waves_no_implicit_cap():
    waves = [
        _active_wave(move_start_price=1.0, current_price=1.55),
        _active_wave(move_start_price=2.0, current_price=3.1),
        _active_wave(move_start_price=3.0, current_price=4.8),
        _active_wave(move_start_price=4.0, current_price=6.2),
        _active_wave(move_start_price=5.0, current_price=7.6),
        _active_wave(move_start_price=6.0, current_price=9.1),
        _active_wave(move_start_price=7.0, current_price=10.6),
        _active_wave(move_start_price=8.0, current_price=12.1),
        _active_wave(move_start_price=9.0, current_price=13.7),
        _active_wave(move_start_price=10.0, current_price=15.2),
        _active_wave(move_start_price=11.0, current_price=16.6),
    ]
    eligible = [
        w
        for w in waves
        if eligible_for_distinguished_jump_section(w, current_price=w.current_price)
    ]
    assert len(eligible) == len(waves)


def test_apply_display_sets_required_card_fields():
    wave = _active_wave()
    sig = apply_distinguished_jump_display(_base_signal(price=3.2), _verdict(wave))
    assert sig.display_type == DISPLAY_DISTINGUISHED_PRICE_JUMP
    assert sig.real_jump_move_start_price == pytest.approx(2.0)
    assert sig.price == pytest.approx(3.2)
    assert sig.real_jump_wave_peak_price == pytest.approx(3.3)
    assert sig.real_jump_current_move_pct >= DISTINGUISHED_JUMP_MIN_WAVE_PCT
    assert sig.real_jump_move_start_time
    assert sig.real_jump_first_detected_time
    assert sig.real_jump_wave_state == WAVE_STATE_ACTIVE_UPWARD
    assert sig.real_jump_retracement_from_peak_pct >= 0


def test_sort_by_move_pct_then_newest_wave():
    items = [
        apply_distinguished_jump_display(
            _base_signal(symbol="A", price=3.0),
            _verdict(
                _active_wave(
                    move_start_price=2.0,
                    current_price=3.0,
                    move_start_time=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
                )
            ),
        ),
        apply_distinguished_jump_display(
            _base_signal(symbol="B", price=3.6),
            _verdict(
                _active_wave(
                    move_start_price=2.0,
                    current_price=3.6,
                    move_start_time=datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc),
                )
            ),
        ),
        apply_distinguished_jump_display(
            _base_signal(symbol="C", price=3.2),
            _verdict(
                _active_wave(
                    move_start_price=2.0,
                    current_price=3.2,
                    move_start_time=datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc),
                )
            ),
        ),
    ]
    items.sort(
        key=lambda s: (s.real_jump_current_move_pct, s.real_jump_move_start_time or ""),
        reverse=True,
    )
    assert items[0].symbol == "B"
    assert items[1].symbol == "C"
    assert items[2].symbol == "A"
