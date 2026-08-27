"""Home-screen display filter — strong real buying pressure only (no engine/threshold changes)."""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis.early_upward_surge import (
    DISPLAY_JUMP_ALERT,
    DISPLAY_STRONG_BUY_WATCH,
    evaluate_real_price_jump,
    fast_filter_surge_rank,
    relative_surge_detected,
    relative_surge_from_signal,
)
from config import (
    PREMOVE_DATA_MAX_AGE_SECONDS,
    PREMOVE_MIN_LIQUIDITY_SCORE,
    STAGE_BREAKOUT_NEAR_PCT,
    STAGE_EE_MAX_EXTENSION_PCT,
    STAGE_EE_MAX_SPREAD_PCT,
    STAGE_EE_MIN_CONFLUENCE,
    STAGE_EE_MIN_LIQUIDITY,
    STAGE_EE_MIN_SESSION_CHANGE_PCT,
    STAGE_RVOL_MIN,
    STAGE_VOL_ACCEL_MIN,
)
from models.jump_alert import QUALIFIED_JUMP_SIGNALS
from models.opportunity_now import OpportunityNowSignal
from models.pre_move import PreMoveSignal

_EXCLUDED_PREMOVE = frozenset({
    "NO_SETUP",
    "TOO_LATE_TO_CHASE",
    "INSUFFICIENT_DATA",
    "STALE_PRICE",
    "FAILED_SETUP",
})

_EARLY_STAGES = frozenset({"EARLY_WATCH", "PRE_BREAKOUT", "EARLY_ENTRY", "HIGH_CONVICTION_EARLY", "REARMED", "CONFIRMED_ENTRY"})


@dataclass
class BuyPressureContext:
    change_percent: float = 0.0
    volume_acceleration_1m: float = 0.0
    volume_acceleration_slope: float = 0.0
    rvol: float = 0.0
    rvol_same_time: float | None = None
    trade_velocity_growth: float = 0.0
    dollar_volume_growth: float = 0.0
    breakout_pressure: float = 0.0
    spread_pct: float = 99.0
    liquidity_score: float = 0.0
    vwap_hold: bool = False
    vwap_reclaim: bool = False
    micro_higher_lows: bool = False
    resistance_distance_pct: float = 99.0
    price_volume_response: float = 0.0
    late_guard: bool = False
    is_too_late: bool = False
    premove_status: str = ""
    stage_lifecycle: str = ""


@dataclass
class DisplayVerdict:
    show: bool = False
    display_type: str = ""
    buy_pressure_score: float = 0.0
    confluence_count: int = 0
    confluence_factors: list[str] = field(default_factory=list)
    reject_reason: str = ""


def context_from_premove(sig: PreMoveSignal) -> BuyPressureContext:
    lifecycle = sig.stage_progression.stage_lifecycle or sig.lifecycle or sig.status
    return BuyPressureContext(
        change_percent=sig.change_percent,
        volume_acceleration_1m=sig.volume.volume_acceleration_1m,
        volume_acceleration_slope=sig.volume.volume_acceleration_slope,
        rvol=sig.volume.rvol,
        rvol_same_time=sig.volume.rvol_same_time,
        trade_velocity_growth=float(sig.early_activity.trade_count_growth or 0),
        dollar_volume_growth=sig.early_activity.dollar_volume_growth,
        breakout_pressure=sig.early_activity.breakout_pressure_score,
        spread_pct=sig.liquidity.spread_percent,
        liquidity_score=sig.liquidity.liquidity_score,
        vwap_hold=sig.vwap.vwap_hold,
        vwap_reclaim=sig.vwap.vwap_reclaim,
        micro_higher_lows=sig.early_activity.micro_higher_lows,
        resistance_distance_pct=sig.early_activity.resistance_distance_pct,
        price_volume_response=sig.early_activity.price_volume_response,
        late_guard=sig.late_move.is_too_late,
        is_too_late=sig.late_move.is_too_late or sig.status == "TOO_LATE_TO_CHASE",
        premove_status=sig.status,
        stage_lifecycle=lifecycle,
    )


