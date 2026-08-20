"""Massive/Polygon websocket stream for Market Pulse — per-symbol only."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

import websockets

from config import (
    MARKET_PULSE_WS_BACKOFF_BASE,
    MARKET_PULSE_WS_BACKOFF_MAX,
    MASSIVE_WS_URL,
    get_polygon_api_key,
)
from market_pulse.providers.base import AggregateMinute, LuldEvent, QuoteTick, TradeTick
from market_pulse.subscription_manager import SubscriptionManager

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], Awaitable[None] | None]


class MassiveMarketStreamProvider:
    """WebSocket client with reconnect, backoff, and safe shutdown."""

    def __init__(
        self,
        api_key: str | None = None,
        ws_url: str = MASSIVE_WS_URL,
        subscription_manager: SubscriptionManager | None = None,
    ):
        self._api_key = (api_key or get_polygon_api_key()).strip()
        self._ws_url = ws_url
        self._subs = subscription_manager or SubscriptionManager()
        self._running = False
        self._task: asyncio.Task | None = None
        self._ws = None
        self.connected = False
        self._handlers: dict[str, list[MessageHandler]] = {
            "A": [],
            "AM": [],
            "T": [],
            "Q": [],
            "LULD": [],
        }
        self._backoff = MARKET_PULSE_WS_BACKOFF_BASE

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    @property
    def subscription_manager(self) -> SubscriptionManager:
        return self._subs

    def on(self, feed: str, handler: MessageHandler) -> None:
        key = feed.upper()
        if key in self._handlers:
            self._handlers[key].append(handler)

    async def start(self) -> None:
        if self._running or not self._api_key:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.connected = False

    async def _authenticate(self, ws) -> bool:
        auth_msg = {"action": "auth", "params": self._api_key}
        await ws.send(json.dumps(auth_msg))
        raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        data = json.loads(raw)
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            if row.get("status") == "auth_success":
                return True
            if row.get("status") == "auth_failed":
                logger.warning("Market pulse WS auth failed")
                return False
        return False

    async def _subscribe(self, ws) -> None:
        channels = self._subs.build_ws_subscriptions()
        if not channels:
            return
        if self._subs.contains_wildcard(channels):
            raise ValueError("Wildcard market subscriptions are not allowed")
        msg = {"action": "subscribe", "params": ",".join(channels)}
        await ws.send(json.dumps(msg))

    async def _run_loop(self) -> None:
        while self._running:
            try:
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    if not await self._authenticate(ws):
                        self.connected = False
                        await asyncio.sleep(self._backoff)
                        self._backoff = min(self._backoff * 2, MARKET_PULSE_WS_BACKOFF_MAX)
                        continue
                    await self._subscribe(ws)
                    self.connected = True
                    self._backoff = MARKET_PULSE_WS_BACKOFF_BASE
                    async for raw in ws:
                        if not self._running:
                            break
                        await self._handle_raw(raw)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Market pulse WS error: %s", type(exc).__name__)
                self.connected = False
                if self._running:
                    await asyncio.sleep(self._backoff)
                    self._backoff = min(self._backoff * 2, MARKET_PULSE_WS_BACKOFF_MAX)
            finally:
                self._ws = None
                self.connected = False

    async def _handle_raw(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        rows = payload if isinstance(payload, list) else [payload]
        for row in rows:
            if not isinstance(row, dict):
                continue
            ev = row.get("ev") or row.get("event")
            if not ev:
                continue
            parsed = self._parse_event(ev, row)
            if parsed is None:
                continue
            feed_key = ev.split(".")[0] if "." in ev else ev
            for handler in self._handlers.get(feed_key, []):
                result = handler(parsed)
                if asyncio.iscoroutine(result):
                    await result

    def _parse_event(self, ev: str, row: dict):
        sym = row.get("sym") or row.get("symbol") or ""
        if not sym:
            return None
        base = ev.split(".")[0]
        if base == "T":
            return TradeTick(
                symbol=sym.upper(),
                price=float(row.get("p", 0)),
                size=int(row.get("s", 0)),
                timestamp_ms=int(row.get("t", 0)),
                conditions=row.get("c") or [],
            )
        if base == "Q":
            return QuoteTick(
                symbol=sym.upper(),
                bid=float(row.get("bp", row.get("bid", 0))),
                ask=float(row.get("ap", row.get("ask", 0))),
                bid_size=int(row.get("bs", row.get("bsize", 0))),
                ask_size=int(row.get("as", row.get("asize", 0))),
                timestamp_ms=int(row.get("t", 0)),
            )
        if base == "AM" or base == "A":
            return AggregateMinute(
                symbol=sym.upper(),
                open=float(row.get("o", 0)),
                high=float(row.get("h", 0)),
                low=float(row.get("l", 0)),
                close=float(row.get("c", 0)),
                volume=int(row.get("v", 0)),
                vwap=float(row.get("vw", row.get("c", 0))),
                timestamp_ms=int(row.get("s", row.get("t", 0))),
            )
        if base == "LULD":
            halt = str(row.get("halt", row.get("status", ""))).lower() in ("halted", "halt", "luld")
            return LuldEvent(
                symbol=sym.upper(),
                halt=halt,
                reason=str(row.get("reason", "")),
                timestamp_ms=int(row.get("t", 0)),
            )
        return None

    async def push_message(self, raw: str) -> None:
        """Test hook — inject WS payload without live connection."""
        await self._handle_raw(raw)
