"""فرصة الآن — live confirmation engine + REST fallback."""

from __future__ import annotations

import logging

from analysis.early_upward_surge import fast_filter_surge_rank, neutral_surge_rank
from config import SCANNER_TICK_SECONDS
from models.opportunity_now import OpportunityNowResponse, OpportunityNowSignal
from models.pre_move import PreMoveSignal
from models.premarket_opportunity import PremarketOpportunitySignal, PremarketScanResult
from models.stock import StockSnapshot
from services.extended_hours_gap_detector import (
    ExtendedGapDetection,
    extended_gap_registry,
    sync_extended_gap_detector,
)
from services.display_buy_pressure_filter import (
    DISPLAY_JUMP_ALERT,
    DISPLAY_STRONG_BUY_WATCH,
    apply_display_verdict,
    evaluate_extended_gap_display,
    evaluate_jump_alert_display,
    evaluate_premove_display,
)
from services.real_jump_alert_layer import (
    REAL_JUMP_EXPLOSIVE_WAVE_PCT,
    apply_distinguished_jump_display,
    apply_real_jump_display,
    eligible_for_distinguished_jump_section,
    eligible_for_price_jump_section,
    eligible_premove,
    evaluate_opportunity_real_jump,
    evaluate_premove_real_jump,
    is_explosive_wave,
)
from services.jump_alert_registry import jump_alert_registry
from services.jump_engine_monitor import jump_engine_monitor
from services.live_confirmation_engine import (
    LIVE_MONITOR_POOL,
    STATUS_AR,
    live_confirmation_engine,
)
from services.market_scanner_service import market_scanner
from services.market_session import get_us_market_session, is_regular_session, session_explanation
from services.premarket_opportunity_scanner import get_last_premarket_scan
from services.opportunity_now_scoring import (
    SIGNAL_TTL_SECONDS,
    _snapshot_to_signal,
    reset_signal_cache,
)

from services.price_universe import passes_universe_price

logger = logging.getLogger(__name__)

_STAGE_RANK = {"EXPLOSIVE": 3, "ACTIVE": 2, "WATCH": 1}


def _jump_alert_to_signal(alert, *, session: str) -> OpportunityNowSignal:
    """Map jump_alert_registry entry to opportunity-now signal (same UI path as extended)."""
    status = "NOW"
    stage = alert.stage or alert.ai_signal or "EARLY_ENTRY"
    return OpportunityNowSignal(
        symbol=alert.symbol,
        name=alert.name or alert.symbol,
        price=round(alert.price, 4),
        change_percent=round(alert.change_percent, 2),
        score=float(alert.score),
        status=status,
        status_ar=STATUS_AR.get(status, status),
        opportunity_type=alert.ai_signal or stage,
        appeared_at=alert.created_at,
        expires_at=alert.expires_at,
        entry_zone=round((alert.entry_low + alert.entry_high) / 2, 4),
        entry_zone_low=alert.entry_low,
        entry_zone_high=alert.entry_high or alert.trigger_price,
        stop_loss=alert.stop_loss,
        target_1=alert.tp1,
        target_2=alert.tp2,
        risk_level="متوسط" if alert.score >= 70 else "مرتفع",
        risk_reward_ratio=alert.risk_reward,
        confirmed_factors=0,
        total_factors=17,
        consecutive_confirmations=max(alert.persistence_minutes, 0),
        reasons_ar=[alert.status_reason_ar] if alert.status_reason_ar else [f"PreMove {alert.score}/100"],
        cancellation_reasons_ar=[],
        late_entry_warning=alert.is_too_late,
        has_news_catalyst=False,
        data_timestamp=alert.created_at,
        data_age_seconds=0.0,
        session=session,
        detection_stage=stage,
        jump_alert_id=alert.alert_id,
        jump_qualified=alert.jump_qualified,
        jump_alert_created=alert.jump_alert_created,
        stage_lifecycle=stage,
        rvol=alert.rvol,
        volume_acceleration=alert.volume_acceleration,
        buy_pressure_score=neutral_surge_rank(
            session_change_pct=alert.change_percent,
            rvol=max(alert.rvol, 0.5),
        ),
    )


