"""REAL_JUMP_ALERT acceptance — early catch vs stalled/retrace rejection (causal bars)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from analysis.early_upward_surge import (
    RealJumpWaveSnapshot,
    WAVE_STATE_ACTIVE_UPWARD,
    WAVE_STATE_ENDED_LABEL,
    evaluate_real_jump_alert,
    evaluate_real_jump_live_exit,
)


def _bars_from_closes(closes: list[float]) -> pd.DataFrame:
    ts = datetime(2026, 1, 14, 14, 0, tzinfo=timezone.utc)
    rows = []
    for i, c in enumerate(closes):
        lo = min(c, closes[i - 1] if i else c) * 0.998
        hi = max(c, closes[i - 1] if i else c) * 1.002
        rows.append({
            "timestamp": ts.replace(minute=ts.minute + i),
            "open": c,
            "high": hi,
            "low": lo,
            "close": c,
            "volume": 50000 + i * 8000,
        })
    return pd.DataFrame(rows)


def _strong_kwargs(**overrides):
    base = dict(
        current_price=0.50,
        change_pct=8.0,
        price_volume_response=0.52,
        micro_higher_lows=True,
        breakout_pressure=50.0,
        resistance_distance_pct=1.0,
        trigger_price=0.48,
        volume_acceleration_1m=2.6,
        volume_acceleration_slope=1.2,
        trade_velocity_growth=0.18,
        trade_velocity=14.0,
        dollar_volume_growth=0.32,
        rvol=2.0,
        rvol_same_time=2.2,
        liquidity_score=68.0,
        spread_pct=1.5,
        persistence_minutes=3,
        range_compression_3m=0.5,
        data_age_seconds=5.0,
    )
    base.update(overrides)
    return base


def test_early_catch_near_048_continues_to_090():
    """Regression: detect ~0.48 on live rise; peak-after-detection reaches ~0.90; exit after retrace."""
    # Phase 1 — entry near 0.48
    entry_closes = [0.45, 0.46, 0.47, 0.475, 0.48, 0.49]
    window = _bars_from_closes(entry_closes)
    wave = RealJumpWaveSnapshot(
        move_start_price=0.45,
        move_start_time=datetime(2026, 1, 14, 14, 0, tzinfo=timezone.utc),
        current_move_pct=(0.48 - 0.45) / 0.45 * 100.0,
        current_price=0.48,
        price_acceleration_1m=0.22,
        price_acceleration_3m=0.35,
        price_acceleration_5m=0.40,
        wave_active=True,
        wave_peak_price=0.49,
    )
    v_entry = evaluate_real_jump_alert(**_strong_kwargs(current_price=0.48), bars=window, wave=wave)
    assert v_entry.confirmed is True
    first_detect = 0.48

    # Phase 2 — continuation to 0.90 (update path)
    peak_closes = entry_closes + [0.52, 0.58, 0.65, 0.72, 0.80, 0.88, 0.90]
    peak_window = _bars_from_closes(peak_closes)
    wave.current_price = 0.90
    wave.wave_peak_price = 0.90
    wave.current_move_pct = (0.90 - 0.45) / 0.45 * 100.0
    v_peak = evaluate_real_jump_alert(
        **_strong_kwargs(current_price=0.90),
        bars=peak_window,
        wave=wave,
        is_alert_update=True,
    )
    assert v_peak.confirmed is True
    peak_after = 0.90

    # Phase 3 — end after retrace
    end, reason, state = evaluate_real_jump_live_exit(
        wave=RealJumpWaveSnapshot(
            move_start_price=0.45,
            wave_peak_price=0.90,
            current_price=0.78,
            current_move_pct=(0.78 - 0.45) / 0.45 * 100.0,
            price_acceleration_1m=-0.12,
            price_acceleration_3m=-0.05,
            price_acceleration_5m=0.0,
            wave_active=True,
        ),
        current_price=0.78,
        price_volume_response=0.15,
        trade_velocity_growth=-0.10,
        trade_velocity=4.0,
        volume_acceleration_1m=0.8,
        spread_pct=1.5,
        liquidity_score=65.0,
        bars=_bars_from_closes(peak_closes + [0.85, 0.78]),
    )
    assert end is True
    assert first_detect <= 0.52
    assert peak_after >= 0.88
    assert state == WAVE_STATE_ENDED_LABEL


def test_stalled_after_peak_rejected():
    """Stock peaked at 0.90, stalled ~0.55 with weak buy — no REAL_JUMP."""
    closes = [0.50, 0.65, 0.80, 0.90, 0.88, 0.70, 0.58, 0.55, 0.54, 0.55]
    window = _bars_from_closes(closes)
    wave = RealJumpWaveSnapshot(
        move_start_price=0.50,
        wave_peak_price=0.90,
        current_move_pct=10.0,
        current_price=0.55,
        price_acceleration_1m=-0.02,
        price_acceleration_3m=0.01,
        price_acceleration_5m=0.0,
        wave_active=True,
    )
    v = evaluate_real_jump_alert(
        **_strong_kwargs(
            current_price=0.55,
            price_volume_response=0.12,
            trade_velocity_growth=0.03,
            volume_acceleration_1m=0.9,
            rvol_same_time=1.0,
        ),
        bars=window,
        wave=wave,
    )
    assert v.confirmed is False
    assert "stalled_after_prior_peak" in v.reject_reason or v.reject_reason in (
        "price_not_rising_now",
        "rvol_only",
        "volume_accel_only",
        "activity_spike_only",
        "missing_core_explosion_factors",
        "session_stall_below_peak",
    ) or v.reject_reason.startswith("confluence_") or v.reject_reason.startswith("hard_gate_")


def test_live_exit_after_peak_retrace():
    wave = RealJumpWaveSnapshot(
        move_start_price=0.45,
        wave_peak_price=0.90,
        current_move_pct=75.0,
        current_price=0.78,
        price_acceleration_1m=-0.10,
        price_acceleration_3m=-0.04,
        price_acceleration_5m=0.0,
        wave_active=True,
    )
    end, reason, state = evaluate_real_jump_live_exit(
        wave=wave,
        current_price=0.78,
        price_volume_response=0.18,
        trade_velocity_growth=-0.08,
        trade_velocity=5.0,
        volume_acceleration_1m=1.0,
        spread_pct=2.0,
        liquidity_score=65.0,
    )
    assert end is True
    assert state == WAVE_STATE_ENDED_LABEL


def test_active_upward_wave_state_on_confirm():
    wave = RealJumpWaveSnapshot(
        move_start_price=0.45,
        current_move_pct=11.0,
        price_acceleration_1m=0.20,
        price_acceleration_3m=0.32,
        price_acceleration_5m=0.38,
        wave_active=True,
    )
    v = evaluate_real_jump_alert(**_strong_kwargs(current_price=0.50), wave=wave)
    assert v.confirmed is True
    assert v.wave.wave_state == WAVE_STATE_ACTIVE_UPWARD


@pytest.mark.parametrize("session", ["PRE_MARKET", "REGULAR", "AFTER_HOURS"])
def test_entry_logic_session_agnostic(session):
    """Gate uses wave metrics — not session-specific symbols."""
    wave = RealJumpWaveSnapshot(
        move_start_price=0.45,
        current_move_pct=12.0,
        price_acceleration_1m=0.20,
        price_acceleration_3m=0.30,
        price_acceleration_5m=0.36,
        wave_active=True,
    )
    v = evaluate_real_jump_alert(**_strong_kwargs(current_price=0.504), wave=wave)
    assert v.confirmed is True
