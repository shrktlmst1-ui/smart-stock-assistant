"""Best opportunities — Pre-Move Predictor + Premarket Scanner pipeline."""

from __future__ import annotations

import logging

from analysis.pre_move_scorer import status_rank
from analysis.pre_move_stage_progression import stage_rank_for_sort
from models.pre_move import PreMoveScanResult, PreMoveSignal
from models.premarket_opportunity import PremarketOpportunitySignal, PremarketScanResult
from models.scanner import MarketScanState, OpportunitiesResponse
from models.stock import StockOpportunity
from services.market_session import session_explanation
from services.pre_move_predictor_service import get_last_pre_move_scan, sync_pre_move_scan
from services.premarket_opportunity_scanner import (
    get_last_premarket_scan,
    sync_premarket_scanner,
)

logger = logging.getLogger(__name__)

PREMARKET_EMPTY_TITLE = "لا توجد فرصة دخول فعلية الآن"
PREMARKET_EMPTY_SUB = "يتم مراقبة السوق لحظياً بحثاً عن اختراق أو ارتداد مؤكد"


def _format_premarket_reason(pm: PremarketOpportunitySignal) -> str:
    parts: list[str] = []
    if pm.status == "CONFIRMED_ENTRY":
        if pm.entry > 0:
            parts.append(f"دخول: {pm.entry:.2f}")
        if pm.stop_loss > 0:
            parts.append(f"وقف: {pm.stop_loss:.2f}")
        if pm.tp1 > 0:
            parts.append(f"هدف 1: {pm.tp1:.2f}")
        if pm.tp2 > 0:
            parts.append(f"هدف 2: {pm.tp2:.2f}")
        if pm.risk_reward > 0:
            parts.append(f"R:R: {pm.risk_reward:.1f}")
    elif pm.status == "EARLY_MOMENTUM":
        if pm.early_entry_zone > 0:
            parts.append(f"منطقة مبكرة: {pm.early_entry_zone:.2f}")
        if pm.invalidation_level > 0:
            parts.append(f"إبطال: {pm.invalidation_level:.2f}")
        if pm.distance_to_premarket_high > 0:
            parts.append(f"بعد عن القمة: {pm.distance_to_premarket_high:.1f}%")
        if pm.volume_acceleration > 0:
            parts.append(f"تسارع حجم: {pm.volume_acceleration:.1f}x")
    if pm.reason:
        parts.append(f"السبب: {pm.reason}")
    return " | ".join(parts)


def premarket_to_stock_opportunity(
    pm: PremarketOpportunitySignal,
    *,
    name: str = "",
) -> StockOpportunity:
    is_confirmed = pm.status == "CONFIRMED_ENTRY"
    return StockOpportunity(
        symbol=pm.symbol,
        name=name or pm.symbol,
        price=pm.current_price,
        change_percent=pm.premarket_change_percent,
        score=0,
        trend="صاعد" if pm.premarket_change_percent > 0.5 else "محايد",
        risk_level="مرتفع",
        status="شراء" if is_confirmed else "انتظار",
        ai_signal=pm.status if pm.status in ("CONFIRMED_ENTRY", "EARLY_MOMENTUM") else (pm.trigger_type or "Wait"),
        confidence=0.0,
        confirmed_factors=0,
        total_factors=17,
        safety_passed=is_confirmed,
        status_reason_ar=_format_premarket_reason(pm),
    )