def _premove_to_opportunity_signal(sig: PreMoveSignal, *, session: str) -> OpportunityNowSignal:
    lifecycle = sig.stage_progression.stage_lifecycle or sig.lifecycle or sig.status
    status_map = {
        "EARLY_ENTRY": "NOW",
        "HIGH_CONVICTION_EARLY": "NOW",
        "PRE_BREAKOUT": "READY",
        "EARLY_WATCH": "WATCH",
    }
    status = status_map.get(sig.status, "WATCH")
    return OpportunityNowSignal(
        symbol=sig.symbol,
        name=sig.name or sig.symbol,
        price=round(sig.current_price, 4),
        change_percent=round(sig.change_percent, 2),
        score=float(sig.pre_move_score),
        status=status,  # type: ignore[arg-type]
        status_ar=STATUS_AR.get(status, status),
        opportunity_type=sig.status,
        appeared_at=sig.first_detected_at or sig.data_timestamp,
        expires_at="",
        entry_zone=round((sig.entry_low + sig.entry_high) / 2, 4),
        entry_zone_low=sig.entry_low,
        entry_zone_high=sig.entry_high,
        stop_loss=sig.stop_loss,
        target_1=sig.tp1,
        target_2=sig.tp2,
        risk_level=sig.risk_level,
        risk_reward_ratio=sig.risk_reward,
        confirmed_factors=len(sig.early_activity.confluence_factors),
        total_factors=17,
        consecutive_confirmations=0,
        reasons_ar=[sig.reason] if sig.reason else sig.early_activity.confluence_factors[:4],
        cancellation_reasons_ar=[],
        late_entry_warning=sig.late_move.is_too_late,
        data_timestamp=sig.data_timestamp,
        data_age_seconds=sig.data_age_seconds,
        session=session,
        stage_lifecycle=lifecycle,
        rvol=sig.volume.rvol,
        volume_acceleration=sig.volume.volume_acceleration_1m,
        display_type=sig.display_type,
        buy_pressure_score=sig.buy_pressure_score,
        confluence_count=sig.confluence_count,
        confluence_factors=list(sig.confluence_factors),
    )


def _collect_home_display_signals(session: str) -> list[OpportunityNowSignal]:
    """Strong real buying only — backend-confirmed first, max 3 under $10."""
    from services.pre_move_predictor_service import get_last_pre_move_scan

    seen: set[str] = set()
    out: list[OpportunityNowSignal] = []

    for alert_sig in _collect_jump_alerts(session):
        if not passes_universe_price(alert_sig.price) or alert_sig.change_percent <= 0:
            continue
        verdict = evaluate_jump_alert_display(alert_sig)
        if verdict.show:
            enriched = apply_display_verdict(alert_sig, verdict)
            sym = enriched.symbol.upper()
            if sym not in seen:
                out.append(enriched)
                seen.add(sym)

    scan = get_last_pre_move_scan()
    if scan:
        for pm in scan.signals:
            if not passes_universe_price(pm.current_price) or pm.change_percent <= 0:
                continue
            base = _premove_to_opportunity_signal(pm, session=session)
            if pm.display_confirmed and pm.display_type:
                verdict = evaluate_premove_display(pm)
                if verdict.show:
                    enriched = apply_display_verdict(base, verdict)
                    sym = enriched.symbol.upper()
                    if sym not in seen:
                        out.append(enriched)
                        seen.add(sym)
                continue
            verdict = evaluate_premove_display(pm)
            if not verdict.show:
                continue
            enriched = apply_display_verdict(base, verdict)
            sym = enriched.symbol.upper()
            if sym in seen:
                continue
            out.append(enriched)
            seen.add(sym)

    ext = _pick_extended_alert()
    if ext and passes_universe_price(ext.price) and ext.change_percent > 0:
        verdict = evaluate_extended_gap_display(ext)
        if verdict.show:
            enriched = apply_display_verdict(ext, verdict)
            sym = enriched.symbol.upper()
            if sym not in seen:
                out.append(enriched)
                seen.add(sym)

    out.sort(
        key=lambda s: (
            s.display_type == DISPLAY_JUMP_ALERT,
            s.buy_pressure_score,
            s.confluence_count,
            s.score,
        ),
        reverse=True,
    )
    return out[:3]


