"""Trade Replay & Post-Trade Analytics service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from database.signal_analytics_db import get_record_by_id
from database.trade_replay_db import (
    add_price_tick,
    add_timeline_event,
    create_replay,
    finalize_replay,
    get_all_closed_replays,
    get_replay_by_signal_id,
    get_replays_with_signals,
    get_timeline,
    update_replay_metrics,
)
from models.trade_replay import (
    PerformanceInsights,
    PostTradeAnalysis,
    TradeReplayDetail,
    TradeReplayListResponse,
    TradeTimelineEvent,
)

logger = logging.getLogger(__name__)

WIN_STATUSES = frozenset({"Target 1 Hit", "Target 2 Hit", "Target 3 Hit"})
LOSS_STATUSES = frozenset({"Stop Loss Hit"})
BREAKEVEN_THRESHOLD = 0.15


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _unrealized_pct(entry: float, price: float, is_buy: bool) -> float:
    if entry <= 0:
        return 0.0
    if is_buy:
        return (price - entry) / entry * 100
    return (entry - price) / entry * 100


def _drawdown_pct(entry: float, price: float, is_buy: bool) -> float:
    """Adverse move from entry as positive percentage."""
    if entry <= 0:
        return 0.0
    if is_buy:
        return max(0.0, (entry - price) / entry * 100)
    return max(0.0, (price - entry) / entry * 100)


def compute_entry_quality(ai_score: float, confidence: float, risk_reward: float) -> float:
    rr_component = min(risk_reward, 5.0) / 5.0 * 100
    return round(ai_score * 0.45 + confidence * 0.35 + rr_component * 0.20, 2)


def compute_post_trade_quality(
    ai_score: float,
    confidence: float,
    risk_reward: float,
    max_drawdown_pct: float,
    max_profit_pct: float,
    final_result: str,
) -> str:
    rr_score = min(risk_reward, 5.0) / 5.0 * 100
    dd_score = max(0.0, 100.0 - max_drawdown_pct * 4.0)
    profit_score = min(max_profit_pct, 12.0) / 12.0 * 100

    composite = (
        ai_score * 0.22
        + confidence * 0.18
        + rr_score * 0.15
        + dd_score * 0.22
        + profit_score * 0.23
    )
    if final_result == "LOSS":
        composite *= 0.65
    elif final_result == "BREAKEVEN":
        composite *= 0.85

    if composite >= 82:
        return "Excellent"
    if composite >= 70:
        return "Very Good"
    if composite >= 58:
        return "Good"
    if composite >= 45:
        return "Average"
    return "Poor"


def _final_result(track_status: str, profit_pct: float) -> str:
    if track_status in WIN_STATUSES:
        return "WIN"
    if track_status in LOSS_STATUSES:
        return "LOSS"
    if abs(profit_pct) <= BREAKEVEN_THRESHOLD:
        return "BREAKEVEN"
    if profit_pct > 0:
        return "WIN"
    if profit_pct < 0:
        return "LOSS"
    return "BREAKEVEN"


def init_trade_replay(
    signal_id: int,
    *,
    symbol: str,
    entry_price: float,
    ai_score: float,
    confidence: float,
    risk_reward_ratio: float,
    created_at: str,
    signal_time: str,
) -> None:
    """Create replay record and initial timeline event."""
    entry_quality = compute_entry_quality(ai_score, confidence, risk_reward_ratio)
    create_replay(
        signal_id,
        risk_reward_ratio=risk_reward_ratio,
        entry_quality_score=entry_quality,
        created_at=created_at,
    )
    add_timeline_event(
        signal_id,
        event_time=signal_time,
        event_label="Signal Generated",
        price=entry_price,
        sort_order=0,
    )
    logger.debug("Trade replay initialized signal_id=%s %s", signal_id, symbol)


def _timeline_label(status: str) -> str | None:
    return {
        "Active": "Entry Triggered",
        "Target 1 Hit": "Target 1 Hit",
        "Target 2 Hit": "Target 2 Hit",
        "Target 3 Hit": "Target 3 Hit",
        "Stop Loss Hit": "Stop Loss Hit",
        "Expired": "Trade Expired",
    }.get(status)


def _sort_order(status: str) -> int:
    return {
        "Active": 1,
        "Target 1 Hit": 2,
        "Target 2 Hit": 3,
        "Target 3 Hit": 4,
        "Stop Loss Hit": 5,
        "Expired": 6,
    }.get(status, 99)


def observe_trade_price(
    signal_id: int,
    *,
    price: float,
    track: dict,
    old_status: str,
    new_status: str,
    activated_at: str | None,
    now: datetime,
) -> None:
    """Record live price tick and update running excursion metrics."""
    if price <= 0 or track["signal"] not in ("Buy", "Sell"):
        return

    entry = track["entry_price"]
    is_buy = track["signal"] == "Buy"
    observed_at = now.isoformat()

    add_price_tick(signal_id, observed_at, price)

    replay = get_replay_by_signal_id(signal_id)
    if not replay:
        return

    # Only track excursions after entry is triggered
    tracking = new_status in ("Active",) or old_status == "Active" or activated_at
    if not tracking and new_status == "Waiting":
        return

    highest = replay.get("highest_price")
    lowest = replay.get("lowest_price")
    if highest is None:
        highest = price
        lowest = price
    else:
        highest = max(highest, price)
        lowest = min(lowest, price)

    profit = _unrealized_pct(entry, highest if is_buy else lowest, is_buy)
    adverse = _drawdown_pct(entry, lowest if is_buy else highest, is_buy)
    max_profit = max(replay.get("max_profit_pct", 0), profit)
    max_dd = max(replay.get("max_drawdown_pct", 0), adverse)

    entry_ts = _parse_ts(activated_at or track.get("activated_at") or track.get("created_at"))
    elapsed = int((now - entry_ts).total_seconds()) if entry_ts else None

    tp1 = track["target_1"]
    tp2 = track["target_2"]
    tp3 = track["target_3"]
    stop = track["stop_loss"]

    updates: dict = {
        "highest_price": highest,
        "lowest_price": lowest,
        "max_profit_pct": round(max_profit, 3),
        "max_drawdown_pct": round(max_dd, 3),
    }

    if elapsed is not None:
        if is_buy:
            if price >= tp1 and replay.get("time_to_tp1_seconds") is None:
                updates["time_to_tp1_seconds"] = elapsed
            if price >= tp2 and replay.get("time_to_tp2_seconds") is None:
                updates["time_to_tp2_seconds"] = elapsed
            if price >= tp3 and replay.get("time_to_tp3_seconds") is None:
                updates["time_to_tp3_seconds"] = elapsed
            if price <= stop and replay.get("time_to_stop_seconds") is None:
                updates["time_to_stop_seconds"] = elapsed
        else:
            if price <= tp1 and replay.get("time_to_tp1_seconds") is None:
                updates["time_to_tp1_seconds"] = elapsed
            if price <= tp2 and replay.get("time_to_tp2_seconds") is None:
                updates["time_to_tp2_seconds"] = elapsed
            if price <= tp3 and replay.get("time_to_tp3_seconds") is None:
                updates["time_to_tp3_seconds"] = elapsed
            if price >= stop and replay.get("time_to_stop_seconds") is None:
                updates["time_to_stop_seconds"] = elapsed

    update_replay_metrics(signal_id, **updates)


def on_track_status_change(
    signal_id: int,
    *,
    track: dict,
    old_status: str,
    new_status: str,
    activated_at: str | None,
    closed_at: str | None,
    profit_pct: float,
    now: datetime,
) -> None:
    """Add timeline events and finalize post-trade analysis when trade closes."""
    replay = get_replay_by_signal_id(signal_id)
    if not replay:
        return

    event_time = _format_time(now)
    label = _timeline_label(new_status)
    if label and new_status != old_status:
        add_timeline_event(
            signal_id,
            event_time=event_time,
            event_label=label,
            price=track.get("exit_price"),
            sort_order=_sort_order(new_status),
        )

    if new_status in TERMINAL_STATUSES and not replay.get("is_closed"):
        add_timeline_event(
            signal_id,
            event_time=event_time,
            event_label="Trade Closed",
            price=track.get("exit_price"),
            sort_order=10,
        )

        entry_ts = _parse_ts(activated_at or track.get("activated_at") or track.get("created_at"))
        close_ts = _parse_ts(closed_at or now.isoformat())
        duration = int((close_ts - entry_ts).total_seconds()) if entry_ts and close_ts else 0

        final = _final_result(new_status, profit_pct)
        quality = compute_post_trade_quality(
            track.get("ai_score", 0),
            track.get("confidence_score", 0),
            replay.get("risk_reward_ratio", 0),
            replay.get("max_drawdown_pct", 0),
            replay.get("max_profit_pct", 0),
            final,
        )

        refreshed = get_replay_by_signal_id(signal_id) or replay
        finalize_replay(
            signal_id,
            final_result=final,
            trade_duration_seconds=duration,
            post_trade_quality=quality,
            max_profit_pct=refreshed.get("max_profit_pct", 0),
            max_drawdown_pct=refreshed.get("max_drawdown_pct", 0),
            highest_price=refreshed.get("highest_price") or track["entry_price"],
            lowest_price=refreshed.get("lowest_price") or track["entry_price"],
            closed_at=closed_at or now.isoformat(),
        )


def _build_post_trade_analysis(replay: dict, track: dict) -> PostTradeAnalysis:
    return PostTradeAnalysis(
        final_result=replay.get("final_result") or "",
        max_profit_pct=round(replay.get("max_profit_pct", 0), 3),
        max_drawdown_pct=round(replay.get("max_drawdown_pct", 0), 3),
        highest_price_after_entry=replay.get("highest_price"),
        lowest_price_after_entry=replay.get("lowest_price"),
        time_to_target_1_seconds=replay.get("time_to_tp1_seconds"),
        time_to_target_2_seconds=replay.get("time_to_tp2_seconds"),
        time_to_target_3_seconds=replay.get("time_to_tp3_seconds"),
        time_to_stop_loss_seconds=replay.get("time_to_stop_seconds"),
        trade_duration_seconds=replay.get("trade_duration_seconds") or track.get("holding_seconds", 0),
        post_trade_quality=replay.get("post_trade_quality") or "",
        entry_quality_score=round(replay.get("entry_quality_score", 0), 2),
        risk_reward_ratio=round(replay.get("risk_reward_ratio", 0), 2),
    )


def get_trade_replay_detail(signal_id: int) -> TradeReplayDetail | None:
    from database.signal_analytics_db import get_record_by_id

    track = get_record_by_id(signal_id)
    if not track:
        return None
    replay = get_replay_by_signal_id(signal_id)
    if not replay:
        return None

    timeline = [
        TradeTimelineEvent(
            event_time=e["event_time"],
            event_label=e["event_label"],
            price=e.get("price"),
        )
        for e in get_timeline(signal_id)
    ]

    post_trade = _build_post_trade_analysis(replay, track) if replay.get("is_closed") else None

    return TradeReplayDetail(
        signal_id=signal_id,
        symbol=track["symbol"],
        signal=track["signal"],
        signal_date=track["signal_date"],
        signal_time=track["signal_time"],
        entry_price=track["entry_price"],
        stop_loss=track["stop_loss"],
        target_1=track["target_1"],
        target_2=track["target_2"],
        target_3=track["target_3"],
        ai_score=track["ai_score"],
        confidence_score=track["confidence_score"],
        timeframe=track.get("timeframe", "live"),
        track_status=track.get("track_status", ""),
        timeline=timeline,
        post_trade=post_trade,
        live_max_profit_pct=round(replay.get("max_profit_pct", 0), 3),
        live_max_drawdown_pct=round(replay.get("max_drawdown_pct", 0), 3),
        entry_quality_score=round(replay.get("entry_quality_score", 0), 2),
        is_closed=bool(replay.get("is_closed")),
    )


def get_trade_replay_list(limit: int = 50, symbol: str | None = None) -> TradeReplayListResponse:
    rows = get_replays_with_signals(limit=limit * 2)
    if symbol:
        rows = [r for r in rows if r["symbol"].upper() == symbol.upper()]

    details: list[TradeReplayDetail] = []
    for row in rows[:limit]:
        detail = get_trade_replay_detail(row["signal_id"])
        if detail:
            details.append(detail)

    return TradeReplayListResponse(
        replays=details,
        insights=compute_performance_insights(),
    )


def compute_performance_insights() -> PerformanceInsights:
    closed = get_all_closed_replays(limit=5000)
    if not closed:
        return PerformanceInsights()

    from database.signal_analytics_db import get_all_records
    signal_map = {r["id"]: r for r in get_all_records(limit=5000)}

    tp_times: list[int] = []
    drawdowns: list[float] = []
    profits: list[float] = []
    durations: list[int] = []
    tf_wins: dict[str, list[bool]] = {}
    quality_scores: list[tuple[float, str]] = []

    for replay in closed:
        sid = replay["signal_id"]
        sig = signal_map.get(sid, {})
        drawdowns.append(replay.get("max_drawdown_pct", 0))
        profits.append(replay.get("max_profit_pct", 0))
        if replay.get("trade_duration_seconds"):
            durations.append(replay["trade_duration_seconds"])

        for key in ("time_to_tp1_seconds", "time_to_tp2_seconds", "time_to_tp3_seconds"):
            val = replay.get(key)
            if val is not None:
                tp_times.append(val)

        tf = sig.get("timeframe", "live")
        won = replay.get("final_result") == "WIN"
        tf_wins.setdefault(tf, []).append(won)

        eq = replay.get("entry_quality_score", 0)
        quality_scores.append((eq, sig.get("symbol", "")))

    avg_tp = round(sum(tp_times) / len(tp_times), 0) if tp_times else 0.0
    avg_dd = round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else 0.0
    avg_profit = round(sum(profits) / len(profits), 2) if profits else 0.0

    best_holding = 0
    if durations:
        best_holding = max(durations)

    best_tf = ""
    best_tf_wr = -1.0
    for tf, results in tf_wins.items():
        wr = sum(results) / len(results) if results else 0
        if wr > best_tf_wr:
            best_tf_wr = wr
            best_tf = tf

    best_entry = ""
    worst_entry = ""
    if quality_scores:
        best_entry = max(quality_scores, key=lambda x: x[0])[1]
        worst_entry = min(quality_scores, key=lambda x: x[0])[1]

    return PerformanceInsights(
        average_time_to_target_seconds=avg_tp,
        average_drawdown_pct=avg_dd,
        average_profit_pct=avg_profit,
        best_holding_time_seconds=best_holding,
        best_timeframe=f"{best_tf} ({best_tf_wr * 100:.0f}% WR)" if best_tf else "",
        best_entry_quality_symbol=best_entry,
        worst_entry_quality_symbol=worst_entry,
        closed_trades=len(closed),
    )