def context_from_opportunity_signal(sig: OpportunityNowSignal) -> BuyPressureContext:
    return BuyPressureContext(
        change_percent=sig.change_percent,
        rvol=sig.relative_volume,
        spread_pct=99.0 if sig.late_entry_warning else STAGE_EE_MAX_SPREAD_PCT,
        is_too_late=sig.late_entry_warning or sig.status == "CANCELLED",
        premove_status=sig.opportunity_type or sig.status,
        stage_lifecycle=sig.stage_lifecycle or sig.detection_stage,
    )


def _effective_rvol(ctx: BuyPressureContext) -> float:
    if ctx.rvol_same_time is not None and ctx.rvol_same_time > 0:
        return ctx.rvol_same_time
    return ctx.rvol


def count_buy_pressure_confluence(ctx: BuyPressureContext) -> tuple[int, list[str]]:
    """Confluence checklist — uses existing stage constants only."""
    factors: list[str] = []
    liq_min = min(STAGE_EE_MIN_LIQUIDITY, PREMOVE_MIN_LIQUIDITY_SCORE)

    if ctx.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN or ctx.volume_acceleration_slope >= 1.08:
        factors.append("volume_acceleration")
    if _effective_rvol(ctx) >= STAGE_RVOL_MIN:
        factors.append("rvol")
    if ctx.trade_velocity_growth >= 0.15:
        factors.append("trade_velocity")
    if ctx.dollar_volume_growth >= 0.25 or ctx.breakout_pressure >= 35.0:
        factors.append("buy_flow")
    if ctx.change_percent >= STAGE_EE_MIN_SESSION_CHANGE_PCT and ctx.price_volume_response >= 0.35:
        factors.append("price_momentum")
    elif ctx.change_percent >= STAGE_EE_MIN_SESSION_CHANGE_PCT:
        factors.append("price_up")
    if ctx.vwap_hold or ctx.vwap_reclaim:
        factors.append("vwap")
    if ctx.micro_higher_lows:
        factors.append("higher_lows")
    if ctx.resistance_distance_pct <= STAGE_BREAKOUT_NEAR_PCT * 2:
        factors.append("near_trigger")
    if ctx.liquidity_score >= liq_min:
        factors.append("liquidity")
    if ctx.spread_pct <= STAGE_EE_MAX_SPREAD_PCT:
        factors.append("spread_ok")
    if 0 < ctx.change_percent < STAGE_EE_MAX_EXTENSION_PCT:
        factors.append("early_move")

    return len(factors), factors


def _has_relative_surge(ctx: BuyPressureContext) -> bool:
    return relative_surge_detected(
        change_percent=ctx.change_percent,
        volume_acceleration_1m=ctx.volume_acceleration_1m,
        volume_acceleration_slope=ctx.volume_acceleration_slope,
        rvol=ctx.rvol,
        rvol_same_time=ctx.rvol_same_time,
        trade_velocity_growth=ctx.trade_velocity_growth,
        dollar_volume_growth=ctx.dollar_volume_growth,
        breakout_pressure=ctx.breakout_pressure,
    )


def _passes_freshness_gate(sig: PreMoveSignal) -> bool:
    """Minimal sanity for backend-confirmed display — no full re-analysis."""
    if sig.current_price <= 0 or sig.current_price > 10.0:
        return False
    if sig.change_percent <= 0:
        return False
    if sig.data_age_seconds > PREMOVE_DATA_MAX_AGE_SECONDS:
        return False
    if sig.liquidity.spread_percent > STAGE_EE_MAX_SPREAD_PCT:
        return False
    if sig.liquidity.liquidity_score < PREMOVE_MIN_LIQUIDITY_SCORE:
        return False
    if sig.late_move.is_too_late and not sig.display_confirmed:
        return False
    return True


def _movement_start_price(sig: PreMoveSignal) -> float:
    if sig.first_detected_price > 0:
        return sig.first_detected_price
    if sig.entry_low > 0:
        return sig.entry_low
    if sig.trigger_price > 0:
        return sig.trigger_price * 0.985
    return 0.0


