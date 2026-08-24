"""Pre-Move Predictor — production pipeline integrated with market scanner."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from analysis.pre_move_breakout import compute_breakout_metrics
from analysis.pre_move_compression import compute_compression_metrics
from analysis.pre_move_early_activity import (
    check_failed_setup,
    compute_early_activity_metrics,
    compute_signal_decay,
    passes_early_activity_fast_gate,
)
from analysis.pre_move_late_guard import compute_late_move_guard
from analysis.pre_move_levels import compute_trade_levels
from analysis.pre_move_liquidity import compute_liquidity_metrics
from analysis.pre_move_news import compute_news_metrics
from analysis.pre_move_scorer import (
    build_reason,
    compute_composite_score,
    status_emoji,
    status_rank,
)
from analysis.pre_move_stage_progression import (
    build_snapshot,
    evaluate_stage_transition,
    lifecycle_to_status,
    stage_rank_for_sort,
)
from analysis.pre_move_volume import compute_rvol_same_time, compute_volume_metrics
from analysis.pre_move_vwap import compute_vwap_metrics
from config import (
    PREMOVE_CANDIDATE_LIMIT,
    PREMOVE_DATA_MAX_AGE_SECONDS,
    PREMOVE_DEEP_LIMIT,
    PREMOVE_ENABLED,
    PREMOVE_FAST_SCAN_LIMIT,
    PREMOVE_MIN_ANALYSIS_BARS,
    PREMOVE_MIN_LIQUIDITY_SCORE,
    PREMOVE_MIN_SCORE_DISPLAY,
    SCANNER_MAX_PRICE,
    SCANNER_MIN_PRICE,
)
from database.pre_move_db import upsert_prediction
from models.pre_move import PreMoveLifecycleEvent, PreMoveScanResult, PreMoveScanStats, PreMoveSignal
from models.stock import NewsItem
from services.extended_hours_gap_detector import _safe_float, is_eligible_extended_gap_symbol
from services.market_session import ET, get_us_market_session
from services.pre_move_stage_store import clear_stale_states, get_or_create_state, update_stage_state
from services.news_service import fetch_stock_news
from services.scanner_filters import parse_snapshot_item

logger = logging.getLogger(__name__)

def _normalize_snapshot(raw: dict[str, dict] | list[dict] | None) -> dict[str, dict]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    return {(i.get("ticker") or "").upper(): i for i in raw if i.get("ticker")}


_bar_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_last_result: PreMoveScanResult | None = None


def get_last_pre_move_scan() -> PreMoveScanResult | None:
    return _last_result


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _fetch_bars(client, symbol: str, session: str) -> pd.DataFrame:
    key = f"{symbol}:{session}"
    cached = _bar_cache.get(key)
    if cached and time.monotonic() - cached[0] < 60:
        return cached[1]
    if session == "PRE_MARKET":
        df = await client.get_premarket_minute_bars(symbol)
    else:
        df = await client.get_premarket_minute_bars(symbol)
    _bar_cache[key] = (time.monotonic(), df)
    if len(_bar_cache) > 200:
        oldest = sorted(_bar_cache.items(), key=lambda x: x[1][0])[:50]
        for k, _ in oldest:
            _bar_cache.pop(k, None)
    return df


def _fast_filter(snapshot_raw: dict[str, dict], limit: int) -> list[dict[str, Any]]:
    """Stage 1–2: fast universe scan + early activity detection."""
    rows: list[dict[str, Any]] = []
    scanned = 0
    for sym, item in snapshot_raw.items():
        if scanned >= limit:
            break
        if not is_eligible_extended_gap_symbol(sym, item):
            continue
        scanned += 1
        metrics = parse_snapshot_item(item)
        if not metrics:
            continue
        if metrics.price < SCANNER_MIN_PRICE or metrics.price > SCANNER_MAX_PRICE:
            continue
        activity = (
            metrics.change_percent >= 3.0
            or metrics.premarket_change_pct >= 5.0
            or metrics.relative_volume >= 1.2
            or metrics.volume_spike
            or abs(metrics.change_percent) >= 2.0
            or metrics.premarket_change_pct >= 1.5
            or (metrics.relative_volume >= 1.05 and abs(metrics.change_percent) >= 1.0)
            or (metrics.premarket_change_pct >= 1.0 and metrics.relative_volume >= 1.1)
        )
        if not activity:
            continue
        rows.append({
            "symbol": metrics.symbol,
            "name": metrics.name,
            "price": metrics.price,
            "change_percent": metrics.change_percent or metrics.premarket_change_pct,
            "volume": metrics.volume,
            "rvol": metrics.relative_volume,
            "spread_pct": metrics.spread_pct,
            "day_high": metrics.day_high,
            "prev_day_high": metrics.day_high,
            "premarket_change": metrics.premarket_change_pct,
            "item": item,
            "fast_score": metrics.composite_score,
        })
    rows.sort(key=lambda r: (r["change_percent"], r["rvol"], r["fast_score"]), reverse=True)
    return rows[:PREMOVE_CANDIDATE_LIMIT]


async def _deep_analyze(candidate: dict[str, Any], session: str) -> PreMoveSignal | None:
    from services.stock_service import get_client

    sym = candidate["symbol"]
    price = candidate["price"]
    change_pct = candidate["change_percent"]
    item = candidate["item"]
    now_iso = datetime.now(timezone.utc).isoformat()

    client = get_client()
    try:
        async with asyncio.timeout(20):
            bars = await _fetch_bars(client, sym, session)
            nbbo: dict = {}
            try:
                nbbo = await client.get_last_nbbo(sym)
            except Exception:
                pass
            prior_bars: pd.DataFrame | None = None
            try:
                from datetime import timedelta
                prior_date = (datetime.now(ET) - timedelta(days=1)).strftime("%Y-%m-%d")
                prior_bars = await client.get_minute_bars_on_date(sym, prior_date)
            except Exception:
                prior_bars = None
            news_items: list[NewsItem] = []
            try:
                from services.news_service import fetch_stock_news
                news_items = await fetch_stock_news(client, sym, limit=5)
            except Exception:
                news_items = []
    except (asyncio.TimeoutError, TimeoutError):
        logger.debug("[PREMOVE] %s deep analyze timeout — skip", sym)
        return None
    except Exception as exc:
        logger.debug("[PREMOVE] %s analyze failed: %s", sym, type(exc).__name__)
        return None

    if bars.empty or len(bars) < PREMOVE_MIN_ANALYSIS_BARS:
        return PreMoveSignal(
            signal_id=f"{sym}:{now_iso[:10]}",
            symbol=sym,
            name=candidate.get("name", sym),
            current_price=price,
            change_percent=change_pct,
            status="INSUFFICIENT_DATA",
            rejection_reason="INSUFFICIENT_DATA",
            data_timestamp=now_iso,
        )

    pre = item.get("preMarket") or {}
    day = item.get("day") or {}
    prev = item.get("prevDay") or {}
    pm_high = _safe_float(pre.get("h"))
    day_high = _safe_float(day.get("h"), candidate.get("day_high", 0))
    prev_high = _safe_float(prev.get("h"), 0)

    bid = _safe_float(nbbo.get("p") or nbbo.get("bid"))
    ask = _safe_float(nbbo.get("P") or nbbo.get("ask"))
    spread = candidate.get("spread_pct", 0.5)
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread = round((ask - bid) / mid * 100, 2) if mid else spread

    vol_metrics = compute_volume_metrics(bars)
    vol_metrics.rvol_same_time = compute_rvol_same_time(bars, prior_bars)

    compression = compute_compression_metrics(bars, price)
    vwap_m = compute_vwap_metrics(bars, price)
    breakout = compute_breakout_metrics(
        bars, price,
        premarket_high=pm_high,
        day_high=day_high,
        prev_day_high=prev_high,
    )
    liq = compute_liquidity_metrics(price, int(candidate.get("volume", 0)), spread, bar_count=len(bars))
    news_m = compute_news_metrics(news_items, change_pct)

    early = compute_early_activity_metrics(
        bars, price,
        vol_metrics=vol_metrics,
        compression=compression,
        breakout=breakout,
        spread_pct=spread,
        rvol_same_time=vol_metrics.rvol_same_time,
    )

    if not passes_early_activity_fast_gate(early, vol_metrics=vol_metrics, has_fresh_news=news_m.news_catalyst_score >= 40):
        if change_pct < 2.0 and vol_metrics.volume_acceleration_1m < 1.3:
            pass  # still analyze — gate is for scanner prioritization only

    base_price = float(bars["low"].astype(float).head(max(5, len(bars) // 4)).min()) or price * 0.95
    trigger, entry_low, entry_high, stop, tp1, tp2, rrr = compute_trade_levels(
        price, breakout, bars, vwap=vwap_m.vwap,
    )

    late = compute_late_move_guard(
        bars, price, change_pct,
        vwap=vwap_m.vwap,
        base_price=base_price,
        spread_percent=spread,
        risk_reward=rrr,
    )

    late_penalty = late.late_move_score * 0.15 if late.is_too_late else 0.0
    decay = compute_signal_decay(
        minutes_since_peak=0.0,
        minutes_since_status=0.0,
        peak_score=0,
        current_raw_score=0,
    )
    early.signal_decay = decay
    score, breakdown = compute_composite_score(
        vol_metrics, compression, vwap_m, breakout, news_m, liq,
        early_activity=early,
        bars=bars, price=price, late_penalty=late_penalty, signal_decay=decay,
        change_pct=change_pct, too_late=late.is_too_late,
    )

    failed = check_failed_setup(
        bars, early, base_price=base_price, price=price, had_early_watch=False,
    )

    session_date = now_iso[:10]
    stage_state = get_or_create_state(sym, session_date)
    prior_snaps = stage_state.history()
    prior_peak = max((s.price for s in prior_snaps), default=price)
    if stage_state.base_price <= 0:
        stage_state.base_price = base_price
    prior_lows = [float(bars["low"].iloc[i]) for i in range(max(0, len(bars) - 4), len(bars))]

    snap = build_snapshot(
        timestamp=now_iso,
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

    new_lifecycle, stage_metrics = evaluate_stage_transition(
        stage_state,
        snap,
        bars=bars,
        stop_loss=stop,
        tp1=tp1,
        has_fresh_news=(
            news_m.news_catalyst_score >= 40
            and not news_m.news_already_priced_in
            and (news_m.news_recency_minutes is None or news_m.news_recency_minutes <= 120)
        ),
        news_catalyst_score=news_m.news_catalyst_score,
    )
    stage_state = update_stage_state(sym, session_date, snap, new_lifecycle, stage_metrics)

    status = lifecycle_to_status(
        new_lifecycle,
        progression_score=stage_metrics.stage_progression_score,
        persistence_minutes=stage_metrics.persistence_minutes,
    )
    timing = "LATE" if late.is_too_late else (
        "EARLY" if new_lifecycle in ("EARLY_ENTRY", "PRE_BREAKOUT") else "NORMAL"
    )

    risk = "منخفض" if liq.liquidity_score >= 70 and spread <= 1.0 else (
        "مرتفع" if spread > 2.0 or liq.liquidity_score < 50 else "متوسط"
    )

    reason = build_reason(vol_metrics, vwap_m, breakout, news_m, compression=compression, early=early)
    if late.is_too_late:
        reason = "⚠️ الحركة بدأت بالفعل — لا تطارد السهم"

    sig = PreMoveSignal(
        signal_id=f"{sym}:{now_iso[:10]}",
        symbol=sym,
        name=candidate.get("name", sym),
        current_price=round(price, 4),
        change_percent=round(change_pct, 2),
        pre_move_score=score,
        status=status,
        lifecycle=new_lifecycle if new_lifecycle != "DISCOVERED" else (
            status if status not in ("NO_SETUP", "INSUFFICIENT_DATA") else "DISCOVERED"
        ),
        timing=timing,
        emoji=status_emoji(status),
        first_detected_at=stage_state.first_detected_at or now_iso,
        first_detected_price=round(stage_state.first_detected_price or price, 4),
        first_detected_score=score,
        trigger_price=trigger,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop,
        tp1=tp1,
        tp2=tp2,
        risk_reward=rrr,
        volume=vol_metrics,
        early_activity=early,
        compression=compression,
        vwap=vwap_m,
        breakout=breakout,
        news=news_m,
        liquidity=liq,
        late_move=late,
        score_breakdown=breakdown,
        stage_progression=stage_metrics,
        risk_level=risk,
        reason=reason,
        data_timestamp=now_iso,
        data_age_seconds=0.0,
        lifecycle_history=[PreMoveLifecycleEvent(at=now_iso, status=status, score=score, price=price)],
    )

    ok, reject = validate_signal(sig)
    sig.validated = ok
    if not ok:
        sig.rejection_reason = reject
        if reject == "TOO_LATE_TO_CHASE":
            sig.status = "TOO_LATE_TO_CHASE"
            sig.emoji = status_emoji("TOO_LATE_TO_CHASE")

    if liq.liquidity_score < PREMOVE_MIN_LIQUIDITY_SCORE and status in (
        "EARLY_ENTRY", "HIGH_CONVICTION_EARLY", "PRE_BREAKOUT",
    ):
        sig.rejection_reason = "LOW_LIQUIDITY"
        sig.validated = False

    return sig


async def scan_pre_move_async(
    snapshot_raw: dict[str, dict] | None = None,
    *,
    deep_limit: int | None = None,
) -> PreMoveScanResult:
    from services.market_scanner_service import market_scanner

    t0 = time.monotonic()
    stats = PreMoveScanStats()
    session = get_us_market_session()

    if not PREMOVE_ENABLED:
        return PreMoveScanResult(message="Pre-Move Predictor disabled")

    raw = _normalize_snapshot(snapshot_raw if snapshot_raw is not None else market_scanner._snapshot_raw)
    if not raw:
        return PreMoveScanResult(message="No snapshot data")

    candidates = _fast_filter(raw, PREMOVE_FAST_SCAN_LIMIT)
    stats.scanned = min(len(raw), PREMOVE_FAST_SCAN_LIMIT)
    stats.early_candidates = len(candidates)

    deep_n = deep_limit or PREMOVE_DEEP_LIMIT
    to_analyze = candidates[:deep_n]

    signals: list[PreMoveSignal] = []
    rejected: list[PreMoveSignal] = []

    t_deep = time.monotonic()
    for cand in to_analyze:
        try:
            sig = await _deep_analyze(cand, session)
        except Exception as exc:
            logger.debug("[PREMOVE] %s analyze failed: %s", cand["symbol"], type(exc).__name__)
            continue
        if not sig:
            continue
        stats.deep_analyzed += 1

        if sig.status == "INSUFFICIENT_DATA":
            stats.insufficient_data += 1
            rejected.append(sig)
            continue
        if sig.rejection_reason == "LOW_LIQUIDITY":
            stats.rejected_liquidity += 1
            rejected.append(sig)
            continue
        if sig.status == "TOO_LATE_TO_CHASE":
            stats.too_late += 1
            rejected.append(sig)
            continue
        if not sig.validated and sig.rejection_reason:
            stats.rejected_validation += 1
            rejected.append(sig)
            continue

        if sig.status == "PRE_BREAKOUT" or sig.stage_progression.stage_lifecycle == "PRE_BREAKOUT":
            stats.pre_breakout += 1
        if sig.status in ("EARLY_ENTRY", "HIGH_CONVICTION_EARLY") or sig.stage_progression.stage_lifecycle == "EARLY_ENTRY":
            stats.early_entry += 1
        if sig.status == "HIGH_CONVICTION_EARLY":
            stats.high_conviction += 1

        stage_score = sig.stage_progression.stage_progression_score
        display_ok = (
            sig.status not in ("NO_SETUP", "INSUFFICIENT_DATA", "FAILED_SETUP")
            and (sig.pre_move_score >= PREMOVE_MIN_SCORE_DISPLAY or stage_score >= 32)
        )
        if display_ok:
            signals.append(sig)
            try:
                upsert_prediction({
                    "signal_id": sig.signal_id,
                    "symbol": sig.symbol,
                    "first_detected_at": sig.first_detected_at,
                    "first_detected_price": sig.first_detected_price,
                    "first_detected_score": sig.first_detected_score,
                    "pre_move_score": sig.pre_move_score,
                    "status": sig.status,
                    "lifecycle": sig.lifecycle,
                    "trigger_price": sig.trigger_price,
                    "entry_low": sig.entry_low,
                    "entry_high": sig.entry_high,
                    "stop_loss": sig.stop_loss,
                    "tp1": sig.tp1,
                    "tp2": sig.tp2,
                    "rvol": sig.volume.rvol,
                    "volume_acceleration": sig.volume.volume_acceleration,
                    "news_score": sig.news.news_catalyst_score,
                    "liquidity_score": sig.liquidity.liquidity_score,
                    "late_move_score": sig.late_move.late_move_score,
                    "reason": sig.reason,
                    "lifecycle_history": [e.model_dump() for e in sig.lifecycle_history],
                    "session_date": datetime.now(ET).strftime("%Y-%m-%d"),
                })
            except Exception as exc:
                logger.debug("[PREMOVE] db upsert %s: %s", sig.symbol, type(exc).__name__)

            logger.info(
                "[PREMOVE] %s score=%d trigger=%.4f late=%s",
                sig.symbol, sig.pre_move_score, sig.trigger_price, sig.late_move.is_too_late,
            )
        elif sig.rejection_reason:
            rejected.append(sig)
            logger.info("[PREMOVE] %s rejected reason=%s", sig.symbol, sig.rejection_reason)

    stats.deep_duration_ms = round((time.monotonic() - t_deep) * 1000, 1)
    stats.scan_duration_ms = round((time.monotonic() - t0) * 1000, 1)

    clear_stale_states()
    signals.sort(
        key=lambda s: (
            stage_rank_for_sort(
                s.stage_progression.stage_lifecycle,
                s.stage_progression.stage_progression_score,
                s.stage_progression.momentum_persistence_score,
                late_guard=s.late_move.is_too_late,
            ),
            status_rank(s.status),
            s.stage_progression.stage_progression_score,
            s.pre_move_score,
        ),
        reverse=True,
    )

    global _last_result
    result = PreMoveScanResult(
        signals=signals,
        rejected=rejected,
        stats=stats,
        message=f"{len(signals)} pre-move setups",
    )
    _last_result = result

    logger.info(
        "[PREMOVE] scanned=%d candidates=%d deep=%d early_entry=%d too_late=%d liq_reject=%d ms=%.0f",
        stats.scanned, stats.early_candidates, stats.deep_analyzed,
        stats.early_entry, stats.too_late, stats.rejected_liquidity, stats.scan_duration_ms,
    )
    return result


def sync_pre_move_scan(
    snapshot_raw: dict[str, dict] | None = None,
    *,
    deep_limit: int | None = None,
) -> PreMoveScanResult:
    try:
        return _run_async(scan_pre_move_async(snapshot_raw, deep_limit=deep_limit))
    except Exception as exc:
        logger.warning("[PREMOVE] scan failed: %s", type(exc).__name__)
        return PreMoveScanResult(message="Pre-Move scan failed")
