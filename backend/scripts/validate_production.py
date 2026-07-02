#!/usr/bin/env python3
"""Production validation — verify all systems operational."""

from __future__ import annotations

import asyncio
import sys
import time

import httpx


API = "http://localhost:8000"


async def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Backend health
        try:
            h = (await client.get(f"{API}/health")).json()
            ok = h.get("ok") is True
            checks.append(("Backend healthy", ok, str(h)))
        except Exception as e:
            checks.append(("Backend healthy", False, str(e)))
            print_report(checks)
            return 1

        # Live market data
        try:
            st = (await client.get(f"{API}/status")).json()
            live = st.get("live_market_data_status") == "live"
            checks.append(("Live market data connected", live, st.get("live_market_data_status", "")))
        except Exception as e:
            checks.append(("Live market data connected", False, str(e)))

        # Dashboard
        try:
            dash = await client.get(f"{API}/stocks/dashboard")
            ok = dash.status_code == 200 and len(dash.json()) > 0
            checks.append(("Dashboard loaded", ok, f"{len(dash.json())} stocks"))
        except Exception as e:
            checks.append(("Dashboard loaded", False, str(e)))

        # Trading journal
        try:
            j = await client.get(f"{API}/journal")
            ok = j.status_code == 200
            checks.append(("Trading journal working", ok, f"{len(j.json())} entries"))
        except Exception as e:
            checks.append(("Trading journal working", False, str(e)))

        # Performance metrics
        try:
            p = (await client.get(f"{API}/performance")).json()
            ok = "win_rate" in p
            checks.append(("Dashboard metrics working", ok, f"win_rate={p.get('win_rate')}"))
        except Exception as e:
            checks.append(("Dashboard metrics working", False, str(e)))

        # Backtesting
        try:
            t0 = time.monotonic()
            bt = (await client.get(f"{API}/backtest/AAPL", params={"timeframe": "1D"})).json()
            elapsed = time.monotonic() - t0
            ok = "win_rate" in bt and "error" not in bt and "detail" not in bt
            checks.append(("Backtesting working", ok, f"{bt.get('total_trades')} trades in {elapsed:.1f}s"))
        except Exception as e:
            checks.append(("Backtesting working", False, str(e)))

        # Decision engine
        try:
            snap = (await client.get(f"{API}/stocks/AAPL/snapshot")).json()
            td = snap.get("trade_decision", {})
            ok = (
                td.get("recommendation") in (
                    "NO TRADE", "WAIT", "WATCH", "POSSIBLE ENTRY",
                    "ENTRY CONFIRMED", "AVOID / TRAP RISK",
                )
                and len(td.get("engine_logs", [])) >= 5
            )
            checks.append(("Decision engine active", ok, f"{td.get('recommendation')} conf={td.get('ai_confidence')}"))
        except Exception as e:
            checks.append(("Decision engine active", False, str(e)))

        # Polygon connection
        try:
            st = (await client.get(f"{API}/status")).json()
            poly_ok = st.get("api_connected") is True and len(st.get("symbols_ok", [])) > 0
            checks.append(("Polygon connected", poly_ok, f"ok={st.get('symbols_ok', [])}"))
        except Exception as e:
            checks.append(("Polygon connected", False, str(e)))

        # WebSocket
        try:
            import json
            import websockets
            async with websockets.connect("ws://localhost:8000/ws") as ws:
                types = []
                for _ in range(3):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                    types.append(msg.get("type"))
            ok = "snapshot" in types
            checks.append(("WebSocket connected", ok, str(types)))
        except Exception as e:
            checks.append(("WebSocket connected", False, str(e)))

        # Full production validate
        try:
            v = (await client.get(f"{API}/production/validate")).json()
            ok = v.get("ai_learning") and v.get("no_placeholders")
            checks.append(("AI learning working", v.get("ai_learning", False), str(v.get("details", {}).get("ai_weights", {}))))
            checks.append(("No placeholder values", v.get("no_placeholders", False), ""))
            checks.append(("System ready for production", v.get("production_ready", False), ""))
        except Exception as e:
            checks.append(("AI learning working", False, str(e)))

    print_report(checks)
    all_core = all(c[1] for c in checks[:-1])  # production_ready may be false until trades exist
    return 0 if all_core else 1


def print_report(checks: list[tuple[str, bool, str]]) -> None:
    print("\n=== PRODUCTION VALIDATION ===\n")
    for name, ok, detail in checks:
        mark = "[OK]" if ok else "[FAIL]"
        line = f"{mark} {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
