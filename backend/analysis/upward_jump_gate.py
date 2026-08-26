"""Upward-only jump gate — reject breakdowns and bearish momentum."""

from __future__ import annotations

from config import (
    PREMOVE_MIN_LIQUIDITY_SCORE,
    STAGE_BREAKOUT_NEAR_PCT,
    STAGE_EE_MIN_SESSION_CHANGE_PCT,
    STAGE_RVOL_MIN,
    STAGE_VOL_ACCEL_MIN,
)
from models.pre_move import PreMoveSignal

UPWARD_STAGE_SUFFIX = "_UP"


def upward_stage_label(stage: str) -> str:
    base = (stage or "DISCOVERED").upper()
    if base.endswith("_UP"):
        return base
    return f"{base}{UPWARD_STAGE_SUFFIX}"


def evaluate_upward_jump(sig: PreMoveSignal) -> tuple[bool, str]:
    """
    Bullish jump only — NOT_JUMP on breakdown / negative momentum.
    Uses existing stage/score metrics; does not alter threshold constants.
    """
    if sig.change_percent <= 0:
        return False, "NOT_JUMP_NEGATIVE_MOMENTUM"

    regress = list(sig.stage_progression.regression_signals or [])
    if any("broken" in r or "breakdown" in r or "lower_low" in r for r in regress):
        return False, "NOT_JUMP_SUPPORT_BREAK"

    if sig.late_move.is_too_late:
        return False, "NOT_JUMP_TOO_LATE"

    if sig.liquidity.liquidity_score < PREMOVE_MIN_LIQUIDITY_SCORE:
        return False, "NOT_JUMP_LOW_LIQUIDITY"

    vwap_ok = (
        sig.vwap.vwap_hold
        or sig.vwap.vwap_reclaim
        or sig.vwap.distance_from_vwap_pct >= -0.75
    )
    hl_ok = sig.early_activity.micro_higher_lows or sig.compression.higher_lows_score >= 0.35
    trigger_ok = (
        sig.trigger_price > 0
        and sig.current_price >= sig.trigger_price * 0.985
    ) or sig.early_activity.breakout_pressure_score >= 45.0
    breakout_ok = (
        sig.early_activity.breakout_pressure_score >= 40.0
        or sig.breakout.distance_to_breakout_pct <= STAGE_BREAKOUT_NEAR_PCT
    )
    vol_accel_ok = (
        sig.volume.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
        or sig.volume.volume_acceleration >= STAGE_VOL_ACCEL_MIN
    )
    rvol_ok = sig.volume.rvol >= STAGE_RVOL_MIN
    trade_vel = sig.early_activity.trade_velocity
    trade_vel_ok = trade_vel is None or trade_vel > 0
    momentum_ok = sig.change_percent >= min(1.0, STAGE_EE_MIN_SESSION_CHANGE_PCT)

    evidence = [
        vwap_ok,
        hl_ok,
        trigger_ok or breakout_ok,
        vol_accel_ok,
        rvol_ok,
        trade_vel_ok,
        momentum_ok,
    ]
    if sum(evidence) < 4:
        return False, "NOT_JUMP_INSUFFICIENT_UP_EVIDENCE"

    return True, ""
