#!/usr/bin/env python3
"""Live WebSocket source truth — production hub only on Render (no competing connection).

Modes:
  --production (default on Render)  GET /internal/ws-truth on localhost — same uvicorn process hub
  --direct                          FORBIDDEN on Render unless WS_TRUTH_ALLOW_DIRECT=1 (causes 1008)

A.* alone is NOT proof of T/Q. PASS requires t_subscribe_success, q_subscribe_success,
trades_delta>0, quotes_delta>0, and pipeline evaluation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LISTEN_SECONDS = int(os.getenv("WS_TRUTH_SECONDS", "45"))


def _is_render() -> bool:
    return bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_NAME"))


def _production_api_base() -> str:
    port = os.getenv("PORT", "8000")
    return os.getenv("WS_TRUTH_API_BASE", f"http://127.0.0.1:{port}")


def fetch_production_truth(seconds: int) -> dict:
    url = f"{_production_api_base()}/internal/ws-truth?seconds={seconds}"
    try:
        with urllib.request.urlopen(url, timeout=seconds + 30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"passed": False, "errors": [f"http_{exc.code}:{body[:200]}"]}
    except Exception as exc:
        return {"passed": False, "errors": [str(exc)]}


async def run_in_process_production(seconds: int) -> dict:
    from services.ws_truth_audit import run_production_truth_audit

    report = await run_production_truth_audit(listen_seconds=seconds)
    return report.to_dict()


def print_report(data: dict) -> None:
    print("\n" + "=" * 72)
    print("WS SOURCE TRUTH — PRODUCTION HUB")
    print("=" * 72)
    print(f"mode:              {data.get('mode', 'unknown')}")
    print(f"session:           {data.get('session', '')}")
    print(f"1 auth_success:    {data.get('auth_success')}")
    print(f"2 a_subscribe:     {data.get('a_subscribe_success')} (NOT sufficient alone)")
    print(f"2 t_subscribe:     {data.get('t_subscribe_success')}")
    print(f"2 q_subscribe:     {data.get('q_subscribe_success')}")
    print(f"2 subscribe_ok:    {data.get('subscribe_success')} (T AND Q required)")
    print("   provider_status_messages:")
    for m in data.get("provider_status_messages", [])[-15:]:
        print(f"     {m}")
    ch = data.get("subscribed_channels", {})
    print(f"   channels:        T={ch.get('T_count')} Q={ch.get('Q_count')} A={ch.get('A_count')}")
    print(f"     T_symbols:     {ch.get('T_symbols_sample', [])}")
    print(f"     Q_symbols:     {ch.get('Q_symbols_sample', [])}")
    print(f"3 trades_delta:    {data.get('trades_delta')}")
    print(f"4 quotes_delta:    {data.get('quotes_delta')}")
    print(f"   aggregates_delta:{data.get('aggregates_delta')}")
    lt = data.get("last_trade", {})
    print(f"5 last_trade:      sym={lt.get('symbol')} price={lt.get('price')} time={lt.get('exchange_time')}")
    lq = data.get("last_quote", {})
    print(f"   last_quote:      sym={lq.get('symbol')} price={lq.get('price')} bid={lq.get('bid')} ask={lq.get('ask')} time={lq.get('exchange_time')}")
    print(f"   dynamic_symbols: {data.get('dynamic_symbols', [])}")
    print("6 pipeline:")
    for p in data.get("pipeline_results", []):
        print(f"   {p}")
    if data.get("errors"):
        print(f"errors: {data['errors']}")
    print("-" * 72)
    print(f"OVERALL: {'PASS' if data.get('passed') else 'FAIL'}")
    if _is_render():
        print("NOTE: Use --production (default) — never --direct on Render (1008 max_connections).")
    print("=" * 72)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--production",
        action="store_true",
        help="Audit running production hub via /internal/ws-truth (default on Render)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="BLOCKED on Render — opens 2nd WS connection (1008 policy violation)",
    )
    parser.add_argument("--in-process", action="store_true", help="Run audit inside current Python process")
    parser.add_argument("--seconds", type=int, default=LISTEN_SECONDS)
    args = parser.parse_args()

    use_production = args.production or args.in_process or not args.direct
    if _is_render() and args.direct and os.getenv("WS_TRUTH_ALLOW_DIRECT") != "1":
        print("ERROR: --direct forbidden on Render (single WS connection). Use --production.")
        return 2

    if args.direct and os.getenv("WS_TRUTH_ALLOW_DIRECT") != "1":
        print("ERROR: --direct disabled. Set WS_TRUTH_ALLOW_DIRECT=1 only for isolated local testing.")
        print("       Second connection causes 1008 when production hub is running.")
        return 2

    if args.in_process:
        data = await run_in_process_production(args.seconds)
    elif use_production:
        data = fetch_production_truth(args.seconds)
        if not data.get("passed") and "http_404" in str(data.get("errors")):
            data["errors"] = data.get("errors", []) + [
                "endpoint_missing — deploy /internal/ws-truth or use --in-process inside uvicorn"
            ]
    else:
        print("ERROR: --direct removed from default path; use --production")
        return 2

    print_report(data)
    out = Path(__file__).resolve().parent / "ws_source_truth_report.json"
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Report: {out}")
    return 0 if data.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
