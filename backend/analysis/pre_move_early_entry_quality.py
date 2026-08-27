"""EARLY_ENTRY Quality Gate — precision layer without delaying timing."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config import (
    STAGE_EE_MAX_BREAKOUT_FAILURE_RISK,
    STAGE_EE_MAX_REJECTION_SCORE,
    STAGE_EE_MAX_STOP_DISTANCE_PCT,
    STAGE_EE_MIN_CONFLUENCE_QUALITY,
    STAGE_EE_MIN_ENTRY_LOCATION,
    STAGE_EE_MIN_LIQUIDITY_MANDATORY,
    STAGE_EE_MIN_PRICE_HOLDING_MANDATORY,
    STAGE_EE_MIN_RRR_QUALITY,
    STAGE_EE_NO_NEWS_MIN_QUALITY,
    STAGE_VOL_ACCEL_MIN,
)
from models.pre_move_stage import StageSnapshot


@dataclass
class QualityGateThresholds:
    """Runtime-overridable thresholds — used for multi-day calibration."""

    min_confluence_quality: float = STAGE_EE_MIN_CONFLUENCE_QUALITY
    no_news_min_quality: float = STAGE_EE_NO_NEWS_MIN_QUALITY
    min_price_holding_mandatory: float = STAGE_EE_MIN_PRICE_HOLDING_MANDATORY
    min_liquidity_mandatory: float = STAGE_EE_MIN_LIQUIDITY_MANDATORY
    min_rrr_quality: float = STAGE_EE_MIN_RRR_QUALITY
    max_stop_distance_pct: float = STAGE_EE_MAX_STOP_DISTANCE_PCT
    max_rejection_score: float = STAGE_EE_MAX_REJECTION_SCORE
    max_breakout_failure_risk: float = STAGE_EE_MAX_BREAKOUT_FAILURE_RISK
    min_entry_location: float = STAGE_EE_MIN_ENTRY_LOCATION
    min_spread_stability: float = 45.0
    min_liquidity_consistency: float = 35.0
    max_churn_volume_efficiency: float = 14.0


@dataclass
class ConfluenceWeights:
    """Weighted confluence scoring — price holding dominates."""

    price_holding: float = 0.26
    vol_pts: float = 0.14
    vol_efficiency: float = 0.10
    vwap_pts: float = 0.10
    compression_q: float = 0.08
    resistance_q: float = 0.10
    entry_loc: float = 0.10
    liq_pts: float = 0.06
    spread_pts: float = 0.04
    persist_pts: float = 0.02


DEFAULT_THRESHOLDS = QualityGateThresholds()
DEFAULT_WEIGHTS = ConfluenceWeights()


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


@dataclass
class EarlyEntryQualityMetrics:
    confluence_quality_score: float = 0.0
    price_holding_score: float = 0.0
    volume_efficiency_score: float = 0.0
    rejection_score: float = 0.0
    upper_wick_ratio: float = 0.0
    breakout_failure_risk: float = 0.0
    spread_stability: float = 0.0
    liquidity_consistency: float = 0.0
    compression_quality: float = 0.0
    resistance_quality: float = 0.0
    entry_location_score: float = 0.0
    stop_distance_pct: float = 0.0
    rrr_quality: str = "WEAK"
    rrr_value: float = 0.0
    buyer_follow_through: float | None = None
    catalyst_confirmed: bool = False
    quality_gate_passed: bool = False
    block_reasons: list[str] = field(default_factory=list)
    quality_factors: list[str] = field(default_factory=list)


def compute_bar_microstructure(bars: pd.DataFrame) -> dict[str, float]:
    out = {
        "bar_open": 0.0,
        "bar_high": 0.0,
        "bar_low": 0.0,
        "upper_wick_ratio": 0.0,
        "close_position": 0.5,
        "body_pct": 0.0,
    }
    if bars.empty or len(bars) < 1:
        return out
    last = bars.iloc[-1]
    o, h, l, c = float(last["open"]), float(last["high"]), float(last["low"]), float(last["close"])
    out["bar_open"], out["bar_high"], out["bar_low"] = o, h, l
    rng = max(h - l, 1e-9)
    body_top = max(o, c)
    upper_wick = max(0.0, h - body_top)
    out["upper_wick_ratio"] = round(upper_wick / rng, 3)
    out["close_position"] = round((c - l) / rng, 3)
    out["body_pct"] = round(abs(c - o) / max(c, 1e-9) * 100.0, 2)
    return out


def compute_rejection_score(micro: dict[str, float], *, near_resistance: bool) -> float:
    uwr = micro.get("upper_wick_ratio", 0.0)
    cp = micro.get("close_position", 0.5)
    score = uwr * 70.0 + max(0.0, 0.55 - cp) * 60.0
    if near_resistance and uwr >= 0.45 and cp < 0.5:
        score += 25.0
    return round(_clamp(score), 1)


def compute_volume_efficiency(bars: pd.DataFrame) -> float:
    if bars.empty or len(bars) < 2:
        return 50.0
    cur = bars.iloc[-1]
    prev = bars.iloc[-2]
    c0, c1 = float(cur["close"]), float(prev["close"])
    v0, v1 = float(cur["volume"]), float(prev["volume"])
    if c1 <= 0 or v1 <= 0:
        return 35.0
    price_move_pct = abs(c0 - c1) / c1 * 100.0
    vol_ratio = v0 / max(v1, 1.0)

    # Distribution / churn: volume spike without price progress
    if vol_ratio >= 1.4 and price_move_pct < 0.12:
        return 14.0
    if vol_ratio >= 1.25 and price_move_pct < 0.08:
        return 15.0

    # Pre-breakout accumulation — small moves are normal before the trigger
    if price_move_pct < 0.35:
        neutral = 38.0 + price_move_pct * 40.0 + min(vol_ratio, 1.5) * 8.0
        return round(_clamp(neutral), 1)

    efficiency = price_move_pct / max(vol_ratio, 0.5)
    return round(_clamp(efficiency * 25.0 + min(price_move_pct, 3.0) * 15.0), 1)


def compute_spread_stability(history: list[StageSnapshot], snap: StageSnapshot) -> float:
    spreads = [s.spread_pct for s in history[-3:]] + [snap.spread_pct]
    if len(spreads) < 2:
        return 70.0
    widening = spreads[-1] - spreads[0]
    if widening > 2.0:
        return round(max(0.0, 30.0 - widening * 10.0), 1)
    if widening > 1.0:
        return round(55.0 - widening * 15.0, 1)
    return round(_clamp(85.0 - max(0.0, widening) * 10.0), 1)


def compute_liquidity_consistency(bars: pd.DataFrame) -> float:
    if bars.empty or len(bars) < 3:
        return 50.0
    vols = bars["volume"].astype(float).tail(4).tolist()
    if not vols or max(vols) <= 0:
        return 30.0
    mean_v = sum(vols) / len(vols)
    if mean_v <= 0:
        return 30.0
    variance = sum((v - mean_v) ** 2 for v in vols) / len(vols)
    cv = (variance ** 0.5) / mean_v
    last_ratio = vols[-1] / mean_v
    if cv > 1.2 and last_ratio > 2.5:
        return 25.0
    if cv > 0.9:
        return round(_clamp(60.0 - cv * 20.0), 1)
    return round(_clamp(70.0 + min(last_ratio, 2.0) * 10.0 - cv * 15.0), 1)


def compute_compression_quality(snap: StageSnapshot) -> float:
    comp = snap.compression_score * 100.0 if snap.compression_score else 0.0
    rc = snap.range_compression_3m
    if rc > 0 and rc < 0.85 and snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN:
        return round(_clamp(comp + 25.0 + snap.higher_lows_score * 20.0), 1)
    if rc > 0.95 or comp < 25:
        return round(max(10.0, comp * 0.5), 1)
    return round(_clamp(comp + snap.higher_lows_score * 15.0), 1)


def compute_resistance_quality(
    history: list[StageSnapshot],
    snap: StageSnapshot,
    *,
    trigger: float,
) -> float:
    if trigger <= 0 or snap.price <= 0:
        return 40.0
    tests = 0
    for s in history[-6:]:
        dist = (trigger - s.price) / snap.price * 100.0 if trigger > s.price else 0.0
        if 0 < dist <= 3.0:
            tests += 1
    hl_bonus = 20.0 if snap.micro_higher_lows or snap.higher_lows_score >= 0.4 else 0.0
    base = min(50.0 + tests * 12.0, 85.0) + hl_bonus
    if snap.breakout_pressure >= 50:
        base += 10.0
    return round(_clamp(base), 1)


def compute_breakout_failure_risk(
    history: list[StageSnapshot],
    snap: StageSnapshot,
    *,
    trigger: float,
    rejection: float,
    spread_stability: float,
) -> float:
    risk = 0.0
    failed_tests = 0
    for s in history[-5:]:
        if trigger > 0 and s.price > 0:
            dist = (trigger - s.price) / s.price * 100.0
            if 0 < dist <= 2.5 and s.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN:
                failed_tests += 1
    risk += min(failed_tests * 15.0, 45.0)

    if len(history) >= 2:
        if history[-1].volume_acceleration_1m > snap.volume_acceleration_1m + 0.2:
            risk += 12.0
        if snap.spread_pct > history[-1].spread_pct + 1.0:
            risk += 15.0

    risk += rejection * 0.35
    risk += max(0.0, 60.0 - spread_stability) * 0.4

    if snap.price_holding_score < 50:
        risk += 15.0
    return round(_clamp(risk), 1)


def compute_entry_location_score(
    *,
    price: float,
    trigger: float,
    stop: float,
    tp1: float,
) -> float:
    if price <= 0:
        return 0.0
    dist_trigger = (trigger - price) / price * 100.0 if trigger > price else 0.0
    stop_dist = (price - stop) / price * 100.0 if stop > 0 and stop < price else 99.0
    room_tp1 = (tp1 - price) / price * 100.0 if tp1 > price else 0.0

    trigger_pts = _clamp(100.0 - dist_trigger * 25.0) if dist_trigger <= 4 else max(20.0, 70.0 - dist_trigger * 8.0)
    stop_pts = _clamp(100.0 - max(0.0, stop_dist - 4.0) * 12.0)
    room_pts = _clamp(min(room_tp1, 8.0) * 12.0)
    return round(trigger_pts * 0.45 + stop_pts * 0.30 + room_pts * 0.25, 1)


def classify_rrr_quality(rrr: float, *, min_rrr: float | None = None) -> str:
    floor = min_rrr if min_rrr is not None else STAGE_EE_MIN_RRR_QUALITY
    if rrr < floor:
        return "REJECT"
    if rrr < 2.0:
        return "WEAK"
    if rrr < 3.0:
        return "GOOD"
    return "STRONG"


def compute_confluence_quality_score(
    *,
    snap: StageSnapshot,
    price_holding: float,
    vol_efficiency: float,
    vwap_pts: float,
    compression_q: float,
    resistance_q: float,
    entry_loc: float,
    liq_consistency: float,
    spread_stab: float,
    persist_min: int,
    weights: ConfluenceWeights | None = None,
) -> float:
    w = weights or DEFAULT_WEIGHTS
    vol_pts = _clamp(snap.volume_acceleration_1m / 2.0 * 50.0 + vol_efficiency * 0.5)
    liq_pts = _clamp(snap.liquidity_score * 0.5 + liq_consistency * 0.5)
    spread_pts = spread_stab
    persist_pts = _clamp(persist_min / 5.0 * 100.0)

    raw = (
        price_holding * w.price_holding
        + vol_pts * w.vol_pts
        + vol_efficiency * w.vol_efficiency
        + vwap_pts * w.vwap_pts
        + compression_q * w.compression_q
        + resistance_q * w.resistance_q
        + entry_loc * w.entry_loc
        + liq_pts * w.liq_pts
        + spread_pts * w.spread_pts
        + persist_pts * w.persist_pts
    )
    return round(_clamp(raw), 1)


def _vwap_quality_pts(snap: StageSnapshot) -> float:
    if snap.vwap_reclaim:
        return 90.0
    if snap.vwap_hold:
        return 75.0
    if snap.distance_from_vwap_pct <= 1.5:
        return 60.0
    if snap.distance_from_vwap_pct <= 3.0:
        return 40.0
    return 20.0


def apply_quality_thresholds(
    *,
    price_holding: float,
    liquidity_score: float,
    rrr_value: float,
    stop_distance_pct: float,
    rejection_score: float,
    breakout_failure_risk: float,
    volume_efficiency: float,
    entry_location: float,
    spread_stability: float,
    liquidity_consistency: float,
    confluence_quality: float,
    catalyst_confirmed: bool,
    higher_low_broken: bool = False,
    thresholds: QualityGateThresholds | None = None,
) -> tuple[bool, list[str]]:
    """Offline quality simulation — no look-ahead, market-pattern only."""
    th = thresholds or DEFAULT_THRESHOLDS
    blocks: list[str] = []

    if price_holding < th.min_price_holding_mandatory:
        blocks.append(f"price_holding_{price_holding:.0f}<{th.min_price_holding_mandatory:.0f}")
    if liquidity_score < th.min_liquidity_mandatory:
        blocks.append(f"liquidity_{liquidity_score:.0f}<{th.min_liquidity_mandatory:.0f}")
    if classify_rrr_quality(rrr_value, min_rrr=th.min_rrr_quality) == "REJECT":
        blocks.append(f"rrr_{rrr_value:.1f}<{th.min_rrr_quality:.1f}")
    if stop_distance_pct > th.max_stop_distance_pct:
        blocks.append(f"stop_dist_{stop_distance_pct:.1f}%>{th.max_stop_distance_pct:.1f}%")
    if rejection_score > th.max_rejection_score:
        blocks.append(f"rejection_{rejection_score:.0f}>{th.max_rejection_score:.0f}")
    if breakout_failure_risk > th.max_breakout_failure_risk:
        blocks.append(f"breakout_failure_risk_{breakout_failure_risk:.0f}")
    if volume_efficiency <= th.max_churn_volume_efficiency:
        blocks.append(f"churn_volume_{volume_efficiency:.0f}")
    if entry_location < th.min_entry_location:
        blocks.append(f"entry_location_{entry_location:.0f}<{th.min_entry_location:.0f}")
    if spread_stability < th.min_spread_stability:
        blocks.append(f"spread_unstable_{spread_stability:.0f}")
    if liquidity_consistency < th.min_liquidity_consistency:
        blocks.append(f"liquidity_inconsistent_{liquidity_consistency:.0f}")

    min_q = th.min_confluence_quality if catalyst_confirmed else th.no_news_min_quality
    if confluence_quality < min_q:
        blocks.append(f"confluence_quality_{confluence_quality:.0f}<{min_q:.0f}")
    if higher_low_broken:
        blocks.append("higher_low_broken")

    return len(blocks) == 0, blocks


def evaluate_early_entry_quality_gate(
    snap: StageSnapshot,
    history: list[StageSnapshot],
    bars: pd.DataFrame,
    *,
    stop_loss: float,
    tp1: float,
    trigger_price: float,
    persist_min: int,
    has_fresh_news: bool = False,
    news_catalyst_score: float = 0.0,
    thresholds: QualityGateThresholds | None = None,
    weights: ConfluenceWeights | None = None,
    fast_watch_locked: bool = False,
) -> EarlyEntryQualityMetrics:
    """Quality layer — runs after timing gate passes; rejects weak setups."""
    th = thresholds or DEFAULT_THRESHOLDS
    w = weights or DEFAULT_WEIGHTS
    m = EarlyEntryQualityMetrics()
    blocks: list[str] = []

    micro = compute_bar_microstructure(bars)
    dist_trigger = (
        (trigger_price - snap.price) / snap.price * 100.0
        if trigger_price > snap.price else snap.distance_to_breakout_pct
    )
    near_res = dist_trigger <= 3.0

    m.upper_wick_ratio = micro["upper_wick_ratio"]
    m.rejection_score = compute_rejection_score(micro, near_resistance=near_res)
    m.volume_efficiency_score = compute_volume_efficiency(bars)
    m.spread_stability = compute_spread_stability(history, snap)
    m.liquidity_consistency = compute_liquidity_consistency(bars)
    m.compression_quality = compute_compression_quality(snap)
    m.resistance_quality = compute_resistance_quality(history, snap, trigger=trigger_price)
    m.price_holding_score = snap.price_holding_score
    m.entry_location_score = compute_entry_location_score(
        price=snap.price, trigger=trigger_price, stop=stop_loss, tp1=tp1,
    )
    m.breakout_failure_risk = compute_breakout_failure_risk(
        history, snap, trigger=trigger_price,
        rejection=m.rejection_score, spread_stability=m.spread_stability,
    )

    if stop_loss > 0 and snap.price > stop_loss:
        m.stop_distance_pct = round((snap.price - stop_loss) / snap.price * 100.0, 2)
    m.rrr_value = snap.risk_reward
    m.rrr_quality = classify_rrr_quality(snap.risk_reward, min_rrr=th.min_rrr_quality)
    m.catalyst_confirmed = has_fresh_news and news_catalyst_score >= 40

    vwap_pts = _vwap_quality_pts(snap)
    m.confluence_quality_score = compute_confluence_quality_score(
        snap=snap,
        price_holding=m.price_holding_score,
        vol_efficiency=m.volume_efficiency_score,
        vwap_pts=vwap_pts,
        compression_q=m.compression_quality,
        resistance_q=m.resistance_quality,
        entry_loc=m.entry_location_score,
        liq_consistency=m.liquidity_consistency,
        spread_stab=m.spread_stability,
        persist_min=persist_min,
        weights=w,
    )

    hl_broken = False
    if len(bars) >= 2:
        if float(bars["low"].iloc[-1]) < float(bars["low"].iloc[-2]) and snap.micro_higher_lows:
            hl_broken = True

    passed, blocks = apply_quality_thresholds(
        price_holding=m.price_holding_score,
        liquidity_score=snap.liquidity_score,
        rrr_value=m.rrr_value,
        stop_distance_pct=m.stop_distance_pct,
        rejection_score=m.rejection_score,
        breakout_failure_risk=m.breakout_failure_risk,
        volume_efficiency=m.volume_efficiency_score,
        entry_location=m.entry_location_score,
        spread_stability=m.spread_stability,
        liquidity_consistency=m.liquidity_consistency,
        confluence_quality=m.confluence_quality_score,
        catalyst_confirmed=m.catalyst_confirmed,
        higher_low_broken=hl_broken,
        thresholds=th,
    )
    if fast_watch_locked and snap.volume_acceleration_1m >= STAGE_VOL_ACCEL_MIN:
        blocks = [b for b in blocks if not b.startswith("churn_volume_")]
        passed = len(blocks) == 0
    m.block_reasons = blocks
    m.quality_gate_passed = passed

    if m.quality_gate_passed:
        m.quality_factors = [
            f"ConfluenceQuality: {m.confluence_quality_score:.0f}",
            f"PriceHolding: {m.price_holding_score:.0f}",
            f"VolEfficiency: {m.volume_efficiency_score:.0f}",
            f"Rejection: {m.rejection_score:.0f}",
            f"SpreadStability: {m.spread_stability:.0f}",
            f"EntryLocation: {m.entry_location_score:.0f}",
            f"RRR: {m.rrr_quality} ({m.rrr_value:.1f})",
        ]

    return m