def real_price_jump_from_premove(sig: PreMoveSignal):
    ctx = context_from_premove(sig)
    return evaluate_real_price_jump(
        current_price=sig.current_price,
        change_pct=sig.change_percent,
        price_volume_response=ctx.price_volume_response,
        micro_higher_lows=ctx.micro_higher_lows,
        vwap_hold=ctx.vwap_hold,
        vwap_reclaim=ctx.vwap_reclaim,
        breakout_pressure=ctx.breakout_pressure,
        resistance_distance_pct=ctx.resistance_distance_pct,
        trigger_price=sig.trigger_price,
        movement_start_price=_movement_start_price(sig),
        volume_acceleration_1m=ctx.volume_acceleration_1m,
        volume_acceleration_slope=ctx.volume_acceleration_slope,
        rvol=ctx.rvol,
        rvol_same_time=ctx.rvol_same_time,
        trade_velocity_growth=ctx.trade_velocity_growth,
        dollar_volume_growth=ctx.dollar_volume_growth,
        persistence_minutes=sig.stage_progression.persistence_minutes,
    )


def real_price_jump_from_opportunity(sig: OpportunityNowSignal):
    ctx = context_from_opportunity_signal(sig)
    price_volume_response = ctx.price_volume_response
    entry_high = sig.entry_zone_high or sig.entry_zone
    if (
        price_volume_response < 0.35
        and sig.jump_qualified
        and sig.change_percent >= STAGE_EE_MIN_SESSION_CHANGE_PCT
        and entry_high > 0
        and sig.price >= entry_high * 0.992
    ):
        price_volume_response = max(price_volume_response, 0.35)
    return evaluate_real_price_jump(
        current_price=sig.price,
        change_pct=sig.change_percent,
        price_volume_response=price_volume_response,
        micro_higher_lows=ctx.micro_higher_lows,
        vwap_hold=ctx.vwap_hold,
        vwap_reclaim=ctx.vwap_reclaim,
        breakout_pressure=ctx.breakout_pressure or (45.0 if sig.detection_stage == "EXPLOSIVE" else 0.0),
        resistance_distance_pct=ctx.resistance_distance_pct,
        trigger_price=entry_high,
        movement_start_price=sig.entry_zone_low or sig.entry_zone,
        volume_acceleration_1m=sig.volume_acceleration,
        rvol=sig.rvol or sig.relative_volume,
        trade_velocity_growth=ctx.trade_velocity_growth,
        persistence_minutes=sig.consecutive_confirmations,
    )


def classify_jump_display_type(
    *,
    requested_type: str,
    real_jump_confirmed: bool,
    monitoring_worthy: bool,
) -> str:
    if requested_type == DISPLAY_STRONG_BUY_WATCH:
        return DISPLAY_STRONG_BUY_WATCH
    if requested_type == DISPLAY_JUMP_ALERT:
        if real_jump_confirmed:
            return DISPLAY_JUMP_ALERT
        if monitoring_worthy:
            return DISPLAY_STRONG_BUY_WATCH
        return DISPLAY_JUMP_ALERT
    if real_jump_confirmed:
        return DISPLAY_JUMP_ALERT
    if monitoring_worthy:
        return DISPLAY_STRONG_BUY_WATCH
    return requested_type


def display_sort_tier(display_type: str) -> int:
    if display_type == DISPLAY_JUMP_ALERT:
        return 0
    if display_type == DISPLAY_STRONG_BUY_WATCH:
        return 1
    return 2


def display_sort_key(sig: OpportunityNowSignal) -> tuple:
    return (
        display_sort_tier(sig.display_type),
        -sig.buy_pressure_score,
        -sig.confluence_count,
        -sig.score,
    )


