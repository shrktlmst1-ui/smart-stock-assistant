"""
Detailed stage timeline + multi-symbol validation.
Run: python scripts/xpon_stage_timeline.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.premove_replay_lib import (
    ET,
    analyze_causal_bar,
    filter_premarket_regular,
    replay_session,
    summarize_replay,
)
from analysis.pre_move_levels import compute_trade_levels
from analysis.pre_move_breakout import compute_breakout_metrics
from analysis.pre_move_vwap import compute_vwap_metrics
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient

SESSION_DATE = "2026-08-24"

SYMBOLS = [
    "XPON",
    "LUCY",
    "BTCT",
    "BMEA",
    "GNS",   # candidate: often volatile / potential fake breakout
    "SGBX",  # candidate: low-move day check
]


def _levels_at_bar(bars, prior_bars, news, prev_close, idx) -> dict:
    t = analyze_causal_bar(bars, prior_bars, news, prev_close, idx)
    window = bars.iloc[: idx + 1]
    price = float(window["close"].iloc[-1])
    pm_mask = window["timestamp"].dt.tz_convert(ET).dt.time < datetime.strptime("09:30", "%H:%M").time()
    pm_high = float(window.loc[pm_mask]["high"].max()) if pm_mask.any() else 0.0
    vwap_m = compute_vwap_metrics(window, price)
    brk = compute_breakout_metrics(window, price, premarket_high=pm_high, day_high=0, prev_day_high=0)
    trigger, el, eh, stop, tp1, tp2, rrr = compute_trade_levels(price, brk, window, vwap=vwap_m.vwap)
    t["trigger_price"] = trigger
    t["entry_low"] = el
    t["entry_high"] = eh
    t["stop_loss"] = stop
    t["tp1"] = tp1
    t["tp2"] = tp2
    t["risk_reward"] = rrr
    bd = t.get("breakdown") or {}
    t["premove_score"] = t["score"]
    from analysis.pre_move_volume import compute_rvol_same_time, compute_volume_metrics
    vm = compute_volume_metrics(window)
    t["rvol"] = vm.rvol
    t["rvol_same_time"] = compute_rvol_same_time(window, prior_bars)
    t["pre_expansion_bonus"] = bd.get("pre_expansion_bonus", 0)
    t["late_guard_active"] = t["late_guard"]
    return t


def _format_row(t: dict) -> dict:
    rvol_st = t.get("rvol_same_time")
    ps = t.get("premove_score", t.get("score"))
    return {
        "time": t["time_et"],
        "price": t["price"],
        "premove_score": ps,
        "early_activity_score": t["early_activity_score"],
        "rvol": t.get("rvol"),
        "rvol_same_time": rvol_st if rvol_st is not None else "N/A",
        "volume_acceleration_1m": t["volume_acceleration_1m"],
        "volume_acceleration_slope": t.get("volume_acceleration_slope"),
        "trade_velocity": t["trade_velocity"],
        "compression_3m": t["compression_3m"],
        "higher_lows": t["micro_higher_lows"],
        "higher_lows_score": t["higher_lows_score"],
        "resistance_distance_pct": t["resistance_distance_pct"],
        "price_volume_response": t.get("price_volume_response"),
        "confluence_factors": t.get("confluence_factors", []),
        "pre_expansion_bonus": t.get("pre_expansion_bonus", 0),
        "change_pct": t["change_pct"],
        "status": t["status"],
        "late_guard": t["late_guard"],
        "late_reasons": t.get("late_reasons", []),
    }


def _timeline_watch_to_late(timeline: list[dict]) -> list[dict]:
    ew_idx = next((i for i, t in enumerate(timeline) if t["status"] == "EARLY_WATCH"), None)
    if ew_idx is None:
        ew_idx = next((i for i, t in enumerate(timeline) if t["score"] >= 60), 0)
    late_idx = next((i for i, t in enumerate(timeline) if t["status"] == "TOO_LATE_TO_CHASE"), len(timeline) - 1)
    start = ew_idx if ew_idx is not None else 0
    return [_format_row(t) for t in timeline[start : late_idx + 1]]


async def replay_symbol(client: PolygonClient, symbol: str) -> dict:
    bars = await client.get_minute_bars_on_date(symbol, SESSION_DATE)
    prior_date = (datetime.strptime(SESSION_DATE, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prior_bars = await client.get_minute_bars_on_date(symbol, prior_date)
    snap = await client.get_snapshot(symbol)
    news = await fetch_stock_news(client, symbol, limit=20)
    bars = filter_premarket_regular(bars)
    prev = float((snap.get("prevDay") or {}).get("c") or 0)
    if prev <= 0 and not prior_bars.empty:
        prev = float(prior_bars["close"].iloc[-1])
    if bars.empty:
        return {"symbol": symbol, "error": "no bars"}

    timeline = replay_session(bars, prior_bars, news, prev)
    summary = summarize_replay(symbol, SESSION_DATE, bars, timeline, prev)

    # enrich milestones with trade levels
    milestones = {}
    for key, status_filter in [
        ("early_watch", lambda t: t["status"] == "EARLY_WATCH"),
        ("pre_breakout", lambda t: t["status"] == "PRE_BREAKOUT"),
        ("early_entry", lambda t: t["status"] in ("EARLY_ENTRY", "HIGH_CONVICTION_EARLY")),
        ("too_late", lambda t: t["status"] == "TOO_LATE_TO_CHASE"),
        ("late_guard", lambda t: t["late_guard"]),
    ]:
        hit = next((t for t in timeline if status_filter(t)), None)
        if hit:
            enriched = _levels_at_bar(bars, prior_bars, news, prev, hit["bar_idx"])
            milestones[key] = enriched

    base = float(bars["low"].min())
    session_high = float(bars["high"].max())
    early_entry = milestones.get("early_entry")
    pct_before_entry = None
    pct_remaining = None
    if early_entry and base > 0:
        ep = early_entry["price"]
        pct_before_entry = round((ep - base) / base * 100, 2)
        if session_high > ep:
            total = session_high - base
            remaining = session_high - ep
            pct_remaining = round(remaining / total * 100, 1) if total > 0 else None

    ew = milestones.get("early_watch")
    lg = milestones.get("late_guard")
    tl = milestones.get("too_late")
    lead_watch_to_late = None
    if ew and tl:
        t0 = datetime.strptime(ew["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        t1 = datetime.strptime(tl["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        lead_watch_to_late = round((t1 - t0).total_seconds() / 60, 1)

    return {
        **{k: v for k, v in summary.items() if k != "timeline"},
        "milestones": milestones,
        "watch_to_late_timeline": _timeline_watch_to_late(timeline),
        "stage_progression": {
            "early_watch": ew["time_et"] if ew else None,
            "pre_breakout": milestones.get("pre_breakout", {}).get("time_et") if milestones.get("pre_breakout") else None,
            "early_entry": early_entry["time_et"] if early_entry else None,
            "too_late": tl["time_et"] if tl else None,
            "skipped_stages": (
                "PRE_BREAKOUT+EARLY_ENTRY skipped"
                if ew and not milestones.get("pre_breakout") and tl
                else None
            ),
        },
        "pct_before_early_entry": pct_before_entry,
        "pct_remaining_after_early_entry": pct_remaining,
        "lead_watch_to_late_minutes": lead_watch_to_late,
        "full_timeline_count": len(timeline),
    }


async def main() -> dict:
    results: dict = {}
    client = PolygonClient()
    try:
        for sym in SYMBOLS:
            try:
                results[sym] = await replay_symbol(client, sym)
            except Exception as e:
                results[sym] = {"symbol": sym, "error": str(e)}
    finally:
        await client.close()

    table = []
    for sym, r in results.items():
        if r.get("error"):
            table.append({"symbol": sym, "error": r["error"]})
            continue
        m = r.get("milestones") or {}
        table.append({
            "symbol": sym,
            "EARLY_WATCH": f"{m.get('early_watch', {}).get('time_et', '—')} @ ${m.get('early_watch', {}).get('price', '—')}" if m.get("early_watch") else "—",
            "PRE_BREAKOUT": f"{m.get('pre_breakout', {}).get('time_et', '—')} @ ${m.get('pre_breakout', {}).get('price', '—')}" if m.get("pre_breakout") else "—",
            "EARLY_ENTRY": f"{m.get('early_entry', {}).get('time_et', '—')} @ ${m.get('early_entry', {}).get('price', '—')}" if m.get("early_entry") else "—",
            "Breakout": f"{r.get('breakout_time', '—')} @ ${r.get('breakout_price', '—')}",
            "TOO_LATE": f"{r.get('too_late_time', '—')} @ ${r.get('too_late_price', '—')}",
            "Lead_Time": r.get("lead_watch_to_late_minutes") or r.get("lead_time_minutes"),
            "Pct_Move_Before_Entry": r.get("pct_before_early_entry"),
            "Valid_False": "VALID" if r.get("valid_detection") and not r.get("false_positive") else ("FALSE+" if r.get("false_positive") else "PARTIAL" if m.get("early_watch") else "NO"),
            "stage_skip": r.get("stage_progression", {}).get("skipped_stages"),
        })

    return {"session_date": SESSION_DATE, "comparison_table": table, "symbols": results}


if __name__ == "__main__":
    out = asyncio.run(main())
    path = Path(__file__).resolve().parent / "xpon_stage_timeline.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