def _collect_real_jump_alerts(session: str) -> list[OpportunityNowSignal]:
    """REAL_JUMP_ALERT — independent layer above display_signals."""
    from services.jump_alert_registry import jump_alert_registry
    from services.pre_move_predictor_service import get_last_pre_move_scan

    seen: set[str] = set()
    out: list[OpportunityNowSignal] = []

    scan = get_last_pre_move_scan()
    if scan:
        for pm in scan.signals:
            if not eligible_premove(pm):
                continue
            verdict = evaluate_premove_real_jump(pm)
            wave = verdict.wave
            if not verdict.confirmed or not wave or not eligible_for_price_jump_section(
                verdict.kpi, current_move_pct=wave.current_move_pct,
            ):
                continue
            sym = pm.symbol.upper()
            if sym in seen:
                continue
            base = _premove_to_opportunity_signal(pm, session=session)
            out.append(apply_real_jump_display(base, verdict))
            seen.add(sym)

    for alert in jump_alert_registry.get_qualified_alerts():
        base = _jump_alert_to_signal(alert, session=session)
        if not passes_universe_price(base.price):
            continue
        sym = base.symbol.upper()
        if sym in seen:
            continue
        verdict = evaluate_opportunity_real_jump(base)
        wave = verdict.wave
        if not verdict.confirmed or not wave or not eligible_for_price_jump_section(
            verdict.kpi, current_move_pct=wave.current_move_pct,
        ):
            continue
        out.append(apply_real_jump_display(base, verdict))
        seen.add(sym)

    out.sort(
        key=lambda s: (
            is_explosive_wave(s.real_jump_current_move_pct),
            s.real_jump_current_move_pct,
            s.buy_pressure_score,
            s.confluence_count,
            s.score,
        ),
        reverse=True,
    )
    return out


def _collect_distinguished_jump_alerts(session: str) -> list[OpportunityNowSignal]:
    """قفزة سعرية مميزة — live wave >= 50% from move_start; no cap."""
    from services.jump_alert_registry import jump_alert_registry
    from services.pre_move_predictor_service import get_last_pre_move_scan

    seen: set[str] = set()
    out: list[OpportunityNowSignal] = []

    scan = get_last_pre_move_scan()
    if scan:
        for pm in scan.signals:
            if not eligible_premove(pm):
                continue
            verdict = evaluate_premove_real_jump(pm)
            wave = verdict.wave
            if not wave or not eligible_for_distinguished_jump_section(
                wave, current_price=pm.current_price,
            ):
                continue
            sym = pm.symbol.upper()
            if sym in seen:
                continue
            base = _premove_to_opportunity_signal(pm, session=session)
            out.append(apply_distinguished_jump_display(base, verdict))
            seen.add(sym)

    for alert in jump_alert_registry.get_qualified_alerts():
        base = _jump_alert_to_signal(alert, session=session)
        if not passes_universe_price(base.price):
            continue
        sym = base.symbol.upper()
        if sym in seen:
            continue
        verdict = evaluate_opportunity_real_jump(base)
        wave = verdict.wave
        if not wave or not eligible_for_distinguished_jump_section(
            wave, current_price=base.price,
        ):
            continue
        out.append(apply_distinguished_jump_display(base, verdict))
        seen.add(sym)

    out.sort(
        key=lambda s: (
            s.real_jump_current_move_pct,
            s.real_jump_move_start_time or "",
        ),
        reverse=True,
    )
    return out


