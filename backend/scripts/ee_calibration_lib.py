"""Multi-day EARLY_ENTRY calibration — causal, no look-ahead, no symbol-specific logic."""

from __future__ import annotations

import itertools
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from analysis.pre_move_early_entry_quality import (
    ConfluenceWeights,
    QualityGateThresholds,
    apply_quality_thresholds,
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
)

ET = ZoneInfo("America/New_York")


@dataclass
class EECandidate:
    """One timing-gate-pass moment — causal snapshot for offline threshold simulation."""

    symbol: str
    session_date: str
    bar_idx: int
    time_et: str
    price: float
    trigger_price: float
    stop_loss: float
    tp1: float
    tp2: float
    rrr: float
    liquidity_score: float
    price_holding: float
    confluence_quality: float
    rejection_score: float
    volume_efficiency: float
    breakout_failure_risk: float
    entry_location: float
    spread_stability: float
    liquidity_consistency: float
    stop_distance_pct: float
    catalyst_confirmed: bool
    higher_low_broken: bool = False
    ee_success: bool = False
    stop_hit: bool = False
    tp1_hit: bool = False
    tp2_hit: bool = False
    lead_time_min: float | None = None
    remaining_after_pct: float | None = None
    move_before_pct: float | None = None
    quality_blocks: list[str] = field(default_factory=list)
    session_had_pb: bool = False


def trading_days_before(end_date: str, count: int = 10) -> list[str]:
    """Walk backward skipping weekends — temporal order oldest first."""
    d = datetime.strptime(end_date, "%Y-%m-%d")
    days: list[str] = []
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return sorted(days)


def temporal_split(dates: list[str]) -> dict[str, list[str]]:
    n = len(dates)
    cal_end = max(1, int(n * 0.6))
    val_end = max(cal_end + 1, int(n * 0.8)) if n >= 5 else cal_end + 1
    return {
        "calibration": dates[:cal_end],
        "validation": dates[cal_end:val_end],
        "out_of_sample": dates[val_end:],
    }


