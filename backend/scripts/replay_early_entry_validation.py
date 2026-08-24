"""
EARLY_ENTRY Gate validation — PB→EE precision focus, walk-forward, causal replay.

Run: python scripts/replay_early_entry_validation.py [--date 2026-08-24] [--max-symbols 60]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.premove_replay_lib import filter_premarket_regular, replay_session
from scripts.replay_stage_progression_market import classify_universe, fetch_grouped_daily
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient

ET = ZoneInfo("America/New_York")
BENCHMARKS = ["XPON", "BTCT", "LUCY", "BMEA", "GNS"]


def _outcome_after_ee(bars, ee_idx: int, *, stop: float, tp1: float, tp2: float) -> dict:
    """Causal post-EE outcome — only bars after EE minute."""
    hit_stop = hit_tp1 = hit_tp2 = False
    stop_bar = tp1_bar = tp2_bar = None
    for i in range(ee_idx + 1, len(bars)):
        lo = float(bars["low"].iloc[i])
        hi = float(bars["high"].iloc[i])
        ts = bars["timestamp"].iloc[i].tz_convert(ET).strftime("%H:%M")
        if not hit_stop and stop > 0 and lo <= stop:
            hit_stop = True
            stop_bar = ts
        if not hit_tp1 and tp1 > 0 and hi >= tp1:
            hit_tp1 = True
            tp1_bar = ts
        if not hit_tp2 and tp2 > 0 and hi >= tp2:
            hit_tp2 = True
            tp2_bar = ts
    return {
        "stop_hit": hit_stop,
        "tp1_hit": hit_tp1,
        "tp2_hit": hit_tp2,
        "stop_bar": stop_bar,
        "tp1_bar": tp1_bar,
        "tp2_bar": tp2_bar,
    }


async def replay_symbol(client: PolygonClient, symbol: str, session_date: str) -> dict:
    bars_raw = await client.get_minute_bars_on_date(symbol, session_date)
    prior_date = (datetime.strptime(session_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        prior_bars = await client.get_minute_bars_on_date(symbol, prior_date)
    except Exception:
        prior_bars = None

    try:
        snap = await client.get_snapshot(symbol)
    except Exception:
        snap = {}
    try:
        news = await fetch_stock_news(client, symbol, limit=10)
    except Exception:
        news = []

    bars = filter_premarket_regular(bars_raw)
    if bars.empty or len(bars) < 5:
        return {"symbol": symbol, "session_date": session_date, "error": "insufficient_bars"}

    prev = snap.get("prevDay") or {}
    previous_close = float(prev.get("c") or 0)
    if previous_close <= 0 and prior_bars is not None and not prior_bars.empty:
        previous_close = float(prior_bars["close"].iloc[-1])

    timeline = replay_session(bars, prior_bars, news, previous_close, symbol=symbol, session_date=session_date)
    base = float(bars["low"].min())
    session_high = float(bars["high"].max())

    pb_evt = next((t for t in timeline if t.get("lifecycle") == "PRE_BREAKOUT"), None)
    ee_evt = next((t for t in timeline if t.get("lifecycle") == "EARLY_ENTRY"), None)
    breakout_evt = next((t for t in timeline if t.get("lifecycle") == "BREAKOUT_CONFIRMED"), None)
    if not breakout_evt:
        for t in timeline:
            if t.get("status") == "CONFIRMED_ENTRY":
                breakout_evt = t
                break

    ee_outcome = {}
    if ee_evt:
        ee_outcome = _outcome_after_ee(
            bars, ee_evt["bar_idx"],
            stop=ee_evt.get("stop_loss", 0),
            tp1=ee_evt.get("tp1", 0),
            tp2=ee_evt.get("tp2", 0),
        )

    session_chg = (session_high - previous_close) / previous_close * 100 if previous_close else 0
    ee_success = False
    if ee_evt:
        outcome = ee_outcome
        favorable = session_high >= ee_evt["price"] * 1.03
        stopped = outcome.get("stop_hit", False)
        ee_success = favorable and not stopped

    ee_fp = ee_evt is not None and not ee_success
    ee_lead = None
    if ee_evt and breakout_evt:
        t0 = datetime.strptime(ee_evt["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        t1 = datetime.strptime(breakout_evt["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        ee_lead = round((t1 - t0).total_seconds() / 60.0, 1)

    remaining = None
    move_before = None
    if ee_evt and session_high > base:
        total = session_high - base
        if total > 0:
            move_before = round((ee_evt["price"] - base) / total * 100, 1)
            remaining = round((session_high - ee_evt["price"]) / total * 100, 1)

    # Collect PB windows that blocked EE
    pb_blocks = [
        {
            "time": t["time_et"],
            "blocks": t.get("ee_block_reasons", []),
            "quality_blocks": t.get("ee_quality_blocks", []),
            "readiness": t.get("trigger_readiness_score"),
            "confluence_quality": t.get("ee_confluence_quality"),
        }
        for t in timeline
        if t.get("lifecycle") == "PRE_BREAKOUT" and (t.get("ee_block_reasons") or t.get("ee_quality_blocks"))
    ]

    return {
        "symbol": symbol,
        "session_date": session_date,
        "session_change_pct": round(session_chg, 1),
        "base_price": round(base, 4),
        "session_high": session_high,
        "had_pre_breakout": pb_evt is not None,
        "had_early_entry": ee_evt is not None,
        "pb_time": pb_evt["time_et"] if pb_evt else None,
        "pb_price": pb_evt["price"] if pb_evt else None,
        "ee_time": ee_evt["time_et"] if ee_evt else None,
        "ee_price": ee_evt["price"] if ee_evt else None,
        "ee_confidence": ee_evt.get("ee_confidence", []) if ee_evt else [],
        "ee_rrr": ee_evt.get("risk_reward") if ee_evt else None,
        "ee_confluence_quality": ee_evt.get("ee_confluence_quality") if ee_evt else None,
        "ee_price_holding": ee_evt.get("ee_quality_factors") if ee_evt else None,
        "ee_volume_efficiency": ee_evt.get("ee_volume_efficiency") if ee_evt else None,
        "ee_rejection_score": ee_evt.get("ee_rejection_score") if ee_evt else None,
        "ee_breakout_failure_risk": ee_evt.get("ee_breakout_failure_risk") if ee_evt else None,
        "trigger_price": ee_evt.get("trigger_price") if ee_evt else None,
        "stop_loss": ee_evt.get("stop_loss") if ee_evt else None,
        "tp1": ee_evt.get("tp1") if ee_evt else None,
        "tp2": ee_evt.get("tp2") if ee_evt else None,
        "breakout_time": breakout_evt["time_et"] if breakout_evt else None,
        "breakout_price": breakout_evt["price"] if breakout_evt else None,
        "ee_lead_time_min": ee_lead,
        "move_before_ee_pct": move_before,
        "remaining_after_ee_pct": remaining,
        "ee_success": ee_success,
        "ee_false_positive": ee_fp,
        "outcome": ee_outcome,
        "pb_block_samples": pb_blocks[:3],
        "xpon_ee_blocks_at_late": pb_blocks if symbol == "XPON" else None,
    }


def aggregate(results: list[dict]) -> dict:
    valid = [r for r in results if "error" not in r]
    pb = [r for r in valid if r["had_pre_breakout"]]
    ee = [r for r in valid if r["had_early_entry"]]
    ee_fp = [r for r in ee if r.get("ee_false_positive")]
    ee_ok = [r for r in ee if r.get("ee_success") and not r.get("ee_false_positive")]

    leads = [r["ee_lead_time_min"] for r in ee if r.get("ee_lead_time_min") is not None]
    move_before = [r["move_before_ee_pct"] for r in ee if r.get("move_before_ee_pct") is not None]
    remaining = [r["remaining_after_ee_pct"] for r in ee if r.get("remaining_after_ee_pct") is not None]

    stops = sum(1 for r in ee if r.get("outcome", {}).get("stop_hit"))
    tp1s = sum(1 for r in ee if r.get("outcome", {}).get("tp1_hit"))
    tp2s = sum(1 for r in ee if r.get("outcome", {}).get("tp2_hit"))

    ee_with_breakout = [r for r in ee if r.get("breakout_time")]
    ee_break_success = sum(1 for r in ee_with_breakout if r.get("ee_success"))
    rrr_vals = [r["ee_rrr"] for r in ee if r.get("ee_rrr") is not None]
    movers = [r for r in valid if r.get("session_change_pct", 0) >= 8]
    ee_coverage = round(len(ee) / len(movers), 3) if movers else 0.0

    return {
        "total_pre_breakout": len(pb),
        "total_early_entry": len(ee),
        "pb_to_ee_conversion": round(len(ee) / len(pb), 3) if pb else 0.0,
        "ee_to_breakout_success": round(ee_break_success / len(ee_with_breakout), 3) if ee_with_breakout else 0.0,
        "early_entry_precision": round(len(ee_ok) / len(ee), 3) if ee else 0.0,
        "early_entry_false_positive_rate": round(len(ee_fp) / len(valid), 3) if valid else 0.0,
        "median_ee_lead_time_min": statistics.median(leads) if leads else None,
        "median_move_before_ee_pct": statistics.median(move_before) if move_before else None,
        "median_remaining_after_ee_pct": statistics.median(remaining) if remaining else None,
        "stop_hit_rate_after_ee": round(stops / len(ee), 3) if ee else 0.0,
        "tp1_hit_rate_after_ee": round(tp1s / len(ee), 3) if ee else 0.0,
        "tp2_hit_rate_after_ee": round(tp2s / len(ee), 3) if ee else 0.0,
        "median_rrr": round(statistics.median(rrr_vals), 2) if rrr_vals else None,
        "ee_coverage": ee_coverage,
    }


def ee_breakdown(results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        if "error" in r or not r.get("had_early_entry"):
            continue
        rows.append({
            "symbol": r["symbol"],
            "session_date": r.get("session_date"),
            "ee_time": r.get("ee_time"),
            "ee_price": r.get("ee_price"),
            "trigger": r.get("trigger_price"),
            "stop": r.get("stop_loss"),
            "tp1": r.get("tp1"),
            "tp2": r.get("tp2"),
            "rrr": r.get("ee_rrr"),
            "confluence_quality": r.get("ee_confluence_quality"),
            "volume_efficiency": r.get("ee_volume_efficiency"),
            "rejection_score": r.get("ee_rejection_score"),
            "breakout_failure_risk": r.get("ee_breakout_failure_risk"),
            "result": "SUCCESS" if r.get("ee_success") else "FALSE_POS",
            "stop_hit": r.get("outcome", {}).get("stop_hit"),
            "tp1_hit": r.get("outcome", {}).get("tp1_hit"),
        })
    return rows


def rejected_breakdown(results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        if "error" in r or not r.get("had_pre_breakout") or r.get("had_early_entry"):
            continue
        for sample in r.get("pb_block_samples") or []:
            blocks = (sample.get("blocks") or []) + (sample.get("quality_blocks") or [])
            reason = "other"
            for b in blocks:
                bl = b.lower()
                if "price_holding" in bl:
                    reason = "weak_price_holding"
                elif "rrr" in bl or "stop_dist" in bl:
                    reason = "bad_rrr"
                elif "rejection" in bl:
                    reason = "rejection_wick"
                elif "liquidity" in bl:
                    reason = "weak_liquidity"
                elif "spread" in bl:
                    reason = "widening_spread"
                elif "vol_efficiency" in bl or "churn" in bl:
                    reason = "churn_volume"
                elif "breakout_failure" in bl or "higher_low" in bl:
                    reason = "failed_persistence"
            rows.append({
                "symbol": r["symbol"],
                "session_date": r.get("session_date"),
                "pb_time": r.get("pb_time"),
                "block_time": sample.get("time"),
                "reason": reason,
                "blocks": blocks[:5],
                "confluence_quality": sample.get("confluence_quality"),
            })
    return rows[:30]


def result_table(results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        if "error" in r:
            continue
        if not r.get("had_pre_breakout") and not r.get("had_early_entry"):
            continue
        outcome = "EE_BLOCKED" if r.get("had_pre_breakout") and not r.get("had_early_entry") else (
            "EE_SUCCESS" if r.get("ee_success") and not r.get("ee_false_positive") else (
                "EE_FALSE_POS" if r.get("ee_false_positive") else (
                    "EE_WEAK" if r.get("had_early_entry") else "PB_ONLY"
                )
            )
        )
        rows.append({
            "symbol": r["symbol"],
            "PB Time": r.get("pb_time"),
            "PB Price": r.get("pb_price"),
            "EE Time": r.get("ee_time"),
            "EE Price": r.get("ee_price"),
            "Breakout Time": r.get("breakout_time"),
            "Breakout Price": r.get("breakout_price"),
            "Lead Time": r.get("ee_lead_time_min"),
            "R:R": r.get("ee_rrr"),
            "TP1 Hit": r.get("outcome", {}).get("tp1_hit"),
            "Stop Hit": r.get("outcome", {}).get("stop_hit"),
            "Result": outcome,
        })
    return rows


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", action="append", dest="dates", default=None)
    parser.add_argument("--max-symbols", type=int, default=55)
    args = parser.parse_args()

    dates = args.dates or ["2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24"]
    n = len(dates)
    cal_end = max(1, int(n * 0.6))
    val_end = max(cal_end + 1, int(n * 0.8)) if n >= 3 else n
    splits = {"calibration": dates[:cal_end], "validation": dates[cal_end:val_end], "out_of_sample": dates[val_end:]}

    client = PolygonClient()
    all_results: list[dict] = []
    split_results: dict[str, list[dict]] = {k: [] for k in splits}

    try:
        for date in dates:
            try:
                grouped = await fetch_grouped_daily(client, date)
                symbols = classify_universe(grouped, max_movers=args.max_symbols // 2)["all"][: args.max_symbols]
                for b in BENCHMARKS:
                    if b not in symbols:
                        symbols.append(b)
            except Exception:
                symbols = BENCHMARKS

            for sym in symbols:
                try:
                    res = await replay_symbol(client, sym, date)
                    all_results.append(res)
                    for sn, sd in splits.items():
                        if date in sd:
                            split_results[sn].append(res)
                except Exception as exc:
                    all_results.append({"symbol": sym, "session_date": date, "error": str(exc)})
    finally:
        await client.close()

    table = result_table(all_results)
    success = [r for r in table if r["Result"] == "EE_SUCCESS"][:5]
    failed = [r for r in table if r["Result"] in ("EE_FALSE_POS", "EE_WEAK")][:5]
    blocked = [r for r in table if r["Result"] == "EE_BLOCKED"][:5]

    benchmarks = {r["symbol"]: r for r in all_results if r.get("symbol") in BENCHMARKS and "error" not in r}

    before_baseline = {
        "label": "BEFORE (timing gate only, 2026-08-24)",
        "total_pre_breakout": 25,
        "total_early_entry": 7,
        "pb_to_ee_conversion": 0.28,
        "early_entry_precision": 0.143,
        "early_entry_false_positive_rate": 0.12,
        "median_ee_lead_time_min": 6.0,
        "median_move_before_ee_pct": 16.7,
        "median_remaining_after_ee_pct": 83.3,
        "stop_hit_rate_after_ee": 0.571,
        "tp1_hit_rate_after_ee": 0.12,
        "tp2_hit_rate_after_ee": None,
    }
    after_kpis = aggregate(all_results)

    report = {
        "generated_at": datetime.now(ET).isoformat(),
        "dates": dates,
        "walk_forward_splits": splits,
        "before_baseline": before_baseline,
        "after_quality_gate": after_kpis,
        "delta": {
            k: round(after_kpis.get(k, 0) - before_baseline.get(k, 0), 3)
            if isinstance(after_kpis.get(k), (int, float)) and isinstance(before_baseline.get(k), (int, float))
            else None
            for k in before_baseline
            if k != "label"
        },
        "aggregate_kpis": after_kpis,
        "split_kpis": {k: aggregate(v) for k, v in split_results.items() if v},
        "early_entry_breakdown": ee_breakdown(all_results),
        "rejected_breakdown": rejected_breakdown(all_results),
        "examples_success": success,
        "examples_failed": failed,
        "examples_blocked": blocked,
        "benchmarks": {
            sym: {
                "pb_time": b.get("pb_time"),
                "ee_time": b.get("ee_time"),
                "ee_blocks": b.get("pb_block_samples"),
                "session_change_pct": b.get("session_change_pct"),
            }
            for sym, b in benchmarks.items()
        },
        "full_table_sample": table[:25],
    }

    out = Path(__file__).resolve().parent / "early_entry_validation_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    asyncio.run(main())
