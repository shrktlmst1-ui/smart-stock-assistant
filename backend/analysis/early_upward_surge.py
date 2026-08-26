"""Early upward surge — relative activity spike before large % move."""

from __future__ import annotations

from config import (
    STAGE_EE_MAX_EXTENSION_PCT,
    STAGE_EE_MIN_PROGRESSION,
    STAGE_EE_MIN_RVOL,
    STAGE_RVOL_MIN,
    STAGE_VOL_ACCEL_MIN,
    STAGE_VOL_ACCEL_STRONG,
)
from models.pre_move import PreMoveSignal
from models.pre_move_stage import StageSnapshot


def _effective_rvol(
    *,
    rvol: float,
    rvol_same_time: float | None,
) -> float:
    if rvol_same_time is not None and rvol_same_time > 0:
        return rvol_same_time
    return rvol


def relative_surge_detected(
    *,
    change_percent: float,
    volume_acceleration_1m: float,
    volume_acceleration_slope: float = 0.0,
    rvol: float = 0.0,
    rvol_same_time: float | None = None,
    trade_velocity_growth: float | None = None,
    dollar_volume_growth: float = 0.0,
    breakout_pressure: float = 0.0,
) -> bool:
    """
    Sudden relative activity vs prior baseline — not absolute share volume.
    Allows low total volume if acceleration + RVOL + trade activity spike.
    """
    if change_percent <= 0:
        return False
    if change_percent >= STAGE_EE_MAX_EXTENSION_PCT:
        return False

    rvol_eff = _effective_rvol(rvol=rvol, rvol_same_time=rvol_same_time)
    accel_ok = (
        volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
        or volume_acceleration_slope >= 1.08
    )
    rvol_ok = rvol_eff >= STAGE_RVOL_MIN or rvol >= STAGE_RVOL_MIN
    trade_ok = (trade_velocity_growth or 0) >= 0.15
    liq_flow_ok = dollar_volume_growth >= 0.25 or breakout_pressure >= 35.0

    return accel_ok and rvol_ok and (trade_ok or liq_flow_ok)


def relative_surge_from_signal(sig: PreMoveSignal) -> bool:
    return relative_surge_detected(
        change_percent=sig.change_percent,
        volume_acceleration_1m=sig.volume.volume_acceleration_1m,
        volume_acceleration_slope=sig.volume.volume_acceleration_slope,
        rvol=sig.volume.rvol,
        rvol_same_time=sig.volume.rvol_same_time,
        trade_velocity_growth=sig.early_activity.trade_count_growth,
        dollar_volume_growth=sig.early_activity.dollar_volume_growth,
        breakout_pressure=sig.early_activity.breakout_pressure_score,
    )


def relative_surge_from_snapshot(snap: StageSnapshot) -> bool:
    return relative_surge_detected(
        change_percent=snap.change_pct,
        volume_acceleration_1m=snap.volume_acceleration_1m,
        volume_acceleration_slope=snap.volume_acceleration_slope,
        rvol=snap.rvol,
        rvol_same_time=snap.rvol_same_time,
        trade_velocity_growth=snap.trade_velocity_growth,
        dollar_volume_growth=snap.dollar_volume_growth,
        breakout_pressure=snap.breakout_pressure,
    )


def surge_direct_early_entry(
    snap: StageSnapshot,
    *,
    progression_score: float,
    ew_signals: int,
    move_from_base_pct: float,
) -> bool:
    """Fast EE on strong relative surge — uses existing high-bar constants only."""
    if move_from_base_pct >= STAGE_EE_MAX_EXTENSION_PCT:
        return False
    if ew_signals < 5:
        return False
    if progression_score < STAGE_EE_MIN_PROGRESSION + 8:
        return False
    if not relative_surge_from_snapshot(snap):
        return False
    return (
        snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_STRONG
        and _effective_rvol(rvol=snap.rvol, rvol_same_time=snap.rvol_same_time) >= STAGE_EE_MIN_RVOL
        and (snap.vwap_hold or snap.vwap_reclaim or snap.distance_from_vwap_pct <= 2.5)
    )


def fast_filter_surge_rank(change_percent: float, rvol: float) -> float:
    """Rank early setups: high RVOL, penalize extended session move."""
    extension_penalty = max(0.0, change_percent - 12.0) * 3.0
    return rvol * 2.5 + min(change_percent, 12.0) * 0.5 - extension_penalty
