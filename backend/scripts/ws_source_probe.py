#!/usr/bin/env python3
"""Phase 1 — Stocks WebSocket source probe (diagnostic only, no production writes).

Tests: Connect → Auth → A.* → T/Q for auto-selected symbols.
Stops immediately if A, T, or Q channel fails.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets

from config import POLYGON_WS_URL, SCANNER_MAX_PRICE, SCANNER_MIN_PRICE, get_polygon_api_key
from services.connection_service import _wait_ws_auth
from services.market_session import get_us_market_session
from services.polygon_client import PolygonClient
from services.session_price import _ns_to_datetime

PROBE_SECONDS = 60
AUTO_SYMBOL_COUNT = 8
QUEUE_MAX = 10_000


@dataclass
class ChannelStats:
    messages: int = 0
    symbols: set[str] = field(default_factory=set)
    ages_ms: list[float] = field(default_factory=list)
    subscribe_ok: bool = False
    subscribe_status: str = "pending"


@dataclass
class ProbeReport:
    ws_url: str
    session: str
    connect_ok: bool = False
    auth_ok: bool = False
    reconnect_count: int = 0
    dropped_messages: int = 0
    queue_high_water: int = 0
    queue_size_end: int = 0
    channels: dict[str, ChannelStats] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""

    def channel(self, ev: str) -> ChannelStats:
        if ev not in self.channels:
            self.channels[ev] = ChannelStats()
        return self.channels[ev]

    @property
    def passed(self) -> bool:
        if not (self.connect_ok and self.auth_ok):
            return False
        for key in ("A", "T", "Q"):
            ch = self.channels.get(key)
            if not ch or not ch.subscribe_ok or ch.messages == 0:
                return False
        return True


def _price_from_snapshot(ticker: dict) -> float:
    day = ticker.get("day") or {}
    prev = ticker.get("prevDay") or {}
    last = ticker.get("lastTrade") or {}
    for src in (last, day, prev):
        p = src.get("p") or src.get("c")
        if p and float(p) > 0:
            return float(p)
    return 0.0


def _volume_from_snapshot(ticker: dict) -> float:
    day = ticker.get("day") or {}
    return float(day.get("v") or 0)


async def _pick_symbols_from_market() -> list[str]:
    client = PolygonClient()
    try:
        tickers = await client.get_full_market_snapshot()
    finally:
        await client.close()
    candidates: list[tuple[str, float, float]] = []
    for t in tickers:
        sym = (t.get("ticker") or "").upper()
        if not sym or len(sym) > 5:
            continue
        price = _price_from_snapshot(t)
        if price < SCANNER_MIN_PRICE or price > SCANNER_MAX_PRICE:
            continue
        vol = _volume_from_snapshot(t)
        if vol <= 0:
            continue
        candidates.append((sym, vol, price))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:AUTO_SYMBOL_COUNT]]


def _event_age_ms(ev: dict, received_mono: float) -> float | None:
    """Exchange timestamp age in ms."""
    sym_ev = ev.get("ev", "")
    ts = ev.get("t") or ev.get("s") or ev.get("e")
    if ts is None:
        return None
    try:
        ts_f = float(ts)
    except (TypeError, ValueError):
        return None
    if ts_f > 1e15:
        ex_dt = _ns_to_datetime(ts_f)
    elif ts_f > 1e12:
        ex_dt = datetime.fromtimestamp(ts_f / 1000.0, tz=timezone.utc)
    else:
        ex_dt = datetime.fromtimestamp(ts_f, tz=timezone.utc)
    if ex_dt is None:
        return None
    now = datetime.now(timezone.utc)
    return max(0.0, (now - ex_dt).total_seconds() * 1000.0)


async def run_probe(duration_sec: int = PROBE_SECONDS) -> ProbeReport:
    api_key = get_polygon_api_key()
    report = ProbeReport(
        ws_url=POLYGON_WS_URL,
        session=get_us_market_session(),
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    if not api_key:
        report.errors.append("no_api_key")
        return report

    symbols = await _pick_symbols_from_market()
    if not symbols:
        report.errors.append("no_symbols_from_snapshot")
        return report

    msg_queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
    stop = asyncio.Event()

    async def reader(ws) -> None:
        nonlocal report
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                report.errors.append(f"recv_error:{exc}")
                break
            try:
                if msg_queue.full():
                    report.dropped_messages += 1
                    try:
                        msg_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                msg_queue.put_nowait((time.monotonic(), raw))
                qs = msg_queue.qsize()
                if qs > report.queue_high_water:
                    report.queue_high_water = qs
            except asyncio.QueueFull:
                report.dropped_messages += 1

    async def processor(ws) -> None:
        nonlocal report
        subscribed_a = False
        subscribed_tq = False
        tq_params = ",".join(
            f"{ch}.{s}" for s in symbols for ch in ("T", "Q")
        )
        deadline = time.monotonic() + duration_sec

        while time.monotonic() < deadline and not stop.is_set():
            try:
                _, raw = await asyncio.wait_for(msg_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if not subscribed_a:
                    await ws.send(json.dumps({"action": "subscribe", "params": "A.*"}))
                    report.channel("A").subscribe_status = "sent A.*"
                if not subscribed_tq and time.monotonic() > deadline - duration_sec + 5:
                    await ws.send(json.dumps({"action": "subscribe", "params": tq_params}))
                    report.channel("T").subscribe_status = f"sent T for {len(symbols)} syms"
                    report.channel("Q").subscribe_status = f"sent Q for {len(symbols)} syms"
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            events = data if isinstance(data, list) else [data]
            for ev in events:
                if ev.get("ev") == "status":
                    st = ev.get("status", "")
                    msg = ev.get("message", "")
                    if st == "success" and "A.*" in msg:
                        report.channel("A").subscribe_ok = True
                        report.channel("A").subscribe_status = msg
                        subscribed_a = True
                    if st == "success" and any(f"T.{s}" in msg or f"Q.{s}" in msg for s in symbols):
                        if "T." in msg:
                            report.channel("T").subscribe_ok = True
                            report.channel("T").subscribe_status = msg[:200]
                        if "Q." in msg:
                            report.channel("Q").subscribe_ok = True
                            report.channel("Q").subscribe_status = msg[:200]
                        subscribed_tq = True
                    continue

                ev_type = ev.get("ev", "")
                if ev_type not in ("A", "T", "Q"):
                    continue
                ch = report.channel(ev_type)
                ch.messages += 1
                sym = (ev.get("sym") or "").upper()
                if sym:
                    ch.symbols.add(sym)
                age = _event_age_ms(ev, time.monotonic())
                if age is not None:
                    ch.ages_ms.append(age)

        report.queue_size_end = msg_queue.qsize()

    try:
        async with websockets.connect(POLYGON_WS_URL, ping_interval=20, ping_timeout=20) as ws:
            report.connect_ok = True
            await ws.send(json.dumps({"action": "auth", "params": api_key}))
            auth_ok, auth_msg = await _wait_ws_auth(ws)
            report.auth_ok = auth_ok
            if not auth_ok:
                report.errors.append(f"auth_failed:{auth_msg}")
                return report

            await ws.send(json.dumps({"action": "subscribe", "params": "A.*"}))
            report.channel("A").subscribe_status = "sent A.*"

            await asyncio.sleep(2.0)
            tq_params = ",".join(f"{ch}.{s}" for s in symbols for ch in ("T", "Q"))
            await ws.send(json.dumps({"action": "subscribe", "params": tq_params}))
            report.channel("T").subscribe_status = f"sent T x{len(symbols)}"
            report.channel("Q").subscribe_status = f"sent Q x{len(symbols)}"

            reader_task = asyncio.create_task(reader(ws))
            proc_task = asyncio.create_task(processor(ws))
            await asyncio.sleep(duration_sec)
            stop.set()
            reader_task.cancel()
            proc_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
            try:
                await proc_task
            except asyncio.CancelledError:
                pass

            for key in ("A", "T", "Q"):
                ch = report.channel(key)
                if ch.messages > 0:
                    ch.subscribe_ok = True

    except Exception as exc:
        report.errors.append(str(exc))

    report.ended_at = datetime.now(timezone.utc).isoformat()
    report._auto_symbols = symbols  # type: ignore[attr-defined]
    return report


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def print_report(r: ProbeReport) -> None:
    symbols = getattr(r, "_auto_symbols", [])
    print("\n" + "=" * 72)
    print("PHASE 1 — WEBSOCKET SOURCE PROBE")
    print("=" * 72)
    print(f"WebSocket URL:     {r.ws_url}")
    print(f"Market session:    {r.session}")
    print(f"Connect:           {'PASS' if r.connect_ok else 'FAIL'}")
    print(f"Auth:              {'PASS' if r.auth_ok else 'FAIL'}")
    print(f"Auto symbols ({len(symbols)}): {', '.join(symbols)}")
    print(f"Duration:          {PROBE_SECONDS}s")
    print(f"Reconnects:        {r.reconnect_count}")
    print(f"Dropped messages:  {r.dropped_messages}")
    print(f"Queue high water:  {r.queue_high_water}")
    print(f"Queue size (end):  {r.queue_size_end}")
    print("-" * 72)
    for key in ("A", "T", "Q"):
        ch = r.channels.get(key)
        if not ch:
            print(f"{key}: FAIL — no subscription")
            continue
        med_age = _median(ch.ages_ms)
        p95 = sorted(ch.ages_ms)[int(len(ch.ages_ms) * 0.95)] if ch.ages_ms else 0
        ok = ch.subscribe_ok and ch.messages > 0
        print(
            f"{key}: {'PASS' if ok else 'FAIL'} | "
            f"subscribe={ch.subscribe_status[:80]} | "
            f"messages={ch.messages} | symbols={len(ch.symbols)} | "
            f"age_ms median={med_age:.0f} p95={p95:.0f}"
        )
    if r.errors:
        print(f"Errors: {r.errors}")
    print("-" * 72)
    overall = "PASS" if r.passed else "FAIL"
    print(f"OVERALL: {overall}")
    if not r.passed:
        print("STOP — A/T/Q source not verified. Do not use REST for live alerts.")
    print("=" * 72)


async def main() -> int:
    report = await run_probe(PROBE_SECONDS)
    print_report(report)
    out_path = Path(__file__).resolve().parent / "ws_source_probe_report.json"
    payload = {
        "ws_url": report.ws_url,
        "session": report.session,
        "connect_ok": report.connect_ok,
        "auth_ok": report.auth_ok,
        "reconnect_count": report.reconnect_count,
        "dropped_messages": report.dropped_messages,
        "queue_high_water": report.queue_high_water,
        "queue_size_end": report.queue_size_end,
        "auto_symbols": getattr(report, "_auto_symbols", []),
        "channels": {
            k: {
                "subscribe_ok": v.subscribe_ok,
                "subscribe_status": v.subscribe_status,
                "messages": v.messages,
                "symbol_count": len(v.symbols),
                "symbols_sample": sorted(v.symbols)[:20],
                "age_ms_median": _median(v.ages_ms),
            }
            for k, v in report.channels.items()
        },
        "passed": report.passed,
        "errors": report.errors,
        "started_at": report.started_at,
        "ended_at": report.ended_at,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report saved: {out_path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
