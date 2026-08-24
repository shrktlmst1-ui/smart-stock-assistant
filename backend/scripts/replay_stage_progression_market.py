"""
Market-wide Stage Progression replay — causal, walk-forward, no symbol-specific logic.

Run: python scripts/replay_stage_progression_market.py [--date 2026-08-24] [--max-symbols 80]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.premove_replay_lib import filter_premarket_regular, replay_session, summarize_replay
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient

DEFAULT_DATES = ["2026-08-22", "2026-08-23", "2026-08-24"]
BENCHMARKS = {"XPON", "LUCY", "BTCT", "BMEA", "GNS"}
MIN_PRICE = 0.5
MAX_PRICE = 50.0


async def fetch_grouped_daily(client: PolygonClient, date: str) -> list[dict]:
    data = await client._request(f"/v2/aggs/grouped/locale/us/market/stocks/{date}")
    return data.get("results", []) or []


def classify_universe(rows: list[dict], *, max_movers: int = 40, max_controls: int = 25) -> dict[str, list[str]]:
    """Build mover + control sample without look-ahead beyond session open."""
    eligible = []
    for r in rows:
        sym = r.get("T") or r.get("ticker") or ""
        if not sym or len(sym) > 5:
            continue
        o, c, v = float(r.get("o") or 0), float(r.get("c") or 0), float(r.get("v") or 0)
        if o <= 0 or c <= 0 or v < 50_000:
            continue
        chg = (c - o) / o * 100.0
        if not (MIN_PRICE <= c <= MAX_PRICE):
            continue
        eligible.append({"symbol": sym, "change_pct": chg, "volume": v, "close": c})

    eligible.sort(key=lambda x: x["change_pct"], reverse=True)

    buckets: dict[str, list[str]] = {
        "movers_10": [],
        "movers_20": [],
        "movers_50": [],
        "movers_100": [],
        "sideways": [],
        "controls": [],
    }

    for item in eligible:
        chg = item["change_pct"]
        sym = item["symbol"]
        if chg >= 100 and len(buckets["movers_100"]) < 8:
            buckets["movers_100"].append(sym)
        elif chg >= 50 and len(buckets["movers_50"]) < 10:
            buckets["movers_50"].append(sym)
        elif chg >= 20 and len(buckets["movers_20"]) < 12:
            buckets["movers_20"].append(sym)
        elif chg >= 10 and len(buckets["movers_10"]) < 15:
            buckets["movers_10"].append(sym)
        elif -2 <= chg <= 2 and len(buckets["sideways"]) < 10:
            buckets["sideways"].append(sym)

    flat_movers = []
    for k in ("movers_100", "movers_50", "movers_20", "movers_10"):
        flat_movers.extend(buckets[k])

    pool = [x for x in eligible if x["symbol"] not in flat_movers and -3 <= x["change_pct"] <= 5]
    random.shuffle(pool)
    buckets["controls"] = [x["symbol"] for x in pool[:max_controls]]

    # Always include benchmarks if present in eligible
    sym_set = {x["symbol"] for x in eligible}
    for b in BENCHMARKS:
        if b in sym_set:
            for k in buckets:
                if b not in buckets[k]:
                    if k == "movers_10" and b not in flat_movers:
                        buckets["movers_10"].append(b)
                    break

    all_syms = list(dict.fromkeys(flat_movers + buckets["sideways"] + buckets["controls"]))
    if len(all_syms) > max_movers + max_controls:
        all_syms = all_syms[: max_movers + max_controls]

    buckets["all"] = all_syms
    return buckets


async def replay_one(client: PolygonClient, symbol: str, session_date: str) -> dict:
    bars = await client.get_minute_bars_on_date(symbol, session_date)
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
        news_raw = await fetch_stock_news(client, symbol, limit=15)
    except Exception:
        news_raw = []

    bars = filter_premarket_regular(bars)
    if bars.empty or len(bars) < 5:
        return {"symbol": symbol, "session_date": session_date, "error": "insufficient_bars", "bars": len(bars)}

    prev = snap.get("prevDay") or {}
    previous_close = float(prev.get("c") or 0)
    if previous_close <= 0 and prior_bars is not None and not prior_bars.empty:
        previous_close = float(prior_bars["close"].iloc[-1])
    if previous_close <= 0:
        previous_close = float(bars["close"].iloc[0])

    timeline = replay_session(
        bars, prior_bars, news_raw, previous_close,
        symbol=symbol, session_date=session_date,
    )
    summary = summarize_replay(symbol, session_date, bars, timeline, previous_close)

    session_high = summary["session_high"]
    base = summary["base_price"]

    def _move_before(evt: dict | None) -> float | None:
        if not evt or base <= 0 or session_high <= base:
            return None
        return round((evt["price"] - base) / (session_high - base) * 100.0, 1)

    def _remaining_after(evt: dict | None) -> float | None:
        if not evt or session_high <= evt["price"]:
            return None
        total = session_high - base
        if total <= 0:
            return None
        return round((session_high - evt["price"]) / total * 100.0, 1)

    ew = next((t for t in timeline if t.get("lifecycle") == "EARLY_WATCH"), None)
    pb = next((t for t in timeline if t.get("lifecycle") == "PRE_BREAKOUT"), None)
    ee = next((t for t in timeline if t.get("lifecycle") == "EARLY_ENTRY"), None)

    summary.update({
        "percent_move_before_EW": _move_before(ew),
        "percent_move_before_PB": _move_before(pb),
        "percent_move_before_EE": _move_before(ee),
        "remaining_move_after_EE": _remaining_after(ee),
        "max_stage_progression_score": max((t.get("stage_progression_score", 0) for t in timeline), default=0),
        "max_persistence_minutes": max((t.get("persistence_minutes", 0) for t in timeline), default=0),
        "had_failed_setup": any(t.get("lifecycle") == "FAILED_SETUP" for t in timeline),
        "session_change_pct": round((session_high - previous_close) / previous_close * 100, 1) if previous_close else 0,
    })
    summary["timeline"] = timeline
    return summary


def aggregate_kpis(results: list[dict]) -> dict:
    valid = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    ew = sum(1 for r in valid if r.get("early_watch_time"))
    pb = sum(1 for r in valid if r.get("pre_breakout_time"))
    ee = sum(1 for r in valid if r.get("early_entry_time"))
    bc = sum(1 for r in valid if r.get("breakout_confirmed_time"))
    failed = sum(1 for r in valid if r.get("failed_setup_time") or r.get("had_failed_setup"))
    late = sum(1 for r in valid if r.get("too_late_time"))
    detected = sum(1 for r in valid if r.get("first_detection_time"))

    strong_movers = [r for r in valid if r.get("session_change_pct", 0) >= 20]
    strong_detected = [r for r in strong_movers if r.get("first_detection_time")]
    early_entry_hits = [r for r in valid if r.get("early_entry_time")]
    false_positives = [
        r for r in valid
        if r.get("early_entry_time") and r.get("session_change_pct", 0) < 8
    ]

    recall = len(strong_detected) / len(strong_movers) if strong_movers else 0.0
    precision = (
        (len(early_entry_hits) - len(false_positives)) / len(early_entry_hits)
        if early_entry_hits else 0.0
    )
    fp_rate = len(false_positives) / len(valid) if valid else 0.0

    lead_times = [r["lead_time_minutes"] for r in valid if r.get("lead_time_minutes") is not None]
    lead_times.sort()
    median_lead = lead_times[len(lead_times) // 2] if lead_times else None

    move_before_ee = [r["percent_move_before_EE"] for r in valid if r.get("percent_move_before_EE") is not None]
    move_before_ee.sort()
    median_move_before = move_before_ee[len(move_before_ee) // 2] if move_before_ee else None

    ew_to_pb = sum(1 for r in valid if r.get("early_watch_time") and r.get("pre_breakout_time"))
    pb_to_ee = sum(1 for r in valid if r.get("pre_breakout_time") and r.get("early_entry_time"))
    ee_to_break = sum(1 for r in valid if r.get("early_entry_time") and r.get("breakout_time"))

    return {
        "total_symbols_scanned": len(results),
        "successful_replays": len(valid),
        "errors": len(errors),
        "early_candidates": detected,
        "EARLY_WATCH": ew,
        "PRE_BREAKOUT": pb,
        "EARLY_ENTRY": ee,
        "BREAKOUT_CONFIRMED": bc,
        "FAILED_SETUP": failed,
        "TOO_LATE": late,
        "valid_breakouts": sum(1 for r in valid if r.get("breakout_time")),
        "false_positives": len(false_positives),
        "false_positive_rate": round(fp_rate, 3),
        "early_detection_recall": round(recall, 3),
        "early_entry_precision": round(max(0.0, precision), 3),
        "EW_to_PB_conversion": round(ew_to_pb / ew, 3) if ew else 0.0,
        "PB_to_EE_conversion": round(pb_to_ee / pb, 3) if pb else 0.0,
        "EE_to_breakout_success": round(ee_to_break / ee, 3) if ee else 0.0,
        "median_lead_time_min": median_lead,
        "median_move_before_EE_pct": median_move_before,
        "strong_movers_count": len(strong_movers),
        "strong_movers_detected": len(strong_detected),
    }


def pick_examples(results: list[dict]) -> dict:
    valid = [r for r in results if "error" not in r]

    def row(r: dict, result: str) -> dict:
        return {
            "symbol": r["symbol"],
            "first_detection": r.get("first_detection_time"),
            "EW": r.get("early_watch_time"),
            "PB": r.get("pre_breakout_time"),
            "EE": r.get("early_entry_time"),
            "breakout": r.get("breakout_time"),
            "lead_time": r.get("lead_time_minutes"),
            "result": result,
        }

    success = [
        r for r in valid
        if r.get("early_watch_time")
        and r.get("session_change_pct", 0) >= 15
        and (r.get("percent_move_before_EW") or 100) < 40
    ]
    failed = [r for r in valid if r.get("had_failed_setup") or r.get("false_positive")]
    normal = [r for r in valid if not r.get("early_entry_time") and r.get("session_change_pct", 0) < 5]

    return {
        "successful_early": [row(r, "SUCCESS") for r in success[:5]],
        "failed_setups": [row(r, "FAILED/FAKE") for r in failed[:5]],
        "normal_no_entry": [row(r, "NO_ENTRY") for r in normal[:5]],
    }


async def main() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", action="append", dest="dates", default=None)
    parser.add_argument("--max-symbols", type=int, default=60)
    args = parser.parse_args()

    dates = args.dates or DEFAULT_DATES
    n_dates = len(dates)
    dev_cut = max(1, int(n_dates * 0.6))
    val_cut = max(dev_cut + 1, int(n_dates * 0.8)) if n_dates >= 3 else n_dates

    splits = {
        "development": dates[:dev_cut],
        "validation": dates[dev_cut:val_cut] if n_dates >= 2 else [],
        "out_of_sample": dates[val_cut:] if n_dates >= 3 else [],
    }

    client = PolygonClient()
    all_results: list[dict] = []
    split_results: dict[str, list[dict]] = {k: [] for k in splits}

    try:
        for date in dates:
            try:
                grouped = await fetch_grouped_daily(client, date)
            except Exception as exc:
                print(f"[WARN] grouped daily {date}: {exc}")
                grouped = []

            if grouped:
                universe = classify_universe(grouped, max_movers=args.max_symbols // 2)
                symbols = universe["all"][: args.max_symbols]
            else:
                symbols = list(BENCHMARKS)

            print(f"[INFO] {date}: replaying {len(symbols)} symbols")
            for sym in symbols:
                try:
                    res = await replay_one(client, sym, date)
                    all_results.append(res)
                    for split_name, split_dates in splits.items():
                        if date in split_dates:
                            split_results[split_name].append(res)
                except Exception as exc:
                    all_results.append({"symbol": sym, "session_date": date, "error": str(exc)})
    finally:
        await client.close()

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "dates": dates,
        "walk_forward_splits": splits,
        "aggregate_kpis": aggregate_kpis(all_results),
        "split_kpis": {k: aggregate_kpis(v) for k, v in split_results.items() if v},
        "examples": pick_examples(all_results),
        "benchmark_summaries": {
            r["symbol"]: {k: r.get(k) for k in (
                "session_date", "early_watch_time", "pre_breakout_time", "early_entry_time",
                "too_late_time", "first_detection_time", "lead_time_minutes",
                "percent_move_before_EW", "percent_move_before_EE", "remaining_move_after_EE",
                "max_stage_progression_score", "valid_detection", "false_positive", "session_change_pct",
            )}
            for r in all_results if r.get("symbol") in BENCHMARKS and "error" not in r
        },
    }

    out_path = Path(__file__).resolve().parent / "stage_progression_market_report.json"
    slim = dict(report)
    out_path.write_text(json.dumps(slim, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, ensure_ascii=False, indent=2, default=str))
    print("\n--- EXAMPLES ---")
    print(json.dumps(report["examples"], ensure_ascii=False, indent=2, default=str))
    print(f"\nReport saved: {out_path}")
    return report


if __name__ == "__main__":
    asyncio.run(main())
