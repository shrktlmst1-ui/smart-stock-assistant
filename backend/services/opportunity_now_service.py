"""فرصة الآن — live confirmation engine + REST fallback."""

from __future__ import annotations

import logging

from config import SCANNER_TICK_SECONDS
from models.opportunity_now import OpportunityNowResponse, OpportunityNowSignal
from models.stock import StockSnapshot
from services.live_confirmation_engine import (
    LIVE_MONITOR_POOL,
    STATUS_AR,
    live_confirmation_engine,
)
from services.market_scanner_service import market_scanner
from services.market_session import get_us_market_session, is_regular_session, session_explanation
from services.opportunity_now_scoring import (
    SIGNAL_TTL_SECONDS,
    _snapshot_to_signal,
    reset_signal_cache,
)

logger = logging.getLogger(__name__)

MAX_PRICE_USD = 10.0
MIN_PRICE_USD = 0.50


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
        if snap.price > 0 and snap.price <= MAX_PRICE_USD:
            result.append(snap)
    return result


def _risk_level(score: float, spread: float) -> str:
    if score >= 80 and spread <= 0.3:
        return "منخفض"
    if score >= 70:
        return "متوسط"
    return "مرتفع"


def _candidate_to_signal(c) -> OpportunityNowSignal:
    spread = c.spread_pct
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
    )


def sync_engine_from_scanner() -> None:
    monitor = market_scanner._rank_pool[:LIVE_MONITOR_POOL]
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

        best = live_confirmation_engine.best_candidate(market_open=market_open)
        signals: list[OpportunityNowSignal] = []
        for cand in live_confirmation_engine._candidates.values():
            if cand.last_price <= 0 or cand.score <= 0:
                continue
            if cand.status in ("WATCH", "READY", "NOW", "CANCELLED"):
                signals.append(_candidate_to_signal(cand))
        signals.sort(key=lambda s: (s.status == "NOW", s.score), reverse=True)

        if best and best.last_price > 0:
            top = _candidate_to_signal(best)
            if not market_open and top.status == "NOW":
                top.status = "WATCH"
                top.status_ar = STATUS_AR["WATCH"]
            resp_status = top.status if top.status != "NONE" else "NONE"
        else:
            top = None
            resp_status = "NONE"

        none_message = "لا توجد فرصة مكتملة الآن"
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
        )
