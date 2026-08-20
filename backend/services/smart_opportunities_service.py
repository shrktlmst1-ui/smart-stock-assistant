"""Smart Opportunities Service — uses cached scanner data, no per-stock API spam."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from analysis.entry_decision import evaluate_entry_decision
from config import (
    SMART_SCANNER_MAX_SPREAD_PCT,
    SMART_SCANNER_MIN_AI_SCORE,
    SMART_SCANNER_MIN_DAY_VOLUME,
    SMART_SCANNER_MIN_RVOL,
    SMART_SCANNER_TOP_N,
)
from database.smart_signal_logger import log_smart_signal, update_smart_signal_outcome
from models.smart_opportunity import SmartOpportunityItem, SmartOpportunitiesResponse
from models.stock import StockSnapshot
from services.market_scanner_service import market_scanner
from services.market_session import get_us_market_session, session_explanation
from market_pulse.service import get_pulse_for_symbol

logger = logging.getLogger(__name__)

# In-memory signal creation times (symbol -> ISO timestamp)
_signal_created: dict[str, str] = {}


def _ai_score(snap: StockSnapshot) -> float:
    return snap.trade_decision.professional_ai_score or snap.ai_signal.ai_score


def _spread_pct(snap: StockSnapshot) -> float:
    """Estimate spread from day range if not in snapshot."""
    price = snap.price or 1.0
    high = snap.indicators.resistance if snap.indicators else price
    low = snap.indicators.support if snap.indicators else price
    if high > low > 0:
        return round((high - low) / price * 100, 2)
    vol = snap.volume_engine
    if vol and vol.relative_volume:
        return min(0.3, 0.1 + vol.relative_volume * 0.02)
    return 0.2


def _rvol(snap: StockSnapshot) -> float:
    if snap.volume_engine:
        return snap.volume_engine.relative_volume or snap.volume_engine.session_rvol or 1.0
    if snap.volume_liquidity:
        return snap.volume_liquidity.relative_volume or 1.0
    return 1.0


def _passes_smart_filter(snap: StockSnapshot, spread: float) -> bool:
    score = _ai_score(snap)
    rvol = _rvol(snap)
    volume = snap.volume or 0
    return (
        score >= SMART_SCANNER_MIN_AI_SCORE
        and rvol >= SMART_SCANNER_MIN_RVOL
        and spread <= SMART_SCANNER_MAX_SPREAD_PCT
        and volume >= SMART_SCANNER_MIN_DAY_VOLUME
    )


def _snapshot_to_opportunity(
    snap: StockSnapshot,
    market_status: str,
    metrics_spread: float | None = None,
) -> SmartOpportunityItem:
    td = snap.trade_decision
    smc = snap.smc
    spread = metrics_spread if metrics_spread is not None else _spread_pct(snap)
    rvol = _rvol(snap)
    ai = _ai_score(snap)

    sym = snap.symbol.upper()
    if sym not in _signal_created:
        _signal_created[sym] = snap.last_updated or datetime.now(timezone.utc).isoformat()

    smc_flags = {
        "bos": smc.bos,
        "order_block": len(smc.order_blocks) > 0,
        "fair_value_gap": any(not g.filled for g in smc.fair_value_gaps),
        "liquidity_sweep": smc.liquidity_sweep,
    }

    failed = [
        k for k, v in (td.factor_scores or {}).items()
        if v < 45
    ] if td.factor_scores else []

    decision = evaluate_entry_decision(
        price=snap.price,
        ai_score=ai,
        rrr=td.risk_reward_ratio,
        rvol=rvol,
        spread_pct=spread,
        volume=snap.volume,
        entry_low=td.entry_zone_low,
        entry_high=td.entry_zone_high,
        stop_loss=td.stop_loss,
        take_profit_1=td.take_profit_1,
        take_profit_2=td.take_profit_2,
        direction=td.direction,
        trap_risk=td.trap_risk,
        news_risk=td.news_risk,
        professional_signal=td.professional_signal or "",
        recommendation=td.recommendation,
        failed_factors=failed,
        devils_advocate=td.devils_advocate,
        last_updated=snap.last_updated,
        signal_created_at=_signal_created.get(sym),
        smc_flags=smc_flags,
    )

    if decision.state == "EXPIRED":
        update_smart_signal_outcome(sym, "expired")
        _signal_created.pop(sym, None)

    pulse = get_pulse_for_symbol(sym)

    return SmartOpportunityItem(
        symbol=sym,
        name=snap.name,
        price=snap.price,
        change_percent=snap.change_percent,
        rvol=round(rvol, 2),
        spread_pct=round(spread, 2),
        ai_score=round(ai, 1),
        market_status=market_status,  # type: ignore[arg-type]
        last_updated=snap.last_updated,
        volume=snap.volume,
        entry_state=decision.state,
        entry_label_ar=decision.label_ar,
        entry_color=decision.color,
        entry_reasons=decision.entry_reasons,
        warnings=decision.warnings,
        entry_zone_low=decision.entry_zone_low,
        entry_zone_high=decision.entry_zone_high,
        stop_loss=decision.stop_loss,
        take_profit_1=decision.take_profit_1,
        take_profit_2=decision.take_profit_2,
        risk_reward_ratio=decision.risk_reward_ratio,
        signal_created_at=decision.signal_created_at,
        signal_expires_at=decision.signal_expires_at,
        data_fresh=decision.data_fresh,
        data_age_seconds=decision.data_age_seconds,
        direction=td.direction,
        bos=smc.bos,
        choch=smc.choch,
        order_block=len(smc.order_blocks) > 0,
        fair_value_gap=any(not g.filled for g in smc.fair_value_gaps),
        liquidity_sweep=smc.liquidity_sweep,
        pulse_score=pulse.get("pulse_score") if pulse else None,
        pulse_decision=pulse.get("pulse_decision") if pulse else None,
        pulse_headline=pulse.get("pulse_headline") if pulse else None,
        pulse_is_live=pulse.get("pulse_is_live") if pulse else None,
        pulse_catalyst=pulse.get("pulse_catalyst") if pulse else None,
    )


def _metrics_spread_map(scanner) -> dict[str, float]:
    out: dict[str, float] = {}
    for m, _ in getattr(scanner, "_scored_metrics", []) or []:
        out[m.symbol] = m.spread_pct
    return out


def get_smart_opportunities() -> SmartOpportunitiesResponse:
    """
    Build top-N smart opportunities from cached scanner snapshots.
    Fast coarse filter first, then entry decision on survivors only.
    """
    state = market_scanner.get_state()
    session = state.market_status if state and state.market_status else get_us_market_session()
    explanation = state.explanation if state and state.explanation else session_explanation(session)

    if not state or not state.snapshots:
        return SmartOpportunitiesResponse(
            market_status=session,
            explanation=explanation,
            no_signal_reason=state.no_signal_reason if state else "لا توجد بيانات ماسح — انتظر التحديث",
        )

    spread_map = _metrics_spread_map(market_scanner)
    all_snaps = list(state.snapshots)

    # Also include deeply analyzed snapshots from scanner cache
    cached = market_scanner._snapshots  # noqa: SLF001 — reuse cache
    for sym, snap in cached.items():
        if sym not in {s.symbol for s in all_snaps}:
            all_snaps.append(snap)

    filtered: list[StockSnapshot] = []
    for snap in all_snaps:
        spread = spread_map.get(snap.symbol, _spread_pct(snap))
        if _passes_smart_filter(snap, spread):
            filtered.append(snap)

    filtered.sort(key=_ai_score, reverse=True)
    top = filtered[:SMART_SCANNER_TOP_N]

    opportunities: list[SmartOpportunityItem] = []
    for snap in top:
        spread = spread_map.get(snap.symbol, _spread_pct(snap))
        opp = _snapshot_to_opportunity(snap, session, spread)
        opportunities.append(opp)

        if opp.entry_state in ("ENTER_NOW", "WAIT_PRICE"):
            try:
                log_smart_signal(
                    opp.symbol,
                    opp.entry_state,
                    opp.ai_score,
                    opp.price,
                    change_percent=opp.change_percent,
                    rvol=opp.rvol,
                    spread_pct=opp.spread_pct,
                    entry_zone_low=opp.entry_zone_low,
                    entry_zone_high=opp.entry_zone_high,
                    stop_loss=opp.stop_loss,
                    take_profit_1=opp.take_profit_1,
                    take_profit_2=opp.take_profit_2,
                    risk_reward_ratio=opp.risk_reward_ratio,
                    signal_created_at=opp.signal_created_at,
                    signal_expires_at=opp.signal_expires_at,
                    payload=opp.model_dump(),
                )
            except Exception as e:
                logger.warning("Smart signal log failed for %s: %s", opp.symbol, e)

    no_reason = ""
    if not opportunities:
        no_reason = (
            f"فُحص {len(all_snaps)} سهم — لا يوجد {SMART_SCANNER_TOP_N} فرص "
            f"تجتاز الفلترة (RVOL≥{SMART_SCANNER_MIN_RVOL}, AI≥{SMART_SCANNER_MIN_AI_SCORE}, "
            f"سبريد≤{SMART_SCANNER_MAX_SPREAD_PCT}%, حجم≥{SMART_SCANNER_MIN_DAY_VOLUME:,})"
        )

    return SmartOpportunitiesResponse(
        market_status=session,
        explanation=explanation,
        opportunities=opportunities,
        scanned_count=len(all_snaps),
        filtered_count=len(filtered),
        last_scan_ms=state.last_tick_ms if state else 0.0,
        no_signal_reason=no_reason or (state.no_signal_reason if not opportunities else ""),
    )