def evaluate_premove_display(sig: PreMoveSignal) -> DisplayVerdict:
    if sig.display_confirmed and sig.display_type in (DISPLAY_STRONG_BUY_WATCH, DISPLAY_JUMP_ALERT):
        if _passes_freshness_gate(sig):
            ctx = context_from_premove(sig)
            jump = real_price_jump_from_premove(sig)
            dtype = classify_jump_display_type(
                requested_type=sig.display_type,
                real_jump_confirmed=jump.confirmed,
                monitoring_worthy=True,
            )
            return DisplayVerdict(
                show=True,
                display_type=dtype,
                buy_pressure_score=sig.buy_pressure_score or fast_filter_surge_rank(
                    sig.change_percent, _effective_rvol(ctx),
                ),
                confluence_count=sig.confluence_count,
                confluence_factors=list(sig.confluence_factors),
            )
        return DisplayVerdict(reject_reason=sig.display_reject_reason or "stale_or_invalid")

    if sig.status in _EXCLUDED_PREMOVE and not sig.display_confirmed:
        return DisplayVerdict(reject_reason=sig.status or "excluded")
    if sig.late_move.is_too_late and not sig.display_confirmed:
        return DisplayVerdict(reject_reason="late_move")
    if sig.change_percent <= 0:
        return DisplayVerdict(reject_reason="no_upward_move")
    if sig.rejection_reason in ("TOO_LATE_TO_CHASE", "LOW_LIQUIDITY") and sig.status != "EARLY_ENTRY":
        return DisplayVerdict(reject_reason=sig.rejection_reason or "rejected")

    ctx = context_from_premove(sig)
    confluence, factors = count_buy_pressure_confluence(ctx)
    surge = relative_surge_from_signal(sig)
    buy_score = fast_filter_surge_rank(sig.change_percent, _effective_rvol(ctx))

    lifecycle = ctx.stage_lifecycle
    jump = real_price_jump_from_premove(sig)
    if sig.status in QUALIFIED_JUMP_SIGNALS and sig.validated and not ctx.is_too_late:
        dtype = classify_jump_display_type(
            requested_type=DISPLAY_JUMP_ALERT,
            real_jump_confirmed=jump.confirmed,
            monitoring_worthy=True,
        )
        return DisplayVerdict(
            show=True,
            display_type=dtype,
            buy_pressure_score=buy_score,
            confluence_count=confluence,
            confluence_factors=factors,
        )

    if sig.status == "CONFIRMED_ENTRY" or lifecycle == "BREAKOUT_CONFIRMED":
        if surge and confluence >= max(4, STAGE_EE_MIN_CONFLUENCE - 1):
            return DisplayVerdict(
                show=True,
                display_type=DISPLAY_STRONG_BUY_WATCH,
                buy_pressure_score=buy_score,
                confluence_count=confluence,
                confluence_factors=factors,
            )

    if lifecycle not in _EARLY_STAGES and sig.status not in _EARLY_STAGES:
        return DisplayVerdict(reject_reason="not_early_stage")

    if not surge:
        return DisplayVerdict(reject_reason="no_relative_surge")

    if confluence < STAGE_EE_MIN_CONFLUENCE:
        return DisplayVerdict(reject_reason=f"confluence_{confluence}<{STAGE_EE_MIN_CONFLUENCE}")

    return DisplayVerdict(
        show=True,
        display_type=DISPLAY_STRONG_BUY_WATCH,
        buy_pressure_score=buy_score,
        confluence_count=confluence,
        confluence_factors=factors,
    )


def evaluate_jump_alert_display(sig: OpportunityNowSignal) -> DisplayVerdict:
    if not sig.jump_qualified or not sig.jump_alert_created:
        return DisplayVerdict(reject_reason="not_jump_qualified")
    if sig.late_entry_warning or sig.change_percent <= 0:
        return DisplayVerdict(reject_reason="late_or_flat")
    jump = real_price_jump_from_opportunity(sig)
    dtype = classify_jump_display_type(
        requested_type=DISPLAY_JUMP_ALERT,
        real_jump_confirmed=jump.confirmed,
        monitoring_worthy=True,
    )
    return DisplayVerdict(
        show=True,
        display_type=dtype,
        buy_pressure_score=sig.buy_pressure_score or sig.score,
        confluence_count=sig.confluence_count,
        confluence_factors=list(sig.confluence_factors),
    )


