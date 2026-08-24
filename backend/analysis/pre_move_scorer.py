"""Pre-Move composite scorer and status classification."""

from __future__ import annotations

from config import (
    PREMOVE_WEIGHT_BREAKOUT,
    PREMOVE_WEIGHT_EARLY_ACTIVITY,
    PREMOVE_WEIGHT_LIQUIDITY,
    PREMOVE_WEIGHT_NEWS,
    PREMOVE_WEIGHT_STRUCTURE,
    PREMOVE_WEIGHT_VOLUME,
    PREMOVE_WEIGHT_VWAP,
)
from analysis.pre_move_breakout import score_breakout_pressure
from analysis.pre_move_compression import score_structure_component
from analysis.pre_move_early_activity import compute_pre_expansion_bonus, score_early_activity_component
from analysis.pre_move_liquidity import score_liquidity_component
from analysis.pre_move_news import score_news_component
from analysis.pre_move_volume import score_volume_component
from analysis.pre_move_vwap import score_vwap_component
from models.pre_move import (
    PreMoveBreakoutMetrics,
    PreMoveCompressionMetrics,
    PreMoveEarlyActivityMetrics,
    PreMoveLiquidityMetrics,
    PreMoveNewsMetrics,
    PreMoveScoreBreakdown,
    PreMoveStatus,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)

_STATUS_EMOJI = {
    "NO_SETUP": "",
    "EARLY_WATCH": "🟡",
    "PRE_BREAKOUT": "🟠",
    "EARLY_ENTRY": "🟢",
    "HIGH_CONVICTION_EARLY": "🔥",
    "TOO_LATE_TO_CHASE": "⚠️",
    "CONFIRMED_ENTRY": "✅",
    "INSUFFICIENT_DATA": "",
    "FAILED_SETUP": "🔴",
}


def classify_status(
    score: int,
    *,
    too_late: bool,
    failed_setup: bool = False,
) -> PreMoveStatus:
    if too_late:
        return "TOO_LATE_TO_CHASE"
    if failed_setup:
        return "FAILED_SETUP"
    if score >= 90:
        return "HIGH_CONVICTION_EARLY"
    if score >= 80:
        return "EARLY_ENTRY"
    if score >= 70:
        return "PRE_BREAKOUT"
    if score >= 60:
        return "EARLY_WATCH"
    return "NO_SETUP"


def compute_composite_score(
    volume: PreMoveVolumeMetrics,
    compression: PreMoveCompressionMetrics,
    vwap: PreMoveVwapMetrics,
    breakout: PreMoveBreakoutMetrics,
    news: PreMoveNewsMetrics,
    liquidity: PreMoveLiquidityMetrics,
    *,
    early_activity: PreMoveEarlyActivityMetrics | None = None,
    bars,
    price: float,
    late_penalty: float = 0.0,
    signal_decay: float = 0.0,
    change_pct: float = 0.0,
    too_late: bool = False,
) -> tuple[int, PreMoveScoreBreakdown]:
    early = early_activity or PreMoveEarlyActivityMetrics()
    bd = PreMoveScoreBreakdown(
        early_activity_max=PREMOVE_WEIGHT_EARLY_ACTIVITY,
        volume_max=PREMOVE_WEIGHT_VOLUME,
        structure_max=PREMOVE_WEIGHT_STRUCTURE,
        vwap_max=PREMOVE_WEIGHT_VWAP,
        breakout_pressure_max=PREMOVE_WEIGHT_BREAKOUT,
        news_max=PREMOVE_WEIGHT_NEWS,
        liquidity_max=PREMOVE_WEIGHT_LIQUIDITY,
    )

    bd.early_activity = score_early_activity_component(early, max_pts=PREMOVE_WEIGHT_EARLY_ACTIVITY)
    bd.volume = score_volume_component(volume, max_pts=PREMOVE_WEIGHT_VOLUME)
    bd.structure = score_structure_component(compression, bars, price, max_pts=PREMOVE_WEIGHT_STRUCTURE)
    bd.vwap = score_vwap_component(vwap, max_pts=PREMOVE_WEIGHT_VWAP)
    bd.breakout_pressure = score_breakout_pressure(breakout, max_pts=PREMOVE_WEIGHT_BREAKOUT)
    bd.news = score_news_component(news, max_pts=PREMOVE_WEIGHT_NEWS)
    bd.liquidity = score_liquidity_component(liquidity, max_pts=PREMOVE_WEIGHT_LIQUIDITY)

    bd.confluence_bonus = early.confluence_bonus
    bd.pre_expansion_bonus, _ = compute_pre_expansion_bonus(
        early, change_pct=change_pct, too_late=too_late,
    )
    bd.signal_decay = signal_decay

    if volume.rvol_same_time is None:
        bd.unavailable_factors.append("RVOL_SAME_TIME")
    for uf in early.unavailable_factors:
        if uf not in bd.unavailable_factors:
            bd.unavailable_factors.append(uf)

    raw = (
        bd.early_activity
        + bd.volume
        + bd.structure
        + bd.vwap
        + bd.breakout_pressure
        + bd.news
        + bd.liquidity
        + bd.confluence_bonus
        + bd.pre_expansion_bonus
        - late_penalty
        - signal_decay
    )
    score = max(0, min(100, int(round(raw))))
    bd.late_move_penalty = late_penalty
    return score, bd