def pre_move_to_stock_opportunity(sig: PreMoveSignal, *, name: str = "") -> StockOpportunity:
    is_entry = sig.status in ("EARLY_ENTRY", "HIGH_CONVICTION_EARLY", "CONFIRMED_ENTRY")
    parts: list[str] = []
    if sig.emoji:
        parts.append(sig.emoji)
    parts.append(f"PreMove {sig.pre_move_score}/100")
    if sig.stage_progression.stage_progression_score > 0:
        parts.append(f"StageProg {sig.stage_progression.stage_progression_score:.0f}")
    if sig.stage_progression.persistence_minutes > 0:
        parts.append(f"Persist {sig.stage_progression.persistence_minutes}m")
    if sig.first_detected_price > 0:
        parts.append(f"أول رصد: ${sig.first_detected_price:.2f}")
    rvol = sig.volume.rvol_same_time if sig.volume.rvol_same_time is not None else sig.volume.rvol
    if rvol > 0:
        parts.append(f"RVOL {rvol:.1f}x")
    if sig.volume.volume_acceleration > 0:
        parts.append(f"Vol accel {sig.volume.volume_acceleration:.1f}x")
    if sig.vwap.vwap_reclaim:
        parts.append("VWAP RECLAIMED")
    elif sig.vwap.vwap_hold:
        parts.append("VWAP HOLD")
    if sig.trigger_price > 0:
        parts.append(f"Trigger: ${sig.trigger_price:.2f}")
    if sig.entry_low > 0 and sig.entry_high > 0:
        parts.append(f"Entry: ${sig.entry_low:.2f}–${sig.entry_high:.2f}")
    if sig.stop_loss > 0:
        parts.append(f"Stop: ${sig.stop_loss:.2f}")
    if sig.tp1 > 0:
        parts.append(f"TP1: ${sig.tp1:.2f}")
    if sig.tp2 > 0:
        parts.append(f"TP2: ${sig.tp2:.2f}")
    if sig.risk_reward > 0:
        parts.append(f"R:R {sig.risk_reward:.1f}")
    if sig.reason:
        parts.append(f"Reason: {sig.reason}")

    return StockOpportunity(
        symbol=sig.symbol,
        name=name or sig.name or sig.symbol,
        price=sig.current_price,
        change_percent=sig.change_percent,
        score=max(sig.pre_move_score, int(sig.stage_progression.stage_progression_score)),
        trend="صاعد" if sig.change_percent > 0.5 else "محايد",
        risk_level=sig.risk_level,
        status="شراء" if is_entry and sig.timing != "LATE" else "انتظار",
        ai_signal=sig.status,
        confidence=0.0,
        confirmed_factors=0,
        total_factors=17,
        safety_passed=is_entry and sig.liquidity.liquidity_score >= 40,
        status_reason_ar=" | ".join(parts),
    )


def _resolve_name(symbol: str, state: MarketScanState | None) -> str:
    if not state:
        return symbol
    for snap in state.snapshots:
        if snap.symbol.upper() == symbol.upper():
            return snap.name or symbol
    return symbol