def extract_candidates_from_timeline(
    symbol: str,
    session_date: str,
    timeline: list[dict],
    bars,
    *,
    base_price: float,
    session_high: float,
) -> list[EECandidate]:
    """Extract all timing-gate-pass PB windows + outcomes — causal only."""
    from scripts.replay_early_entry_validation import _outcome_after_ee

    candidates: list[EECandidate] = []
    pb_seen = any(t.get("lifecycle") == "PRE_BREAKOUT" for t in timeline)

    breakout_evt = next((t for t in timeline if t.get("lifecycle") == "BREAKOUT_CONFIRMED"), None)
    if not breakout_evt:
        breakout_evt = next((t for t in timeline if t.get("status") == "CONFIRMED_ENTRY"), None)

    for t in timeline:
        if not t.get("ee_timing_gate_passed"):
            continue
        if t.get("lifecycle") not in ("PRE_BREAKOUT", "EARLY_ENTRY"):
            continue

        outcome = _outcome_after_ee(
            bars, t["bar_idx"],
            stop=t.get("stop_loss", 0),
            tp1=t.get("tp1", 0),
            tp2=t.get("tp2", 0),
        )
        price = t["price"]
        favorable = session_high >= price * 1.03
        success = favorable and not outcome.get("stop_hit", False)

        lead = None
        if breakout_evt and t.get("time_et") and breakout_evt.get("time_et"):
            t0 = datetime.strptime(t["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            t1 = datetime.strptime(breakout_evt["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            lead = round((t1 - t0).total_seconds() / 60.0, 1)

        remaining = move_before = None
        if session_high > base_price > 0:
            total = session_high - base_price
            if total > 0:
                move_before = round((price - base_price) / total * 100, 1)
                remaining = round((session_high - price) / total * 100, 1)

        blocks = list(t.get("ee_quality_blocks") or t.get("ee_block_reasons") or [])
        hl_broken = any("higher_low_broken" in b for b in blocks)

        candidates.append(EECandidate(
            symbol=symbol,
            session_date=session_date,
            bar_idx=t["bar_idx"],
            time_et=t["time_et"],
            price=price,
            trigger_price=t.get("trigger_price", 0),
            stop_loss=t.get("stop_loss", 0),
            tp1=t.get("tp1", 0),
            tp2=t.get("tp2", 0),
            rrr=t.get("risk_reward", 0),
            liquidity_score=float(t.get("liquidity_score") or 0),
            price_holding=float(t.get("ee_price_holding") or t.get("price_holding_score") or 0),
            confluence_quality=float(t.get("ee_confluence_quality") or 0),
            rejection_score=float(t.get("ee_rejection_score") or 0),
            volume_efficiency=float(t.get("ee_volume_efficiency") or 0),
            breakout_failure_risk=float(t.get("ee_breakout_failure_risk") or 0),
            entry_location=float(t.get("ee_entry_location") or 0),
            spread_stability=float(t.get("ee_spread_stability") or 0),
            liquidity_consistency=float(t.get("ee_liquidity_consistency") or 0),
            stop_distance_pct=float(t.get("ee_stop_distance_pct") or 0),
            catalyst_confirmed=bool(t.get("ee_catalyst_confirmed")),
            higher_low_broken=hl_broken,
            ee_success=success,
            stop_hit=outcome.get("stop_hit", False),
            tp1_hit=outcome.get("tp1_hit", False),
            tp2_hit=outcome.get("tp2_hit", False),
            lead_time_min=lead,
            remaining_after_pct=remaining,
            move_before_pct=move_before,
            quality_blocks=blocks,
            session_had_pb=pb_seen,
        ))

    return candidates


def _first_ee_per_session(
    candidates: list[EECandidate],
    *,
    use_quality: bool,
    thresholds: QualityGateThresholds | None = None,
) -> list[EECandidate]:
    """First timing (or timing+quality) pass per symbol-day — no look-ahead."""
    th = thresholds or DEFAULT_THRESHOLDS
    by_key: dict[tuple[str, str], EECandidate] = {}

    for c in sorted(candidates, key=lambda x: x.bar_idx):
        key = (c.symbol, c.session_date)
        if key in by_key:
            continue
        if use_quality:
            ok, _ = apply_quality_thresholds(
                price_holding=c.price_holding,
                liquidity_score=c.liquidity_score,
                rrr_value=c.rrr,
                stop_distance_pct=c.stop_distance_pct,
                rejection_score=c.rejection_score,
                breakout_failure_risk=c.breakout_failure_risk,
                volume_efficiency=c.volume_efficiency,
                entry_location=c.entry_location,
                spread_stability=c.spread_stability,
                liquidity_consistency=c.liquidity_consistency,
                confluence_quality=c.confluence_quality,
                catalyst_confirmed=c.catalyst_confirmed,
                higher_low_broken=c.higher_low_broken,
                thresholds=th,
            )
            if not ok:
                continue
        by_key[key] = c
    return list(by_key.values())


def compute_kpis(
    candidates: list[EECandidate],
    *,
    use_quality: bool,
    thresholds: QualityGateThresholds | None = None,
    all_sessions: list[tuple[str, str]] | None = None,
) -> dict:
    """Aggregate KPIs from candidate pool."""
    ee = _first_ee_per_session(candidates, use_quality=use_quality, thresholds=thresholds)
    pb_keys = {(c.symbol, c.session_date) for c in candidates if c.session_had_pb}
    ee_ok = [c for c in ee if c.ee_success]
    ee_fp = [c for c in ee if not c.ee_success]

    leads = [c.lead_time_min for c in ee if c.lead_time_min is not None]
    remaining = [c.remaining_after_pct for c in ee if c.remaining_after_pct is not None]

    total_sessions = len(all_sessions) if all_sessions else len(pb_keys) or 1

    return {
        "total_pre_breakout": len(pb_keys),
        "total_early_entry": len(ee),
        "pb_to_ee_conversion": round(len(ee) / len(pb_keys), 3) if pb_keys else 0.0,
        "early_entry_precision": round(len(ee_ok) / len(ee), 3) if ee else 0.0,
        "early_entry_false_positive_rate": round(len(ee_fp) / total_sessions, 3) if total_sessions else 0.0,
        "stop_hit_rate_after_ee": round(sum(1 for c in ee if c.stop_hit) / len(ee), 3) if ee else 0.0,
        "tp1_hit_rate_after_ee": round(sum(1 for c in ee if c.tp1_hit) / len(ee), 3) if ee else 0.0,
        "tp2_hit_rate_after_ee": round(sum(1 for c in ee if c.tp2_hit) / len(ee), 3) if ee else 0.0,
        "median_ee_lead_time_min": statistics.median(leads) if leads else None,
        "median_remaining_after_ee_pct": statistics.median(remaining) if remaining else None,
        "ee_coverage": round(len(ee) / total_sessions, 3) if total_sessions else 0.0,
    }


def composite_objective(kpis: dict) -> float:
    """Multi-objective score — precision + low stops + timing preserved + coverage."""
    prec = kpis.get("early_entry_precision", 0)
    stop = kpis.get("stop_hit_rate_after_ee", 1)
    fp = kpis.get("early_entry_false_positive_rate", 1)
    conv = kpis.get("pb_to_ee_conversion", 0)
    lead = kpis.get("median_ee_lead_time_min") or 0
    rem = kpis.get("median_remaining_after_ee_pct") or 0
    ee_count = kpis.get("total_early_entry", 0)

    lead_score = min(lead / 10.0, 1.0) if lead else 0.3
    rem_score = min(rem / 80.0, 1.0) if rem else 0.3
    coverage_penalty = 0.0 if ee_count >= 2 else (2 - ee_count) * 0.15

    return (
        prec * 0.30
        + (1 - stop) * 0.25
        + (1 - fp) * 0.15
        + lead_score * 0.10
        + rem_score * 0.10
        + min(conv, 0.25) * 0.10
        - coverage_penalty
    )


def search_thresholds(
    cal_candidates: list[EECandidate],
    *,
    weights: ConfluenceWeights | None = None,
) -> tuple[QualityGateThresholds, ConfluenceWeights, float, dict]:
    """Grid search on calibration set only — market-wide thresholds."""
    w = weights or DEFAULT_WEIGHTS

    grid = {
        "min_confluence_quality": [52, 56, 60],
        "no_news_min_quality": [56, 60, 64],
        "min_price_holding_mandatory": [50, 54, 58],
        "max_rejection_score": [52, 58, 64],
        "max_breakout_failure_risk": [48, 54, 60],
        "min_entry_location": [48, 52, 56],
        "min_liquidity_mandatory": [40, 42, 45],
    }

    keys = list(grid.keys())
    best_score = -999.0
    best_th = DEFAULT_THRESHOLDS
    best_kpis: dict = {}

    for combo in itertools.product(*[grid[k] for k in keys]):
        params = dict(zip(keys, combo))
        th = QualityGateThresholds(**params)
        kpis = compute_kpis(cal_candidates, use_quality=True, thresholds=th)
        score = composite_objective(kpis)
        if score > best_score:
            best_score = score
            best_th = th
            best_kpis = kpis

    return best_th, w, best_score, best_kpis


def candidate_to_row(c: EECandidate, *, result: str, rejection: str = "") -> dict:
    return {
        "symbol": c.symbol,
        "session_date": c.session_date,
        "ee_time": c.time_et,
        "ee_price": c.price,
        "trigger": c.trigger_price,
        "stop": c.stop_loss,
        "tp1": c.tp1,
        "tp2": c.tp2,
        "rrr": c.rrr,
        "lead_time_min": c.lead_time_min,
        "confluence_quality": c.confluence_quality,
        "price_holding": c.price_holding,
        "volume_efficiency": c.volume_efficiency,
        "rejection_score": c.rejection_score,
        "result": result,
        "rejection_reason": rejection,
    }


def thresholds_to_config_dict(th: QualityGateThresholds, w: ConfluenceWeights) -> dict:
    return {
        "thresholds": asdict(th),
        "weights": asdict(w),
    }
