"""REAL_JUMP rejection gates — post-peak, post-stall spread, high-volume absorption."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from analysis.early_upward_surge import RealJumpWaveSnapshot, evaluate_real_jump_alert


def _bars_from_closes(closes: list[float], *, base_vol: int = 50000) -> pd.DataFrame:
    ts = datetime(2026, 1, 14, 14, 0, tzinfo=timezone.utc)
    rows = []
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i else c
        lo = min(c, prev) * 0.998
        hi = max(c, prev) * 1.002
        rows.append({
            "timestamp": ts.replace(minute=ts.minute + i),
            "open": c,
            "high": hi,
            "low": lo,
            "close": c,
            "volume": base_vol + i * 8000,
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


def test_post_peak_weak_momentum_reject():
    """Bounce below session high with modest move_pct — not a live jump."""
    closes = [1.58] * 12 + [1.52, 1.50, 1.48, 1.47, 1.46]
    window = _bars_from_closes(closes)
    wave = RealJumpWaveSnapshot(
        move_start_price=1.34,
        current_move_pct=8.96,
        current_price=1.46,
        price_acceleration_1m=1.77,
        price_acceleration_3m=1.39,
        price_acceleration_5m=1.43,
        wave_active=True,
        wave_peak_price=1.58,
    )
    v = evaluate_real_jump_alert(
        **_strong_kwargs(
            current_price=1.46,
            change_pct=5.0,
            price_volume_response=0.35,
            volume_acceleration_1m=5.0,
            rvol_same_time=2.4,
            spread_pct=0.7,
            persistence_minutes=1,
        ),
        bars=window,
        wave=wave,
    )
    assert v.confirmed is False
    assert v.reject_reason == "post_peak_weak_momentum"


def test_post_stall_bad_spread_reject():
    """Post-spike re-arm with catastrophic spread must not confirm."""
    closes = [1.10] * 8 + [1.49, 1.40, 1.35, 1.30, 1.28, 1.26]
    window = _bars_from_closes(closes)
    wave = RealJumpWaveSnapshot(
        move_start_price=1.135,
        current_move_pct=11.0,
        current_price=1.26,
        price_acceleration_1m=6.67,
        price_acceleration_3m=5.88,
        price_acceleration_5m=5.0,
        wave_active=True,
        wave_peak_price=1.49,
    )
    v = evaluate_real_jump_alert(
        **_strong_kwargs(
            current_price=1.26,
            change_pct=10.0,
            price_volume_response=0.55,
            volume_acceleration_1m=2.3,
            rvol_same_time=247.0,
            spread_pct=32.0,
            persistence_minutes=1,
        ),
        bars=window,
        wave=wave,
    )
    assert v.confirmed is False
    assert v.reject_reason == "post_stall_bad_spread"


def test_high_volume_absorption_reject():
    """High activity in a tight range near session highs — not a price explosion."""
    base = [1.03] * 10 + [1.05, 1.06, 1.07, 1.08, 1.09, 1.10, 1.105, 1.11, 1.115, 1.12, 1.125]
    closes = base + [1.125]
    window = _bars_from_closes(closes)
    wave = RealJumpWaveSnapshot(
        move_start_price=1.03,
        current_move_pct=9.22,
        current_price=1.125,
        price_acceleration_1m=0.45,
        price_acceleration_3m=0.45,
        price_acceleration_5m=0.45,
        wave_active=True,
        wave_peak_price=1.125,
    )
    v = evaluate_real_jump_alert(
        **_strong_kwargs(
            current_price=1.125,
            change_pct=4.0,
            price_volume_response=0.55,
            volume_acceleration_1m=2.5,
            rvol_same_time=1.94,
            spread_pct=0.44,
            persistence_minutes=2,
        ),
        bars=window,
        wave=wave,
    )
    assert v.confirmed is False
    assert v.reject_reason == "high_volume_absorption"


def test_valid_early_real_jump_still_passes():
    """Explosive early leg at session highs must still confirm."""
    closes = [0.376] * 20 + [0.378, 0.380, 0.385, 0.395, 0.410, 0.4199]
    window = _bars_from_closes(closes, base_vol=80000)
    wave = RealJumpWaveSnapshot(
        move_start_price=0.3765,
        current_move_pct=11.53,
        current_price=0.4199,
        price_acceleration_1m=5.0,
        price_acceleration_3m=9.86,
        price_acceleration_5m=11.05,
        wave_active=True,
        wave_peak_price=0.4199,
    )
    v = evaluate_real_jump_alert(
        **_strong_kwargs(
            current_price=0.4199,
            change_pct=11.0,
            price_volume_response=0.85,
            volume_acceleration_1m=4.6,
            rvol_same_time=536.0,
            trade_velocity=124.0,
            spread_pct=5.4,
            persistence_minutes=3,
        ),
        bars=window,
        wave=wave,
    )
    assert v.confirmed is True