def collect_display_pipeline_stats(session: str) -> dict:
    """Audit counters for live pipeline — WS → scan → display."""
    from services.live_price_registry import live_price_registry
    from services.pre_move_predictor_service import get_last_pre_move_scan
    from services.stocks_ws_hub import stocks_ws_hub

    scan = get_last_pre_move_scan()
    display_out = _collect_home_display_signals(session)
    rejects: dict[str, int] = {}

    if scan:
        for pm in scan.signals + scan.rejected:
            v = evaluate_premove_display(pm)
            if not v.show and pm.display_confirmed:
                rejects["backend_confirmed_but_filter_blocked"] = rejects.get("backend_confirmed_but_filter_blocked", 0) + 1
            elif not v.show:
                key = v.reject_reason or "unknown"
                rejects[key] = rejects.get(key, 0) + 1

    stats = scan.stats if scan else None
    strong = sum(1 for s in (scan.signals if scan else []) if s.display_type == DISPLAY_STRONG_BUY_WATCH)
    jumps = sum(1 for s in (scan.signals if scan else []) if s.display_type == DISPLAY_JUMP_ALERT)
    ew = sum(
        1 for s in (scan.signals if scan else [])
        if s.status == "EARLY_WATCH" or s.stage_progression.stage_lifecycle == "EARLY_WATCH"
    )
    pb = stats.pre_breakout if stats else 0
    ee = stats.early_entry if stats else 0
    too_late = stats.too_late if stats else 0

    return {
        "ws_connected": stocks_ws_hub.is_running,
        "ws_trades_received": live_price_registry.status.trades_received,
        "ws_symbols_with_ticks": len(live_price_registry.status.subscribed_symbols or []),
        "candidates": stats.early_candidates if stats else 0,
        "deep_analyzed": stats.deep_analyzed if stats else 0,
        "early_watch": ew,
        "pre_breakout": pb,
        "strong_buy_watch_backend": strong,
        "jump_qualified": ee,
        "jump_alert_backend": jumps,
        "too_late_to_chase": too_late,
        "display_signals_shown": len(display_out),
        "display_filter_rejects": rejects,
        "top_reject_reasons": sorted(rejects.items(), key=lambda x: -x[1])[:5],
    }


def _collect_jump_alerts(session: str) -> list[OpportunityNowSignal]:
    """Qualified REGULAR/PreMove jumps — unified DISPLAYED path."""
    out: list[OpportunityNowSignal] = []
    for alert in jump_alert_registry.get_qualified_alerts():
        sig = _jump_alert_to_signal(alert, session=session)
        if sig.price > 0 and sig.change_percent > 0 and sig.jump_qualified:
            out.append(sig)
    out.sort(key=lambda s: s.score, reverse=True)
    return out


def _collect_snapshots() -> list[StockSnapshot]:
    seen: set[str] = set()
    result: list[StockSnapshot] = []
    state = market_scanner.get_state()
    symbols: list[str] = list(market_scanner._rank_pool[:LIVE_MONITOR_POOL])

    if state:
        for row in state.top_opportunities + state.watchlist_candidates:
            symbols.append(row.symbol.upper())
        for snap in state.snapshots:
            symbols.append(snap.symbol.upper())
    for sym in market_scanner._candidate_symbols:
        symbols.append(sym.upper())

    for sym in dict.fromkeys(symbols):
        snap = market_scanner._snapshots.get(sym)
        if not snap and state:
            snap = next((s for s in state.snapshots if s.symbol.upper() == sym), None)
        if not snap or sym in seen:
            continue
        seen.add(sym)
        if snap.price > 0 and passes_universe_price(snap.price):
            result.append(snap)
    return result


def _risk_level(score: float, spread: float) -> str:
    if score >= 80 and spread <= 0.3:
        return "منخفض"
    if score >= 70:
        return "متوسط"
    return "مرتفع"


def _extended_fields(symbol: str) -> dict:
    det = extended_gap_registry.get(symbol)
    if not det:
        return {}
    session_label = "PRE_MARKET" if det.session == "PRE_MARKET" else "AFTER_HOURS"
    return {
        "session": session_label,
        "previous_close": det.previous_close,
        "extended_price": det.extended_price,
        "extended_gap_pct": det.extended_gap_pct,
        "extended_volume": det.extended_volume,
        "relative_volume": det.relative_volume,
        "catalyst_type": det.catalyst_type,
        "catalyst_title_ar": det.catalyst_title_ar,
        "catalyst_source": det.catalyst_source,
        "catalyst_published_at": det.catalyst_published_at,
        "detection_stage": det.detection_stage,
        "risk_flags_ar": det.risk_flags_ar,
        "detected_at": det.detected_at,
        "has_confirmed_news": det.has_confirmed_news,
        "has_news_catalyst": det.has_confirmed_news,
        "volume_status": det.volume_status,
    }