def evaluate_extended_gap_display(sig: OpportunityNowSignal) -> DisplayVerdict:
    if sig.late_entry_warning or sig.status == "CANCELLED":
        return DisplayVerdict(reject_reason="late_chase")
    if sig.extended_gap_pct <= 0 or sig.change_percent <= 0:
        return DisplayVerdict(reject_reason="no_gap")
    if sig.extended_gap_pct >= STAGE_EE_MAX_EXTENSION_PCT and not sig.has_confirmed_news:
        return DisplayVerdict(reject_reason="extended_without_catalyst")

    ctx = BuyPressureContext(
        change_percent=sig.extended_gap_pct,
        rvol=sig.relative_volume,
        breakout_pressure=50.0 if sig.detection_stage == "EXPLOSIVE" else 25.0,
        trade_velocity_growth=0.2 if sig.relative_volume >= STAGE_RVOL_MIN else 0.0,
        dollar_volume_growth=0.3 if sig.extended_volume > 50_000 else 0.0,
        liquidity_score=50.0 if sig.volume_status == "KNOWN" else 30.0,
        spread_pct=STAGE_EE_MAX_SPREAD_PCT,
        premove_status=sig.detection_stage,
        stage_lifecycle=sig.detection_stage,
    )
    confluence, factors = count_buy_pressure_confluence(ctx)
    surge = _has_relative_surge(ctx) or (
        sig.relative_volume >= STAGE_RVOL_MIN and sig.extended_gap_pct >= STAGE_EE_MIN_SESSION_CHANGE_PCT
    )

    if not surge:
        return DisplayVerdict(reject_reason="no_extended_surge")

    if sig.detection_stage == "EXPLOSIVE" and sig.has_confirmed_news:
        requested = DISPLAY_JUMP_ALERT
    elif sig.detection_stage in ("ACTIVE", "EXPLOSIVE", "WATCH"):
        requested = DISPLAY_STRONG_BUY_WATCH if sig.detection_stage != "EXPLOSIVE" else DISPLAY_JUMP_ALERT
    else:
        return DisplayVerdict(reject_reason="weak_stage")

    if confluence < max(3, STAGE_EE_MIN_CONFLUENCE - 2):
        return DisplayVerdict(reject_reason=f"extended_confluence_{confluence}")

    jump = evaluate_real_price_jump(
        current_price=sig.price,
        change_pct=sig.extended_gap_pct or sig.change_percent,
        price_volume_response=0.35 if sig.relative_volume >= STAGE_RVOL_MIN else 0.15,
        breakout_pressure=50.0 if sig.detection_stage == "EXPLOSIVE" else 25.0,
        resistance_distance_pct=STAGE_BREAKOUT_NEAR_PCT if sig.detection_stage == "EXPLOSIVE" else 99.0,
        movement_start_price=sig.previous_close,
        volume_acceleration_1m=sig.volume_acceleration,
        rvol=sig.relative_volume,
        trade_velocity_growth=0.2 if sig.relative_volume >= STAGE_RVOL_MIN else 0.0,
        dollar_volume_growth=0.3 if sig.extended_volume > 50_000 else 0.0,
        persistence_minutes=2 if sig.detection_stage == "EXPLOSIVE" else 0,
    )
    dtype = classify_jump_display_type(
        requested_type=requested,
        real_jump_confirmed=jump.confirmed,
        monitoring_worthy=True,
    )

    return DisplayVerdict(
        show=True,
        display_type=dtype,
        buy_pressure_score=fast_filter_surge_rank(sig.extended_gap_pct, sig.relative_volume),
        confluence_count=confluence,
        confluence_factors=factors,
    )


def apply_display_verdict(sig: OpportunityNowSignal, verdict: DisplayVerdict) -> OpportunityNowSignal:
    if not verdict.show:
        return sig
    data = sig.model_dump()
    data["display_type"] = verdict.display_type
    data["buy_pressure_score"] = round(verdict.buy_pressure_score, 2)
    data["confluence_count"] = verdict.confluence_count
    data["confluence_factors"] = verdict.confluence_factors
    if verdict.display_type == DISPLAY_JUMP_ALERT:
        data["status"] = "NOW"
        data["status_ar"] = "قفزة مؤكدة"
    elif verdict.display_type == DISPLAY_STRONG_BUY_WATCH:
        data["status"] = "WATCH"
        data["status_ar"] = "ضغط شراء قوي"
        data["opportunity_type"] = DISPLAY_STRONG_BUY_WATCH
    return OpportunityNowSignal(**data)
