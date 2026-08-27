"""Independent REAL_JUMP_ALERT layer — sits above existing display signals unchanged."""

from __future__ import annotations

from analysis.early_upward_surge import (
    DISPLAY_REAL_JUMP_ALERT,
    RealPriceJumpVerdict,
    evaluate_real_jump_alert,
    fast_filter_surge_rank,
)
from config import PREMOVE_DATA_MAX_AGE_SECONDS, PREMOVE_MIN_LIQUIDITY_SCORE
from models.opportunity_now import OpportunityNowSignal
from models.pre_move import PreMoveSignal
from services.display_buy_pressure_filter import context_from_premove, context_from_opportunity_signal

MAX_PRICE_USD = 10.0
REAL_JUMP_MAX = 3


def _movement_start(sig: PreMoveSignal) -> float:
    if sig.first_detected_price > 0:
        return sig.first_detected_price
    if sig.entry_low > 0:
        return sig.entry_low
    if sig.trigger_price > 0:
        return sig.trigger_price * 0.985
    return 0.0


def evaluate_premove_real_jump(sig: PreMoveSignal) -> RealPriceJumpVerdict:
    ctx = context_from_premove(sig)
    ea = sig.early_activity
    return evaluate_real_jump_alert(
        current_price=sig.current_price,
        change_pct=sig.change_percent,
        price_volume_response=ctx.price_volume_response,
        micro_higher_lows=ctx.micro_higher_lows,
        vwap_hold=ctx.vwap_hold,
        vwap_reclaim=ctx.vwap_reclaim,
        breakout_pressure=ctx.breakout_pressure,
        resistance_distance_pct=ctx.resistance_distance_pct,
        trigger_price=sig.trigger_price,
        movement_start_price=_movement_start(sig),
        volume_acceleration_1m=ctx.volume_acceleration_1m,
        volume_acceleration_slope=ctx.volume_acceleration_slope,
        rvol=ctx.rvol,
        rvol_same_time=ctx.rvol_same_time,
        trade_velocity_growth=ctx.trade_velocity_growth,
        trade_velocity=ea.trade_velocity,
        dollar_volume_growth=ctx.dollar_volume_growth,
        liquidity_score=ctx.liquidity_score,
        spread_pct=ctx.spread_pct,
        persistence_minutes=sig.stage_progression.persistence_minutes,
        move_from_base_pct=sig.stage_progression.move_from_base_pct,
        compression_only=sig.compression.compression_score >= 0.5 and ctx.change_percent < 2.0,
        watch_only=sig.status in ("EARLY_WATCH", "PRE_BREAKOUT") and not sig.display_confirmed,
    )


def evaluate_opportunity_real_jump(sig: OpportunityNowSignal) -> RealPriceJumpVerdict:
    ctx = context_from_opportunity_signal(sig)
    entry_high = sig.entry_zone_high or sig.entry_zone
    return evaluate_real_jump_alert(
        current_price=sig.price,
        change_pct=sig.change_percent,
        price_volume_response=ctx.price_volume_response,
        micro_higher_lows=ctx.micro_higher_lows,
        breakout_pressure=ctx.breakout_pressure or (45.0 if sig.detection_stage == "EXPLOSIVE" else 0.0),
        resistance_distance_pct=ctx.resistance_distance_pct,
        trigger_price=entry_high,
        movement_start_price=sig.entry_zone_low or sig.entry_zone,
        volume_acceleration_1m=sig.volume_acceleration,
        rvol=sig.rvol or sig.relative_volume,
        trade_velocity_growth=ctx.trade_velocity_growth,
        dollar_volume_growth=ctx.dollar_volume_growth,
        liquidity_score=max(ctx.liquidity_score, PREMOVE_MIN_LIQUIDITY_SCORE),
        spread_pct=ctx.spread_pct,
        persistence_minutes=sig.consecutive_confirmations,
        move_from_base_pct=sig.change_percent,
    )


def apply_real_jump_display(sig: OpportunityNowSignal, verdict: RealPriceJumpVerdict) -> OpportunityNowSignal:
    data = sig.model_dump()
    data["display_type"] = DISPLAY_REAL_JUMP_ALERT
    data["status"] = "NOW"
    data["status_ar"] = "قفزة سعرية حقيقية"
    data["opportunity_type"] = DISPLAY_REAL_JUMP_ALERT
    data["confluence_factors"] = list(verdict.evidence_factors)
    data["confluence_count"] = len(verdict.evidence_factors)
    if not data.get("buy_pressure_score"):
        rvol = sig.rvol or sig.relative_volume or 0.5
        data["buy_pressure_score"] = round(fast_filter_surge_rank(sig.change_percent, rvol), 2)
    return OpportunityNowSignal(**data)


def eligible_premove(sig: PreMoveSignal) -> bool:
    if sig.current_price <= 0 or sig.current_price > MAX_PRICE_USD:
        return False
    if sig.change_percent <= 0:
        return False
    if sig.data_age_seconds > PREMOVE_DATA_MAX_AGE_SECONDS:
        return False
    if sig.late_move.is_too_late:
        return False
    return True
