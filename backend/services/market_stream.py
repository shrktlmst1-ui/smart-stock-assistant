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
    SCANNER_TOP_N,
    WEBSOCKET_ENABLED,
    get_polygon_api_key,
)
from services.connection_service import get_connection_status, _wait_ws_auth
from services.market_scanner_service import market_scanner
from services.polygon_client import PolygonClient

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]


class MarketStream:
    def __init__(self) -> None:
        self.client = PolygonClient()
        self._running = False
        self._task: asyncio.Task | None = None
        self._tick_task: asyncio.Task | None = None
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

        if use_ws:
            self.mode = "websocket_scanner"
            self._task = asyncio.create_task(self._run_websocket_with_fallback())
        else:
            self.mode = "scanner_rest"

        logger.info(
            "Institutional scanner stream: mode=%s tick=%ss top=%d",
            self.mode, SCANNER_TICK_SECONDS, SCANNER_TOP_N,
        )

    async def stop(self) -> None:
        self._running = False
        for task in (self._task, self._tick_task):
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

    async def _run_fast_tick(self) -> None:
        """Institutional scanner — full market coarse + deep top 20 every 15s."""
        await self._broadcast_status()
        while self._running:
            t0 = time.monotonic()
            try:
                state = await market_scanner.run_fast_tick()
                self.last_tick_ms = state.last_tick_ms

                self._snapshots.clear()
                for snap in state.snapshots:
                    await self._emit_snapshot(snap)

                await self._emit_scan_update(state)

                if self.last_tick_ms > 30000:
                    logger.warning("Scanner tick slow: %.0fms (pool=%d)", self.last_tick_ms, state.candidate_pool)
            except Exception as e:
                logger.error("Scanner tick error: %s", e)
            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, SCANNER_TICK_SECONDS - elapsed))

    async def _run_websocket_with_fallback(self) -> None:
        ws_failures = 0
        while self._running:
            try:
                await self._run_websocket()
            except Exception as e:
                ws_failures += 1
                logger.error("WebSocket failed (%d): %s", ws_failures, e)
                if ws_failures >= 3:
                    self.mode = "scanner_rest"
                    return
                await asyncio.sleep(3)

    async def _run_websocket(self) -> None:
        self.mode = "websocket_scanner"
        state = market_scanner.get_state()
        symbols = [s.symbol for s in (state.snapshots if state else [])][:SCANNER_TOP_N]
        api_key = get_polygon_api_key()
        if not api_key:
            raise ConnectionError("POLYGON_API_KEY not configured — set env var on Render")

        async with websockets.connect(POLYGON_WS_URL, ping_interval=20) as ws:
            await ws.send(json.dumps({"action": "auth", "params": api_key}))
            auth_ok, auth_msg = await _wait_ws_auth(ws)
            if not auth_ok:
                raise ConnectionError(f"WebSocket auth failed: {auth_msg}")

            if symbols:
                channels = []
                for s in symbols:
                    channels.extend([f"T.{s}", f"AM.{s}"])
                await ws.send(json.dumps({"action": "subscribe", "params": ",".join(channels)}))

            async for message in ws:
                if not self._running:
                    break
                await asyncio.sleep(0)
