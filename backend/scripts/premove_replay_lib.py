"""Shared causal Pre-Move replay helpers — no look-ahead."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from analysis.pre_move_breakout import compute_breakout_metrics
from analysis.pre_move_compression import compute_compression_metrics
from analysis.pre_move_early_activity import (
    check_failed_setup,
    compute_early_activity_metrics,
    compute_signal_decay,
)
from analysis.pre_move_late_guard import compute_late_move_guard
from analysis.pre_move_levels import compute_trade_levels
from analysis.pre_move_liquidity import compute_liquidity_metrics
from analysis.pre_move_news import compute_news_metrics
from analysis.pre_move_scorer import compute_composite_score, compute_move_kpis
from analysis.pre_move_stage_progression import (
    build_snapshot,
    evaluate_stage_transition,
    lifecycle_to_status,
)
from analysis.pre_move_volume import compute_rvol_same_time, compute_volume_metrics
from analysis.pre_move_vwap import compute_vwap_metrics
from models.pre_move_stage import RollingStageState
from services.pre_move_stage_store import create_replay_state
from models.stock import NewsItem

ET = ZoneInfo("America/New_York")
MIN_BARS = 3


def filter_premarket_regular(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    et = df["timestamp"].dt.tz_convert(ET)
    mask = (
        ((et.dt.time >= datetime.strptime("04:00", "%H:%M").time()) & (et.dt.time < datetime.strptime("09:30", "%H:%M").time()))
        | ((et.dt.time >= datetime.strptime("09:30", "%H:%M").time()) & (et.dt.time < datetime.strptime("16:00", "%H:%M").time()))
    )
    return df.loc[mask].copy().reset_index(drop=True)


def parse_news(items: list[NewsItem], as_of: datetime) -> list[NewsItem]:
    out: list[NewsItem] = []
    for n in items:
        try:
            pub = datetime.fromisoformat(n.published_at.replace(" UTC", "").replace("Z", "+00:00"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub <= as_of:
                out.append(n)
        except Exception:
            continue
    return out


def analyze_causal_bar(
    bars: pd.DataFrame,
    prior_bars: pd.DataFrame | None,
    news_all: list[NewsItem],
    previous_close: float,
    bar_idx: int,
    *,
    peak_score: int = 0,
    minutes_since_peak: float = 0.0,
    had_early_watch: bool = False,
    stage_state: RollingStageState | None = None,
    session_date: str = "",
    quality_gate_enabled: bool = True,
    quality_thresholds=None,
    confluence_weights=None,
) -> dict:
    window = bars.iloc[: bar_idx + 1].copy()
    price = float(window["close"].iloc[-1])
    bar_ts = window["timestamp"].iloc[-1]
    if hasattr(bar_ts, "to_pydatetime"):
        bar_ts = bar_ts.to_pydatetime()
    if bar_ts.tzinfo is None:
        bar_ts = bar_ts.replace(tzinfo=timezone.utc)

    change_pct = (price - previous_close) / previous_close * 100.0 if previous_close > 0 else 0.0
    cum_vol = int(window["volume"].astype(float).sum())

    pm_mask = window["timestamp"].dt.tz_convert(ET).dt.time < datetime.strptime("09:30", "%H:%M").time()
    pm_bars = window.loc[pm_mask]
    reg_bars = window.loc[~pm_mask]
    pm_high = float(pm_bars["high"].max()) if not pm_bars.empty else 0.0
    day_high = float(reg_bars["high"].max()) if not reg_bars.empty else float(window["high"].max())

    last = window.iloc[-1]
    spread = round((float(last["high"]) - float(last["low"])) / price * 100.0, 2) if price else 0.5
    vol_1m = int(last["volume"])

    vol_metrics = compute_volume_metrics(window)
    vol_metrics.rvol_same_time = compute_rvol_same_time(window, prior_bars)
    compression = compute_compression_metrics(window, price)
    vwap_m = compute_vwap_metrics(window, price)
    breakout = compute_breakout_metrics(
        window, price, premarket_high=pm_high, day_high=day_high, prev_day_high=0.0,
    )
    liq = compute_liquidity_metrics(price, cum_vol, spread, bar_count=len(window))
    news_m = compute_news_metrics(parse_news(news_all, bar_ts), change_pct)

    early = compute_early_activity_metrics(
        window, price,
        vol_metrics=vol_metrics,
        compression=compression,
        breakout=breakout,
        spread_pct=spread,
        rvol_same_time=vol_metrics.rvol_same_time,
    )

    base_price = float(window["low"].astype(float).head(max(3, len(window) // 4)).min()) or price * 0.95
    trigger, entry_low, entry_high, stop, tp1, tp2, rrr = compute_trade_levels(price, breakout, window, vwap=vwap_m.vwap)

    late = compute_late_move_guard(
        window, price, change_pct,
        vwap=vwap_m.vwap,
        base_price=base_price,
        spread_percent=spread,
        risk_reward=rrr,
    )

    late_penalty = late.late_move_score * 0.15 if late.is_too_late else 0.0
    decay = compute_signal_decay(
        minutes_since_peak=minutes_since_peak,
        minutes_since_status=minutes_since_peak,
        peak_score=peak_score,
        current_raw_score=peak_score,
    )
    early.signal_decay = decay

    score, bd = compute_composite_score(
        vol_metrics, compression, vwap_m, breakout, news_m, liq,
        early_activity=early,
        bars=window, price=price,
        late_penalty=late_penalty,
        signal_decay=decay,
        change_pct=change_pct,
        too_late=late.is_too_late,
    )

    failed = check_failed_setup(
        window, early, base_price=base_price, price=price, had_early_watch=had_early_watch,
    )

    ts_iso = bar_ts.isoformat()
    if stage_state is None:
        stage_state = create_replay_state("REPLAY", session_date or ts_iso[:10])

    prior_snaps = stage_state.history()
    prior_peak = max((s.price for s in prior_snaps), default=price)
    if stage_state.base_price <= 0:
        stage_state.base_price = base_price
    prior_lows = [float(window["low"].iloc[i]) for i in range(max(0, len(window) - 4), len(window))]

    snap = build_snapshot(
        timestamp=ts_iso,
        price=price,
        change_pct=change_pct,
        pre_move_score=score,
        volume_acceleration_1m=early.volume_acceleration_1m,
        volume_acceleration_3m=early.volume_acceleration_3m,
        volume_acceleration_slope=early.volume_acceleration_slope,
        rvol=vol_metrics.rvol,
        rvol_same_time=vol_metrics.rvol_same_time,
        dollar_volume_growth=early.dollar_volume_growth,
        trade_velocity=early.trade_velocity,
        trade_velocity_growth=early.trade_count_growth,
        early_activity_score=early.early_activity_score,
        compression_score=compression.compression_score,
        range_compression_3m=early.range_compression_3m,
        micro_higher_lows=early.micro_higher_lows,
        higher_lows_score=compression.higher_lows_score,
        resistance_distance_pct=early.resistance_distance_pct,
        distance_to_breakout_pct=breakout.distance_to_breakout_pct,
        breakout_pressure=early.breakout_pressure_score,
        vwap_hold=vwap_m.vwap_hold,
        vwap_reclaim=vwap_m.vwap_reclaim,
        distance_from_vwap_pct=vwap_m.distance_from_vwap_pct,
        liquidity_score=liq.liquidity_score,
        spread_pct=spread,
        price_volume_response=early.price_volume_response,
        news_catalyst_score=news_m.news_catalyst_score,
        risk_reward=rrr,
        trigger_price=trigger,
        late_guard=late.is_too_late,
        failed_setup=failed,
        prior_peak_price=prior_peak,
        base_price=stage_state.base_price,
        prior_lows=prior_lows,
    )

    lifecycle, stage_metrics = evaluate_stage_transition(
        stage_state,
        snap,
        bars=window,
        stop_loss=stop,
        tp1=tp1,
        has_fresh_news=(
            news_m.news_catalyst_score >= 40
            and not news_m.news_already_priced_in
            and (news_m.news_recency_minutes is None or news_m.news_recency_minutes <= 120)
        ),
        news_catalyst_score=news_m.news_catalyst_score,
        quality_gate_enabled=quality_gate_enabled,
        quality_thresholds=quality_thresholds,
        confluence_weights=confluence_weights,
    )
    stage_state.append(snap)
    if lifecycle != stage_state.current_stage:
        stage_state.stage_entered_at = ts_iso
        stage_state.minutes_in_stage = 0.0
        if lifecycle != "PRE_BREAKOUT":
            stage_state.pb_consecutive_windows = 0
    else:
        stage_state.minutes_in_stage += 1.0
    stage_state.current_stage = lifecycle
    stage_state.peak_progression_score = max(stage_state.peak_progression_score, stage_metrics.stage_progression_score)
    if lifecycle in ("EARLY_WATCH", "PRE_BREAKOUT", "EARLY_ENTRY") and not stage_state.first_detected_at:
        stage_state.first_detected_at = ts_iso
        stage_state.first_detected_price = price

    status = lifecycle_to_status(
        lifecycle,
        progression_score=stage_metrics.stage_progression_score,
        persistence_minutes=stage_metrics.persistence_minutes,
    )

    trade_vel = early.trade_velocity
    trade_label = round(trade_vel, 1) if trade_vel is not None else "DATA_UNAVAILABLE"

    return {
        "bar_idx": bar_idx,
        "time_et": bar_ts.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S"),
        "price": round(price, 4),
        "volume_1m": vol_1m,
        "change_pct": round(change_pct, 2),
        "volume_acceleration_1m": early.volume_acceleration_1m,
        "volume_acceleration_slope": early.volume_acceleration_slope,
        "rvol_same_time": vol_metrics.rvol_same_time,
        "trade_velocity": trade_label,
        "compression_3m": early.range_compression_3m,
        "micro_higher_lows": early.micro_higher_lows,
        "higher_lows_score": early.micro_higher_lows_score,
        "resistance_distance_pct": early.resistance_distance_pct,
        "early_activity_score": early.early_activity_score,
        "confluence_bonus": early.confluence_bonus,
        "confluence_factors": early.confluence_factors,
        "score": score,
        "status": status,
        "lifecycle": lifecycle,
        "stage_progression_score": stage_metrics.stage_progression_score,
        "momentum_persistence_score": stage_metrics.momentum_persistence_score,
        "persistence_minutes": stage_metrics.persistence_minutes,
        "signal_decay": stage_metrics.signal_decay,
        "progression_trend": stage_metrics.progression_trend,
        "trigger_readiness_score": stage_metrics.trigger_readiness_score,
        "move_from_base_pct": stage_metrics.move_from_base_pct,
        "pb_persistence_windows": stage_metrics.pb_persistence_windows,
        "resistance_approaching": stage_metrics.resistance_approaching,
        "ee_gate_passed": stage_metrics.ee_gate_passed,
        "ee_confidence": stage_metrics.ee_confidence,
        "ee_block_reasons": stage_metrics.ee_block_reasons,
        "ee_confluence_quality": stage_metrics.ee_confluence_quality,
        "ee_rejection_score": stage_metrics.ee_rejection_score,
        "ee_volume_efficiency": stage_metrics.ee_volume_efficiency,
        "ee_breakout_failure_risk": stage_metrics.ee_breakout_failure_risk,
        "ee_quality_factors": stage_metrics.ee_quality_factors,
        "ee_quality_blocks": stage_metrics.ee_quality_blocks,
        "ee_entry_location": stage_metrics.ee_entry_location,
        "ee_spread_stability": stage_metrics.ee_spread_stability,
        "ee_liquidity_consistency": stage_metrics.ee_liquidity_consistency,
        "ee_stop_distance_pct": stage_metrics.ee_stop_distance_pct,
        "ee_price_holding": stage_metrics.ee_price_holding,
        "ee_catalyst_confirmed": stage_metrics.ee_catalyst_confirmed,
        "liquidity_score": liq.liquidity_score,
        "price_holding_score": snap.price_holding_score,
        "ee_timing_gate_passed": stage_metrics.ee_timing_gate_passed,
        "trigger_price": trigger,
        "evidence_factors": stage_metrics.evidence_factors,
        "regression_signals": stage_metrics.regression_signals,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop,
        "tp1": tp1,
        "tp2": tp2,
        "risk_reward": rrr,
        "late_guard": late.is_too_late,
        "late_score": late.late_move_score,
        "late_reasons": late.reasons,
        "activity_deviation": early.activity_deviation_score,
        "price_volume_response": early.price_volume_response,
        "breakdown": bd.model_dump(),
    }


def replay_session(
    bars: pd.DataFrame,
    prior_bars: pd.DataFrame | None,
    news_all: list[NewsItem],
    previous_close: float,
    *,
    symbol: str = "REPLAY",
    session_date: str = "",
    quality_gate_enabled: bool = True,
    quality_thresholds=None,
    confluence_weights=None,
) -> list[dict]:
    timeline: list[dict] = []
    peak_score = 0
    had_watch = False
    peak_bar_idx = 0
    stage_state = create_replay_state(symbol, session_date or "replay")
    for i in range(MIN_BARS - 1, len(bars)):
        if timeline:
            peak_score = max(peak_score, timeline[-1]["score"])
            if timeline[-1]["status"] == "EARLY_WATCH" or timeline[-1].get("lifecycle") == "EARLY_WATCH":
                had_watch = True
            if timeline[-1]["score"] >= peak_score:
                peak_bar_idx = i - 1
        mins_since = max(0.0, (i - peak_bar_idx) * 1.0)
        timeline.append(
            analyze_causal_bar(
                bars, prior_bars, news_all, previous_close, i,
                peak_score=peak_score,
                minutes_since_peak=mins_since,
                had_early_watch=had_watch,
                stage_state=stage_state,
                session_date=session_date,
                quality_gate_enabled=quality_gate_enabled,
                quality_thresholds=quality_thresholds,
                confluence_weights=confluence_weights,
            )
        )
    return timeline


def summarize_replay(
    symbol: str,
    session_date: str,
    bars: pd.DataFrame,
    timeline: list[dict],
    previous_close: float,
) -> dict:
    base = float(bars["low"].min())
    session_high = float(bars["high"].max())

    first_detect = next(
        (t for t in timeline if t.get("lifecycle") in ("EARLY_WATCH", "PRE_BREAKOUT", "EARLY_ENTRY") or t["status"] == "EARLY_WATCH"),
        None,
    )
    early_watch = next((t for t in timeline if t.get("lifecycle") == "EARLY_WATCH" or t["status"] == "EARLY_WATCH"), None)
    pre_breakout = next((t for t in timeline if t.get("lifecycle") == "PRE_BREAKOUT" or t["status"] == "PRE_BREAKOUT"), None)
    early_entry = next(
        (t for t in timeline if t.get("lifecycle") == "EARLY_ENTRY" or t["status"] in ("EARLY_ENTRY", "HIGH_CONVICTION_EARLY")),
        None,
    )
    breakout_confirmed = next((t for t in timeline if t.get("lifecycle") == "BREAKOUT_CONFIRMED" or t["status"] == "CONFIRMED_ENTRY"), None)
    failed_setup = next((t for t in timeline if t.get("lifecycle") == "FAILED_SETUP" or t["status"] == "FAILED_SETUP"), None)
    too_late = next((t for t in timeline if t["status"] == "TOO_LATE_TO_CHASE"), None)
    late_guard_on = next((t for t in timeline if t["late_guard"]), None)

    breakout_evt = None
    for i in range(1, len(bars)):
        window = bars.iloc[: i + 1]
        prior_high = float(window["high"].iloc[:-1].max()) if len(window) > 1 else 0.0
        close = float(window["close"].iloc[-1])
        if prior_high > 0 and close > prior_high * 1.005:
            ts = window["timestamp"].iloc[-1]
            breakout_evt = {
                "time_et": ts.tz_convert(ET).strftime("%Y-%m-%d %H:%M:%S"),
                "price": round(close, 4),
            }
            break

    kpis = compute_move_kpis(
        base_price=base,
        detection_price=first_detect["price"] if first_detect else 0.0,
        session_high=session_high,
    )

    lead_min = None
    if first_detect and breakout_evt:
        t0 = datetime.strptime(first_detect["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        t1 = datetime.strptime(breakout_evt["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        lead_min = round((t1 - t0).total_seconds() / 60.0, 1)

    valid = first_detect is not None and (first_detect.get("price", 999) < session_high * 0.7)
    false_positive = (
        first_detect is not None
        and session_high < base * 1.08
        and first_detect["score"] >= 60
    )

    return {
        "symbol": symbol,
        "session_date": session_date,
        "base_price": round(base, 4),
        "session_high": session_high,
        "previous_close": previous_close,
        "first_detection_time": first_detect["time_et"] if first_detect else None,
        "first_detection_price": first_detect["price"] if first_detect else None,
        "first_detection_score": first_detect["score"] if first_detect else None,
        "early_watch_time": early_watch["time_et"] if early_watch else None,
        "early_watch_price": early_watch["price"] if early_watch else None,
        "pre_breakout_time": pre_breakout["time_et"] if pre_breakout else None,
        "pre_breakout_price": pre_breakout["price"] if pre_breakout else None,
        "early_entry_time": early_entry["time_et"] if early_entry else None,
        "early_entry_price": early_entry["price"] if early_entry else None,
        "breakout_confirmed_time": breakout_confirmed["time_et"] if breakout_confirmed else None,
        "breakout_confirmed_price": breakout_confirmed["price"] if breakout_confirmed else None,
        "failed_setup_time": failed_setup["time_et"] if failed_setup else None,
        "failed_setup_price": failed_setup["price"] if failed_setup else None,
        "breakout_time": breakout_evt["time_et"] if breakout_evt else None,
        "breakout_price": breakout_evt["price"] if breakout_evt else None,
        "late_guard_time": late_guard_on["time_et"] if late_guard_on else None,
        "late_guard_price": late_guard_on["price"] if late_guard_on else None,
        "too_late_time": too_late["time_et"] if too_late else None,
        "too_late_price": too_late["price"] if too_late else None,
        "lead_time_minutes": lead_min,
        "percent_move_before_detection": kpis["percent_move_before_detection"],
        "move_captured_before_detection_pct": kpis["move_captured_before_detection"],
        "valid_detection": valid,
        "false_positive": false_positive,
        "max_score": max((t["score"] for t in timeline), default=0),
        "timeline": timeline,
    }