def _candidate_to_signal(c) -> OpportunityNowSignal:
    spread = c.spread_pct
    ext = _extended_fields(c.symbol)
    return OpportunityNowSignal(
        symbol=c.symbol,
        name=c.name,
        price=round(c.last_price, 4),
        change_percent=round(c.change_percent, 2),
        score=c.score,
        status=c.status,
        status_ar=STATUS_AR.get(c.status, c.status),
        opportunity_type=c.status,
        appeared_at=c.now_started_at.isoformat() if c.now_started_at else c.last_updated,
        expires_at=c.expires_at.isoformat() if c.expires_at else "",
        entry_zone=round((c.entry_zone_low + c.entry_zone_high) / 2, 4),
        entry_zone_low=c.entry_zone_low,
        entry_zone_high=c.entry_zone_high,
        stop_loss=c.stop_loss,
        target_1=c.target_1,
        target_2=c.target_2,
        risk_level=_risk_level(c.score, spread),  # type: ignore[arg-type]
        risk_reward_ratio=c.risk_reward_ratio,
        confirmed_factors=c.confirmed_factors,
        total_factors=c.total_factors,
        consecutive_confirmations=c.consecutive_confirmations,
        reasons_ar=c.nomination_reasons[:6],
        cancellation_reasons_ar=c.cancellation_reasons[:6],
        late_entry_warning=any("VWAP" in r or "مطاردة" in r for r in c.cancellation_reasons),
        data_timestamp=c.last_updated,
        data_age_seconds=round(c.data_age_seconds, 1),
        **ext,
    )


def _detection_to_signal(det: ExtendedGapDetection) -> OpportunityNowSignal:
    cand = live_confirmation_engine._candidates.get(det.symbol)
    if cand and cand.last_price > 0:
        return _candidate_to_signal(cand)
    status = "CANCELLED" if det.is_late_chase else "WATCH"
    cancellation = [
        "تم رصد القفزة، لكن الدخول الآن مطاردة",
        "لا تدخل حتى يحدث تراجع وتأكيد جديد",
        "لا تطارد السهم",
    ] if det.is_late_chase else []
    return OpportunityNowSignal(
        symbol=det.symbol,
        name=det.name,
        price=det.extended_price,
        change_percent=det.extended_gap_pct,
        score={"WATCH": 65.0, "ACTIVE": 75.0, "EXPLOSIVE": 88.0}[det.detection_stage],
        status=status,
        status_ar=STATUS_AR.get(status, status),
        opportunity_type=status,
        appeared_at=det.detected_at,
        expires_at="",
        entry_zone=round((det.previous_close * 1.001 + det.previous_close * 1.04) / 2, 4),
        entry_zone_low=round(det.previous_close * 1.001, 4),
        entry_zone_high=round(det.previous_close * 1.04, 4),
        stop_loss=round(det.previous_close * 0.97, 4),
        target_1=round(det.extended_price * 1.03, 4),
        target_2=round(det.extended_price * 1.06, 4),
        risk_level="مرتفع",
        risk_reward_ratio=0.0,
        confirmed_factors=0,
        total_factors=17,
        consecutive_confirmations=0,
        reasons_ar=[
            f"{'قبل الافتتاح' if det.session == 'PRE_MARKET' else 'بعد الإغلاق'}: +{det.extended_gap_pct:.1f}%",
            det.catalyst_title_ar,
            *det.risk_flags_ar[:2],
        ],
        cancellation_reasons_ar=cancellation,
        late_entry_warning=det.is_late_chase,
        has_news_catalyst=det.has_confirmed_news,
        data_timestamp=det.detected_at,
        data_age_seconds=0.0,
        session=det.session,
        previous_close=det.previous_close,
        extended_price=det.extended_price,
        extended_gap_pct=det.extended_gap_pct,
        extended_volume=det.extended_volume,
        relative_volume=det.relative_volume,
        catalyst_type=det.catalyst_type,
        catalyst_title_ar=det.catalyst_title_ar,
        catalyst_source=det.catalyst_source,
        catalyst_published_at=det.catalyst_published_at,
        detection_stage=det.detection_stage,
        risk_flags_ar=det.risk_flags_ar,
        detected_at=det.detected_at,
        has_confirmed_news=det.has_confirmed_news,
        volume_status=det.volume_status,
    )


