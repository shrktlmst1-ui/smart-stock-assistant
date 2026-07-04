"""Professional Signal Analytics — recording, tracking, stats, and ranking."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from database.signal_analytics_db import (
    TERMINAL_STATUSES,
    get_all_records,
    get_open_tracks,
    get_signal_records,
    insert_signal_record,
    update_track,
)
from models.signal_analytics import (
    AnalyticsDashboard,
    PerformanceReport,
    RankedSignalsResponse,
    SignalAnalyticsRecord,
    SignalExplanationItem,
)
from models.trading import AISignal, DashboardMeters, TradeDecision
from services.trade_replay_service import (
    init_trade_replay,
    observe_trade_price,
    on_track_status_change,
)

logger = logging.getLogger(__name__)

MIN_FACTOR_PASS = 45.0
TRACK_EXPIRY_HOURS = 48

EXPLANATION_CHECKS: tuple[tuple[str, str], ...] = (
    ("trend", "Trend Alignment"),
    ("bos", "BOS Confirmed"),
    ("choch", "CHOCH Confirmed"),
    ("order_blocks", "Order Block"),
    ("fair_value_gaps", "FVG"),
    ("liquidity_sweep", "Liquidity Sweep"),
    ("relative_volume", "Relative Volume"),
    ("vwap", "VWAP"),
    ("ema_alignment", "EMA Alignment"),
    ("retest", "Retest"),
)

WIN_STATUSES = frozenset({"Target 1 Hit", "Target 2 Hit", "Target 3 Hit"})
LOSS_STATUSES = frozenset({"Stop Loss Hit"})


def _compute_target_3(entry: float, stop: float, is_long: bool) -> float:
    """Analytics-only TP3 at 4R — does not alter risk engine."""
    risk = abs(entry - stop)
    if risk <= 0:
        risk = max(entry * 0.01, 0.01)
    return round(entry + risk * 4.0 if is_long else entry - risk * 4.0, 2)


def build_explanation(
    factor_scores: dict[str, float],
    filters_passed: list[str],
    filters_failed: list[str],
) -> list[dict]:
    passed_set = set(filters_passed)
    failed_set = set(filters_failed)
    items: list[dict] = []

    for key, label in EXPLANATION_CHECKS:
        if key == "ema_alignment":
            ema_keys = ("ema20", "ema50", "ema200")
            scores = [factor_scores.get(k, 0) for k in ema_keys]
            passed = all(s >= MIN_FACTOR_PASS for s in scores) or any(
                k in passed_set for k in ema_keys
            )
        elif key == "retest":
            score = factor_scores.get("retest", factor_scores.get("smc", 50))
            passed = score >= MIN_FACTOR_PASS and "retest" not in failed_set
            if any("retest" in f.lower() for f in filters_failed):
                passed = False
            label = "Retest Confirmed" if passed else "Retest Missing"
            items.append({"label": label, "passed": passed})
            continue
        else:
            score = factor_scores.get(key, 0)
            passed = key in passed_set or score >= MIN_FACTOR_PASS
            if key in failed_set or any(key in f for f in filters_failed):
                passed = False
        items.append({"label": label, "passed": passed})
    return items


def compute_trade_quality(
    ai_score: float,
    confidence: float,
    trend_strength: float,
    relative_volume: float,
) -> tuple[int, str]:
    composite = (
        ai_score * 0.35
        + confidence * 0.30
        + trend_strength * 0.20
        + relative_volume * 0.15
    )
    if composite >= 85:
        return 5, "Excellent"
    if composite >= 75:
        return 4, "Very Good"
    if composite >= 65:
        return 3, "Good"
    if composite >= 50:
        return 2, "Average"
    return 1, "Weak"


def classify_failure(
    signal: str,
    factor_scores: dict[str, float],
    *,
    news_risk: float = 0.0,
    filters_failed: list[str] | None = None,
) -> str:
    """Classify losing trade reason from existing factor data."""
    failed = filters_failed or []
    failed_text = " ".join(failed).lower()

    if factor_scores.get("relative_volume", 50) < 40:
        return "Weak Volume"
    if factor_scores.get("news_impact", 0) > 65 or news_risk > 55:
        return "News Event"
    if factor_scores.get("atr", 50) > 72:
        return "High Volatility"
    if "false" in failed_text or "breakout" in failed_text:
        return "False Breakout"
    if signal in ("Buy", "Strong Buy") and factor_scores.get("trend", 50) < 42:
        return "Market Reversal"
    if signal in ("Sell", "Strong Sell") and factor_scores.get("trend", 50) > 58:
        return "Market Reversal"
    if signal in ("Buy", "Strong Buy") and "resistance" in failed_text:
        return "Resistance Failure"
    if signal in ("Sell", "Strong Sell") and "support" in failed_text:
        return "Support Break"
    if factor_scores.get("bos", 50) < 40 or factor_scores.get("smc", 50) < 40:
        return "False Breakout"
    return "Market Reversal"


def _rank_score(record: dict) -> float:
    return (
        record.get("confidence_score", 0) * 10000
        + record.get("ai_score", 0) * 100
        + record.get("trend_strength", 0)
        + record.get("relative_volume", 0) * 0.01
    )


def record_analytics_signal(
    symbol: str,
    ai_signal: AISignal,
    decision: TradeDecision,
    meters: DashboardMeters,
    *,
    market_status: str,
    sector: str = "",
    industry: str = "",
    timeframe: str = "live",
) -> int:
    """Persist rich analytics snapshot — does not alter signal generation."""
    now = datetime.now(timezone.utc)
    factor_scores = dict(decision.factor_scores or {})
    is_long = decision.direction == "long" or ai_signal.signal in ("Buy", "Strong Buy")
    entry = ai_signal.entry or decision.current_price
    stop = ai_signal.stop_loss or decision.stop_loss
    tp1 = ai_signal.target_1 or decision.take_profit_1
    tp2 = ai_signal.target_2 or decision.take_profit_2
    tp3 = _compute_target_3(entry, stop, is_long)

    trend_dir = decision.direction
    if trend_dir == "neutral":
        trend_dir = "long" if ai_signal.signal in ("Buy", "Strong Buy") else (
            "short" if ai_signal.signal in ("Sell", "Strong Sell") else "neutral"
        )

    rel_vol = factor_scores.get("relative_volume", meters.trend_strength)
    trend_strength = meters.trend_strength or factor_scores.get("trend", 0)
    stars, quality_label = compute_trade_quality(
        decision.professional_ai_score or ai_signal.ai_score,
        ai_signal.confidence,
        trend_strength,
        rel_vol,
    )
    explanation = build_explanation(
        factor_scores,
        decision.filters_passed,
        decision.filters_failed,
    )
    track_status = "Waiting"
    if ai_signal.signal not in ("Buy", "Sell"):
        track_status = "Expired"

    data = {
        "symbol": symbol,
        "signal": ai_signal.signal,
        "signal_date": now.strftime("%Y-%m-%d"),
        "signal_time": now.strftime("%H:%M:%S"),
        "timeframe": timeframe,
        "ai_score": round(decision.professional_ai_score or ai_signal.ai_score, 2),
        "confidence_score": round(ai_signal.confidence, 2),
        "entry_price": round(entry, 2),
        "stop_loss": round(stop, 2),
        "target_1": round(tp1, 2),
        "target_2": round(tp2, 2),
        "target_3": tp3,
        "trend_direction": trend_dir,
        "market_status": market_status,
        "sector": sector,
        "industry": industry,
        "track_status": track_status,
        "trade_quality_stars": stars,
        "trade_quality_label": quality_label,
        "explanation": explanation,
        "factor_scores": factor_scores,
        "filters_passed": decision.filters_passed,
        "filters_failed": decision.filters_failed,
        "trend_strength": round(trend_strength, 2),
        "relative_volume": round(rel_vol, 2),
        "created_at": now.isoformat(),
    }
    record_id = insert_signal_record(data)
    risk_rr = decision.risk_reward_ratio or ai_signal.risk_reward_ratio
    init_trade_replay(
        record_id,
        symbol=symbol,
        entry_price=round(entry, 2),
        ai_score=round(decision.professional_ai_score or ai_signal.ai_score, 2),
        confidence=round(ai_signal.confidence, 2),
        risk_reward_ratio=round(risk_rr, 2),
        created_at=now.isoformat(),
        signal_time=now.strftime("%H:%M"),
    )
    logger.debug("Analytics signal recorded %s id=%s", symbol, record_id)
    return record_id


def _profit_pct(entry: float, exit_price: float, is_buy: bool) -> float:
    if entry <= 0:
        return 0.0
    if is_buy:
        return round((exit_price - entry) / entry * 100, 3)
    return round((entry - exit_price) / entry * 100, 3)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve_price_outcome(
    *,
    is_buy: bool,
    price: float,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    tp3: float,
    signal: str,
    factor_scores: dict,
    filters_failed: list,
    news_risk: float,
) -> tuple[str | None, float, float, str | None]:
    """Return (status, exit_price, profit_pct, failure_reason) if terminal/active hit."""
    if is_buy:
        if price <= stop:
            return (
                "Stop Loss Hit",
                stop,
                _profit_pct(entry, stop, True),
                classify_failure(signal, factor_scores, news_risk=news_risk, filters_failed=filters_failed),
            )
        if price >= tp3:
            return "Target 3 Hit", tp3, _profit_pct(entry, tp3, True), None
        if price >= tp2:
            return "Target 2 Hit", tp2, _profit_pct(entry, tp2, True), None
        if price >= tp1:
            return "Target 1 Hit", tp1, _profit_pct(entry, tp1, True), None
    else:
        if price >= stop:
            return (
                "Stop Loss Hit",
                stop,
                _profit_pct(entry, stop, False),
                classify_failure(signal, factor_scores, news_risk=news_risk, filters_failed=filters_failed),
            )
        if price <= tp3:
            return "Target 3 Hit", tp3, _profit_pct(entry, tp3, False), None
        if price <= tp2:
            return "Target 2 Hit", tp2, _profit_pct(entry, tp2, False), None
        if price <= tp1:
            return "Target 1 Hit", tp1, _profit_pct(entry, tp1, False), None
    return None, price, 0.0, None


def update_analytics_tracks(
    symbol: str,
    price: float,
    *,
    news_risk: float = 0.0,
) -> int:
    """Monitor open analytics trades and update status from live price."""
    if price <= 0:
        return 0
    updated = 0
    now = datetime.now(timezone.utc)

    for track in get_open_tracks(symbol):
        if track["signal"] not in ("Buy", "Sell"):
            continue

        entry = track["entry_price"]
        stop = track["stop_loss"]
        tp1 = track["target_1"]
        tp2 = track["target_2"]
        tp3 = track["target_3"]
        is_buy = track["signal"] == "Buy"
        status = track["track_status"]
        created = _parse_ts(track.get("created_at"))
        activated_at = track.get("activated_at")

        if created and (now - created) > timedelta(hours=TRACK_EXPIRY_HOURS):
            if status in ("Waiting", "Active"):
                holding = int((now - created).total_seconds())
                closed_ts = now.isoformat()
                observe_trade_price(
                    track["id"],
                    price=price,
                    track=track,
                    old_status=status,
                    new_status="Expired",
                    activated_at=activated_at,
                    now=now,
                )
                update_track(
                    track["id"],
                    track_status="Expired",
                    profit_pct=0.0,
                    exit_price=price,
                    closed_at=closed_ts,
                    holding_seconds=holding,
                )
                updated_track = dict(track)
                updated_track["exit_price"] = price
                on_track_status_change(
                    track["id"],
                    track=updated_track,
                    old_status=status,
                    new_status="Expired",
                    activated_at=activated_at,
                    closed_at=closed_ts,
                    profit_pct=0.0,
                    now=now,
                )
                updated += 1
            continue

        new_status = status
        exit_price = price
        profit = 0.0
        failure: str | None = None
        new_activated: str | None = None

        if status == "Waiting":
            tolerance = max(entry * 0.005, 0.01)
            if abs(price - entry) <= tolerance or (is_buy and price >= entry) or (
                not is_buy and price <= entry
            ):
                new_status = "Active"
                new_activated = now.isoformat()

        active_now = new_status == "Active" or status == "Active"
        if active_now:
            outcome, exit_price, profit, failure = _resolve_price_outcome(
                is_buy=is_buy,
                price=price,
                entry=entry,
                stop=stop,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                signal=track["signal"],
                factor_scores=track.get("factor_scores") or {},
                filters_failed=track.get("filters_failed") or [],
                news_risk=news_risk,
            )
            if outcome:
                new_status = outcome

        if new_status != status or new_activated:
            start = _parse_ts(new_activated or activated_at or track.get("created_at"))
            holding = int((now - start).total_seconds()) if start else 0
            closed = now.isoformat() if new_status in TERMINAL_STATUSES else None

            observe_trade_price(
                track["id"],
                price=price,
                track=track,
                old_status=status,
                new_status=new_status,
                activated_at=new_activated or activated_at,
                now=now,
            )

            update_track(
                track["id"],
                track_status=new_status,
                profit_pct=profit,
                exit_price=exit_price if new_status in TERMINAL_STATUSES else None,
                failure_reason=failure,
                activated_at=new_activated,
                closed_at=closed,
                holding_seconds=holding if new_status in TERMINAL_STATUSES else 0,
            )

            updated_track = dict(track)
            updated_track["exit_price"] = exit_price if new_status in TERMINAL_STATUSES else None
            on_track_status_change(
                track["id"],
                track=updated_track,
                old_status=status,
                new_status=new_status,
                activated_at=new_activated or activated_at,
                closed_at=closed,
                profit_pct=profit,
                now=now,
            )

            updated += 1
            logger.info(
                "Analytics track %s #%s: %s -> %s",
                symbol, track["id"], status, new_status,
            )
        elif status in ("Waiting", "Active"):
            observe_trade_price(
                track["id"],
                price=price,
                track=track,
                old_status=status,
                new_status=status,
                activated_at=activated_at,
                now=now,
            )
    return updated


def _build_dashboard(records: list[dict]) -> AnalyticsDashboard:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    closed = [r for r in records if r.get("track_status") in WIN_STATUSES | LOSS_STATUSES]
    wins = [r for r in closed if r.get("track_status") in WIN_STATUSES]
    losses = [r for r in closed if r.get("track_status") in LOSS_STATUSES]

    win_rate = round(len(wins) / len(closed) * 100, 2) if closed else 0.0
    avg_profit = (
        round(sum(r.get("profit_pct", 0) for r in wins) / len(wins), 2) if wins else 0.0
    )
    avg_loss = (
        round(abs(sum(r.get("profit_pct", 0) for r in losses)) / len(losses), 2)
        if losses else 0.0
    )

    holding_records = [r for r in closed if r.get("holding_seconds", 0) > 0]
    avg_holding_h = (
        round(sum(r["holding_seconds"] for r in holding_records) / len(holding_records) / 3600, 2)
        if holding_records else 0.0
    )

    today_records = [r for r in records if r.get("created_at", "") >= today_start]
    highest_ai = max((r.get("ai_score", 0) for r in today_records), default=0.0)
    highest_conf = max((r.get("confidence_score", 0) for r in today_records), default=0.0)

    best_sector = _best_group(closed, "sector")
    best_tf = _best_group(closed, "timeframe")

    open_tracks = [r for r in records if r.get("track_status") not in TERMINAL_STATUSES]
    active = [r for r in open_tracks if r.get("track_status") == "Active"]

    return AnalyticsDashboard(
        total_signals=len(records),
        winning_signals=len(wins),
        losing_signals=len(losses),
        win_rate_pct=win_rate,
        average_profit_pct=avg_profit,
        average_loss_pct=avg_loss,
        average_holding_time_hours=avg_holding_h,
        best_performing_sector=best_sector,
        best_performing_timeframe=best_tf,
        highest_ai_score_today=round(highest_ai, 2),
        highest_confidence_today=round(highest_conf, 2),
        open_tracks=len(open_tracks),
        active_tracks=len(active),
    )


def _best_group(closed: list[dict], field: str) -> str:
    if not closed:
        return ""
    groups: dict[str, list[dict]] = {}
    for r in closed:
        key = (r.get(field) or "").strip()
        if not key:
            continue
        groups.setdefault(key, []).append(r)
    if not groups:
        return ""
    best_key = ""
    best_wr = -1.0
    for key, trades in groups.items():
        wins = sum(1 for t in trades if t.get("track_status") in WIN_STATUSES)
        wr = wins / len(trades) if trades else 0
        if wr > best_wr:
            best_wr = wr
            best_key = key
    return f"{best_key} ({best_wr * 100:.0f}% WR)" if best_key else ""


def _to_record(row: dict) -> SignalAnalyticsRecord:
    explanation = [
        SignalExplanationItem(**item) if isinstance(item, dict) else item
        for item in (row.get("explanation") or [])
    ]
    return SignalAnalyticsRecord(
        id=row["id"],
        symbol=row["symbol"],
        signal=row["signal"],
        signal_date=row["signal_date"],
        signal_time=row["signal_time"],
        timeframe=row.get("timeframe", "live"),
        ai_score=row["ai_score"],
        confidence_score=row["confidence_score"],
        entry_price=row["entry_price"],
        stop_loss=row["stop_loss"],
        target_1=row["target_1"],
        target_2=row["target_2"],
        target_3=row["target_3"],
        trend_direction=row["trend_direction"],
        market_status=row["market_status"],
        sector=row.get("sector", ""),
        industry=row.get("industry", ""),
        track_status=row.get("track_status", "Waiting"),
        trade_quality_stars=row.get("trade_quality_stars", 1),
        trade_quality_label=row.get("trade_quality_label", "Weak"),
        explanation=explanation,
        trend_strength=row.get("trend_strength", 0),
        relative_volume=row.get("relative_volume", 0),
        failure_reason=row.get("failure_reason"),
        profit_pct=row.get("profit_pct", 0),
        exit_price=row.get("exit_price"),
        created_at=row["created_at"],
        closed_at=row.get("closed_at"),
        holding_seconds=row.get("holding_seconds", 0),
        rank_score=_rank_score(row),
    )


def get_ranked_signals(limit: int = 50, symbol: str | None = None) -> RankedSignalsResponse:
    rows = get_signal_records(symbol=symbol, limit=limit * 3)
    all_rows = get_all_records(limit=5000)
    dashboard = _build_dashboard(all_rows)

    ranked = sorted(
        rows,
        key=lambda r: (
            -r.get("confidence_score", 0),
            -r.get("ai_score", 0),
            -r.get("trend_strength", 0),
            -r.get("relative_volume", 0),
        ),
    )[:limit]
    signals = [_to_record(r) for r in ranked]
    return RankedSignalsResponse(signals=signals, dashboard=dashboard)


def get_analytics_dashboard() -> AnalyticsDashboard:
    return _build_dashboard(get_all_records(limit=5000))


def get_performance_report() -> PerformanceReport:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()
    month_start = (now - timedelta(days=30)).isoformat()

    records = get_all_records(limit=5000)
    dashboard = _build_dashboard(records)

    closed = [r for r in records if r.get("track_status") in WIN_STATUSES | LOSS_STATUSES]
    returns = [r.get("profit_pct", 0) for r in closed]
    avg_return = round(sum(returns) / len(returns), 2) if returns else 0.0

    drawdowns = [abs(r.get("profit_pct", 0)) for r in closed if r.get("track_status") in LOSS_STATUSES]
    avg_dd = round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else 0.0

    sym_stats: dict[str, list[float]] = {}
    for r in closed:
        sym_stats.setdefault(r["symbol"], []).append(r.get("profit_pct", 0))

    best_sym = ""
    worst_sym = ""
    if sym_stats:
        best_sym = max(sym_stats, key=lambda s: sum(sym_stats[s]) / len(sym_stats[s]))
        worst_sym = min(sym_stats, key=lambda s: sum(sym_stats[s]) / len(sym_stats[s]))

    return PerformanceReport(
        today_signals=sum(1 for r in records if r.get("created_at", "") >= today_start),
        week_signals=sum(1 for r in records if r.get("created_at", "") >= week_start),
        month_signals=sum(1 for r in records if r.get("created_at", "") >= month_start),
        overall_total=len(records),
        win_rate=dashboard.win_rate_pct,
        average_return_pct=avg_return,
        average_drawdown_pct=avg_dd,
        best_symbol=best_sym,
        worst_symbol=worst_sym,
        wins=dashboard.winning_signals,
        losses=dashboard.losing_signals,
        dashboard=dashboard,
    )
