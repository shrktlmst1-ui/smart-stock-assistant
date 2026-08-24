"""
Multi-stock Pre-Move replay — BEFORE vs AFTER comparison.
Run: python scripts/replay_premove_multi.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.premove_replay_lib import filter_premarket_regular, replay_session, summarize_replay
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient

SESSION_DATE = "2026-08-24"

BEFORE_BASELINE: dict[str, dict] = {
    "XPON": {
        "first_detection_time": None,
        "first_detection_price": None,
        "first_detection_score": None,
        "early_watch_time": None,
        "pre_breakout_time": None,
        "early_entry_time": None,
        "breakout_price": 7.0,
        "late_guard_time": "2026-08-24 08:32:00",
        "late_guard_price": 6.21,
        "too_late_time": "2026-08-24 08:28:00",
        "too_late_price": 4.40,
        "max_score": 39,
        "percent_move_before_detection": None,
        "valid_detection": False,
        "false_positive": False,
    },
    "LUCY": {
        "first_detection_time": None,
        "first_detection_price": None,
        "first_detection_score": 42,
        "early_watch_time": None,
        "max_score": 42,
        "valid_detection": False,
        "false_positive": False,
    },
    "BTCT": {
        "first_detection_time": None,
        "first_detection_price": None,
        "first_detection_score": 12,
        "early_watch_time": None,
        "max_score": 12,
        "valid_detection": False,
        "false_positive": False,
    },
}

REPLAY_SYMBOLS = [
    ("XPON", SESSION_DATE),
    ("LUCY", SESSION_DATE),
    ("BTCT", SESSION_DATE),
    ("BMEA", SESSION_DATE),
    ("GNS", SESSION_DATE),
]


async def replay_symbol(client: PolygonClient, symbol: str, session_date: str) -> dict:
    bars = await client.get_minute_bars_on_date(symbol, session_date)
    prior_date = (datetime.strptime(session_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prior_bars = await client.get_minute_bars_on_date(symbol, prior_date)
    snap = await client.get_snapshot(symbol)
    news_raw = await fetch_stock_news(client, symbol, limit=20)

    bars = filter_premarket_regular(bars)
    prev = snap.get("prevDay") or {}
    previous_close = float(prev.get("c") or 0)
    if previous_close <= 0 and not prior_bars.empty:
        previous_close = float(prior_bars["close"].iloc[-1])

    timeline = replay_session(bars, prior_bars, news_raw, previous_close, symbol=symbol, session_date=session_date)
    return summarize_replay(symbol, session_date, bars, timeline, previous_close)


async def main() -> dict:
    results: dict[str, dict] = {}
    client = PolygonClient()
    try:
        for sym, dt in REPLAY_SYMBOLS:
            try:
                results[sym] = await replay_symbol(client, sym, dt)
            except Exception as exc:
                results[sym] = {"symbol": sym, "error": str(exc)}
    finally:
        await client.close()

    comparison = []
    for sym, after in results.items():
        before = BEFORE_BASELINE.get(sym, {})
        comparison.append({
            "symbol": sym,
            "before": {
                "first_detection_price": before.get("first_detection_price"),
                "first_detection_time": before.get("first_detection_time"),
                "first_score": before.get("first_detection_score") or before.get("max_score"),
                "early_watch": before.get("early_watch_time"),
                "pre_breakout": before.get("pre_breakout_time"),
                "early_entry": before.get("early_entry_time"),
                "breakout_price": before.get("breakout_price"),
                "pct_move_before_detection": before.get("percent_move_before_detection"),
                "valid": before.get("valid_detection"),
                "false_positive": before.get("false_positive"),
            },
            "after": {
                "first_detection_price": after.get("first_detection_price"),
                "first_detection_time": after.get("first_detection_time"),
                "first_score": after.get("first_detection_score"),
                "early_watch": after.get("early_watch_time"),
                "pre_breakout": after.get("pre_breakout_time"),
                "early_entry": after.get("early_entry_time"),
                "breakout_price": after.get("breakout_price"),
                "lead_time": after.get("lead_time_minutes"),
                "pct_move_before_detection": after.get("percent_move_before_detection"),
                "valid": after.get("valid_detection"),
                "false_positive": after.get("false_positive"),
            },
        })

    xpon = results.get("XPON", {})
    return {
        "session_date": SESSION_DATE,
        "comparison": comparison,
        "xpon_timeline": xpon.get("timeline", []),
        "full_results": {k: {kk: vv for kk, vv in v.items() if kk != "timeline"} for k, v in results.items()},
    }


if __name__ == "__main__":
    out = asyncio.run(main())
    out_path = Path(__file__).resolve().parent / "premove_replay_after.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