def _pick_top_signal(
    signals: list[OpportunityNowSignal],
    best,
    *,
    market_open: bool,
) -> OpportunityNowSignal | None:
    """Regular trading opportunity only — extended gaps use extended_alert."""
    if best and best.last_price > 0:
        top = _candidate_to_signal(best)
        if not market_open and top.status == "NOW":
            top.status = "WATCH"
            top.status_ar = STATUS_AR["WATCH"]
        if top.price > 0 and top.score > 0 and top.change_percent > 0:
            return top

    regular = [
        s for s in signals
        if s.score > 0 and s.change_percent > 0 and s.extended_gap_pct <= 0 and not s.detection_stage
    ]
    for preferred in ("NOW", "READY", "WATCH"):
        tier = [s for s in regular if s.status == preferred]
        if tier:
            return max(tier, key=lambda s: s.score)
    return None


def _pick_extended_alert() -> OpportunityNowSignal | None:
    detections = extended_gap_registry.all()
    if not detections:
        return None
    best = max(
        detections,
        key=lambda d: (_STAGE_RANK.get(d.detection_stage, 0), d.extended_gap_pct),
    )
    sig = _detection_to_signal(best)
    if sig.price > 0 and sig.extended_gap_pct > 0 and sig.detection_stage:
        return sig
    return None


def _premarket_to_opportunity_signal(pm: PremarketOpportunitySignal) -> OpportunityNowSignal:
    if pm.status == "CONFIRMED_ENTRY":
        status = "NOW"
    elif pm.status == "EARLY_MOMENTUM":
        status = "WATCH"
    else:
        status = "WATCH"
    entry = pm.entry if pm.status == "CONFIRMED_ENTRY" else pm.early_entry_zone
    stop = pm.stop_loss if pm.status == "CONFIRMED_ENTRY" else pm.invalidation_level
    return OpportunityNowSignal(
        symbol=pm.symbol,
        name=pm.symbol,
        price=pm.current_price,
        change_percent=pm.premarket_change_percent,
        score=0.0,
        status=status,
        status_ar=STATUS_AR.get(status, status),
        opportunity_type=pm.status if pm.status != "WATCH" else (pm.trigger_type or "PREMARKET"),
        appeared_at="",
        expires_at="",
        entry_zone=entry,
        entry_zone_low=entry,
        entry_zone_high=entry,
        stop_loss=stop,
        target_1=pm.tp1,
        target_2=pm.tp2,
        risk_level="مرتفع",
        risk_reward_ratio=pm.risk_reward,
        confirmed_factors=0,
        total_factors=17,
        consecutive_confirmations=0,
        reasons_ar=[pm.reason] if pm.reason else [],
        cancellation_reasons_ar=[],
        late_entry_warning=pm.status == "EARLY_MOMENTUM",
        has_news_catalyst=False,
        movement_without_news=False,
        data_timestamp="",
        data_age_seconds=0.0,
        session="PRE_MARKET",
        previous_close=0.0,
        extended_price=pm.current_price,
        extended_gap_pct=pm.premarket_change_percent,
        extended_volume=pm.premarket_volume,
        relative_volume=pm.relative_volume,
        detection_stage=pm.trigger_type or pm.status,
        risk_flags_ar=[],
        volume_status="KNOWN",
    )



def sync_engine_from_scanner() -> None:
    sync_extended_gap_detector()
    monitor = live_confirmation_engine._monitor_symbols or market_scanner._rank_pool[:LIVE_MONITOR_POOL]
    if not live_confirmation_engine._monitor_symbols:
        live_confirmation_engine.set_monitor_symbols(monitor)
    for snap in _collect_snapshots():
        if snap.symbol.upper() in live_confirmation_engine._monitor_symbols:
            try:
                live_confirmation_engine.ingest_snapshot(snap, ws_tick=False)
            except Exception as exc:
                logger.debug("Engine ingest skip %s: %s", snap.symbol, type(exc).__name__)