def _merge_opportunities(
    pre_move_signals: list[PreMoveSignal],
    premarket_signals: list[PremarketOpportunitySignal],
    *,
    limit: int,
    state: MarketScanState | None,
) -> list[StockOpportunity]:
    by_symbol: dict[str, StockOpportunity] = {}

    ranked_pre_move = sorted(
        pre_move_signals,
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

    for sig in ranked_pre_move:
        if sig.status in ("NO_SETUP", "TOO_LATE_TO_CHASE", "INSUFFICIENT_DATA", "FAILED_SETUP"):
            continue
        by_symbol[sig.symbol.upper()] = pre_move_to_stock_opportunity(
            sig, name=_resolve_name(sig.symbol, state),
        )

    for pm in premarket_signals:
        sym = pm.symbol.upper()
        if sym in by_symbol:
            existing = by_symbol[sym]
            if pm.status == "CONFIRMED_ENTRY" and status_rank("CONFIRMED_ENTRY") >= status_rank(existing.ai_signal):  # type: ignore[arg-type]
                by_symbol[sym] = premarket_to_stock_opportunity(pm, name=_resolve_name(sym, state))
                by_symbol[sym].score = max(existing.score, by_symbol[sym].score)
            continue
        if pm.status in ("CONFIRMED_ENTRY", "EARLY_MOMENTUM"):
            by_symbol[sym] = premarket_to_stock_opportunity(pm, name=_resolve_name(sym, state))

    ranked = sorted(
        by_symbol.values(),
        key=lambda o: (
            status_rank(o.ai_signal),  # type: ignore[arg-type]
            o.score,
        ),
        reverse=True,
    )
    return ranked[:limit]


def build_premarket_opportunities_response(
    scan: PremarketScanResult,
    *,
    limit: int = 20,
    state: MarketScanState | None = None,
    session: str = "PRE_MARKET",
) -> OpportunitiesResponse:
    """Premarket-only response (tests / legacy)."""
    opportunities = _merge_opportunities([], scan.opportunities, limit=limit, state=state)
    return OpportunitiesResponse(
        market_status=session,  # type: ignore[arg-type]
        opportunities=opportunities,
        watchlist_candidates=[],
        explanation=session_explanation(session),  # type: ignore[arg-type]
        no_signal_reason=(
            f"{PREMARKET_EMPTY_TITLE}\n{PREMARKET_EMPTY_SUB}"
            if not opportunities else scan.message
        ),
        debug=state.debug if state else None,
    )


def build_opportunities_from_scans(
    pre_move: PreMoveScanResult,
    premarket: PremarketScanResult,
    *,
    limit: int = 20,
    state: MarketScanState | None = None,
    session: str = "PRE_MARKET",
) -> OpportunitiesResponse:
    """Merge cached scan results — no Polygon calls."""
    opportunities = _merge_opportunities(
        pre_move.signals,
        premarket.opportunities,
        limit=limit,
        state=state,
    )

    message = premarket.message if premarket.opportunities else pre_move.message

    return OpportunitiesResponse(
        market_status=session,  # type: ignore[arg-type]
        opportunities=opportunities,
        watchlist_candidates=[],
        explanation=session_explanation(session),  # type: ignore[arg-type]
        no_signal_reason=(
            f"{PREMARKET_EMPTY_TITLE}\n{PREMARKET_EMPTY_SUB}"
            if not opportunities
            else message
        ),
        debug=state.debug if state else None,
    )


def run_opportunities_scans(
    snapshot_raw: dict | None,
    session: str,
) -> tuple[PreMoveScanResult, PremarketScanResult, bool, int]:
    """Run Pre-Move + Premarket scans (background only). Returns (pre_move, premarket, partial, failed)."""
    import time

    from services.perf_utils import perf_timer

    partial = False
    failed = 0

    with perf_timer("fast_scan", session=session):
        t0 = time.monotonic()
        try:
            pre_move = sync_pre_move_scan(snapshot_raw)
        except Exception as exc:
            logger.warning("Pre-Move scan failed: %s", type(exc).__name__)
            partial = True
            failed += 1
            cached = get_last_pre_move_scan()
            pre_move = cached if cached is not None else PreMoveScanResult(message="scan failed")

        if session == "PRE_MARKET":
            try:
                premarket = sync_premarket_scanner(snapshot_raw)
            except Exception as exc:
                logger.warning("Premarket scan failed: %s", type(exc).__name__)
                partial = True
                failed += 1
                cached_pm = get_last_premarket_scan()
                premarket = cached_pm or PremarketScanResult()
        else:
            premarket = PremarketScanResult()

        fast_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "[PERF] fast_scan_ms=%.0f deep_scan_ms=%.0f scanned=%d candidates=%d deep=%d",
            fast_ms,
            pre_move.stats.deep_duration_ms,
            pre_move.stats.scanned,
            pre_move.stats.early_candidates,
            pre_move.stats.deep_analyzed,
        )

    return pre_move, premarket, partial, failed


def build_best_opportunities_response(
    *,
    limit: int = 20,
    state: MarketScanState | None = None,
    session: str = "PRE_MARKET",
    snapshot_raw: dict | None = None,
) -> OpportunitiesResponse:
    """Full synchronous path — tests and forced refresh only."""
    pre_move, premarket, _, _ = run_opportunities_scans(snapshot_raw, session)
    response = build_opportunities_from_scans(
        pre_move, premarket, limit=limit, state=state, session=session,
    )
    logger.info(
        "BEST_OPPORTUNITIES source=PREMOVE_SCANNER count=%d premarket=%d session=%s",
        len(response.opportunities),
        len(premarket.opportunities),
        session,
    )
    return response


def get_best_opportunities_premarket(
    *,
    limit: int = 20,
    state: MarketScanState | None = None,
) -> OpportunitiesResponse:
    from services.market_scanner_service import market_scanner
    from services.snapshot_cache_service import get_opportunities_response

    session = state.market_status if state and state.market_status else "PRE_MARKET"
    return get_opportunities_response(
        limit=limit,
        state=state,
        session=session,
        trigger_refresh=True,
    )
