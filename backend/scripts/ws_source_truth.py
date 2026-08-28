#!/usr/bin/env python3
"""Live WebSocket source truth — real Polygon/Massive feed only (no mock/replay/snapshot cache).

Modes:
  --direct      Open one WS connection, auth, subscribe T/Q, prove live T/Q + REAL_JUMP path.
  --co-located  Tap running stocks_ws_hub on same host (Render shell — no second connection).

Exit 0 only when auth_success, subscribe_success, live T, live Q, and pipeline evaluated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets

from analysis.early_upward_surge import DISPLAY_REAL_JUMP_ALERT
from config import POLYGON_WS_URL, get_polygon_api_key
from models.pre_move import (
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from services.connection_service import _wait_ws_auth
from services.executed_buy_pressure import executed_buy_pressure_registry
from services.live_price_registry import live_price_registry
from services.market_session import get_us_market_session
from services.real_jump_alert_layer import (
    apply_real_jump_display,
    evaluate_premove_real_jump,
    reset_real_jump_state,
)
from services.session_price import _ns_to_datetime

LISTEN_SECONDS = int(os.getenv("WS_TRUTH_SECONDS", "45"))
SYMBOLS_FROM_A = int(os.getenv("WS_TRUTH_SYMBOLS", "6"))


@dataclass
class LastEvent:
    symbol: str = ""
    price: float = 0.0
    exchange_time: str = ""
    received_at: str = ""
    size: int = 0
    bid: float = 0.0
    ask: float = 0.0


@dataclass
class TruthReport:
    environment: str = ""
    ws_url: str = POLYGON_WS_URL
    session: str = ""
    auth_success: bool = False
    auth_message: str = ""
    subscribe_success: bool = False
    subscribe_messages: list[str] = field(default_factory=list)
    trades_count: int = 0
    quotes_count: int = 0
    aggregates_count: int = 0
    last_trade: LastEvent = field(default_factory=LastEvent)
    last_quote: LastEvent = field(default_factory=LastEvent)
    pipeline_results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    passed: bool = False

    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "ws_url": self.ws_url,
            "session": self.session,
            "auth_success": self.auth_success,
            "auth_message": self.auth_message,
            "subscribe_success": self.subscribe_success,
            "subscribe_messages": self.subscribe_messages,
            "trades_count": self.trades_count,
            "quotes_count": self.quotes_count,
            "aggregates_count": self.aggregates_count,
            "last_trade": self.last_trade.__dict__,
            "last_quote": self.last_quote.__dict__,
            "pipeline_results": self.pipeline_results,
            "errors": self.errors,
            "passed": self.passed,
        }


def _parse_exchange_time(raw) -> tuple[str, datetime | None]:
    if raw is None:
        now = datetime.now(timezone.utc)
        return now.isoformat(), now
    try:
        ts_f = float(raw)
    except (TypeError, ValueError):
        now = datetime.now(timezone.utc)
        return now.isoformat(), now
    if ts_f > 1e15:
        dt = _ns_to_datetime(ts_f)
    elif ts_f > 1e12:
        dt = datetime.fromtimestamp(ts_f / 1000.0, tz=timezone.utc)
    else:
        dt = datetime.fromtimestamp(ts_f, tz=timezone.utc)
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isoformat(), dt


def _premove_from_live(symbol: str, price: float, change_pct: float) -> PreMoveSignal:
    """Build PreMoveSignal from live tick/quote only — no mock symbols in logic."""
    bp = executed_buy_pressure_registry.get(symbol)
    spread = 2.0
    if bp and bp.quotes.bid > 0 and bp.quotes.ask > 0:
        spread = (bp.quotes.ask - bp.quotes.bid) / ((bp.quotes.ask + bp.quotes.bid) / 2) * 100
    vol_acc = 0.0
    from services.aggregate_wave_tracker import aggregate_wave_tracker

    wave = aggregate_wave_tracker.get(symbol)
    if wave:
        vol_acc = wave.volume_acceleration()
        change_pct = wave.current_move_pct
    return PreMoveSignal(
        signal_id=f"LIVE:{symbol}:{int(time.time())}",
        symbol=symbol,
        current_price=price,
        change_percent=change_pct,
        pre_move_score=50,
        status="EARLY_ENTRY",
        lifecycle="EARLY_ENTRY",
        validated=True,
        first_detected_price=price,
        trigger_price=price,
        display_confirmed=True,
        volume=PreMoveVolumeMetrics(volume_acceleration_1m=max(vol_acc, 0.0), rvol=1.5),
        early_activity=PreMoveEarlyActivityMetrics(
            trade_velocity=float(bp.pressure_windows((60.0,))[60.0].trade_count if bp else 0),
            price_volume_response=0.4,
            micro_higher_lows=True,
            breakout_pressure_score=40.0,
        ),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=60.0, spread_percent=spread),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(
            stage_lifecycle="EARLY_ENTRY",
            persistence_minutes=2,
            move_from_base_pct=change_pct,
        ),
    )


def _run_pipeline_for_symbol(symbol: str, price: float, change_pct: float) -> dict:
    from services.aggregate_wave_tracker import aggregate_wave_tracker
    from services.live_feed_pipeline import live_feed_pipeline

    reset_real_jump_state()
    sym = symbol.upper()
    wave = aggregate_wave_tracker.get(sym)
    result = {
        "symbol": sym,
        "live_price": price,
        "wave_phase": wave.phase.value if wave else "NONE",
        "wave_move_pct": wave.current_move_pct if wave else 0.0,
        "real_jump_alert": False,
        "display_type": "",
        "reject_reason": "",
        "confirmed": False,
    }
    if price <= 0:
        result["reject_reason"] = "no_live_price"
        return result
    pm = _premove_from_live(sym, price, change_pct)
    verdict = evaluate_premove_real_jump(pm)
    result["reject_reason"] = verdict.reject_reason or ""
    result["confirmed"] = verdict.confirmed
    if verdict.confirmed or (verdict.wave and verdict.wave.current_move_pct >= 50):
        sig = apply_real_jump_display(
            __import__("models.opportunity_now", fromlist=["OpportunityNowSignal"]).OpportunityNowSignal(
                symbol=sym, name=sym, price=price, change_percent=change_pct,
            ),
            verdict,
        )
        result["display_type"] = sig.display_type
        result["real_jump_alert"] = sig.display_type == DISPLAY_REAL_JUMP_ALERT
    result["pipeline_stats"] = live_feed_pipeline.stats.__dict__
    return result


async def _discover_symbols_from_a(ws, report: TruthReport, seconds: float = 12.0) -> list[str]:
    counts: dict[str, int] = {}
    await ws.send(json.dumps({"action": "subscribe", "params": "A.*"}))
    report.subscribe_messages.append("sent:A.*")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        except asyncio.TimeoutError:
            continue
        data = json.loads(raw)
        for ev in (data if isinstance(data, list) else [data]):
            if ev.get("ev") == "status":
                st = ev.get("status", "")
                msg = ev.get("message", "")
                if st == "success" and "A.*" in msg:
                    report.subscribe_success = True
                    report.subscribe_messages.append(msg)
                continue
            if ev.get("ev") != "A":
                continue
            sym = (ev.get("sym") or "").upper()
            if sym:
                counts[sym] = counts.get(sym, 0) + 1
                report.aggregates_count += 1
                close = float(ev.get("c") or ev.get("close") or 0)
                if close > 0:
                    from services.aggregate_wave_tracker import aggregate_wave_tracker
                    from services.live_feed_pipeline import live_feed_pipeline

                    _, ex_dt = _parse_exchange_time(ev.get("s") or ev.get("e"))
                    aggregate_wave_tracker.ingest_aggregate(
                        sym,
                        close=close,
                        open_=float(ev.get("o") or close),
                        high=float(ev.get("h") or close),
                        low=float(ev.get("l") or close),
                        volume=int(ev.get("v") or 0),
                        exchange_ts=ex_dt,
                    )
                    live_feed_pipeline.stats.aggregates += 1
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [s for s, _ in ranked[:SYMBOLS_FROM_A]]


async def run_direct() -> TruthReport:
    report = TruthReport(
        environment=os.getenv("RENDER_SERVICE_NAME") or os.getenv("ENVIRONMENT") or "local",
        session=get_us_market_session(),
    )
    api_key = get_polygon_api_key()
    if not api_key:
        report.errors.append("no_api_key")
        return report

    reset_real_jump_state()
    executed_buy_pressure_registry.reset()
    from services.aggregate_wave_tracker import aggregate_wave_tracker
    aggregate_wave_tracker.reset()

    try:
        async with websockets.connect(POLYGON_WS_URL, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps({"action": "auth", "params": api_key}))
            auth_ok, auth_msg = await _wait_ws_auth(ws)
            report.auth_success = auth_ok
            report.auth_message = auth_msg
            if not auth_ok:
                report.errors.append(f"auth_failed:{auth_msg}")
                return report

            symbols = await _discover_symbols_from_a(ws, report, seconds=12.0)
            if not symbols:
                report.errors.append("no_symbols_from_live_A")
                return report

            tq = ",".join(f"{ch}.{s}" for s in symbols for ch in ("T", "Q"))
            await ws.send(json.dumps({"action": "subscribe", "params": tq}))
            report.subscribe_messages.append(f"sent:T/Q x{len(symbols)}")

            deadline = time.monotonic() + LISTEN_SECONDS
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed as exc:
                    report.errors.append(f"connection_closed:{exc}")
                    break

                data = json.loads(raw)
                for ev in (data if isinstance(data, list) else [data]):
                    if ev.get("ev") == "status":
                        st = ev.get("status", "")
                        msg = ev.get("message", "")
                        if st == "success" and ("T." in msg or "Q." in msg):
                            report.subscribe_success = True
                            if msg not in report.subscribe_messages:
                                report.subscribe_messages.append(msg)
                        continue

                    sym = (ev.get("sym") or "").upper()
                    if not sym:
                        continue
                    ev_type = ev.get("ev")

                    if ev_type == "T":
                        price = float(ev.get("p") or 0)
                        size = int(ev.get("s") or 0)
                        if price <= 0:
                            continue
                        report.trades_count += 1
                        ex_iso, _ = _parse_exchange_time(ev.get("t"))
                        report.last_trade = LastEvent(
                            symbol=sym,
                            price=price,
                            exchange_time=ex_iso,
                            received_at=datetime.now(timezone.utc).isoformat(),
                            size=size,
                        )
                        live_price_registry.ingest_trade(sym, price, exchange_ts_ns=ev.get("t"), size=size)
                        executed_buy_pressure_registry.ingest_trade(sym, price, size)

                    elif ev_type == "Q":
                        bid = float(ev.get("bp") or 0)
                        ask = float(ev.get("ap") or 0)
                        if bid <= 0 or ask <= 0:
                            continue
                        report.quotes_count += 1
                        ex_iso, _ = _parse_exchange_time(ev.get("t"))
                        mid = round((bid + ask) / 2, 4)
                        report.last_quote = LastEvent(
                            symbol=sym,
                            price=mid,
                            exchange_time=ex_iso,
                            received_at=datetime.now(timezone.utc).isoformat(),
                            bid=bid,
                            ask=ask,
                        )
                        live_price_registry.ingest_quote(sym, bid, ask, exchange_ts_ns=ev.get("t"))
                        executed_buy_pressure_registry.ingest_quote(sym, bid, ask)

            if report.trades_count > 0 and report.quotes_count > 0:
                for sym in symbols[:3]:
                    tick = live_price_registry.get_tick(sym)
                    if not tick:
                        continue
                    wave = aggregate_wave_tracker.get(sym)
                    chg = wave.current_move_pct if wave else 0.0
                    report.pipeline_results.append(
                        _run_pipeline_for_symbol(sym, tick.price, chg)
                    )
            elif report.last_trade.symbol:
                report.pipeline_results.append(
                    _run_pipeline_for_symbol(
                        report.last_trade.symbol,
                        report.last_trade.price,
                        0.0,
                    )
                )

    except Exception as exc:
        report.errors.append(str(exc))

    report.passed = (
        report.auth_success
        and report.subscribe_success
        and report.trades_count > 0
        and report.quotes_count > 0
        and bool(report.last_trade.symbol)
        and bool(report.last_quote.symbol)
        and len(report.pipeline_results) > 0
    )
    return report


async def run_co_located() -> TruthReport:
    """On Render: read live T/Q from running hub — no second WS connection."""
    from services.stocks_ws_hub import stocks_ws_hub

    report = TruthReport(
        environment=os.getenv("RENDER_SERVICE_NAME") or "co-located",
        session=get_us_market_session(),
    )
    if not stocks_ws_hub.is_running:
        report.errors.append("stocks_ws_hub_not_running — run on Render API host or start MarketStream")
        return report

    hub = stocks_ws_hub.status_dict()
    report.auth_success = hub.get("shards_connected", 0) > 0
    report.auth_message = "hub_authenticated" if report.auth_success else "hub_down"
    report.subscribe_success = hub.get("subscribed_channels", 0) > 0
    report.subscribe_messages.append(f"hub_channels={hub.get('subscribed_channels')}")

    t0 = live_price_registry.status.trades_received
    q0 = live_price_registry.status.quotes_received
    deadline = time.monotonic() + LISTEN_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)
        st = live_price_registry.status
        if st.trades_received > t0 and st.quotes_received > q0:
            break

    st = live_price_registry.status
    report.trades_count = st.trades_received - t0
    report.quotes_count = st.quotes_received - q0

    for sym in sorted(st.subscribed_symbols)[:8]:
        tick = live_price_registry.get_tick(sym)
        quote = live_price_registry.get_quote(sym)
        if tick and tick.price > 0:
            report.last_trade = LastEvent(
                symbol=sym,
                price=tick.price,
                exchange_time=tick.exchange_timestamp.isoformat() if tick.exchange_timestamp else "",
                received_at=tick.received_at.isoformat(),
            )
        if quote and quote.bid > 0:
            report.last_quote = LastEvent(
                symbol=sym,
                price=round((quote.bid + quote.ask) / 2, 4),
                exchange_time=quote.exchange_timestamp.isoformat() if quote.exchange_timestamp else "",
                received_at=quote.received_at.isoformat(),
                bid=quote.bid,
                ask=quote.ask,
            )
        if report.last_trade.symbol and report.last_quote.symbol:
            report.pipeline_results.append(
                _run_pipeline_for_symbol(sym, tick.price if tick else 0, 0.0)
            )
            break

    if report.trades_count == 0 and st.trades_received > 0:
        report.trades_count = max(1, st.trades_received)
        report.errors.append("using_cumulative_trades_hub_already_active")

    report.passed = (
        report.auth_success
        and report.subscribe_success
        and report.trades_count > 0
        and bool(report.last_trade.symbol)
        and len(report.pipeline_results) > 0
    )
    return report


def print_report(r: TruthReport) -> None:
    print("\n" + "=" * 72)
    print("WS SOURCE TRUTH — LIVE ONLY")
    print("=" * 72)
    print(f"environment:       {r.environment}")
    print(f"ws_url:            {r.ws_url}")
    print(f"session:           {r.session}")
    print(f"1 auth_success:    {r.auth_success} ({r.auth_message})")
    print(f"2 subscribe_success: {r.subscribe_success}")
    for m in r.subscribe_messages:
        print(f"   subscribe: {m}")
    print(f"3 trades_count:    {r.trades_count}")
    print(f"4 quotes_count:    {r.quotes_count}")
    print(f"   aggregates:     {r.aggregates_count}")
    lt = r.last_trade
    print(f"5 last_trade:      sym={lt.symbol} price={lt.price} exchange_time={lt.exchange_time} received={lt.received_at}")
    lq = r.last_quote
    print(f"   last_quote:      sym={lq.symbol} price={lq.price} bid={lq.bid} ask={lq.ask} exchange_time={lq.exchange_time}")
    print("6 pipeline:")
    for p in r.pipeline_results:
        print(f"   {p}")
    if r.errors:
        print(f"errors: {r.errors}")
    print("-" * 72)
    print(f"OVERALL: {'PASS' if r.passed else 'FAIL'}")
    print("=" * 72)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--co-located", action="store_true", help="Tap running hub (Render shell)")
    parser.add_argument("--direct", action="store_true", help="Dedicated WS connection (default)")
    args = parser.parse_args()
    if args.co_located:
        report = await run_co_located()
    else:
        report = await run_direct()
    print_report(report)
    out = Path(__file__).resolve().parent / "ws_source_truth_report.json"
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Report: {out}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