def get_opportunity_now() -> OpportunityNowResponse:
    try:
        session = get_us_market_session()
        state = market_scanner.get_state()
        if state and state.market_status:
            session = state.market_status

        market_open = is_regular_session(session)
        message = session_explanation(session)
        if not market_open:
            message = "السوق مغلق — مراقبة فقط"

        sync_engine_from_scanner()

        jump_alerts = _collect_jump_alerts(session)
        display_signals = _collect_home_display_signals(session)
        real_jump_alerts = _collect_real_jump_alerts(session)
        distinguished_jump_alerts = _collect_distinguished_jump_alerts(session)
        engine_snap = jump_engine_monitor.get_snapshot()
        jump_engine_status = engine_snap.jump_engine_status

        premarket_scan: PremarketScanResult | None = None
        if session == "PRE_MARKET":
            from services.premarket_opportunity_scanner import get_last_premarket_scan

            premarket_scan = get_last_premarket_scan()

        best = live_confirmation_engine.best_candidate(market_open=market_open)
        signals: list[OpportunityNowSignal] = []
        for cand in live_confirmation_engine._candidates.values():
            ext = extended_gap_registry.get(cand.symbol)
            if cand.last_price <= 0:
                continue
            if ext or (cand.score > 0 and cand.status in ("WATCH", "READY", "NOW", "CANCELLED")):
                sig = _candidate_to_signal(cand)
                if sig.price > 0 and (sig.score > 0 or sig.extended_gap_pct > 0):
                    signals.append(sig)

        if premarket_scan:
            for pm in premarket_scan.opportunities + premarket_scan.watches:
                sig = _premarket_to_opportunity_signal(pm)
                if sig.price > 0:
                    signals.append(sig)

        for ja in jump_alerts:
            if ja.symbol.upper() not in {s.symbol.upper() for s in signals}:
                signals.append(ja)

        signals.sort(
            key=lambda s: (s.detection_stage == "EXPLOSIVE", s.extended_gap_pct, s.status == "NOW", s.score),
            reverse=True,
        )

        if session == "PRE_MARKET" and premarket_scan and not display_signals:
            if premarket_scan.top_opportunity:
                top = _premarket_to_opportunity_signal(premarket_scan.top_opportunity)
                resp_status = "NOW"
                none_message = premarket_scan.message
            elif premarket_scan.top_early:
                top = _premarket_to_opportunity_signal(premarket_scan.top_early)
                resp_status = "WATCH"
                none_message = premarket_scan.message
            else:
                top = None
                resp_status = "NONE"
                none_message = "لا يوجد شراء قوي فعلي الآن"
        else:
            top = display_signals[0] if display_signals else None
            if top:
                resp_status = top.status if top.status != "NONE" else "NONE"
            else:
                resp_status = "NONE"
            none_message = (
                "لا يوجد شراء قوي فعلي الآن"
                if not display_signals
                else "لا توجد فرصة مكتملة الآن"
            )

        extended_alert = next(
            (ds for ds in display_signals if ds.extended_gap_pct > 0 and ds.detection_stage),
            None,
        )
        live_source = (
            "websocket"
            if live_confirmation_engine.ws_connected and not live_confirmation_engine.ws_fallback
            else "rest"
        )

        return OpportunityNowResponse(
            status=resp_status,
            status_ar=STATUS_AR.get(resp_status, none_message),
            market_status=session,
            market_open=market_open,
            scan_interval_seconds=SCANNER_TICK_SECONDS,
            message=none_message if resp_status == "NONE" else STATUS_AR.get(resp_status, message),
            live_source=live_source,
            ws_connected=live_confirmation_engine.ws_connected,
            monitor_pool_size=len(live_confirmation_engine._monitor_symbols),
            signals=signals,
            top_signal=top if top and top.price > 0 else None,
            extended_alert=extended_alert,
            premarket_scan=premarket_scan,
            jump_alerts=jump_alerts,
            jump_engine_status=jump_engine_status,
            display_signals=display_signals,
            real_jump_alerts=real_jump_alerts,
            distinguished_jump_alerts=distinguished_jump_alerts,
        )
    except Exception as exc:
        logger.warning("Opportunity now unavailable: %s", type(exc).__name__)
        return OpportunityNowResponse(
            status="NONE",
            status_ar="لا توجد فرصة مكتملة الآن",
            market_status="CLOSED",
            market_open=False,
            message="تعذر تحميل فرصة الآن مؤقتاً — لا توجد فرصة مكتملة الآن",
            signals=[],
            top_signal=None,
            extended_alert=None,
            premarket_scan=None,
        )