def build_reason(
    volume: PreMoveVolumeMetrics,
    vwap: PreMoveVwapMetrics,
    breakout: PreMoveBreakoutMetrics,
    news: PreMoveNewsMetrics,
    *,
    compression: PreMoveCompressionMetrics | None = None,
    early: PreMoveEarlyActivityMetrics | None = None,
) -> str:
    parts: list[str] = []
    if early and early.volume_acceleration_1m >= 1.2:
        parts.append(f"Vol accel {early.volume_acceleration_1m:.1f}x")
    elif volume.volume_acceleration >= 1.2:
        parts.append(f"Volume acceleration {volume.volume_acceleration:.1f}x")
    rvol = volume.rvol_same_time if volume.rvol_same_time is not None else volume.rvol
    if rvol >= 1.2:
        parts.append(f"RVOL {rvol:.1f}x")
    if early and early.activity_deviation_score >= 0.3:
        parts.append("activity spike vs baseline")
    if vwap.vwap_reclaim:
        parts.append("VWAP reclaim")
    elif vwap.vwap_hold:
        parts.append("VWAP hold")
    if breakout.distance_to_breakout_pct > 0:
        parts.append(f"{breakout.distance_to_breakout_pct:.1f}% below trigger")
    if early and early.micro_higher_lows:
        parts.append("micro higher lows")
    elif compression and compression.higher_lows_score >= 0.5:
        parts.append("higher lows")
    if early and early.volume_rising_inside_compression:
        parts.append("compression + rising vol")
    elif compression and compression.compression_score >= 0.4:
        parts.append("tight consolidation")
    if news.news_catalyst_score >= 40 and not news.news_already_priced_in:
        parts.append("fresh catalyst")
    if early and early.confluence_factors:
        parts.append(f"confluence ({', '.join(early.confluence_factors[:3])})")
    return " + ".join(parts) if parts else "Early activity building"


def status_emoji(status: PreMoveStatus) -> str:
    return _STATUS_EMOJI.get(status, "")


def status_rank(status: PreMoveStatus) -> int:
    order = {
        "HIGH_CONVICTION_EARLY": 5,
        "EARLY_ENTRY": 4,
        "PRE_BREAKOUT": 3,
        "EARLY_WATCH": 2,
        "CONFIRMED_ENTRY": 1,
        "NO_SETUP": 0,
        "TOO_LATE_TO_CHASE": -1,
        "INSUFFICIENT_DATA": -2,
        "FAILED_SETUP": -3,
    }
    return order.get(status, 0)


def compute_move_kpis(
    *,
    base_price: float,
    detection_price: float,
    session_high: float,
) -> dict[str, float | None]:
    """Move Captured Before Detection KPI."""
    if base_price <= 0 or detection_price <= 0 or session_high <= base_price:
        return {"percent_move_before_detection": None, "move_captured_before_detection": None}
    total_move = session_high - base_price
    move_before = max(0.0, detection_price - base_price)
    pct = round(move_before / total_move * 100.0, 1) if total_move > 0 else 0.0
    pct_from_base = round((detection_price - base_price) / base_price * 100.0, 2)
    return {
        "percent_move_before_detection": pct_from_base,
        "move_captured_before_detection": pct,
    }
