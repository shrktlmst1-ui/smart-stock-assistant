"""Early upward surge — relative activity spike before large % move."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from config import (
    PREMOVE_MIN_LIQUIDITY_SCORE,
    REAL_JUMP_ABSOLUTE_MAX_SPREAD_PCT,
    REAL_JUMP_ABSORPTION_LOOKBACK_BARS,
    REAL_JUMP_ABSORPTION_RANGE_PCT,
    REAL_JUMP_CONFLUENCE_SPREAD_CAP_PCT,
    REAL_JUMP_HIGH_RVOL_ABSORPTION,
    REAL_JUMP_NEAR_PEAK_TOLERANCE_PCT,
    REAL_JUMP_POST_PEAK_MIN_BELOW_PCT,
    REAL_JUMP_PRICE_RESPONSE_MIN_TICKS,
    REAL_JUMP_PRIOR_RANGE_BLOCK_PCT,
    REAL_JUMP_WAVE_END_CONFIRM_TICKS,
    REAL_JUMP_WAVE_END_SIGNALS_REQUIRED,
    STAGE_BREAKOUT_NEAR_PCT,
    STAGE_EE_MAX_EXTENSION_PCT,
    STAGE_EE_MAX_SPREAD_PCT,
    STAGE_EE_MIN_CONFLUENCE,
    STAGE_EE_MIN_PROGRESSION,
    STAGE_EE_MIN_RVOL,
    STAGE_EE_MIN_SESSION_CHANGE_PCT,
    STAGE_RVOL_MIN,
    STAGE_VOL_ACCEL_MIN,
    STAGE_VOL_ACCEL_STRONG,
)
from analysis.real_jump_confluence import (
    CONFLUENCE_PASS_THRESHOLD,
    RealJumpBonusContext,
    compute_explosion_confluence,
    near_psychological_level,
)
from models.pre_move import PreMoveSignal
from models.pre_move_stage import StageSnapshot

DISPLAY_STRONG_BUY_WATCH = "STRONG_BUY_WATCH"
DISPLAY_JUMP_ALERT = "JUMP_ALERT"
DISPLAY_REAL_JUMP_ALERT = "REAL_JUMP_ALERT"


@dataclass
class FastUpwardVerdict:
    qualified: bool = False
    display_type: str = ""
    confluence_count: int = 0
    confluence_factors: list[str] = field(default_factory=list)
    buy_pressure_score: float = 0.0
    accept_reason: str = ""
    reject_reason: str = ""
    reacceleration: bool = False
    soft_rvol_used: bool = False
    fast_upward_path: bool = False


def _effective_rvol(
    *,
    rvol: float,
    rvol_same_time: float | None,
) -> float:
    if rvol_same_time is not None and rvol_same_time > 0:
        return rvol_same_time
    return rvol


def compute_price_acceleration(bars: pd.DataFrame | None) -> tuple[float, float, float]:
    """1m / 3m / 5m close-to-close % acceleration."""
    if bars is None or bars.empty or len(bars) < 2:
        return 0.0, 0.0, 0.0
    closes = bars["close"].astype(float)
    acc_1m = 0.0
    if len(closes) >= 2 and closes.iloc[-2] > 0:
        acc_1m = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100.0
    acc_3m = acc_1m
    if len(closes) >= 4 and closes.iloc[-4] > 0:
        acc_3m = (closes.iloc[-1] - closes.iloc[-4]) / closes.iloc[-4] * 100.0
    acc_5m = acc_3m
    if len(closes) >= 6 and closes.iloc[-6] > 0:
        acc_5m = (closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6] * 100.0
    return round(acc_1m, 3), round(acc_3m, 3), round(acc_5m, 3)


def _price_momentum_persisted(bars: pd.DataFrame | None) -> bool:
    if bars is None or len(bars) < 2:
        return False
    closes = bars["close"].astype(float)
    if len(closes) >= 3:
        return closes.iloc[-1] > closes.iloc[-2] > closes.iloc[-3]
    return closes.iloc[-1] > closes.iloc[-2]


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
    allow_soft_rvol: bool = True,
    price_volume_response: float = 0.0,
    micro_higher_lows: bool = False,
    vwap_support: bool = False,
    early_watch_locked: bool = False,
) -> bool:
    """
    Sudden relative activity vs prior baseline — not absolute share volume.
    RVOL may be soft-bypassed when acceleration + buy pressure + structure align.
    """
    if change_percent <= 0:
        return False
    if change_percent >= STAGE_EE_MAX_EXTENSION_PCT and not early_watch_locked:
        return False

    rvol_eff = _effective_rvol(rvol=rvol, rvol_same_time=rvol_same_time)
    accel_ok = (
        volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
        or volume_acceleration_slope >= 1.08
    )
    rvol_ok = rvol_eff >= STAGE_RVOL_MIN or rvol >= STAGE_RVOL_MIN
    soft_rvol = False
    if not rvol_ok and allow_soft_rvol:
        strong_accel = (
            volume_acceleration_1m >= STAGE_VOL_ACCEL_STRONG
            or volume_acceleration_slope >= 1.12
        )
        buy_ok = (
            (trade_velocity_growth or 0) >= 0.15
            or price_volume_response >= 0.35
            or dollar_volume_growth >= 0.25
        )
        structure_ok = micro_higher_lows or vwap_support or breakout_pressure >= 35.0
        if strong_accel and buy_ok and structure_ok and volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN:
            rvol_ok = True
            soft_rvol = True

    trade_ok = (trade_velocity_growth or 0) >= 0.15
    liq_flow_ok = dollar_volume_growth >= 0.25 or breakout_pressure >= 35.0
    buy_pressure_ok = price_volume_response >= 0.35

    flow_ok = trade_ok or liq_flow_ok or buy_pressure_ok
    if soft_rvol:
        return accel_ok and flow_ok
    return accel_ok and rvol_ok and flow_ok


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
        price_volume_response=sig.early_activity.price_volume_response,
        micro_higher_lows=sig.early_activity.micro_higher_lows,
        vwap_support=sig.vwap.vwap_hold or sig.vwap.vwap_reclaim,
        early_watch_locked=sig.display_confirmed,
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
        price_volume_response=snap.price_volume_response,
        micro_higher_lows=snap.micro_higher_lows,
        vwap_support=snap.vwap_hold or snap.vwap_reclaim,
    )


def detect_re_acceleration(history: list[StageSnapshot], snap: StageSnapshot) -> bool:
    """New independent surge after prior move + calm — not a weak bounce."""
    if len(history) < 2:
        return False
    recent = history[-6:]
    prior_peak = max(s.price for s in recent)
    prior_calm = any(
        s.volume_acceleration_1m < 1.05 and s.price <= prior_peak * 0.995
        for s in recent[-4:-1]
    ) or any(s.failed_setup for s in recent[-3:])
    had_prior_move = any(s.change_pct >= 3.0 for s in recent) or prior_peak > (recent[0].price * 1.02)

    new_accel = snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN
    buy_pressure = (
        snap.price_volume_response >= 0.35
        or (snap.trade_velocity_growth or 0) >= 0.12
        or snap.breakout_pressure >= 35.0
    )
    higher_high = snap.price >= max(s.price for s in recent[:-1]) if len(recent) > 1 else True
    higher_low = snap.micro_higher_lows or snap.higher_lows_score >= 0.3
    vwap_ok = snap.vwap_hold or snap.vwap_reclaim or snap.distance_from_vwap_pct <= 2.5
    low_ref = min(s.price for s in recent)
    bounce_pct = (snap.price - low_ref) / low_ref * 100.0 if low_ref > 0 else 0.0
    not_weak = bounce_pct >= 1.5 or snap.change_pct >= STAGE_EE_MIN_SESSION_CHANGE_PCT

    return had_prior_move and new_accel and buy_pressure and higher_high and (higher_low or vwap_ok) and not_weak


def _count_fast_confluence(
    snap: StageSnapshot,
    *,
    acc_1m: float,
    acc_3m: float,
    soft_rvol: bool,
    bars: pd.DataFrame | None,
) -> tuple[int, list[str]]:
    factors: list[str] = []
    rvol_eff = _effective_rvol(rvol=snap.rvol, rvol_same_time=snap.rvol_same_time)

    if snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN or snap.volume_acceleration_slope >= 1.08:
        factors.append("volume_acceleration")
    if rvol_eff >= STAGE_RVOL_MIN:
        factors.append("rvol")
    elif soft_rvol:
        factors.append("rvol_soft")
    if (snap.trade_velocity_growth or 0) >= 0.12:
        factors.append("trade_velocity")
    if snap.dollar_volume_growth >= 0.25 or snap.breakout_pressure >= 35.0:
        factors.append("buy_flow")
    if snap.change_pct >= STAGE_EE_MIN_SESSION_CHANGE_PCT and snap.price_volume_response >= 0.35:
        factors.append("price_momentum")
    elif snap.change_pct >= STAGE_EE_MIN_SESSION_CHANGE_PCT:
        factors.append("price_up")
    if acc_1m > 0.15 or acc_3m > 0.35:
        factors.append("price_acceleration")
    if snap.vwap_hold or snap.vwap_reclaim:
        factors.append("vwap")
    if snap.micro_higher_lows:
        factors.append("higher_lows")
    if snap.resistance_distance_pct <= STAGE_BREAKOUT_NEAR_PCT * 2:
        factors.append("near_trigger")
    if snap.liquidity_score >= PREMOVE_MIN_LIQUIDITY_SCORE:
        factors.append("liquidity")
    if snap.spread_pct <= STAGE_EE_MAX_SPREAD_PCT:
        factors.append("spread_ok")
    if 0 < snap.change_pct < STAGE_EE_MAX_EXTENSION_PCT:
        factors.append("early_move")
    if bars is not None and _price_momentum_persisted(bars):
        factors.append("persistence")

    return len(factors), factors


def evaluate_fast_upward_jump(
    snap: StageSnapshot,
    *,
    history: list[StageSnapshot] | None = None,
    bars: pd.DataFrame | None = None,
    lifecycle: str = "",
    early_watch_locked: bool = False,
    for_jump_alert: bool = False,
    persistence_minutes: int = 0,
    movement_start_price: float = 0.0,
) -> FastUpwardVerdict:
    """
    Parallel FAST_UPWARD_JUMP_PATH — multi-factor real buying, not absolute volume.
    Works alongside stage progression; does not replace it.
    """
    history = history or []
    verdict = FastUpwardVerdict()

    if snap.change_pct <= 0:
        verdict.reject_reason = "no_upward_move"
        return verdict
    if early_watch_locked and snap.liquidity_score >= PREMOVE_MIN_LIQUIDITY_SCORE and snap.spread_pct <= STAGE_EE_MAX_SPREAD_PCT:
        confluence, factors = _count_fast_confluence(
            snap, acc_1m=0, acc_3m=0, soft_rvol=False, bars=bars,
        )
        verdict.qualified = True
        verdict.fast_upward_path = True
        verdict.display_type = DISPLAY_JUMP_ALERT if for_jump_alert else DISPLAY_STRONG_BUY_WATCH
        verdict.accept_reason = "fast_watch_locked_persist"
        verdict.confluence_count = max(confluence, 1)
        verdict.confluence_factors = factors or ["locked_watch"]
        verdict.buy_pressure_score = fast_filter_surge_rank(
            snap.change_pct, max(_effective_rvol(rvol=snap.rvol, rvol_same_time=snap.rvol_same_time), 0.5),
        )
        return verdict
    if snap.change_pct >= STAGE_EE_MAX_EXTENSION_PCT and not early_watch_locked:
        verdict.reject_reason = "extended_move"
        return verdict
    if snap.late_guard and not early_watch_locked:
        verdict.reject_reason = "late_move"
        return verdict
    if snap.spread_pct > STAGE_EE_MAX_SPREAD_PCT:
        verdict.reject_reason = "spread_wide"
        return verdict
    if snap.liquidity_score < PREMOVE_MIN_LIQUIDITY_SCORE:
        verdict.reject_reason = "low_liquidity"
        return verdict

    reaccel = detect_re_acceleration(history, snap)
    verdict.reacceleration = reaccel

    acc_1m, acc_3m, _ = compute_price_acceleration(bars)
    price_accel_ok = acc_1m > 0.1 or acc_3m > 0.25 or snap.price_volume_response >= 0.35

    surge = relative_surge_detected(
        change_percent=snap.change_pct,
        volume_acceleration_1m=snap.volume_acceleration_1m,
        volume_acceleration_slope=snap.volume_acceleration_slope,
        rvol=snap.rvol,
        rvol_same_time=snap.rvol_same_time,
        trade_velocity_growth=snap.trade_velocity_growth,
        dollar_volume_growth=snap.dollar_volume_growth,
        breakout_pressure=snap.breakout_pressure,
        price_volume_response=snap.price_volume_response,
        micro_higher_lows=snap.micro_higher_lows,
        vwap_support=snap.vwap_hold or snap.vwap_reclaim,
        early_watch_locked=early_watch_locked,
    )
    rvol_eff = _effective_rvol(rvol=snap.rvol, rvol_same_time=snap.rvol_same_time)
    soft_rvol = rvol_eff < STAGE_RVOL_MIN and surge
    verdict.soft_rvol_used = soft_rvol

    structure_ok = snap.micro_higher_lows or snap.vwap_hold or snap.vwap_reclaim
    buy_ok = snap.price_volume_response >= 0.35 or (snap.trade_velocity_growth or 0) >= 0.12

    if not surge and not (reaccel and price_accel_ok and buy_ok and structure_ok):
        verdict.reject_reason = "no_surge_or_reaccel"
        return verdict

    confluence, factors = _count_fast_confluence(
        snap, acc_1m=acc_1m, acc_3m=acc_3m, soft_rvol=soft_rvol, bars=bars,
    )
    verdict.confluence_count = confluence
    verdict.confluence_factors = factors
    verdict.buy_pressure_score = fast_filter_surge_rank(snap.change_pct, max(rvol_eff, 0.5))

    min_conf = STAGE_EE_MIN_CONFLUENCE
    if reaccel and lifecycle in ("FAILED_SETUP", "REARMED"):
        min_conf = max(4, STAGE_EE_MIN_CONFLUENCE - 1)

    if confluence < min_conf:
        verdict.reject_reason = f"confluence_{confluence}<{min_conf}"
        return verdict

    if not price_accel_ok and not reaccel:
        verdict.reject_reason = "no_price_acceleration"
        return verdict

    if not (structure_ok or snap.resistance_distance_pct <= STAGE_BREAKOUT_NEAR_PCT * 2):
        verdict.reject_reason = "no_structure"
        return verdict

    if bars is not None and len(bars) >= 2 and not _price_momentum_persisted(bars) and not reaccel:
        verdict.reject_reason = "single_tick_spike"
        return verdict

    verdict.qualified = True
    verdict.fast_upward_path = True
    if for_jump_alert or lifecycle in ("EARLY_ENTRY", "BREAKOUT_CONFIRMED"):
        verdict.display_type = DISPLAY_JUMP_ALERT
        verdict.accept_reason = "fast_upward_jump_alert"
    else:
        verdict.display_type = DISPLAY_STRONG_BUY_WATCH
        verdict.accept_reason = "fast_upward_reaccel" if reaccel else "fast_upward_surge"
    return verdict


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
    """Rank early setups: high RVOL, penalize extended session move (percent-based, price-neutral)."""
    extension_penalty = max(0.0, change_percent - 12.0) * 3.0
    return rvol * 2.5 + min(change_percent, 12.0) * 0.5 - extension_penalty


def neutral_surge_rank(
    *,
    wave_move_pct: float = 0.0,
    session_change_pct: float = 0.0,
    rvol: float = 0.0,
) -> float:
    """Price-neutral rank — prefer live wave % when present, else session %."""
    move_pct = wave_move_pct if wave_move_pct > 0 else session_change_pct
    return fast_filter_surge_rank(move_pct, max(rvol, 0.5))


WAVE_ACCEL_1M_ACTIVE = 0.08
WAVE_ACCEL_3M_ACTIVE = 0.15
WAVE_STAGNANT_1M = 0.03
WAVE_STAGNANT_3M = 0.12
WAVE_NEW_ACCEL_1M = 0.12
WAVE_NEW_ACCEL_3M = 0.22

WAVE_STATE_ACTIVE_UPWARD = "ACTIVE_UPWARD_WAVE"
WAVE_STATE_ENDED_LABEL = "WAVE_ENDED"
WAVE_STATE_TOO_LATE = "TOO_LATE_TO_CHASE"

ENTRY_STATUS_ALLOWED = "ENTRY_ALLOWED"
ENTRY_STATUS_TOO_LATE = "TOO_LATE_TO_CHASE"
ENTRY_STATUS_BAD_SPREAD = "BAD_SPREAD"

BUY_PRESSURE_SOURCE_EXECUTED = "EXECUTED_TRADES"
BUY_PRESSURE_SOURCE_PROXY = "BUY_PRESSURE_PROXY"
DATA_QUALITY_TICK = "TICK_TRADES"
DATA_QUALITY_PROXY = "OHLCV_PROXY"


@dataclass
class RealJumpEarlyDetectionKPI:
    first_detected_time: datetime | None = None
    first_detected_price: float = 0.0
    move_start_price: float = 0.0
    wave_peak_price: float = 0.0
    first_detected_pct: float = 0.0
    wave_peak_move_pct: float = 0.0
    peak_after_detection_pct: float = 0.0
    lead_time_minutes: float = 0.0
    explosion_confluence_score: float = 0.0


@dataclass
class RealJumpWaveSnapshot:
    """Short-window upward wave — independent of session/day change."""

    move_start_time: datetime | None = None
    move_start_price: float = 0.0
    current_move_pct: float = 0.0
    price_acceleration_1m: float = 0.0
    price_acceleration_3m: float = 0.0
    price_acceleration_5m: float = 0.0
    wave_peak_price: float = 0.0
    first_detected_time: datetime | None = None
    first_detected_price: float = 0.0
    first_detected_pct: float = 0.0
    current_price: float = 0.0
    wave_id: str = ""
    wave_active: bool = False
    wave_ended: bool = False
    is_new_wave: bool = False
    wave_state: str = ""
    entry_status: str = ENTRY_STATUS_ALLOWED
    reset_reason: str = ""
    wave_end_time: datetime | None = None
    prior_ended_peak: float = 0.0
    prior_wave_end_time: datetime | None = None
    buy_pressure_source: str = BUY_PRESSURE_SOURCE_PROXY
    data_quality: str = DATA_QUALITY_PROXY
    kpi: RealJumpEarlyDetectionKPI | None = None


@dataclass
class RealPriceJumpVerdict:
    confirmed: bool = False
    reject_reason: str = ""
    evidence_factors: list[str] = field(default_factory=list)
    explosive_score: int = 0
    explosion_confluence_score: float = 0.0
    confluence_components: dict[str, float] = field(default_factory=dict)
    bonus_factors: list[str] = field(default_factory=list)
    wave: RealJumpWaveSnapshot | None = None
    kpi: RealJumpEarlyDetectionKPI | None = None
    is_alert_update: bool = False
    entry_status: str = ENTRY_STATUS_ALLOWED
    buy_pressure_source: str = BUY_PRESSURE_SOURCE_PROXY
    data_quality: str = DATA_QUALITY_PROXY


def _wave_has_upward_momentum(acc_1m: float, acc_3m: float, acc_5m: float) -> bool:
    instant = acc_1m >= 0.20 and acc_3m >= 0.25
    building = acc_1m >= 0.15 and acc_3m >= 0.28 and acc_3m >= acc_1m * 1.15
    sustained = acc_1m >= 0.18 and acc_3m >= 0.30 and acc_5m >= 0.35
    return instant or building or sustained


def _wave_is_stagnant(acc_1m: float, acc_3m: float) -> bool:
    return acc_1m <= WAVE_STAGNANT_1M and acc_3m <= WAVE_STAGNANT_3M


def derive_real_jump_wave(
    *,
    bars: pd.DataFrame | None,
    current_price: float,
    prior: RealJumpWaveSnapshot | None = None,
    move_start_time: datetime | None = None,
    price_acceleration_1m: float | None = None,
    price_acceleration_3m: float | None = None,
    price_acceleration_5m: float | None = None,
) -> RealJumpWaveSnapshot:
    """Detect the current short-window wave from 1m/3m/5m bars or supplied accelerations."""
    acc_1m, acc_3m, acc_5m = compute_price_acceleration(bars)
    if price_acceleration_1m is not None:
        acc_1m = price_acceleration_1m
    if price_acceleration_3m is not None:
        acc_3m = price_acceleration_3m
    if price_acceleration_5m is not None:
        acc_5m = price_acceleration_5m

    wave = RealJumpWaveSnapshot(
        price_acceleration_1m=acc_1m,
        price_acceleration_3m=acc_3m,
        price_acceleration_5m=acc_5m,
    )

    move_start = 0.0
    start_time = move_start_time
    if bars is not None and len(bars) >= 2:
        lows = bars["low"].astype(float)
        lookback = min(6, len(bars))
        move_start = float(lows.iloc[-lookback:].min())
        if "timestamp" in bars.columns and len(bars) >= lookback:
            ts = bars["timestamp"].iloc[-lookback]
            if isinstance(ts, pd.Timestamp):
                start_time = ts.to_pydatetime()
    elif prior and prior.move_start_price > 0:
        move_start = prior.move_start_price
        start_time = prior.move_start_time

    if move_start <= 0 and prior and prior.move_start_price > 0:
        move_start = prior.move_start_price
        start_time = prior.move_start_time

    current_move_pct = (
        (current_price - move_start) / move_start * 100.0 if move_start > 0 else 0.0
    )
    momentum = _wave_has_upward_momentum(acc_1m, acc_3m, acc_5m)
    stagnant = _wave_is_stagnant(acc_1m, acc_3m)

    if prior and prior.wave_active and stagnant:
        wave.wave_active = False
        wave.wave_ended = True
        wave.move_start_price = prior.move_start_price
        wave.move_start_time = prior.move_start_time
        wave.current_move_pct = current_move_pct
        return wave

    if prior and not prior.wave_active and momentum and current_move_pct >= 2.0:
        wave.is_new_wave = True
        if bars is not None and len(bars) >= 3:
            move_start = float(bars["low"].astype(float).iloc[-3:].min())
            current_move_pct = (
                (current_price - move_start) / move_start * 100.0 if move_start > 0 else 0.0
            )
        wave.wave_active = True
        wave.move_start_price = move_start
        wave.move_start_time = start_time
        wave.current_move_pct = current_move_pct
        return wave

    if momentum and current_move_pct >= 2.0:
        wave.wave_active = True
        if prior and prior.wave_active and prior.move_start_price > 0:
            wave.move_start_price = prior.move_start_price
            wave.move_start_time = prior.move_start_time
            wave.wave_state = prior.wave_state or "ACTIVE"
            wave.current_move_pct = (
                (current_price - prior.move_start_price) / prior.move_start_price * 100.0
            )
            wave.first_detected_time = prior.first_detected_time
            wave.first_detected_price = prior.first_detected_price
            wave.first_detected_pct = prior.first_detected_pct
            wave.wave_id = prior.wave_id
        else:
            wave.move_start_price = move_start
            wave.move_start_time = start_time
            wave.current_move_pct = current_move_pct
        return wave

    if stagnant or acc_1m < -0.04:
        wave.wave_active = False
        wave.wave_ended = bool(prior and prior.wave_active)
    wave.move_start_price = move_start
    wave.move_start_time = start_time
    wave.current_move_pct = current_move_pct
    return wave


def _higher_high_or_breakout(
    *,
    current_price: float,
    micro_higher_lows: bool,
    trigger_price: float,
    breakout_pressure: float,
    resistance_distance_pct: float,
    bars: pd.DataFrame | None,
) -> bool:
    if micro_higher_lows:
        return True
    if trigger_price > 0 and current_price >= trigger_price * 0.992:
        return True
    if breakout_pressure >= 42.0:
        return True
    if resistance_distance_pct <= STAGE_BREAKOUT_NEAR_PCT * 1.5:
        return True
    if bars is not None and len(bars) >= 2:
        highs = bars["high"].astype(float)
        if highs.iloc[-1] > highs.iloc[-2]:
            return True
    return False


def _multi_tick_upward_persistence(
    *,
    bars: pd.DataFrame | None,
    persistence_minutes: int,
    micro_higher_lows: bool,
    price_volume_response: float,
    current_move_pct: float = 0.0,
    reacceleration: bool,
) -> bool:
    if reacceleration:
        return True
    if persistence_minutes >= 2:
        return True
    if bars is not None and _price_momentum_persisted(bars):
        return True
    if (
        micro_higher_lows
        and price_volume_response >= 0.35
        and current_move_pct >= 2.0
    ):
        return True
    return False


def _strong_accelerating_price_from_wave(
    wave: RealJumpWaveSnapshot,
    *,
    price_volume_response: float,
    bars: pd.DataFrame | None,
) -> tuple[bool, list[str]]:
    factors: list[str] = []
    acc_1m = wave.price_acceleration_1m
    acc_3m = wave.price_acceleration_3m
    acc_5m = wave.price_acceleration_5m
    if bars is not None and len(bars) >= 2:
        acc_1m, acc_3m, acc_5m = compute_price_acceleration(bars)
        wave.price_acceleration_1m = acc_1m
        wave.price_acceleration_3m = acc_3m
        wave.price_acceleration_5m = acc_5m
    if acc_1m > 0.12:
        factors.append("price_accel_1m")
    if acc_3m > 0.28:
        factors.append("price_accel_3m")
    if acc_5m > 0.38:
        factors.append("price_accel_5m")
    building = acc_1m > 0.08 and acc_3m > max(acc_1m * 0.85, 0.15)
    if building:
        factors.append("accel_building")
    if price_volume_response >= 0.4 and wave.current_move_pct >= 2.0:
        factors.append("price_volume_response")
    strong = (
        (acc_1m > 0.15 and acc_3m > 0.25)
        or (building and acc_3m > 0.2)
        or (acc_1m > 0.1 and acc_3m > 0.18 and acc_5m > 0.25)
        or (price_volume_response >= 0.45 and acc_1m > 0.1)
        or _wave_has_upward_momentum(acc_1m, acc_3m, acc_5m)
    )
    return strong, factors


def evaluate_real_price_jump(
    *,
    current_price: float,
    change_pct: float,
    price_volume_response: float = 0.0,
    micro_higher_lows: bool = False,
    vwap_hold: bool = False,
    vwap_reclaim: bool = False,
    breakout_pressure: float = 0.0,
    resistance_distance_pct: float = 99.0,
    trigger_price: float = 0.0,
    movement_start_price: float = 0.0,
    volume_acceleration_1m: float = 0.0,
    volume_acceleration_slope: float = 0.0,
    rvol: float = 0.0,
    rvol_same_time: float | None = None,
    trade_velocity_growth: float | None = None,
    dollar_volume_growth: float = 0.0,
    persistence_minutes: int = 0,
    bars: pd.DataFrame | None = None,
    reacceleration: bool = False,
) -> RealPriceJumpVerdict:
    """
    Confirmed upward price jump — price action required; volume/RVOL are supplementary only.
    """
    out = RealPriceJumpVerdict()
    if change_pct <= 0 or current_price <= 0:
        out.reject_reason = "no_upward_move"
        return out

    acc_1m, acc_3m, _ = compute_price_acceleration(bars)
    price_accel = acc_1m > 0.08 or acc_3m > 0.2 or price_volume_response >= 0.35
    if bars is None or bars.empty:
        price_accel = price_accel or (
            price_volume_response >= 0.35 and change_pct >= STAGE_EE_MIN_SESSION_CHANGE_PCT
        )

    higher_high = _higher_high_or_breakout(
        current_price=current_price,
        micro_higher_lows=micro_higher_lows or vwap_hold or vwap_reclaim,
        trigger_price=trigger_price,
        breakout_pressure=breakout_pressure,
        resistance_distance_pct=resistance_distance_pct,
        bars=bars,
    )
    persistence = _multi_tick_upward_persistence(
        bars=bars,
        persistence_minutes=persistence_minutes,
        micro_higher_lows=micro_higher_lows,
        price_volume_response=price_volume_response,
        current_move_pct=change_pct,
        reacceleration=reacceleration,
    )

    move_start = movement_start_price
    if move_start <= 0 and trigger_price > 0:
        move_start = trigger_price * 0.985
    price_above_start = move_start <= 0 or current_price > move_start

    momentum = change_pct > 0 and price_volume_response >= 0.2

    checks = [
        ("price_accel", price_accel),
        ("higher_high_breakout", higher_high),
        ("multi_tick", persistence),
        ("above_move_start", price_above_start),
        ("momentum", momentum),
    ]
    out.evidence_factors = [name for name, ok in checks if ok]

    if not all(ok for _, ok in checks):
        missing = [name for name, ok in checks if not ok]
        out.reject_reason = f"missing_{'_'.join(missing)}"
        return out

    rvol_eff = _effective_rvol(rvol=rvol, rvol_same_time=rvol_same_time)
    if (
        volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN * 0.85
        or volume_acceleration_slope >= 1.05
        or rvol_eff >= STAGE_RVOL_MIN * 0.85
        or (trade_velocity_growth or 0) >= 0.12
        or dollar_volume_growth >= 0.2
    ):
        out.evidence_factors.append("volume_confirmation")

    out.confirmed = True
    return out


def _momentum_after_first_surge(
    bars: pd.DataFrame | None,
    *,
    persistence_minutes: int,
    reacceleration: bool,
) -> bool:
    if reacceleration:
        return True
    if persistence_minutes >= 2:
        return True
    if bars is not None and len(bars) >= 3 and _price_momentum_persisted(bars):
        return True
    if bars is not None and len(bars) >= 4:
        closes = bars["close"].astype(float)
        if closes.iloc[-1] > closes.iloc[-2] >= closes.iloc[-3]:
            return True
    return False


def _strong_accelerating_price(
    bars: pd.DataFrame | None,
    *,
    price_volume_response: float,
    change_pct: float,
) -> tuple[bool, list[str]]:
    factors: list[str] = []
    acc_1m, acc_3m, acc_5m = compute_price_acceleration(bars)
    if acc_1m > 0.12:
        factors.append("price_accel_1m")
    if acc_3m > 0.28:
        factors.append("price_accel_3m")
    if acc_5m > 0.38:
        factors.append("price_accel_5m")
    building = acc_1m > 0.08 and acc_3m > max(acc_1m * 0.85, 0.15)
    if building:
        factors.append("accel_building")
    if price_volume_response >= 0.4 and change_pct >= STAGE_EE_MIN_SESSION_CHANGE_PCT:
        factors.append("price_volume_response")
    strong = (
        (acc_1m > 0.15 and acc_3m > 0.25)
        or (building and acc_3m > 0.2)
        or (acc_1m > 0.1 and acc_3m > 0.18 and acc_5m > 0.25)
        or (price_volume_response >= 0.45 and acc_1m > 0.1)
    )
    return strong, factors


def _bounce_after_drop(bars: pd.DataFrame | None, current_move_pct: float) -> bool:
    if bars is None or len(bars) < 5:
        return False
    closes = bars["close"].astype(float)
    peak = closes.max()
    trough = closes.iloc[:-1].min()
    if peak <= 0 or trough <= 0:
        return False
    drop_pct = (peak - trough) / peak * 100
    rebound = (closes.iloc[-1] - trough) / trough * 100
    return drop_pct >= 4.0 and rebound < drop_pct * 0.6 and current_move_pct < 8.0


def _retrace_from_wave_peak(wave_peak: float, current_price: float) -> float:
    if wave_peak <= 0 or current_price >= wave_peak:
        return 0.0
    return (wave_peak - current_price) / wave_peak * 100.0


def _stalled_after_prior_peak(
    *,
    bars: pd.DataFrame | None,
    wave: RealJumpWaveSnapshot,
    current_price: float,
    price_volume_response: float,
    trade_velocity_growth: float | None,
    volume_acceleration_1m: float,
    rvol_same_time: float | None,
) -> bool:
    """Peak earlier, retraced, now sideways — weak buy flow (not a live jump)."""
    peak = max(wave.wave_peak_price, current_price, wave.prior_ended_peak)
    if bars is not None and len(bars) >= 5:
        peak = max(peak, float(bars["high"].astype(float).max()))
    if peak <= 0:
        return False
    retrace_pct = _retrace_from_wave_peak(peak, current_price)
    if retrace_pct < 15.0:
        return False
    acc_1m = wave.price_acceleration_1m
    acc_3m = wave.price_acceleration_3m
    stagnant = _wave_is_stagnant(acc_1m, acc_3m) or acc_1m <= 0
    weak_buy = price_volume_response < 0.32 and (trade_velocity_growth or 0) < 0.10
    weak_vol = volume_acceleration_1m < STAGE_VOL_ACCEL_MIN * 0.85
    weak_rvol = (rvol_same_time or 0) < STAGE_EE_MIN_RVOL * 0.70
    in_old_range = peak > 0 and abs(current_price - peak) / peak * 100.0 <= REAL_JUMP_PRIOR_RANGE_BLOCK_PCT
    if wave.prior_ended_peak > 0 and in_old_range and stagnant and (weak_buy or weak_vol):
        return True
    if retrace_pct >= 22.0 and stagnant and (weak_buy or weak_vol):
        return True
    if retrace_pct >= 30.0 and weak_buy and weak_rvol:
        return True
    return False


def _post_peak_cooldown_block(
    *,
    bars: pd.DataFrame | None,
    current_price: float,
    wave: RealJumpWaveSnapshot,
    price_volume_response: float,
) -> bool:
    """Session peak already printed; price lagging without fresh momentum."""
    if bars is None or len(bars) < 20:
        return False
    highs = bars["high"].astype(float)
    peak_val = float(highs.max())
    if peak_val <= 0 or current_price >= peak_val * 0.93:
        return False
    peak_pos = int(highs.values.argmax())
    bars_since_peak = len(highs) - peak_pos - 1
    if bars_since_peak < 12:
        return False
    weak = not _wave_has_upward_momentum(
        wave.price_acceleration_1m, wave.price_acceleration_3m, wave.price_acceleration_5m,
    )
    if current_price < peak_val * 0.94 and weak and price_volume_response < 0.45:
        return True
    return False


def _session_stall_below_peak(
    *,
    bars: pd.DataFrame | None,
    current_price: float,
    wave: RealJumpWaveSnapshot,
    price_volume_response: float,
    rvol_same_time: float | None,
) -> bool:
    """Block alert when price sits below session high without live upward progress."""
    if bars is None or len(bars) < 8:
        return False
    session_peak = float(bars["high"].astype(float).max())
    if session_peak <= 0 or current_price >= session_peak * 0.96:
        return False
    below_peak_pct = (session_peak - current_price) / session_peak * 100.0
    if below_peak_pct < 4.0:
        return False
    weak_momentum = not _wave_has_upward_momentum(
        wave.price_acceleration_1m, wave.price_acceleration_3m, wave.price_acceleration_5m,
    )
    weak_buy = price_volume_response < 0.38
    if below_peak_pct >= 5.0 and weak_momentum and weak_buy:
        return True
    if below_peak_pct >= 4.0 and weak_momentum and price_volume_response < 0.42:
        return True
    return False


def _old_range_reactivation_blocked(
    *,
    wave: RealJumpWaveSnapshot,
    current_price: float,
    bars: pd.DataFrame | None,
) -> bool:
    """Block re-alert inside prior wave range without a genuine re-arm breakout."""
    prior_peak = wave.prior_ended_peak
    if prior_peak <= 0 or wave.wave_active:
        return False
    if wave.prior_wave_end_time is None:
        return False
    in_range = abs(current_price - prior_peak) / prior_peak * 100.0 <= REAL_JUMP_PRIOR_RANGE_BLOCK_PCT
    if not in_range:
        return False
    new_hh = False
    if bars is not None and len(bars) >= 3:
        highs = bars["high"].astype(float)
        new_hh = float(highs.iloc[-1]) > prior_peak * 1.015
    elif current_price > prior_peak * 1.015:
        new_hh = True
    if new_hh and _wave_has_upward_momentum(
        wave.price_acceleration_1m, wave.price_acceleration_3m, wave.price_acceleration_5m,
    ):
        return False
    return True


def _session_has_meaningful_new_high(
    bars: pd.DataFrame | None,
    current_price: float,
    session_peak: float,
) -> bool:
    if session_peak <= 0:
        return False
    if current_price >= session_peak * 0.995:
        return True
    if bars is not None and len(bars) >= 1:
        if float(bars["high"].astype(float).iloc[-1]) >= session_peak * 0.995:
            return True
    return False


def _expansion_from_prior_high(bars: pd.DataFrame | None, current_price: float) -> float:
    if bars is None or len(bars) < 3 or current_price <= 0:
        return 0.0
    lookback = min(REAL_JUMP_ABSORPTION_LOOKBACK_BARS, len(bars) - 1)
    prior = bars.iloc[-lookback - 1:-1]
    if prior.empty:
        return 0.0
    prior_high = float(prior["high"].astype(float).max())
    if prior_high <= 0:
        return 0.0
    return (current_price - prior_high) / prior_high * 100.0


def _post_peak_weak_momentum_reject(
    *,
    bars: pd.DataFrame | None,
    current_price: float,
    wave: RealJumpWaveSnapshot,
    move_pct: float,
    price_volume_response: float,
    rvol_eff: float,
    is_alert_update: bool,
) -> bool:
    """Reject bounce below session peak without a genuine new leg / breakout."""
    if is_alert_update:
        return False
    if bars is None or len(bars) < 8:
        return False
    highs = bars["high"].astype(float)
    session_peak = float(highs.max())
    if session_peak <= 0 or _session_has_meaningful_new_high(bars, current_price, session_peak):
        return False
    below_peak_pct = (session_peak - current_price) / session_peak * 100.0
    if below_peak_pct <= 0.5:
        return False
    peak_pos = int(highs.values.argmax())
    if len(highs) - peak_pos - 1 < 5:
        return False
    expansion = _expansion_from_prior_high(bars, current_price)
    if (
        expansion >= 10.0
        and move_pct >= 15.0
        and current_price >= session_peak * 0.97
        and _wave_has_upward_momentum(
            wave.price_acceleration_1m, wave.price_acceleration_3m, wave.price_acceleration_5m,
        )
    ):
        return False
    if below_peak_pct <= 5.0:
        return True
    if below_peak_pct >= REAL_JUMP_POST_PEAK_MIN_BELOW_PCT:
        return True
    if rvol_eff >= STAGE_EE_MIN_RVOL * 2 and move_pct < 14.0 and below_peak_pct >= 4.0:
        return True
    return False


def _post_stall_bad_spread_reject(
    *,
    bars: pd.DataFrame | None,
    current_price: float,
    wave: RealJumpWaveSnapshot,
    spread_pct: float,
    move_pct: float,
    persistence_minutes: int,
    micro_higher_lows: bool,
    is_alert_update: bool,
) -> bool:
    """After prior spike + stall, block re-arm unless spread and breakout are tradable."""
    if is_alert_update:
        return False
    if spread_pct > REAL_JUMP_ABSOLUTE_MAX_SPREAD_PCT:
        return True
    if spread_pct <= STAGE_EE_MAX_SPREAD_PCT:
        return False
    if bars is None or len(bars) < 10:
        return spread_pct > STAGE_EE_MAX_SPREAD_PCT * 2
    highs = bars["high"].astype(float)
    session_peak = float(highs.max())
    if session_peak <= 0:
        return False
    below_peak_pct = (session_peak - current_price) / session_peak * 100.0
    if below_peak_pct < 5.0:
        return False
    peak_pos = int(highs.values.argmax())
    bars_since_peak = len(highs) - peak_pos - 1
    if bars_since_peak < 8:
        return False
    expansion = _expansion_from_prior_high(bars, current_price)
    fresh_breakout = (
        expansion >= 6.0
        and _wave_has_upward_momentum(
            wave.price_acceleration_1m, wave.price_acceleration_3m, wave.price_acceleration_5m,
        )
        and (persistence_minutes >= 2 or micro_higher_lows)
    )
    if spread_pct > STAGE_EE_MAX_SPREAD_PCT and not fresh_breakout:
        return True
    if spread_pct > STAGE_EE_MAX_SPREAD_PCT * 2 and move_pct < 12.0:
        return True
    return False


def _range_bound_chop_reject(
    *,
    bars: pd.DataFrame | None,
    current_price: float,
    wave: RealJumpWaveSnapshot,
    move_pct: float,
    is_alert_update: bool,
) -> bool:
    """Tight session range near highs with weak acceleration — not a price explosion."""
    if is_alert_update or bars is None or len(bars) < 20:
        return False
    if move_pct >= 12.0 or wave.price_acceleration_1m >= 1.0:
        return False
    highs = bars["high"].astype(float)
    lows = bars["low"].astype(float)
    session_high = float(highs.max())
    session_rng = (session_high - float(lows.min())) / max(current_price, 0.01) * 100.0
    if session_rng > 12.0:
        return False
    dist_from_high = (session_high - current_price) / max(session_high, 0.01) * 100.0
    if dist_from_high > 2.0:
        return False
    expansion = _expansion_from_prior_high(bars, current_price)
    if expansion >= 6.0:
        return False
    return (
        move_pct < 11.0
        and wave.price_acceleration_1m < 0.9
        and wave.price_acceleration_3m < 1.2
    )


def _high_volume_absorption(
    *,
    rvol_eff: float,
    move_pct: float,
    price_volume_response: float,
    wave: RealJumpWaveSnapshot,
    bars: pd.DataFrame | None,
    current_price: float,
    volume_acceleration_1m: float = 0.0,
) -> bool:
    """High RVOL / volume surge without proportional price advance — absorption."""
    expansion = _expansion_from_prior_high(bars, current_price)
    prior_rng_pct = 99.0
    if bars is not None and len(bars) >= 8:
        lookback = min(REAL_JUMP_ABSORPTION_LOOKBACK_BARS, len(bars) - 1)
        prior = bars.iloc[-lookback - 1:-1]
        if not prior.empty:
            prior_high = float(prior["high"].astype(float).max())
            prior_low = float(prior["low"].astype(float).min())
            prior_rng_pct = (prior_high - prior_low) / max(prior_high, 0.01) * 100.0

    vol_surge = (
        rvol_eff >= REAL_JUMP_HIGH_RVOL_ABSORPTION
        or volume_acceleration_1m >= 6.0
        or (rvol_eff >= 3.0 and volume_acceleration_1m >= 4.0)
    )
    if not vol_surge:
        return False
    if (
        move_pct >= 14.0
        and wave.price_acceleration_1m >= 2.0
        and expansion >= 8.0
        and _wave_has_upward_momentum(
            wave.price_acceleration_1m, wave.price_acceleration_3m, wave.price_acceleration_5m,
        )
    ):
        return False
    if (
        prior_rng_pct <= REAL_JUMP_ABSORPTION_RANGE_PCT + 1.0
        and expansion < 5.0
        and move_pct < 11.0
        and wave.price_acceleration_1m < 1.0
        and (volume_acceleration_1m >= 6.0 or rvol_eff >= 3.5)
    ):
        return True
    if (
        prior_rng_pct <= REAL_JUMP_ABSORPTION_RANGE_PCT
        and expansion < 5.0
        and move_pct < 11.0
    ):
        return True
    if bars is not None and len(bars) >= 5:
        closes = bars["close"].astype(float)
        rng_pct = (closes.iloc[-5:].max() - closes.iloc[-5:].min()) / max(closes.iloc[-1], 0.01) * 100.0
        if rng_pct <= 4.0 and expansion < 5.0 and move_pct < 11.0:
            return True
    if rvol_eff >= 30.0 and expansion < 5.0 and move_pct < 11.0:
        return True
    if volume_acceleration_1m >= 10.0 and prior_rng_pct <= 7.0 and expansion < 5.0 and move_pct < 10.0:
        return True
    if (
        price_volume_response < 0.42
        and rvol_eff >= 15.0
        and move_pct < 10.0
        and wave.price_acceleration_1m < 1.0
        and expansion < 4.0
    ):
        return True
    return False


def _mandatory_price_response_gate(
    *,
    wave: RealJumpWaveSnapshot,
    current_price: float,
    price_volume_response: float,
    spread_pct: float,
    micro_higher_lows: bool,
    persistence_minutes: int,
    bars: pd.DataFrame | None,
    is_alert_update: bool,
) -> tuple[bool, str]:
    """Require live upward price response — not volume/RVOL alone."""
    if wave.price_acceleration_1m <= 0 and wave.price_acceleration_3m <= 0.05 and not is_alert_update:
        return False, "price_not_rising_now"
    up_ticks = 0
    if bars is not None and len(bars) >= REAL_JUMP_PRICE_RESPONSE_MIN_TICKS:
        closes = bars["close"].astype(float)
        for i in range(-(REAL_JUMP_PRICE_RESPONSE_MIN_TICKS - 1), 0):
            if closes.iloc[i] > closes.iloc[i - 1]:
                up_ticks += 1
    elif persistence_minutes >= REAL_JUMP_PRICE_RESPONSE_MIN_TICKS - 1:
        up_ticks = REAL_JUMP_PRICE_RESPONSE_MIN_TICKS
    if up_ticks < REAL_JUMP_PRICE_RESPONSE_MIN_TICKS - 1 and not is_alert_update:
        has_momentum = _wave_has_upward_momentum(
            wave.price_acceleration_1m, wave.price_acceleration_3m, wave.price_acceleration_5m,
        )
        if not (has_momentum and (wave.current_move_pct >= 8.0 or up_ticks >= 1)):
            return False, "insufficient_upward_ticks"
    peak = max(wave.wave_peak_price, current_price)
    if peak > 0 and not is_alert_update:
        dist_from_peak = (peak - current_price) / peak * 100.0
        if dist_from_peak > REAL_JUMP_NEAR_PEAK_TOLERANCE_PCT and wave.current_move_pct < 8.0:
            return False, "far_from_wave_peak"
    min_expansion = max(2.5, spread_pct * 1.2)
    if wave.current_move_pct < min_expansion and not micro_higher_lows and not is_alert_update:
        return False, "expansion_below_spread_noise"
    if price_volume_response < 0.28 and wave.current_move_pct < 10.0 and not is_alert_update:
        return False, "weak_volume_price_response"
    return True, ""


def compute_real_jump_entry_status(
    *,
    wave: RealJumpWaveSnapshot,
    spread_pct: float,
    liquidity_score: float,
    is_alert_update: bool,
) -> str:
    """Entry eligibility — separate from wave lifecycle."""
    if liquidity_score < PREMOVE_MIN_LIQUIDITY_SCORE or spread_pct > STAGE_EE_MAX_SPREAD_PCT:
        return ENTRY_STATUS_BAD_SPREAD
    if not is_alert_update and wave.current_move_pct >= STAGE_EE_MAX_EXTENSION_PCT:
        return ENTRY_STATUS_TOO_LATE
    return ENTRY_STATUS_ALLOWED


def evaluate_real_jump_live_exit(
    *,
    wave: RealJumpWaveSnapshot,
    current_price: float,
    price_volume_response: float,
    trade_velocity_growth: float | None,
    trade_velocity: float | None,
    volume_acceleration_1m: float,
    spread_pct: float,
    liquidity_score: float,
    bars: pd.DataFrame | None = None,
    end_signal_streak: int = 0,
) -> tuple[bool, str, str]:
    """
    End REAL_JUMP wave only on composite distribution — never on spread/extension alone.
    Returns (wave_should_end, reason, WAVE_ENDED).
    """
    del spread_pct, liquidity_score  # entry-only — never end wave on these
    peak = max(wave.wave_peak_price, current_price)
    retrace = _retrace_from_wave_peak(peak, current_price)
    acc_1m = wave.price_acceleration_1m
    acc_3m = wave.price_acceleration_3m
    acc_5m = wave.price_acceleration_5m

    if wave.wave_ended or not wave.wave_active:
        return True, "wave_ended", WAVE_STATE_ENDED_LABEL

    # Fast-path: clear distribution after meaningful peak (no single-tick exit)
    if retrace >= 13.0 and price_volume_response < 0.22 and acc_1m < -0.08:
        return True, "distribution_from_peak", WAVE_STATE_ENDED_LABEL
    if acc_1m < -0.10 and acc_3m < -0.04 and retrace >= 18.0:
        return True, "negative_acceleration", WAVE_STATE_ENDED_LABEL

    signals = 0
    if acc_1m < -0.08 and acc_3m < 0.0:
        signals += 1
    if retrace >= 22.0 and price_volume_response < 0.28:
        signals += 1
    if (trade_velocity_growth or 0) < -0.06 and price_volume_response < 0.32:
        signals += 1
    if (
        _wave_is_stagnant(acc_1m, acc_3m)
        and retrace >= 15.0
        and not _wave_has_upward_momentum(acc_1m, acc_3m, acc_5m)
    ):
        signals += 1
    if bars is not None and len(bars) >= 3:
        closes = bars["close"].astype(float)
        if closes.iloc[-1] <= closes.iloc[-3] and acc_1m < 0 and retrace >= 12.0:
            signals += 1
    if (trade_velocity or 0) > 0 and (trade_velocity or 0) < 3.0 and retrace >= 18.0:
        signals += 1
    if volume_acceleration_1m < STAGE_VOL_ACCEL_MIN * 0.75 and retrace >= 20.0:
        signals += 1

    confirmed = end_signal_streak >= REAL_JUMP_WAVE_END_CONFIRM_TICKS
    if signals >= REAL_JUMP_WAVE_END_SIGNALS_REQUIRED and confirmed:
        if retrace >= 22.0 and price_volume_response < 0.30:
            return True, "distribution_from_peak", WAVE_STATE_ENDED_LABEL
        if acc_1m < -0.08 and acc_3m < 0.0:
            return True, "negative_acceleration", WAVE_STATE_ENDED_LABEL
        return True, "stalled_no_progress", WAVE_STATE_ENDED_LABEL
    return False, "", ""


def _single_spike_then_stop(bars: pd.DataFrame | None, wave: RealJumpWaveSnapshot) -> bool:
    if bars is None or len(bars) < 4:
        return False
    closes = bars["close"].astype(float)
    if closes.iloc[-1] >= closes.iloc[-2]:
        return False
    spike = closes.iloc[-3] > closes.iloc[-4] * 1.015
    flat_after = abs(closes.iloc[-1] - closes.iloc[-2]) / max(closes.iloc[-2], 0.01) < 0.004
    drop_after = closes.iloc[-1] < closes.iloc[-2] < closes.iloc[-3]
    return spike and (flat_after or drop_after) and wave.price_acceleration_1m < 0.05


def evaluate_real_jump_alert(
    *,
    current_price: float,
    change_pct: float = 0.0,
    price_volume_response: float = 0.0,
    micro_higher_lows: bool = False,
    vwap_hold: bool = False,
    vwap_reclaim: bool = False,
    breakout_pressure: float = 0.0,
    resistance_distance_pct: float = 99.0,
    trigger_price: float = 0.0,
    movement_start_price: float = 0.0,
    volume_acceleration_1m: float = 0.0,
    volume_acceleration_slope: float = 0.0,
    rvol: float = 0.0,
    rvol_same_time: float | None = None,
    trade_velocity_growth: float | None = None,
    trade_velocity: float | None = None,
    dollar_volume_growth: float = 0.0,
    liquidity_score: float = 0.0,
    spread_pct: float = 99.0,
    persistence_minutes: int = 0,
    move_from_base_pct: float = 0.0,
    range_compression_3m: float = 0.0,
    compression_only: bool = False,
    watch_only: bool = False,
    late_guard: bool = False,
    bars: pd.DataFrame | None = None,
    reacceleration: bool = False,
    wave: RealJumpWaveSnapshot | None = None,
    float_shares: float = 0.0,
    news_catalyst_score: float = 0.0,
    premarket_gap_pct: float = 0.0,
    catalyst_strength: float = 0.0,
    data_age_seconds: float = 0.0,
    is_alert_update: bool = False,
) -> RealPriceJumpVerdict:
    """
    REAL_JUMP_ALERT — instant upward wave fingerprint (1m/3m/5m), not session/day change.
    ``change_pct`` is session context only and never used as a primary gate.
    """
    out = RealPriceJumpVerdict()
    if compression_only:
        out.reject_reason = "compression_without_price_move"
        return out
    if watch_only:
        out.reject_reason = "watch_without_price_jump"
        return out
    if current_price <= 0:
        out.reject_reason = "invalid_price"
        return out
    from config import PREMOVE_DATA_MAX_AGE_SECONDS
    if data_age_seconds > PREMOVE_DATA_MAX_AGE_SECONDS:
        out.reject_reason = "stale_data"
        return out

    active_wave = wave or derive_real_jump_wave(
        bars=bars,
        current_price=current_price,
        move_start_time=None,
    )
    if movement_start_price > 0 and active_wave.move_start_price <= 0:
        active_wave.move_start_price = movement_start_price
        active_wave.current_move_pct = (
            (current_price - movement_start_price) / movement_start_price * 100.0
        )
    out.wave = active_wave
    move_pct = active_wave.current_move_pct

    if not active_wave.wave_active and not reacceleration:
        out.reject_reason = "no_active_wave" if not active_wave.wave_ended else "wave_ended"
        return out
    if active_wave.wave_ended and not reacceleration:
        out.reject_reason = "wave_ended"
        return out
    if move_pct <= 0 and not reacceleration:
        out.reject_reason = "flat_or_down"
        return out
    if change_pct < -1.0 and move_pct < 8.0:
        out.reject_reason = "session_down_weak_bounce"
        return out
    if late_guard and move_pct >= STAGE_EE_MAX_EXTENSION_PCT:
        out.reject_reason = "too_late_to_chase"
        return out
    entry_status = compute_real_jump_entry_status(
        wave=active_wave,
        spread_pct=spread_pct,
        liquidity_score=liquidity_score,
        is_alert_update=is_alert_update,
    )
    active_wave.entry_status = entry_status
    out.entry_status = entry_status
    out.buy_pressure_source = BUY_PRESSURE_SOURCE_PROXY
    out.data_quality = DATA_QUALITY_PROXY
    if not is_alert_update and entry_status == ENTRY_STATUS_TOO_LATE:
        out.reject_reason = "wave_too_extended"
        return out
    if _bounce_after_drop(bars, move_pct):
        out.reject_reason = "bounce_after_drop"
        return out
    if not is_alert_update and _session_stall_below_peak(
        bars=bars,
        current_price=current_price,
        wave=active_wave,
        price_volume_response=price_volume_response,
        rvol_same_time=rvol_same_time,
    ):
        out.reject_reason = "session_stall_below_peak"
        return out
    if not is_alert_update and spread_pct > REAL_JUMP_ABSOLUTE_MAX_SPREAD_PCT:
        out.reject_reason = "post_stall_bad_spread"
        return out
    rvol_eff = _effective_rvol(rvol=rvol, rvol_same_time=rvol_same_time)
    if not is_alert_update and _post_stall_bad_spread_reject(
        bars=bars,
        current_price=current_price,
        wave=active_wave,
        spread_pct=spread_pct,
        move_pct=move_pct,
        persistence_minutes=persistence_minutes,
        micro_higher_lows=micro_higher_lows,
        is_alert_update=is_alert_update,
    ):
        out.reject_reason = "post_stall_bad_spread"
        return out
    if not is_alert_update and _post_peak_weak_momentum_reject(
        bars=bars,
        current_price=current_price,
        wave=active_wave,
        move_pct=move_pct,
        price_volume_response=price_volume_response,
        rvol_eff=rvol_eff,
        is_alert_update=is_alert_update,
    ):
        out.reject_reason = "post_peak_weak_momentum"
        return out
    if not is_alert_update and _old_range_reactivation_blocked(
        wave=active_wave,
        current_price=current_price,
        bars=bars,
    ):
        out.reject_reason = "old_range_reactivation"
        return out
    if not is_alert_update and _stalled_after_prior_peak(
        bars=bars,
        wave=active_wave,
        current_price=current_price,
        price_volume_response=price_volume_response,
        trade_velocity_growth=trade_velocity_growth,
        volume_acceleration_1m=volume_acceleration_1m,
        rvol_same_time=rvol_same_time,
    ):
        out.reject_reason = "stalled_after_prior_peak"
        return out
    if not is_alert_update and _single_spike_then_stop(bars, active_wave):
        out.reject_reason = "single_spike_then_stop"
        return out

    if not is_alert_update and _range_bound_chop_reject(
        bars=bars,
        current_price=current_price,
        wave=active_wave,
        move_pct=move_pct,
        is_alert_update=is_alert_update,
    ):
        out.reject_reason = "high_volume_absorption"
        return out
    if not is_alert_update and _high_volume_absorption(
        rvol_eff=rvol_eff,
        move_pct=move_pct,
        price_volume_response=price_volume_response,
        wave=active_wave,
        bars=bars,
        current_price=current_price,
        volume_acceleration_1m=volume_acceleration_1m,
    ):
        out.reject_reason = "high_volume_absorption"
        return out

    surge_only = relative_surge_detected(
        change_percent=max(move_pct, 0.01),
        volume_acceleration_1m=volume_acceleration_1m,
        volume_acceleration_slope=volume_acceleration_slope,
        rvol=rvol,
        rvol_same_time=rvol_same_time,
        trade_velocity_growth=trade_velocity_growth,
        dollar_volume_growth=dollar_volume_growth,
        breakout_pressure=breakout_pressure,
        price_volume_response=price_volume_response,
        micro_higher_lows=micro_higher_lows,
        vwap_support=vwap_hold or vwap_reclaim,
    )

    price_strong, price_factors = _strong_accelerating_price_from_wave(
        active_wave,
        price_volume_response=price_volume_response,
        bars=bars,
    )
    if not price_strong and (bars is None or bars.empty):
        if (
            price_volume_response >= 0.45
            and move_pct >= 3.0
            and persistence_minutes >= 2
            and volume_acceleration_1m >= STAGE_VOL_ACCEL_STRONG
            and _wave_has_upward_momentum(
                active_wave.price_acceleration_1m,
                active_wave.price_acceleration_3m,
                active_wave.price_acceleration_5m,
            )
        ):
            price_strong = True
            price_factors.extend(["live_momentum_proxy", "multi_tick_proxy"])
    if not price_strong and price_volume_response < 0.4:
        if rvol_eff >= STAGE_RVOL_MIN and move_pct <= 6:
            out.reject_reason = "rvol_only"
            return out
        if volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN and move_pct <= 6:
            out.reject_reason = "volume_accel_only"
            return out
        if surge_only and move_pct <= 6:
            out.reject_reason = "activity_spike_only"
            return out

    if (
        not is_alert_update
        and spread_pct > STAGE_EE_MAX_SPREAD_PCT * 2.5
        and not price_strong
        and price_volume_response < 0.5
    ):
        out.reject_reason = "liquidity_spread_unacceptable"
        return out

    move_start = active_wave.move_start_price
    if move_start <= 0 and trigger_price > 0:
        move_start = trigger_price * 0.985
    expansion_from_start = (
        move_start > 0 and current_price > move_start * 1.025
    ) or move_pct >= 3.0
    tight_base_break = range_compression_3m >= 0.45 or (
        move_pct >= 2.5 and price_volume_response >= 0.35
    )
    price_expansion = expansion_from_start and (tight_base_break or move_pct >= 4.0)

    breakout = _higher_high_or_breakout(
        current_price=current_price,
        micro_higher_lows=micro_higher_lows,
        trigger_price=trigger_price,
        breakout_pressure=breakout_pressure,
        resistance_distance_pct=resistance_distance_pct,
        bars=bars,
    )
    multi_tick = _multi_tick_upward_persistence(
        bars=bars,
        persistence_minutes=persistence_minutes,
        micro_higher_lows=micro_higher_lows,
        price_volume_response=price_volume_response,
        current_move_pct=move_pct,
        reacceleration=reacceleration or active_wave.is_new_wave,
    )
    above_start = move_start <= 0 or current_price > move_start

    vol_accel_ok = (
        volume_acceleration_1m >= STAGE_VOL_ACCEL_STRONG
        or volume_acceleration_slope >= 1.12
    )
    rvol_st_ok = rvol_same_time is not None and rvol_same_time >= STAGE_EE_MIN_RVOL * 0.85
    trade_vel_ok = (trade_velocity_growth or 0) >= 0.15 or (
        (trade_velocity or 0) > 0 and (trade_velocity_growth or 0) >= 0.1
    )
    if not is_alert_update and (trade_velocity_growth or 0) < 0.0:
        out.reject_reason = "trade_velocity_declining"
        return out
    buy_pressure_ok = price_volume_response >= 0.35 or dollar_volume_growth >= 0.25
    if not is_alert_update and active_wave.price_acceleration_1m <= 0 and active_wave.price_acceleration_3m <= 0.05:
        out.reject_reason = "price_not_rising_now"
        return out
    vwap_ok = vwap_hold or vwap_reclaim
    micro_resistance = micro_higher_lows or resistance_distance_pct <= STAGE_BREAKOUT_NEAR_PCT * 1.5
    momentum_hold = _momentum_after_first_surge(
        bars, persistence_minutes=persistence_minutes, reacceleration=reacceleration,
    )

    pct_only = (
        2.0 <= move_pct <= 6.0
        and not (vol_accel_ok and rvol_st_ok and price_expansion and price_strong)
    )
    if pct_only:
        out.reject_reason = "pct_only_no_explosive_fingerprint"
        return out
    if move_pct < 2.5 and not (
        range_compression_3m >= 0.5 and vol_accel_ok and rvol_st_ok and price_strong
    ):
        out.reject_reason = "early_move_insufficient_for_explosive"
        return out
    if bars is not None and len(bars) >= 2:
        bar_acc_1m, bar_acc_3m, _ = compute_price_acceleration(bars)
        if move_pct < 5.0 and bar_acc_1m < 0.75:
            out.reject_reason = "weak_instant_price_acceleration"
            return out
        if move_pct < 8.0 and bar_acc_3m < 0.25:
            out.reject_reason = "weak_instant_price_acceleration"
            return out

    checks = {
        "instant_wave_active": active_wave.wave_active or reacceleration,
        "price_acceleration": price_strong,
        "price_expansion": price_expansion,
        "breakout_higher_high": breakout,
        "multi_tick_persistence": multi_tick,
        "above_move_start": above_start,
        "volume_acceleration": vol_accel_ok,
        "rvol_same_time": rvol_st_ok,
        "trade_velocity": trade_vel_ok,
        "buy_pressure": buy_pressure_ok,
        "liquidity_spread": liquidity_score >= PREMOVE_MIN_LIQUIDITY_SCORE and spread_pct <= STAGE_EE_MAX_SPREAD_PCT,
        "momentum_after_surge": momentum_hold,
    }
    optional = {
        "vwap_support": vwap_ok,
        "micro_resistance": micro_resistance,
    }

    bonus_ctx = RealJumpBonusContext(
        float_shares=float_shares,
        news_catalyst_score=news_catalyst_score,
        premarket_gap_pct=premarket_gap_pct,
        near_psychological_level=near_psychological_level(current_price),
        catalyst_strength=catalyst_strength or (news_catalyst_score / 100.0 if news_catalyst_score else 0.0),
    )
    spread_for_confluence = spread_pct
    if (
        price_strong
        and _wave_has_upward_momentum(
            active_wave.price_acceleration_1m,
            active_wave.price_acceleration_3m,
            active_wave.price_acceleration_5m,
        )
        and STAGE_EE_MAX_SPREAD_PCT < spread_pct <= REAL_JUMP_CONFLUENCE_SPREAD_CAP_PCT
    ):
        spread_for_confluence = STAGE_EE_MAX_SPREAD_PCT
    confluence = compute_explosion_confluence(
        price_acceleration_ok=price_strong,
        acc_1m=active_wave.price_acceleration_1m,
        acc_3m=active_wave.price_acceleration_3m,
        acc_5m=active_wave.price_acceleration_5m,
        breakout_ok=breakout,
        multi_tick_ok=multi_tick,
        volume_acceleration_1m=volume_acceleration_1m,
        volume_acceleration_slope=volume_acceleration_slope,
        trade_velocity_growth=trade_velocity_growth,
        trade_velocity=trade_velocity,
        price_volume_response=price_volume_response,
        dollar_volume_growth=dollar_volume_growth,
        rvol=rvol,
        rvol_same_time=rvol_same_time,
        liquidity_score=liquidity_score,
        spread_pct=spread_for_confluence,
        range_compression_3m=range_compression_3m,
        bonus=bonus_ctx,
    )

    out.explosion_confluence_score = confluence.total_score
    out.confluence_components = confluence.component_scores
    out.bonus_factors = confluence.bonus_factors
    out.evidence_factors = [k for k, ok in checks.items() if ok]
    out.evidence_factors.extend(k for k, ok in optional.items() if ok)
    out.evidence_factors.extend(price_factors)
    out.evidence_factors.extend(
        f"confluence_{k}:{v:.2f}" for k, v in confluence.component_scores.items() if v >= 0.5
    )
    out.evidence_factors.extend(confluence.bonus_factors)
    if active_wave.is_new_wave:
        out.evidence_factors.append("new_instant_wave")
    out.explosive_score = int(round(confluence.total_score * 100))

    if not is_alert_update:
        price_ok, price_reason = _mandatory_price_response_gate(
            wave=active_wave,
            current_price=current_price,
            price_volume_response=price_volume_response,
            spread_pct=spread_pct,
            micro_higher_lows=micro_higher_lows,
            persistence_minutes=persistence_minutes,
            bars=bars,
            is_alert_update=is_alert_update,
        )
        if not price_ok:
            out.reject_reason = price_reason
            return out

    if not confluence.hard_gate_pass:
        missing = [k for k, ok in confluence.hard_gates.items() if not ok]
        out.reject_reason = f"hard_gate_{'_'.join(missing)}"
        return out
    if confluence.total_score < CONFLUENCE_PASS_THRESHOLD:
        out.reject_reason = f"confluence_{confluence.total_score:.2f}<{CONFLUENCE_PASS_THRESHOLD}"
        return out
    if not price_expansion or not vol_accel_ok or not rvol_st_ok or not trade_vel_ok or not buy_pressure_ok:
        out.reject_reason = "missing_core_explosion_factors"
        return out
    if news_catalyst_score >= 40 and not price_strong:
        out.reject_reason = "news_only"
        return out
    if premarket_gap_pct >= 5.0 and not price_strong and not breakout:
        out.reject_reason = "gap_only"
        return out

    if active_wave.wave_active:
        active_wave.wave_state = WAVE_STATE_ACTIVE_UPWARD
    out.confirmed = True
    return out


def real_price_jump_from_snapshot(
    snap: StageSnapshot,
    *,
    bars: pd.DataFrame | None = None,
    movement_start_price: float = 0.0,
    persistence_minutes: int = 0,
    reacceleration: bool = False,
) -> RealPriceJumpVerdict:
    return evaluate_real_price_jump(
        current_price=snap.price,
        change_pct=snap.change_pct,
        price_volume_response=snap.price_volume_response,
        micro_higher_lows=snap.micro_higher_lows,
        vwap_hold=snap.vwap_hold,
        vwap_reclaim=snap.vwap_reclaim,
        breakout_pressure=snap.breakout_pressure,
        resistance_distance_pct=snap.resistance_distance_pct,
        trigger_price=snap.trigger_price,
        movement_start_price=movement_start_price,
        volume_acceleration_1m=snap.volume_acceleration_1m,
        volume_acceleration_slope=snap.volume_acceleration_slope,
        rvol=snap.rvol,
        rvol_same_time=snap.rvol_same_time,
        trade_velocity_growth=snap.trade_velocity_growth,
        dollar_volume_growth=snap.dollar_volume_growth,
        persistence_minutes=persistence_minutes,
        bars=bars,
        reacceleration=reacceleration,
    )


@dataclass
class WatchJumpPromotion:
    promote: bool = False
    reject_reason: str = ""
    evidence_count: int = 0
    evidence_factors: list[str] = field(default_factory=list)


def evaluate_watch_to_jump_confirmation(
    snap: StageSnapshot,
    *,
    bars: pd.DataFrame | None = None,
    lifecycle: str = "",
    data_age_seconds: float = 0.0,
    stale_price: bool = False,
) -> WatchJumpPromotion:
    """
    STRONG_BUY_WATCH → JUMP_QUALIFIED when real-time confirmation stacks.
    Does not lower global thresholds — requires multi-factor live evidence.
    """
    out = WatchJumpPromotion()
    if stale_price:
        out.reject_reason = "stale_price"
        return out
    if data_age_seconds > 120:
        out.reject_reason = "stale_data"
        return out
    if snap.late_guard:
        out.reject_reason = "too_late_to_chase"
        return out
    if snap.change_pct <= 0:
        out.reject_reason = "momentum_lost"
        return out
    if snap.change_pct >= STAGE_EE_MAX_EXTENSION_PCT:
        out.reject_reason = "extended_before_confirm"
        return out
    if snap.liquidity_score < PREMOVE_MIN_LIQUIDITY_SCORE:
        out.reject_reason = "low_liquidity"
        return out
    if snap.spread_pct > STAGE_EE_MAX_SPREAD_PCT:
        out.reject_reason = "spread_wide"
        return out
    if snap.failed_setup and lifecycle not in ("REARMED", "PRE_BREAKOUT", "EARLY_ENTRY"):
        out.reject_reason = "failed_setup"
        return out

    acc_1m, acc_3m, _ = compute_price_acceleration(bars)
    price_accel = acc_1m > 0.08 or acc_3m > 0.2 or snap.price_volume_response >= 0.35
    trigger_break = (
        (snap.trigger_price > 0 and snap.price >= snap.trigger_price * 0.992)
        or snap.breakout_pressure >= 42.0
        or snap.resistance_distance_pct <= STAGE_BREAKOUT_NEAR_PCT * 1.5
    )
    vol_sustained = (
        snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN * 0.85
        or snap.volume_acceleration_3m >= STAGE_VOL_ACCEL_MIN * 0.85
        or snap.volume_acceleration_slope >= 1.02
    )
    rvol_eff = _effective_rvol(rvol=snap.rvol, rvol_same_time=snap.rvol_same_time)
    rvol_ok = rvol_eff >= STAGE_RVOL_MIN * 0.85 or relative_surge_from_snapshot(snap)
    trade_vel_ok = (snap.trade_velocity or 0) > 0 and (snap.trade_velocity_growth or 0) >= -0.08
    buy_pressure = snap.price_volume_response >= 0.3 or (snap.dollar_volume_growth or 0) >= 0.12
    structure = snap.micro_higher_lows or snap.vwap_hold or snap.vwap_reclaim
    momentum = snap.change_pct > 0 and snap.price_volume_response >= 0.2

    checks = [
        ("price_accel", price_accel),
        ("trigger_break", trigger_break),
        ("vol_sustained", vol_sustained),
        ("rvol_ok", rvol_ok),
        ("trade_velocity", trade_vel_ok),
        ("buy_pressure", buy_pressure),
        ("structure", structure),
        ("momentum", momentum),
    ]
    out.evidence_factors = [name for name, ok in checks if ok]
    out.evidence_count = len(out.evidence_factors)

    min_evidence = 5
    if lifecycle in ("PRE_BREAKOUT", "REARMED", "EARLY_ENTRY", "BREAKOUT_CONFIRMED"):
        min_evidence = 4

    if out.evidence_count < min_evidence:
        out.reject_reason = f"insufficient_confirmation_{out.evidence_count}<{min_evidence}"
        return out
    if not price_accel and not vol_sustained:
        out.reject_reason = "momentum_faded"
        return out

    out.promote = True
    return out
