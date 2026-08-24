"""Best opportunities — premarket scanner is the sole source during PRE_MARKET."""

from __future__ import annotations

import logging

from models.premarket_opportunity import PremarketOpportunitySignal, PremarketScanResult
from models.scanner import MarketScanState, OpportunitiesResponse
from models.stock import StockOpportunity
from services.market_session import session_explanation
from services.premarket_opportunity_scanner import sync_premarket_scanner

logger = logging.getLogger(__name__)

PREMARKET_EMPTY_TITLE = "لا توجد فرصة دخول فعلية الآن"
PREMARKET_EMPTY_SUB = "يتم مراقبة السوق لحظياً بحثاً عن اختراق أو ارتداد مؤكد"


def _format_status_reason_ar(pm: PremarketOpportunitySignal) -> str:
    parts: list[str] = []
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
    if pm.reason:
        parts.append(f"السبب: {pm.reason}")
    return " | ".join(parts)


def premarket_to_stock_opportunity(
    pm: PremarketOpportunitySignal,
    *,
    name: str = "",
) -> StockOpportunity:
    return StockOpportunity(
        symbol=pm.symbol,
        name=name or pm.symbol,
        price=pm.current_price,
        change_percent=pm.premarket_change_percent,
        score=0,
        trend="صاعد" if pm.premarket_change_percent > 0.5 else "محايد",
        risk_level="مرتفع",
        status="شراء",
        ai_signal=pm.trigger_type or "ENTRY CONFIRMED",
        confidence=0.0,
        confirmed_factors=0,
        total_factors=17,
        safety_passed=True,
        status_reason_ar=_format_status_reason_ar(pm),
    )


def _resolve_name(symbol: str, state: MarketScanState | None) -> str:
    if not state:
        return symbol
    for snap in state.snapshots:
        if snap.symbol.upper() == symbol.upper():
            return snap.name or symbol
    return symbol


def build_premarket_opportunities_response(
    scan: PremarketScanResult,
    *,
    limit: int = 20,
    state: MarketScanState | None = None,
    session: str = "PRE_MARKET",
) -> OpportunitiesResponse:
    opportunities: list[StockOpportunity] = []
    for pm in scan.opportunities[:limit]:
        if pm.status != "OPPORTUNITY":
            continue
        opportunities.append(
            premarket_to_stock_opportunity(pm, name=_resolve_name(pm.symbol, state))
        )

    logger.info(
        "BEST_OPPORTUNITIES source=PREMARKET_SCANNER count=%d session=%s",
        len(opportunities),
        session,
    )
    if not opportunities:
        logger.info(
            "BEST_OPPORTUNITIES source=PREMARKET_SCANNER count=0 (no legacy fallback)",
        )

    return OpportunitiesResponse(
        market_status=session,  # type: ignore[arg-type]
        opportunities=opportunities,
        watchlist_candidates=[],
        explanation=session_explanation(session),  # type: ignore[arg-type]
        no_signal_reason=(
            f"{PREMARKET_EMPTY_TITLE}\n{PREMARKET_EMPTY_SUB}"
            if not opportunities
            else scan.message
        ),
        debug=state.debug if state else None,
    )


def get_best_opportunities_premarket(
    *,
    limit: int = 20,
    state: MarketScanState | None = None,
) -> OpportunitiesResponse:
    scan = sync_premarket_scanner()
    session = state.market_status if state and state.market_status else "PRE_MARKET"
    return build_premarket_opportunities_response(
        scan,
        limit=limit,
        state=state,
        session=session,
    )
