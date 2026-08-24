"""Stage Progression Engine — evidence evolution over time, not snapshot thresholds."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from config import (
    PREMOVE_MIN_RRR,
    STAGE_BREAKOUT_NEAR_PCT,
    STAGE_DECAY_PER_MIN,
    STAGE_DECAY_START_MIN,
    STAGE_EE_MIN_CONFLUENCE,
    STAGE_EE_REQUIRE_TRIGGER_AND_RESISTANCE,
    STAGE_EE_CONFLUENCE_TOTAL,
    STAGE_EE_CORE_CONFLUENCE_MIN,
    STAGE_EE_MIN_SESSION_CHANGE_PCT,
    STAGE_EE_MAX_EXTENSION_PCT,
    STAGE_EE_MAX_RESISTANCE_DIST_PCT,
    STAGE_EE_MAX_SPREAD_PCT,
    STAGE_EE_MIN_LIQUIDITY,
    STAGE_EE_MIN_PRICE_HOLDING,
    STAGE_EE_MIN_PROGRESSION,
    STAGE_EE_MIN_RRR,
    STAGE_EE_MIN_RVOL,
    STAGE_EE_MIN_TRIGGER_READINESS,
    STAGE_EE_MOMENTUM_PERSISTENCE_MIN,
    STAGE_EE_PB_PERSISTENCE_MIN,
    STAGE_EE_PROGRESSION_TREND_MIN,
    STAGE_EW_MIN_PROGRESSION,
    STAGE_HC_MIN_PROGRESSION,
    STAGE_PB_MIN_PROGRESSION,
    STAGE_PERSISTENCE_2M,
    STAGE_PERSISTENCE_3M,
    STAGE_PERSISTENCE_5M,
    STAGE_REGRESSION_DROP,
    STAGE_RESISTANCE_CLOSE_PCT,
    STAGE_RESISTANCE_NEAR_PCT,
    STAGE_RVOL_MIN,
    STAGE_STALE_WATCH_MIN,
    STAGE_VOL_ACCEL_MIN,
    STAGE_VOL_ACCEL_STRONG,
)
from models.pre_move import PreMoveStatus
from models.pre_move_stage import (
    PreMoveStageProgressionMetrics,
    RollingStageState,
    StageLifecycle,
    StageSnapshot,
)

ET = ZoneInfo("America/New_York")

_STAGE_ORDER = {
    "DISCOVERED": 0,
    "EARLY_WATCH": 1,
    "PRE_BREAKOUT": 2,
    "EARLY_ENTRY": 3,
    "BREAKOUT_CONFIRMED": 4,
    "TOO_LATE_TO_CHASE": -1,
    "FAILED_SETUP": -2,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _norm_ratio(val: float, strong: float, *, cap: float = 3.0) -> float:
    if val <= 0:
        return 0.0
    return _clamp(val / strong * 100.0, 0.0, cap / strong * 100.0 if cap else 100.0)


def _effective_rvol(snap: StageSnapshot) -> float:
    if snap.rvol_same_time is not None and snap.rvol_same_time > 0:
        return snap.rvol_same_time
    return snap.rvol


def build_snapshot(
    *,
    timestamp: str,
    price: float,
    change_pct: float,
    pre_move_score: int,
    volume_acceleration_1m: float,
    volume_acceleration_3m: float,
    volume_acceleration_slope: float,
    rvol: float,
    rvol_same_time: float | None,
    dollar_volume_growth: float,
    trade_velocity: float | None,
    trade_velocity_growth: float | None,
    early_activity_score: float,
    compression_score: float,
    range_compression_3m: float,
    micro_higher_lows: bool,
    higher_lows_score: float,
    resistance_distance_pct: float,
    distance_to_breakout_pct: float,
    breakout_pressure: float,
    vwap_hold: bool,
    vwap_reclaim: bool,
    distance_from_vwap_pct: float,
    liquidity_score: float,
    spread_pct: float,
    price_volume_response: float,
    news_catalyst_score: float,
    risk_reward: float,
    trigger_price: float,
    late_guard: bool,
    failed_setup: bool,
    prior_peak_price: float = 0.0,
    base_price: float = 0.0,
    prior_lows: list[float] | None = None,
) -> StageSnapshot:
    """Build snapshot with derived price-holding score."""
    holding = 50.0
    if prior_peak_price > 0 and price > 0:
        retrace = (prior_peak_price - price) / prior_peak_price * 100.0
        holding = _clamp(100.0 - retrace * 25.0)
    elif change_pct > 0:
        holding = min(100.0, 40.0 + change_pct * 3.0)

    # Higher lows + shrinking pullbacks boost holding
    if prior_lows and len(prior_lows) >= 2:
        if all(prior_lows[i] <= prior_lows[i + 1] for i in range(len(prior_lows) - 1)):
            holding = _clamp(holding + 15.0)
        retrace_sizes = []
        for i in range(1, len(prior_lows)):
            if prior_lows[i - 1] > 0:
                retrace_sizes.append((prior_lows[i - 1] - prior_lows[i]) / prior_lows[i - 1] * 100.0)
        if len(retrace_sizes) >= 2 and retrace_sizes[-1] < retrace_sizes[-2]:
            holding = _clamp(holding + 10.0)

    if base_price > 0 and price > base_price:
        extension = (price - base_price) / base_price * 100.0
        if extension > STAGE_EE_MAX_EXTENSION_PCT * 0.7:
            holding = _clamp(holding - extension * 1.5)

    return StageSnapshot(
        timestamp=timestamp,
        price=price,
        change_pct=change_pct,
        pre_move_score=pre_move_score,
        volume_acceleration_1m=volume_acceleration_1m,
        volume_acceleration_3m=volume_acceleration_3m,
        volume_acceleration_slope=volume_acceleration_slope,
        rvol=rvol,
        rvol_same_time=rvol_same_time,
        dollar_volume_growth=dollar_volume_growth,
        trade_velocity=trade_velocity,
        trade_velocity_growth=trade_velocity_growth,
        early_activity_score=early_activity_score,
        compression_score=compression_score,
        range_compression_3m=range_compression_3m,
        micro_higher_lows=micro_higher_lows,
        higher_lows_score=higher_lows_score,
        resistance_distance_pct=resistance_distance_pct,
        distance_to_breakout_pct=distance_to_breakout_pct,
        breakout_pressure=breakout_pressure,
        vwap_hold=vwap_hold,
        vwap_reclaim=vwap_reclaim,
        distance_from_vwap_pct=distance_from_vwap_pct,
        liquidity_score=liquidity_score,
        spread_pct=spread_pct,
        price_volume_response=price_volume_response,
        price_holding_score=holding,
        news_catalyst_score=news_catalyst_score,
        risk_reward=risk_reward,
        trigger_price=trigger_price,
        late_guard=late_guard,
        failed_setup=failed_setup,
    )


def _score_volume(snap: StageSnapshot) -> float:
    a1 = _norm_ratio(snap.volume_acceleration_1m, STAGE_VOL_ACCEL_STRONG)
    a3 = _norm_ratio(snap.volume_acceleration_3m, STAGE_VOL_ACCEL_STRONG)
    slope = _norm_ratio(snap.volume_acceleration_slope, 1.15)
    rvol = _norm_ratio(_effective_rvol(snap), STAGE_RVOL_MIN)
    dv = _norm_ratio(max(0.0, snap.dollar_volume_growth), 0.5)
    return _clamp(a1 * 0.35 + a3 * 0.25 + slope * 0.15 + rvol * 0.15 + dv * 0.10)


def _score_trade_velocity(snap: StageSnapshot) -> float:
    if snap.trade_velocity is None:
        return 40.0
    base = _norm_ratio(snap.trade_velocity, 50.0)
    if snap.trade_velocity_growth is not None and snap.trade_velocity_growth > 0:
        base = _clamp(base + snap.trade_velocity_growth * 30.0)
    return base


def _score_structure(snap: StageSnapshot) -> float:
    hl = snap.higher_lows_score * 100.0 if snap.higher_lows_score else (70.0 if snap.micro_higher_lows else 20.0)
    comp = snap.compression_score * 100.0 if snap.compression_score else (
        60.0 if snap.range_compression_3m > 0 and snap.range_compression_3m < 0.85 else 25.0
    )
    return _clamp(hl * 0.55 + comp * 0.45)


def _score_resistance(snap: StageSnapshot) -> float:
    dist = snap.distance_to_breakout_pct if snap.distance_to_breakout_pct > 0 else snap.resistance_distance_pct
    if dist <= 0:
        return 100.0
    if dist <= STAGE_BREAKOUT_NEAR_PCT:
        return _clamp(100.0 - dist * 8.0)
    if dist <= STAGE_RESISTANCE_CLOSE_PCT:
        return _clamp(85.0 - dist * 5.0)
    if dist <= STAGE_RESISTANCE_NEAR_PCT:
        return _clamp(65.0 - dist * 3.0)
    return max(10.0, 40.0 - dist)


def _score_vwap(snap: StageSnapshot) -> float:
    if snap.vwap_reclaim:
        return 90.0
    if snap.vwap_hold:
        return 75.0
    if snap.distance_from_vwap_pct <= 1.0:
        return 60.0
    if snap.distance_from_vwap_pct <= 3.0:
        return 40.0
    return max(0.0, 30.0 - snap.distance_from_vwap_pct * 5.0)


def _score_liquidity(snap: StageSnapshot) -> float:
    liq = snap.liquidity_score
    spread_pen = max(0.0, (snap.spread_pct - 1.5) * 12.0)
    return _clamp(liq - spread_pen)


def _score_news(snap: StageSnapshot) -> float:
    return _clamp(snap.news_catalyst_score)


def _score_price_response(snap: StageSnapshot) -> float:
    pvr = snap.price_volume_response * 100.0 if snap.price_volume_response else 30.0
    return _clamp(pvr * 0.6 + snap.price_holding_score * 0.4)


def compute_stage_progression_score(
    snap: StageSnapshot,
    history: list[StageSnapshot],
) -> tuple[float, float, list[str]]:
    """Current evidence + trend vs T-3…T-1. Returns (score, trend_delta, factors)."""
    factors: list[str] = []

    vol = _score_volume(snap)
    trade = _score_trade_velocity(snap)
    struct = _score_structure(snap)
    resist = _score_resistance(snap)
    vwap = _score_vwap(snap)
    liq = _score_liquidity(snap)
    news = _score_news(snap)
    pvr = _score_price_response(snap)
    early = _clamp(snap.early_activity_score / 28.0 * 100.0 if snap.early_activity_score else 30.0)

    base = (
        vol * 0.14
        + trade * 0.06
        + struct * 0.10
        + resist * 0.12
        + vwap * 0.10
        + liq * 0.08
        + news * 0.04
        + pvr * 0.10
        + early * 0.12
        + _clamp(snap.breakout_pressure) * 0.04
        + (80.0 if snap.risk_reward >= PREMOVE_MIN_RRR else snap.risk_reward * 30.0) * 0.10
    )
    base = _clamp(base)

    if vol >= 55:
        factors.append("volume_accel")
    if _effective_rvol(snap) >= STAGE_RVOL_MIN:
        factors.append("rvol")
    if snap.trade_velocity is not None and (snap.trade_velocity_growth or 0) > 0.15:
        factors.append("trade_velocity")
    if snap.micro_higher_lows or snap.higher_lows_score >= 0.4:
        factors.append("higher_lows")
    if snap.compression_score >= 0.35 or (0 < snap.range_compression_3m < 0.85):
        factors.append("compression")
    if resist >= 60:
        factors.append("near_resistance")
    if vwap >= 70:
        factors.append("vwap_support")
    if liq >= 50:
        factors.append("liquidity")
    if news >= 40:
        factors.append("news_catalyst")
    if pvr >= 55:
        factors.append("price_volume_response")

    trend = 0.0
    if len(history) >= 2:
        prev = history[-1]
        prev_vol = _score_volume(prev)
        curr_vol = vol
        trend = (curr_vol - prev_vol) * 0.4
        trend += (snap.price - prev.price) / max(prev.price, 0.01) * 100.0 * 0.15
        trend += (_effective_rvol(snap) - _effective_rvol(prev)) * 8.0

    # Trend bonus: improving evidence over T-3 window
    if len(history) >= 3:
        t3 = history[-3]
        t1 = snap
        rvol_delta = _effective_rvol(t1) - _effective_rvol(t3)
        vol_delta = t1.volume_acceleration_1m - t3.volume_acceleration_1m
        price_delta = t1.price - t3.price
        if rvol_delta > 0.2:
            trend += 4.0
            factors.append("rvol_rising")
        if vol_delta > 0.1:
            trend += 4.0
            factors.append("vol_sustained")
        if price_delta >= 0:
            trend += 3.0
            factors.append("price_holding")
        resist_t3 = t3.distance_to_breakout_pct or t3.resistance_distance_pct
        resist_now = snap.distance_to_breakout_pct or snap.resistance_distance_pct
        if resist_t3 > 0 and resist_now > 0 and resist_now < resist_t3:
            trend += 5.0
            factors.append("approaching_resistance")

    score = _clamp(base + trend * 0.35)
    return round(score, 1), round(trend, 2), factors


def compute_momentum_persistence(history: list[StageSnapshot]) -> tuple[float, int]:
    """How many consecutive minutes activity persists with price holding."""
    if not history:
        return 0.0, 0

    streak = 0
    peak_price = history[0].price
    for snap in reversed(history):
        peak_price = max(peak_price, snap.price)
        retrace = (peak_price - snap.price) / peak_price * 100.0 if peak_price > 0 else 0.0

        vol_ok = (
            snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
            or snap.volume_acceleration_3m >= STAGE_VOL_ACCEL_MIN
            or snap.volume_acceleration_slope >= 1.05
            or _effective_rvol(snap) >= STAGE_RVOL_MIN
        )
        price_ok = retrace <= 1.2 or snap.price_holding_score >= 45.0

        if vol_ok and price_ok:
            streak += 1
        else:
            break

    if streak >= STAGE_PERSISTENCE_5M:
        return 100.0, streak
    if streak >= STAGE_PERSISTENCE_3M:
        return 70.0, streak
    if streak >= STAGE_PERSISTENCE_2M:
        return 45.0, streak
    return max(0.0, streak * 18.0), streak


def compute_stage_signal_decay(
    *,
    current_stage: StageLifecycle,
    minutes_in_stage: float,
    progression_score: float,
    peak_progression_score: float,
) -> float:
    if current_stage not in ("EARLY_WATCH", "PRE_BREAKOUT"):
        return 0.0
    if minutes_in_stage < STAGE_DECAY_START_MIN:
        return 0.0
    extra = minutes_in_stage - STAGE_DECAY_START_MIN
    decay = extra * STAGE_DECAY_PER_MIN
    if progression_score < peak_progression_score - 10:
        decay += (peak_progression_score - progression_score) * 0.15
    if current_stage == "EARLY_WATCH" and minutes_in_stage >= STAGE_STALE_WATCH_MIN:
        decay += (minutes_in_stage - STAGE_STALE_WATCH_MIN) * 1.5
    return round(decay, 2)


def _early_watch_signals(snap: StageSnapshot) -> int:
    count = 0
    if snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_STRONG or snap.volume_acceleration_slope >= 1.1:
        count += 1
    if _effective_rvol(snap) >= STAGE_RVOL_MIN:
        count += 1
    if snap.trade_velocity_growth is not None and snap.trade_velocity_growth >= 0.15:
        count += 1
    elif snap.trade_velocity is not None and snap.trade_velocity >= 30:
        count += 1
    if snap.micro_higher_lows or snap.higher_lows_score >= 0.35:
        count += 1
    if snap.compression_score >= 0.3 or (0 < snap.range_compression_3m < 0.88):
        count += 1
    if snap.news_catalyst_score >= 40:
        count += 1
    if snap.early_activity_score >= 12:
        count += 1
    return count


def _burst_pre_breakout(
    snap: StageSnapshot,
    progression_score: float,
    ew_signals: int,
    trend: float,
) -> bool:
    """High-confluence first-minute escalation — generic, not symbol-specific."""
    if progression_score < STAGE_PB_MIN_PROGRESSION + 12:
        return False
    if ew_signals < 3:
        return False
    resist = _score_resistance(snap)
    if resist < 50 and snap.breakout_pressure < 40:
        return False
    vwap_ok = snap.vwap_hold or snap.vwap_reclaim or snap.distance_from_vwap_pct <= 3.5
    vol_ok = snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN or snap.volume_acceleration_slope >= 1.08
    return vwap_ok and vol_ok and snap.liquidity_score >= 35 and trend >= -2


def _pre_breakout_ready(
    snap: StageSnapshot,
    progression_score: float,
    persistence_score: int,
    trend: float,
) -> bool:
    if progression_score < STAGE_PB_MIN_PROGRESSION:
        return False
    if persistence_score < STAGE_PERSISTENCE_2M:
        return False

    vol_ok = (
        snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
        or snap.volume_acceleration_3m >= STAGE_VOL_ACCEL_MIN
        or snap.volume_acceleration_slope >= 1.05
    )
    near = (
        (snap.distance_to_breakout_pct > 0 and snap.distance_to_breakout_pct <= STAGE_RESISTANCE_NEAR_PCT)
        or (snap.resistance_distance_pct > 0 and snap.resistance_distance_pct <= STAGE_RESISTANCE_NEAR_PCT)
        or snap.breakout_pressure >= 40
    )
    vwap_ok = snap.vwap_hold or snap.vwap_reclaim or snap.distance_from_vwap_pct <= 2.5
    liq_ok = snap.liquidity_score >= 35 and snap.spread_pct <= 4.0
    rr_ok = snap.risk_reward >= 0.9

    core = vol_ok and near and vwap_ok and liq_ok and rr_ok
    momentum_path = trend >= 2.0 and persistence_score >= STAGE_PERSISTENCE_2M and progression_score >= STAGE_PB_MIN_PROGRESSION + 8
    return core or momentum_path


def _distance_to_trigger(snap: StageSnapshot) -> float:
    """Percent distance to trigger/resistance — lower is closer."""
    if snap.trigger_price > 0 and snap.price > 0:
        if snap.price >= snap.trigger_price:
            return 0.0
        return (snap.trigger_price - snap.price) / snap.price * 100.0
    dist = snap.distance_to_breakout_pct if snap.distance_to_breakout_pct > 0 else snap.resistance_distance_pct
    return max(0.0, dist)


def _vwap_support(snap: StageSnapshot) -> bool:
    return snap.vwap_hold or snap.vwap_reclaim or snap.distance_from_vwap_pct <= 2.0


def _resistance_approaching(history: list[StageSnapshot], snap: StageSnapshot) -> bool:
    """Resistance distance shrinking over recent windows (5% → 3% → 1.5%)."""
    dist_now = _distance_to_trigger(snap)
    if dist_now <= 0:
        return False
    if dist_now <= STAGE_EE_MAX_RESISTANCE_DIST_PCT:
        return True
    if len(history) < 2:
        return dist_now <= STAGE_BREAKOUT_NEAR_PCT

    dists = [_distance_to_trigger(h) for h in history[-3:]] + [dist_now]
    dists = [d for d in dists if d > 0]
    if len(dists) < 2:
        return dist_now <= STAGE_BREAKOUT_NEAR_PCT

    shrinking = all(dists[i] >= dists[i + 1] for i in range(len(dists) - 1))
    if shrinking and dist_now <= STAGE_BREAKOUT_NEAR_PCT:
        return True
    if len(dists) >= 3 and dists[0] - dist_now >= 1.5:
        return True
    return dist_now <= STAGE_RESISTANCE_CLOSE_PCT and dists[-2] > dist_now


def _pb_quality_window(snap: StageSnapshot) -> bool:
    """Single evaluation window qualifies as sustained PRE_BREAKOUT evidence."""
    vol_ok = (
        snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
        or snap.volume_acceleration_3m >= STAGE_VOL_ACCEL_MIN
        or snap.volume_acceleration_slope >= 1.05
    )
    vwap_ok = snap.vwap_hold or snap.vwap_reclaim or snap.distance_from_vwap_pct <= 2.5
    liq_ok = snap.liquidity_score >= 35 and snap.spread_pct <= 4.0
    dist = _distance_to_trigger(snap)
    near = dist <= STAGE_RESISTANCE_NEAR_PCT or snap.breakout_pressure >= 40
    return vol_ok and vwap_ok and liq_ok and near


def _update_pb_persistence(state: RollingStageState, snap: StageSnapshot) -> int:
    if state.current_stage == "PRE_BREAKOUT" and _pb_quality_window(snap):
        state.pb_consecutive_windows += 1
    elif _pb_quality_window(snap):
        state.pb_consecutive_windows = max(state.pb_consecutive_windows, 1)
    else:
        state.pb_consecutive_windows = 0
    return state.pb_consecutive_windows


def compute_trigger_readiness_score(
    snap: StageSnapshot,
    history: list[StageSnapshot],
    *,
    persist_min: int,
    move_from_base_pct: float,
) -> float:
    """Composite readiness for EARLY_ENTRY before full breakout."""
    dist = _distance_to_trigger(snap)
    if dist <= 0:
        return 0.0  # already broken out — not EE territory

    # Resistance proximity (25%)
    if dist <= STAGE_EE_MAX_RESISTANCE_DIST_PCT:
        resist_pts = 100.0 - dist * 15.0
    elif dist <= STAGE_BREAKOUT_NEAR_PCT:
        resist_pts = 75.0 - dist * 8.0
    elif dist <= STAGE_RESISTANCE_CLOSE_PCT:
        resist_pts = 55.0 - dist * 5.0
    else:
        resist_pts = max(10.0, 40.0 - dist * 2.0)

    # Volume (20%)
    vol_pts = _score_volume(snap)
    if snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_STRONG:
        vol_pts = _clamp(vol_pts + 10.0)

    # Persistence (15%)
    persist_pts = _clamp(persist_min / STAGE_PERSISTENCE_3M * 100.0)

    # Price holding (20%) — strong weight
    hold_pts = snap.price_holding_score
    if snap.micro_higher_lows or snap.higher_lows_score >= 0.4:
        hold_pts = _clamp(hold_pts + 12.0)

    # Spread + liquidity (10%)
    liq_pts = _score_liquidity(snap)

    # VWAP (10%)
    vwap_pts = _score_vwap(snap)

    # Higher lows / structure (10%)
    struct_pts = _score_structure(snap)

    # Penalty if too extended from base
    ext_pen = 0.0
    if move_from_base_pct > STAGE_EE_MAX_EXTENSION_PCT * 0.5:
        ext_pen = (move_from_base_pct - STAGE_EE_MAX_EXTENSION_PCT * 0.5) * 3.0

    # Bonus if resistance approaching
    approach_bonus = 8.0 if _resistance_approaching(history, snap) else 0.0

    raw = (
        resist_pts * 0.25
        + vol_pts * 0.20
        + persist_pts * 0.15
        + hold_pts * 0.20
        + liq_pts * 0.05
        + vwap_pts * 0.10
        + struct_pts * 0.05
        + approach_bonus
        - ext_pen
    )
    return round(_clamp(raw), 1)


def _vol_accel_label(snap: StageSnapshot) -> str:
    if snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_STRONG:
        return "STRONG"
    if snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN:
        return "PASS"
    return "WEAK"


def evaluate_early_entry_gate(
    state: RollingStageState,
    snap: StageSnapshot,
    history: list[StageSnapshot],
    *,
    effective_score: float,
    persist_min: int,
    trend: float,
    regress: list[str],
    bars=None,
    stop_loss: float = 0.0,
    tp1: float = 0.0,
    has_fresh_news: bool = False,
    news_catalyst_score: float = 0.0,
    quality_gate_enabled: bool = True,
    quality_thresholds=None,
    confluence_weights=None,
) -> tuple[bool, float, list[str], list[str], object | None, bool]:
    """
    Independent EARLY_ENTRY gate — returns (approved, readiness, confidence, blocks, quality, timing_passed).
    """
    from analysis.pre_move_early_entry_quality import evaluate_early_entry_quality_gate

    confidence: list[str] = []
    blocks: list[str] = []

    def _fail(readiness_val: float = 0.0):
        return False, readiness_val, confidence, blocks, None, False

    if state.current_stage != "PRE_BREAKOUT":
        blocks.append("not_in_pre_breakout")
        return _fail()

    if snap.late_guard:
        blocks.append("late_move_guard")
        return _fail()

    if snap.failed_setup:
        blocks.append("failed_setup")
        return _fail()

    if _breakout_confirmed(snap):
        blocks.append("already_breakout")
        return _fail()

    base = state.base_price or snap.price
    move_from_base = (snap.price - base) / base * 100.0 if base > 0 else 0.0
    if move_from_base >= STAGE_EE_MAX_EXTENSION_PCT:
        blocks.append(f"extension_{move_from_base:.1f}pct")
        return _fail()

    if regress:
        blocks.append(f"regression:{','.join(regress[:2])}")
        return _fail()

    readiness = compute_trigger_readiness_score(
        snap, history, persist_min=persist_min, move_from_base_pct=move_from_base,
    )
    dist = _distance_to_trigger(snap)
    approaching = _resistance_approaching(history, snap)
    pb_windows = state.pb_consecutive_windows

    # --- Hard safety blocks (non-negotiable) ---
    if pb_windows < STAGE_EE_PB_PERSISTENCE_MIN:
        blocks.append(f"pb_persistence_{pb_windows}<{STAGE_EE_PB_PERSISTENCE_MIN}")

    if persist_min < STAGE_EE_MOMENTUM_PERSISTENCE_MIN:
        blocks.append(f"momentum_persist_{persist_min}<{STAGE_EE_MOMENTUM_PERSISTENCE_MIN}")

    if dist > STAGE_EE_MAX_RESISTANCE_DIST_PCT:
        blocks.append(f"resistance_dist_{dist:.1f}%>{STAGE_EE_MAX_RESISTANCE_DIST_PCT}%")

    if snap.risk_reward < STAGE_EE_MIN_RRR:
        blocks.append(f"rrr_{snap.risk_reward:.1f}<{STAGE_EE_MIN_RRR:.1f}")

    if snap.liquidity_score < STAGE_EE_MIN_LIQUIDITY:
        blocks.append(f"liquidity_{snap.liquidity_score:.0f}<{STAGE_EE_MIN_LIQUIDITY:.0f}")

    if snap.spread_pct > STAGE_EE_MAX_SPREAD_PCT:
        blocks.append(f"spread_{snap.spread_pct:.1f}%>{STAGE_EE_MAX_SPREAD_PCT}%")

    if blocks:
        return _fail(readiness)

    # --- Confluence 5/7 (timing gate — quality scored separately) ---
    resist_ok = approaching or dist <= STAGE_EE_MAX_RESISTANCE_DIST_PCT * 0.85
    confluence: list[tuple[str, bool]] = [
        ("trigger_readiness", readiness >= STAGE_EE_MIN_TRIGGER_READINESS),
        ("volume_sustained", (
            snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
            or snap.volume_acceleration_3m >= STAGE_VOL_ACCEL_MIN
            or snap.volume_acceleration_slope >= 1.05
            or _effective_rvol(snap) >= STAGE_EE_MIN_RVOL
        )),
        ("vwap_support", _vwap_support(snap)),
        ("price_holding", (
            snap.micro_higher_lows
            or snap.higher_lows_score >= 0.35
            or snap.price_holding_score >= STAGE_EE_MIN_PRICE_HOLDING
        )),
        ("resistance_close", resist_ok),
        ("progression_rising", (
            effective_score >= STAGE_EE_MIN_PROGRESSION - 4
            and trend >= STAGE_EE_PROGRESSION_TREND_MIN
        )),
        ("absorption", snap.price_volume_response >= 0.2 or snap.price_holding_score >= STAGE_EE_MIN_PRICE_HOLDING),
    ]

    passed = sum(1 for _, ok in confluence if ok)
    failed_factors = [name for name, ok in confluence if not ok]

    if passed < STAGE_EE_MIN_CONFLUENCE:
        blocks.append(f"confluence_{passed}/{STAGE_EE_CONFLUENCE_TOTAL}<{STAGE_EE_MIN_CONFLUENCE}")
        blocks.extend(f"missing:{f}" for f in failed_factors[:4])
        return _fail(readiness)

    # Timing gate passed — quality is optional layer
    rvol = _effective_rvol(snap)
    confidence.append(f"Persistence: PASS ({persist_min}m, PB windows {pb_windows})")
    confidence.append(f"Confluence: {passed}/{STAGE_EE_CONFLUENCE_TOTAL}")
    confidence.append(f"Volume Acceleration: {_vol_accel_label(snap)} ({snap.volume_acceleration_1m:.1f}x)")
    confidence.append(f"RVOL: {rvol:.1f}x")
    confidence.append(f"Resistance Distance: {dist:.1f}%")
    if snap.vwap_reclaim:
        confidence.append("VWAP: RECLAIM")
    elif snap.vwap_hold:
        confidence.append("VWAP: HOLD")
    elif snap.distance_from_vwap_pct <= 2.0:
        confidence.append(f"VWAP: NEAR ({snap.distance_from_vwap_pct:.1f}%)")
    confidence.append(f"Higher Lows: {'YES' if snap.micro_higher_lows or snap.higher_lows_score >= 0.35 else 'NO'}")
    confidence.append(f"Price Holding: {snap.price_holding_score:.0f}")
    confidence.append(f"Liquidity: PASS ({snap.liquidity_score:.0f})")
    confidence.append(f"Spread: PASS ({snap.spread_pct:.1f}%)")
    confidence.append(f"R:R: {snap.risk_reward:.1f}")
    confidence.append("Late Guard: CLEAR")
    confidence.append(f"Trigger Readiness: {readiness:.0f}")
    confidence.append(f"Move From Base: {move_from_base:.1f}%")
    if approaching:
        confidence.append("Resistance: APPROACHING")

    if not quality_gate_enabled:
        return True, readiness, confidence, blocks, None, True

    # --- Quality gate (precision layer — no timing delay) ---
    bar_df = bars if isinstance(bars, pd.DataFrame) else pd.DataFrame()
    quality = evaluate_early_entry_quality_gate(
        snap,
        history,
        bar_df,
        stop_loss=stop_loss,
        tp1=tp1,
        trigger_price=snap.trigger_price,
        persist_min=persist_min,
        has_fresh_news=has_fresh_news,
        news_catalyst_score=news_catalyst_score or snap.news_catalyst_score,
        thresholds=quality_thresholds,
        weights=confluence_weights,
    )
    if not quality.quality_gate_passed:
        blocks.extend(quality.block_reasons)
        return False, readiness, confidence, blocks, quality, True

    confidence.extend(quality.quality_factors)
    return True, readiness, confidence, blocks, quality, True


def _early_entry_ready(
    state: RollingStageState,
    snap: StageSnapshot,
    history: list[StageSnapshot],
    *,
    effective_score: float,
    persist_min: int,
    trend: float,
    regress: list[str],
    bars=None,
    stop_loss: float = 0.0,
    tp1: float = 0.0,
    has_fresh_news: bool = False,
    news_catalyst_score: float = 0.0,
    quality_gate_enabled: bool = True,
    quality_thresholds=None,
    confluence_weights=None,
) -> tuple[bool, float, list[str], list[str], object | None, bool]:
    """Wrapper — delegates to independent EE gate + quality layer."""
    return evaluate_early_entry_gate(
        state, snap, history,
        effective_score=effective_score,
        persist_min=persist_min,
        trend=trend,
        regress=regress,
        bars=bars,
        stop_loss=stop_loss,
        tp1=tp1,
        has_fresh_news=has_fresh_news,
        news_catalyst_score=news_catalyst_score,
        quality_gate_enabled=quality_gate_enabled,
        quality_thresholds=quality_thresholds,
        confluence_weights=confluence_weights,
    )


def _breakout_confirmed(snap: StageSnapshot) -> bool:
    if snap.trigger_price > 0 and snap.price >= snap.trigger_price * 0.998:
        return True
    if snap.distance_to_breakout_pct <= 0:
        return True
    return False


def _regression_signals(snap: StageSnapshot, history: list[StageSnapshot]) -> list[str]:
    signals: list[str] = []
    if len(history) >= 1:
        prev = history[-1]
        if prev.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN and snap.volume_acceleration_1m < 0.95:
            signals.append("volume_faded")
        if prev.vwap_hold and not snap.vwap_hold and not snap.vwap_reclaim:
            signals.append("lost_vwap")
        if prev.micro_higher_lows and not snap.micro_higher_lows and snap.higher_lows_score < 0.3:
            signals.append("higher_lows_broken")
        if snap.spread_pct > prev.spread_pct + 1.5 and snap.spread_pct > 3.5:
            signals.append("spread_widened")
        if prev.liquidity_score >= 45 and snap.liquidity_score < 35:
            signals.append("liquidity_dropped")
    if snap.failed_setup:
        signals.append("failed_setup")
    return signals


def evaluate_stage_transition(
    state: RollingStageState,
    snap: StageSnapshot,
    *,
    bars=None,
    stop_loss: float = 0.0,
    tp1: float = 0.0,
    has_fresh_news: bool = False,
    news_catalyst_score: float = 0.0,
    quality_gate_enabled: bool = True,
    quality_thresholds=None,
    confluence_weights=None,
) -> tuple[StageLifecycle, PreMoveStageProgressionMetrics]:
    """Determine next lifecycle stage from rolling evidence."""
    history = state.history()
    all_snaps = history + [snap]
    prog_score, trend, factors = compute_stage_progression_score(snap, history)
    persist_score, persist_min = compute_momentum_persistence(all_snaps)

    peak_prog = max(state.peak_progression_score, prog_score)
    minutes_in = state.minutes_in_stage + 1.0 if state.stage_entered_at else 0.0
    decay = compute_stage_signal_decay(
        current_stage=state.current_stage,
        minutes_in_stage=minutes_in,
        progression_score=prog_score,
        peak_progression_score=peak_prog,
    )
    effective_score = max(0.0, prog_score - decay)

    metrics = PreMoveStageProgressionMetrics(
        previous_lifecycle=state.current_stage,
        stage_progression_score=effective_score,
        momentum_persistence_score=persist_score,
        persistence_minutes=persist_min,
        signal_decay=decay,
        progression_trend=trend,
        evidence_factors=factors,
        snapshot_count=len(all_snaps),
    )

    # Late guard always wins
    if snap.late_guard:
        metrics.stage_lifecycle = "TOO_LATE_TO_CHASE"
        metrics.regression_signals = ["late_move_guard"]
        return "TOO_LATE_TO_CHASE", metrics

    regress = _regression_signals(snap, history)
    metrics.regression_signals = regress

    base = state.base_price or (history[0].price if history else snap.price)
    if state.base_price <= 0 and base > 0:
        state.base_price = base
    move_from_base = (snap.price - state.base_price) / state.base_price * 100.0 if state.base_price > 0 else 0.0
    approaching = _resistance_approaching(history, snap)
    pb_windows = state.pb_consecutive_windows
    if state.current_stage == "PRE_BREAKOUT":
        pb_windows = _update_pb_persistence(state, snap)

    readiness = compute_trigger_readiness_score(
        snap, history, persist_min=persist_min, move_from_base_pct=move_from_base,
    )
    metrics.trigger_readiness_score = readiness
    metrics.move_from_base_pct = round(move_from_base, 2)
    metrics.pb_persistence_windows = pb_windows
    metrics.resistance_approaching = approaching

    if snap.failed_setup or (len(regress) >= 3 and state.current_stage in ("PRE_BREAKOUT", "EARLY_ENTRY")):
        metrics.stage_lifecycle = "FAILED_SETUP"
        return "FAILED_SETUP", metrics

    if peak_prog - effective_score >= STAGE_REGRESSION_DROP and state.current_stage in (
        "PRE_BREAKOUT", "EARLY_ENTRY", "EARLY_WATCH",
    ):
        if snap.failed_setup or len(regress) >= 2:
            metrics.stage_lifecycle = "FAILED_SETUP"
            return "FAILED_SETUP", metrics

    # Breakout confirmed — must come before EE escalation if already broken out
    if _breakout_confirmed(snap) and state.current_stage in ("PRE_BREAKOUT", "EARLY_ENTRY", "EARLY_WATCH"):
        metrics.stage_lifecycle = "BREAKOUT_CONFIRMED"
        metrics.escalation_ready = True
        return "BREAKOUT_CONFIRMED", metrics

    current = state.current_stage
    ew_signals = _early_watch_signals(snap)

    # Regression down — block EE path
    if len(regress) >= 2 and current in ("PRE_BREAKOUT", "EARLY_ENTRY"):
        metrics.stage_lifecycle = "EARLY_WATCH"
        metrics.ee_block_reasons = regress
        return "EARLY_WATCH", metrics
    if len(regress) >= 1 and current == "PRE_BREAKOUT" and effective_score < STAGE_PB_MIN_PROGRESSION - 8:
        metrics.stage_lifecycle = "EARLY_WATCH"
        return "EARLY_WATCH", metrics
    if decay >= 12 and current == "EARLY_WATCH":
        metrics.stage_lifecycle = "FAILED_SETUP"
        return "FAILED_SETUP", metrics

    # Escalation (never skip stages)
    target = current

    if current in ("DISCOVERED",):
        if ew_signals >= 2 and effective_score >= STAGE_EW_MIN_PROGRESSION:
            target = "EARLY_WATCH"
            metrics.escalation_ready = True

    elif current == "EARLY_WATCH":
        if _pre_breakout_ready(snap, effective_score, persist_min, trend):
            target = "PRE_BREAKOUT"
            metrics.escalation_ready = True
        elif _burst_pre_breakout(snap, effective_score, ew_signals, trend):
            target = "PRE_BREAKOUT"
            metrics.escalation_ready = True
        elif effective_score >= STAGE_EW_MIN_PROGRESSION + 15 and persist_min >= STAGE_PERSISTENCE_2M and trend >= 3:
            target = "PRE_BREAKOUT"
            metrics.escalation_ready = True

    elif current == "PRE_BREAKOUT":
        ee_ok, readiness, ee_conf, ee_blocks, ee_quality, timing_passed = _early_entry_ready(
            state, snap, history,
            effective_score=effective_score,
            persist_min=persist_min,
            trend=trend,
            regress=regress,
            bars=bars,
            stop_loss=stop_loss,
            tp1=tp1,
            has_fresh_news=has_fresh_news,
            news_catalyst_score=news_catalyst_score,
            quality_gate_enabled=quality_gate_enabled,
            quality_thresholds=quality_thresholds,
            confluence_weights=confluence_weights,
        )
        metrics.trigger_readiness_score = readiness
        metrics.ee_confidence = ee_conf
        metrics.ee_block_reasons = ee_blocks
        metrics.ee_timing_gate_passed = timing_passed
        if ee_quality is not None:
            metrics.ee_confluence_quality = ee_quality.confluence_quality_score
            metrics.ee_quality_score = ee_quality.confluence_quality_score
            metrics.ee_rejection_score = ee_quality.rejection_score
            metrics.ee_volume_efficiency = ee_quality.volume_efficiency_score
            metrics.ee_breakout_failure_risk = ee_quality.breakout_failure_risk
            metrics.ee_entry_location = ee_quality.entry_location_score
            metrics.ee_spread_stability = ee_quality.spread_stability
            metrics.ee_liquidity_consistency = ee_quality.liquidity_consistency
            metrics.ee_stop_distance_pct = ee_quality.stop_distance_pct
            metrics.ee_price_holding = ee_quality.price_holding_score
            metrics.ee_catalyst_confirmed = ee_quality.catalyst_confirmed
            metrics.ee_quality_factors = ee_quality.quality_factors
            metrics.ee_quality_blocks = ee_quality.block_reasons
        if ee_ok:
            target = "EARLY_ENTRY"
            metrics.escalation_ready = True
            metrics.ee_gate_passed = True

    elif current == "EARLY_ENTRY":
        if _breakout_confirmed(snap):
            target = "BREAKOUT_CONFIRMED"
        else:
            target = "EARLY_ENTRY"

    elif current == "BREAKOUT_CONFIRMED":
        target = "BREAKOUT_CONFIRMED"

    elif current in ("FAILED_SETUP", "TOO_LATE_TO_CHASE"):
        target = current

    # Fresh discovery path (no prior stage)
    if current == "DISCOVERED" and target == "DISCOVERED":
        if ew_signals >= 2 and effective_score >= STAGE_EW_MIN_PROGRESSION:
            target = "EARLY_WATCH"
        elif ew_signals >= 3:
            target = "EARLY_WATCH"

    # Allow jump from DISCOVERED directly if very strong sustained setup
    if current == "DISCOVERED" and persist_min >= STAGE_PERSISTENCE_3M and effective_score >= STAGE_PB_MIN_PROGRESSION + 5:
        if _pre_breakout_ready(snap, effective_score, persist_min, trend):
            target = "PRE_BREAKOUT"

    metrics.stage_lifecycle = target
    return target, metrics


def lifecycle_to_status(
    lifecycle: StageLifecycle,
    *,
    progression_score: float,
    persistence_minutes: int,
) -> PreMoveStatus:
    """Map internal lifecycle to display status."""
    if lifecycle == "TOO_LATE_TO_CHASE":
        return "TOO_LATE_TO_CHASE"
    if lifecycle == "FAILED_SETUP":
        return "FAILED_SETUP"
    if lifecycle == "BREAKOUT_CONFIRMED":
        return "CONFIRMED_ENTRY"
    if lifecycle == "EARLY_ENTRY":
        if progression_score >= STAGE_HC_MIN_PROGRESSION and persistence_minutes >= STAGE_PERSISTENCE_5M:
            return "HIGH_CONVICTION_EARLY"
        return "EARLY_ENTRY"
    if lifecycle == "PRE_BREAKOUT":
        return "PRE_BREAKOUT"
    if lifecycle == "EARLY_WATCH":
        return "EARLY_WATCH"
    return "NO_SETUP"


def stage_rank_for_sort(
    lifecycle: StageLifecycle,
    progression_score: float,
    persistence_score: float,
    *,
    late_guard: bool,
) -> float:
    """Composite rank for best-opportunities — not raw % change."""
    if late_guard:
        return -100.0
    base = {
        "BREAKOUT_CONFIRMED": 500,
        "EARLY_ENTRY": 400,
        "PRE_BREAKOUT": 300,
        "EARLY_WATCH": 200,
        "DISCOVERED": 50,
        "FAILED_SETUP": -50,
        "TOO_LATE_TO_CHASE": -100,
    }.get(lifecycle, 0)
    return base + progression_score * 0.8 + persistence_score * 0.3


def parse_minutes_between(ts_a: str, ts_b: str) -> float:
    try:
        a = datetime.fromisoformat(ts_a.replace("Z", "+00:00"))
        b = datetime.fromisoformat(ts_b.replace("Z", "+00:00"))
        return abs((b - a).total_seconds()) / 60.0
    except Exception:
        return 1.0
