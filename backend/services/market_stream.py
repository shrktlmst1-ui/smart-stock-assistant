"""Real-time market stream — US scanner with 1s fast tick."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

import websockets

from config import (
    POLYGON_WS_URL,
    SCANNER_TICK_SECONDS,
    WEBSOCKET_ENABLED,
    get_polygon_api_key,
)
from services.connection_service import get_connection_status, _wait_ws_auth
from services.jump_engine_monitor import jump_engine_monitor
from services.live_confirmation_engine import LIVE_MONITOR_POOL, live_confirmation_engine
from services.live_price_registry import live_price_registry
from services.market_scanner_service import market_scanner
from services.opportunity_now_service import sync_engine_from_scanner
from services.polygon_client import PolygonClient

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]


class MarketStream:
    def __init__(self) -> None:
        self.client = PolygonClient()
        self._running = False
        self._task: asyncio.Task | None = None
        self._tick_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._broadcast: BroadcastFn | None = None
        self._snapshots: dict[str, dict] = {}
        self.mode: str = "scanner"
        self.last_tick_ms: float = 0.0

    def set_broadcast(self, fn: BroadcastFn) -> None:
        self._broadcast = fn

    def get_snapshots(self) -> list[dict]:
        return list(self._snapshots.values())

    def get_scan_state(self) -> dict | None:
        state = market_scanner.get_state()
        return state.model_dump() if state else None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        status = get_connection_status()
        use_ws = WEBSOCKET_ENABLED and status.websocket_available

        self._tick_task = asyncio.create_task(self._run_fast_tick())
        self._watchdog_task = asyncio.create_task(self._run_watchdog())

        if use_ws:
            self.mode = "websocket_scanner"
            self._task = asyncio.create_task(self._run_websocket_with_fallback())
        else:
            self.mode = "scanner_rest"

        logger.info(
            "Institutional scanner stream: mode=%s tick=%ss monitor=%d",
            self.mode, SCANNER_TICK_SECONDS, LIVE_MONITOR_POOL,
        )

    async def stop(self) -> None:
        self._running = False
        jump_engine_monitor.mark_stopped()
        for task in (self._task, self._tick_task, self._watchdog_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        await self.client.close()
        await market_scanner.client.close()

    async def _broadcast_status(self, extra: dict | None = None) -> None:
        if not self._broadcast:
            return
        status = get_connection_status()
        data = {
            **status.to_dict(),
            "stream_mode": self.mode,
            "last_tick_ms": round(self.last_tick_ms, 1),
            "scanner": True,
        }
        if extra:
            data.update(extra)
        await self._broadcast({
            "type": "status",
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _emit_scan_update(self, state) -> None:
        if not self._broadcast:
            return
        await self._broadcast({
            "type": "scan_update",
            "data": state.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _emit_snapshot(self, snapshot) -> None:
        data = snapshot.model_dump()
        self._snapshots[snapshot.symbol] = data
        if self._broadcast:
            await self._broadcast({
                "type": "snapshot",
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def _run_watchdog(self) -> None:
        """Self-healing — restart scanner/WS tasks if they exit unexpectedly."""
        while self._running:
            await asyncio.sleep(30)
            if not self._running:
                break
            if self._tick_task and self._tick_task.done():
                exc = self._tick_task.exception()
                err = f"tick_task_died:{exc!r}" if exc else "tick_task_died"
                jump_engine_monitor.record_error(err)
                logger.error("[JUMP] Scanner tick task died (%s) — auto-restarting", exc)
                self._tick_task = asyncio.create_task(self._run_fast_tick())
            status = get_connection_status()
            if WEBSOCKET_ENABLED and status.websocket_available:
                if self._task is None or self._task.done():
                    exc = self._task.exception() if self._task else None
                    err = f"ws_task_died:{exc!r}" if exc else "ws_task_missing"
                    jump_engine_monitor.record_error(err)
                    logger.error("[JUMP] WebSocket task died (%s) — auto-restarting", exc)
                    self.mode = "websocket_scanner"
                    self._task = asyncio.create_task(self._run_websocket_with_fallback())

    async def _run_fast_tick(self) -> None:
        """Institutional scanner — full market coarse + deep top 20 every 15s."""
        await self._broadcast_status()
        while self._running:
            t0 = time.monotonic()
            try:
                from services.snapshot_cache_service import cache_stats

                cs = cache_stats()
                jump_engine_monitor.tick_started(
                    scanner_task_alive=True,
                    websocket_connected=live_price_registry.status.connected,
                    last_ws_message_time=live_price_registry.last_message_iso(),
                    reconnect_count=live_price_registry.status.reconnect_count,
                    refresh_in_progress=cs.get("refresh_in_progress", False),
                    refresh_skipped=cs.get("refresh_skipped", 0),
                )

                state = await market_scanner.run_fast_tick()
                self.last_tick_ms = state.last_tick_ms

                self._snapshots.clear()
                for snap in state.snapshots:
                    await self._emit_snapshot(snap)

                await self._emit_scan_update(state)
                try:
                    sync_engine_from_scanner()
                except Exception as exc:
                    logger.debug("Live/extended engine sync skipped: %s", type(exc).__name__)

                try:
                    from services.snapshot_cache_service import schedule_opportunities_refresh

                    schedule_opportunities_refresh(
                        session=state.market_status,
                        state=state,
                        snapshot_raw=market_scanner._snapshot_raw,
                    )
                except Exception as exc:
                    logger.debug("Opportunities snapshot refresh skipped: %s", type(exc).__name__)

                debug = state.debug
                jump_engine_monitor.tick_finished(
                    scanned_count=debug.phase1_quick_scanned if debug else 0,
                    candidate_count=debug.phase2_ranked_candidates if debug else 0,
                )

                if self.last_tick_ms > 30000:
                    logger.warning("Scanner tick slow: %.0fms (pool=%d)", self.last_tick_ms, state.candidate_pool)
            except Exception as e:
                jump_engine_monitor.record_error(f"tick_error:{e}")
                logger.error("Scanner tick error: %s", e)
            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, SCANNER_TICK_SECONDS - elapsed))

    def _monitor_symbols(self) -> list[str]:
        pool = market_scanner._rank_pool[:LIVE_MONITOR_POOL]
        if pool:
            return pool
        state = market_scanner.get_state()
        if state:
            return [s.symbol for s in state.snapshots[:LIVE_MONITOR_POOL]]
        return []

    async def _run_websocket_with_fallback(self) -> None:
        backoff = 2.0
        max_backoff = 60.0
        while self._running:
            try:
                live_price_registry.note_reconnect()
                jump_engine_monitor.record_reconnect()
                await self._run_websocket()
                backoff = 2.0
            except websockets.exceptions.ConnectionClosedError as e:
                code = getattr(e, "code", None)
                live_price_registry.set_error(str(code or e))
                live_price_registry.set_connected(False)
                live_confirmation_engine.set_ws_status(
                    connected=False, fallback=True, error=str(code or e),
                )
                self.mode = "scanner_rest"
                logger.warning("[LIVE_PRICE] websocket closed code=%s — retry in %.0fs", code, backoff)
            except Exception as e:
                live_price_registry.set_error(str(e))
                live_price_registry.set_connected(False)
                live_confirmation_engine.set_ws_status(connected=False, fallback=True, error=str(e))
                self.mode = "scanner_rest"
                logger.warning("[LIVE_PRICE] websocket error %s — retry in %.0fs", type(e).__name__, backoff)
            if not self._running:
                break
            await asyncio.sleep(backoff)
            backoff = min(max_backoff, backoff * 1.5)

    async def _handle_ws_payload(self, payload: list | dict) -> None:
        live_price_registry.note_message_received()
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            ev = item.get("ev") or item.get("event")
            sym = (item.get("sym") or item.get("symbol") or "").upper()
            if not sym:
                continue
            if ev == "T":
                price = float(item.get("p") or item.get("price") or 0)
                size = int(item.get("s") or item.get("size") or 0)
                if price > 0:
                    live_price_registry.ingest_trade(
                        sym, price, exchange_ts_ns=item.get("t"), size=size,
                    )
                    live_confirmation_engine.ingest_ws_trade(sym, price, size)
            elif ev == "Q":
                bid = float(item.get("bp") or item.get("p") or 0)
                ask = float(item.get("ap") or item.get("P") or 0)
                if bid > 0 and ask > 0:
                    live_price_registry.ingest_quote(
                        sym, bid, ask, exchange_ts_ns=item.get("t"),
                    )
            elif ev in ("AM", "A"):
                price = float(item.get("c") or item.get("close") or item.get("p") or 0)
                vol = int(item.get("v") or item.get("volume") or 0)
                if price > 0:
                    live_confirmation_engine.ingest_ws_trade(sym, price, vol)

    async def _run_websocket(self) -> None:
        self.mode = "websocket_scanner"
        symbols = self._monitor_symbols()
        live_confirmation_engine.set_monitor_symbols(symbols)
        api_key = get_polygon_api_key()
        if not api_key:
            raise ConnectionError("POLYGON_API_KEY not configured — set env var on Render")

        async with websockets.connect(POLYGON_WS_URL, ping_interval=20) as ws:
            await ws.send(json.dumps({"action": "auth", "params": api_key}))
            auth_ok, auth_msg = await _wait_ws_auth(ws)
            if not auth_ok:
                live_price_registry.set_connected(False)
                raise ConnectionError(f"WebSocket auth failed: {auth_msg}")

            live_price_registry.set_connected(True, authenticated=True)
            live_confirmation_engine.set_ws_status(connected=True, fallback=False)

            if symbols:
                channels: list[str] = []
                for s in symbols:
                    channels.extend([f"T.{s}", f"Q.{s}"])
                await ws.send(json.dumps({"action": "subscribe", "params": ",".join(channels)}))
                live_price_registry.set_subscribed(symbols)
                logger.info("WS subscribed T+Q for %d symbols (max %d)", len(symbols), LIVE_MONITOR_POOL)

            async for message in ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, list) and data and data[0].get("ev") == "status":
                    status_msg = data[0].get("message", "")
                    if "1008" in status_msg or "policy" in status_msg.lower():
                        live_price_registry.set_connected(False)
                        live_price_registry.set_error(status_msg)
                        live_confirmation_engine.set_ws_status(
                            connected=False, fallback=True, error=status_msg,
                        )
                        raise ConnectionError(f"WebSocket policy violation: {status_msg}")
                    continue
                await self._handle_ws_payload(data)
