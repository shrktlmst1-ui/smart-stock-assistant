"""Shared Polygon/Massive stocks WebSocket hub — one cluster, batched subscriptions.

Polygon allows only ONE simultaneous connection per stocks cluster on Developer plans.
Multiple raw connections cause policy violation (1008). This hub multiplexes all
consumers (Jump Engine, Market Pulse) on a single connection with safe batched
subscribe/unsubscribe. When WS_MAX_CONNECTIONS > 1 (Business tier), symbols are
sharded across connections without reducing market coverage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import websockets

from config import (
    POLYGON_WS_URL,
    WS_CHANNELS_PER_SUBSCRIBE_BATCH,
    WS_MAX_CONNECTIONS,
    WS_RESYNC_SECONDS,
    WS_RECV_TIMEOUT_SECONDS,
    WS_SUBSCRIBE_BATCH_DELAY_SEC,
    WS_SYMBOLS_PER_SHARD,
    get_polygon_api_key,
)
from services.connection_service import _wait_ws_auth
from services.live_price_registry import live_price_registry

logger = logging.getLogger(__name__)

RawHandler = Callable[[list | dict], Awaitable[None] | None]


@dataclass
class ConsumerSpec:
    symbols: set[str] = field(default_factory=set)
    channel_types: tuple[str, ...] = ("T", "Q")
    wildcards: tuple[str, ...] = ()


@dataclass
class ShardState:
    shard_id: int
    symbols: list[str]
    subscribed_channels: set[str] = field(default_factory=set)
    connected: bool = False
    authenticated: bool = False
    last_error: str = ""
    reconnect_count: int = 0
    auth_fail_streak: int = 0
    had_successful_session: bool = False


def _channels_for_symbols(symbols: set[str], channel_types: tuple[str, ...]) -> set[str]:
    out: set[str] = set()
    for sym in symbols:
        s = sym.upper()
        if not s:
            continue
        for ch in channel_types:
            out.add(f"{ch.upper()}.{s}")
    return out


def _partition_symbols(symbols: list[str], max_shards: int, per_shard: int) -> list[list[str]]:
    if not symbols:
        return []
    if max_shards <= 1:
        return [symbols]
    n = min(max_shards, max(1, (len(symbols) + per_shard - 1) // per_shard))
    shards: list[list[str]] = [[] for _ in range(n)]
    for i, sym in enumerate(symbols):
        shards[i % n].append(sym)
    return [s for s in shards if s]


class StocksWsHub:
    """Central stocks WS — batched subscribe, multi-consumer, shard-ready."""

    def __init__(self) -> None:
        self._running = False
        self._consumers: dict[str, ConsumerSpec] = {}
        self._raw_handlers: list[RawHandler] = []
        self._shard_tasks: list[asyncio.Task] = []
        self._sync_task: asyncio.Task | None = None
        self._desired_symbols: list[str] = []
        self._shards: list[ShardState] = []
        self._lock = asyncio.Lock()
        self._subscribe_batch_size = WS_CHANNELS_PER_SUBSCRIBE_BATCH
        self._needs_sync = False

    @property
    def is_running(self) -> bool:
        return self._running

    def add_raw_handler(self, handler: RawHandler) -> None:
        if handler not in self._raw_handlers:
            self._raw_handlers.append(handler)

    def remove_raw_handler(self, handler: RawHandler) -> None:
        if handler in self._raw_handlers:
            self._raw_handlers.remove(handler)

    def set_consumer(
        self,
        consumer_id: str,
        symbols: list[str],
        channel_types: tuple[str, ...] = ("T", "Q"),
        wildcards: tuple[str, ...] = (),
    ) -> None:
        sym_set = {s.upper() for s in symbols if s}
        prev = self._consumers.get(consumer_id)
        if (
            prev
            and prev.symbols == sym_set
            and prev.channel_types == channel_types
            and prev.wildcards == wildcards
        ):
            return
        self._consumers[consumer_id] = ConsumerSpec(
            symbols=sym_set, channel_types=channel_types, wildcards=wildcards,
        )
        self._recompute_symbol_universe()
        self._needs_sync = True
        self._schedule_consumer_sync()

    def clear_consumer(self, consumer_id: str) -> None:
        if consumer_id in self._consumers:
            del self._consumers[consumer_id]
            self._recompute_symbol_universe()
            self._needs_sync = True
            self._schedule_consumer_sync()

    def _schedule_consumer_sync(self) -> None:
        if not self._running:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._on_consumer_changed())

    async def apply_pending_sync(self) -> None:
        if not self._needs_sync:
            return
        self._needs_sync = False
        await self._on_consumer_changed()

    async def _on_consumer_changed(self) -> None:
        self._repartition_if_needed()
        await self._sync_all_shards()

    def _recompute_symbol_universe(self) -> None:
        merged: list[str] = []
        seen: set[str] = set()
        for spec in self._consumers.values():
            for sym in spec.symbols:
                if sym not in seen:
                    seen.add(sym)
                    merged.append(sym)
        self._desired_symbols = merged

    def _desired_channels(self) -> set[str]:
        channels: set[str] = set()
        for spec in self._consumers.values():
            channels |= _channels_for_symbols(spec.symbols, spec.channel_types)
            for wc in spec.wildcards:
                channels.add(wc)
        return channels

    def get_consumer_symbols(self, consumer_id: str) -> list[str]:
        spec = self._consumers.get(consumer_id)
        return sorted(spec.symbols) if spec else []

    def status_dict(self) -> dict:
        connected = sum(1 for s in self._shards if s.connected)
        return {
            "running": self._running,
            "shards_total": len(self._shards),
            "shards_connected": connected,
            "symbols_target": len(self._desired_symbols),
            "consumers": list(self._consumers.keys()),
            "subscribed_channels": sum(len(s.subscribed_channels) for s in self._shards),
            "reconnect_total": sum(s.reconnect_count for s in self._shards),
        }

    @property
    def shards_connected(self) -> int:
        return sum(1 for s in self._shards if s.connected and s.authenticated)

    async def recover_shards(self) -> None:
        """Watchdog nudge — resync subscriptions without tearing down hub state."""
        if not self._running:
            return
        await self.apply_pending_sync()
        await self._sync_all_shards()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._recompute_symbol_universe()
        self._spawn_shards()
        self._sync_task = asyncio.create_task(self._resync_loop())
        logger.info(
            "[STOCKS_WS] hub started shards=%d symbols=%d batch=%d",
            len(self._shards),
            len(self._desired_symbols),
            self._subscribe_batch_size,
        )

    async def stop(self) -> None:
        self._running = False
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        for task in self._shard_tasks:
            if not task.done():
                task.cancel()
        for task in self._shard_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._shard_tasks.clear()
        self._shards.clear()
        live_price_registry.set_hub_health(shards_connected=0, shards_total=0, subscribed=set())
        logger.info("[STOCKS_WS] hub stopped")

    def _spawn_shards(self) -> None:
        partitions = _partition_symbols(
            self._desired_symbols,
            WS_MAX_CONNECTIONS,
            WS_SYMBOLS_PER_SHARD,
        )
        if not partitions:
            partitions = [[]]
        self._shards = [
            ShardState(shard_id=i, symbols=part)
            for i, part in enumerate(partitions)
        ]
        self._shard_tasks = [
            asyncio.create_task(self._run_shard(shard))
            for shard in self._shards
        ]

    async def _resync_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(WS_RESYNC_SECONDS)
                await self.apply_pending_sync()
                await self._sync_all_shards()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("[STOCKS_WS] resync error: %s", type(exc).__name__)

    def _repartition_if_needed(self) -> None:
        partitions = _partition_symbols(
            self._desired_symbols,
            WS_MAX_CONNECTIONS,
            WS_SYMBOLS_PER_SHARD,
        )
        if not partitions:
            return
        current = [s.symbols for s in self._shards]
        if current == partitions:
            return
        logger.info(
            "[STOCKS_WS] repartition symbols %d -> %d shards",
            len(self._desired_symbols),
            len(partitions),
        )
        old_tasks = list(self._shard_tasks)
        for task in old_tasks:
            if not task.done():
                task.cancel()
        self._spawn_shards()
        # Best-effort await cancelled tasks so we don't stack duplicate sockets.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._await_cancelled(old_tasks))
        except RuntimeError:
            pass

    async def _await_cancelled(self, tasks: list[asyncio.Task]) -> None:
        for task in tasks:
            if task.done():
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def _sync_all_shards(self) -> None:
        for shard in self._shards:
            await self._sync_shard_subscriptions(shard)

    def _shard_desired_channels(self, shard: ShardState) -> set[str]:
        sym_set = set(shard.symbols)
        channels: set[str] = set()
        for spec in self._consumers.values():
            relevant = spec.symbols & sym_set
            if relevant:
                channels |= _channels_for_symbols(relevant, spec.channel_types)
            if shard.shard_id == 0 and spec.wildcards:
                channels |= set(spec.wildcards)
        return channels

    async def _send_batched(
        self,
        ws,
        action: str,
        channels: list[str],
        *,
        batch_size: int | None = None,
    ) -> None:
        size = batch_size or self._subscribe_batch_size
        for i in range(0, len(channels), size):
            batch = channels[i : i + size]
            if not batch:
                continue
            await ws.send(json.dumps({"action": action, "params": ",".join(batch)}))
            if i + size < len(channels):
                await asyncio.sleep(WS_SUBSCRIBE_BATCH_DELAY_SEC)

    async def _sync_shard_subscriptions(self, shard: ShardState) -> None:
        ws = getattr(shard, "_ws", None)
        if ws is None or not shard.connected:
            return
        desired = self._shard_desired_channels(shard)
        to_add = sorted(desired - shard.subscribed_channels)
        to_remove = sorted(shard.subscribed_channels - desired)
        try:
            if to_remove:
                await self._send_batched(ws, "unsubscribe", to_remove)
                shard.subscribed_channels -= set(to_remove)
                logger.info("[STOCKS_WS] shard=%d unsubscribed %d channels", shard.shard_id, len(to_remove))
            if to_add:
                await self._send_batched(ws, "subscribe", to_add)
                shard.subscribed_channels |= set(to_add)
                logger.info("[STOCKS_WS] shard=%d subscribed +%d (total %d)", shard.shard_id, len(to_add), len(shard.subscribed_channels))
            self._publish_registry_health()
        except Exception as exc:
            shard.last_error = str(exc)[:200]
            logger.warning("[STOCKS_WS] shard=%d sync failed: %s", shard.shard_id, type(exc).__name__)

    def _publish_registry_health(self) -> None:
        connected = sum(1 for s in self._shards if s.connected and s.authenticated)
        subscribed_syms: set[str] = set()
        for shard in self._shards:
            for ch in shard.subscribed_channels:
                if "." in ch:
                    subscribed_syms.add(ch.split(".", 1)[1])
        live_price_registry.set_hub_health(
            shards_connected=connected,
            shards_total=len(self._shards),
            subscribed=subscribed_syms,
        )
        from services.live_data_gate import live_data_gate

        has_a = any("A.*" in ch or ch.startswith("A.") for s in self._shards for ch in s.subscribed_channels)
        live_data_gate.set_ws_health(
            connected=connected > 0,
            authenticated=connected > 0,
            aggregates_subscribed=has_a,
        )
        if connected > 0:
            live_data_gate.metrics.reconnect_count = sum(s.reconnect_count for s in self._shards)

    def _backoff_for_error(self, err: str, current: float) -> float:
        err_l = err.lower()
        if "max_connections" in err_l:
            live_price_registry.set_error(f"ws:{err[:120]}")
            return max(current, 30.0)
        if "auth_failed" in err_l:
            live_price_registry.set_error(f"ws:{err[:120]}")
            return max(current, 60.0)
        if "policy" in err_l or "1008" in err_l:
            live_price_registry.set_error(f"ws:{err[:120]}")
            return max(current, 5.0)
        live_price_registry.set_error(f"ws:{err[:120]}")
        return current

    async def _run_shard(self, shard: ShardState) -> None:
        backoff = 2.0
        max_backoff = 60.0
        api_key = get_polygon_api_key()
        if not api_key:
            shard.last_error = "no_api_key"
            live_price_registry.set_error("no_api_key")
            return

        while self._running:
            ws = None
            try:
                if shard.had_successful_session:
                    shard.reconnect_count += 1
                    live_price_registry.note_reconnect()
                async with websockets.connect(POLYGON_WS_URL, ping_interval=20, ping_timeout=20) as ws:
                    shard._ws = ws  # type: ignore[attr-defined]
                    await ws.send(json.dumps({"action": "auth", "params": api_key}))
                    auth_ok, auth_msg = await _wait_ws_auth(ws)
                    if not auth_ok:
                        shard.auth_fail_streak += 1
                        raise ConnectionError(f"auth_failed:{auth_msg}")

                    shard.auth_fail_streak = 0
                    shard.connected = True
                    shard.authenticated = True
                    shard.last_error = ""
                    shard.had_successful_session = True
                    live_price_registry.set_error("")
                    self._publish_registry_health()
                    logger.info("[STOCKS_WS] shard=%d connected symbols=%d", shard.shard_id, len(shard.symbols))

                    desired = self._shard_desired_channels(shard)
                    if desired:
                        await self._send_batched(ws, "subscribe", sorted(desired))
                        shard.subscribed_channels = set(desired)
                        self._publish_registry_health()
                        logger.info(
                            "[STOCKS_WS] shard=%d initial subscribe channels=%d",
                            shard.shard_id,
                            len(desired),
                        )

                    backoff = 2.0
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT_SECONDS)
                        except asyncio.TimeoutError:
                            await self.apply_pending_sync()
                            await self._sync_shard_subscriptions(shard)
                            continue
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(data, list) and data and data[0].get("ev") == "status":
                            msg = str(data[0].get("message", ""))
                            st = data[0].get("status", "")
                            if st == "max_connections":
                                shard.last_error = msg
                                raise ConnectionError(f"max_connections:{msg}")
                            if "1008" in msg or "policy" in msg.lower():
                                shard.last_error = msg
                                self._subscribe_batch_size = max(10, self._subscribe_batch_size // 2)
                                logger.warning(
                                    "[STOCKS_WS] shard=%d policy — resubscribe smaller batches (%d)",
                                    shard.shard_id,
                                    self._subscribe_batch_size,
                                )
                                shard.subscribed_channels.clear()
                                desired_now = self._shard_desired_channels(shard)
                                if desired_now:
                                    await self._send_batched(
                                        ws, "subscribe", sorted(desired_now),
                                        batch_size=self._subscribe_batch_size,
                                    )
                                    shard.subscribed_channels = set(desired_now)
                                    self._publish_registry_health()
                                continue
                            continue
                        live_price_registry.note_message_received()
                        for handler in self._raw_handlers:
                            try:
                                result = handler(data)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception as exc:
                                logger.debug("[STOCKS_WS] handler error: %s", type(exc).__name__)

            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosedError as exc:
                code = getattr(exc, "code", None)
                shard.last_error = str(code or exc)
                live_price_registry.set_error(f"closed:{code or exc}")
                logger.warning("[STOCKS_WS] shard=%d closed code=%s", shard.shard_id, code)
            except Exception as exc:
                shard.last_error = str(exc)[:200]
                backoff = self._backoff_for_error(shard.last_error, backoff)
                if "auth_failed" in shard.last_error and shard.auth_fail_streak >= 5:
                    logger.error("[STOCKS_WS] shard=%d auth circuit-breaker — pausing 5min", shard.shard_id)
                    backoff = max(backoff, 300.0)
                logger.warning("[STOCKS_WS] shard=%d error %s", shard.shard_id, type(exc).__name__)
            finally:
                shard.connected = False
                shard.authenticated = False
                shard._ws = None  # type: ignore[attr-defined]
                # Keep subscribed_channels intent — resubscribe on reconnect, don't lose consumer state.
                self._publish_registry_health()

            if not self._running:
                break
            await asyncio.sleep(backoff)
            backoff = min(max_backoff, backoff * 1.5)


stocks_ws_hub = StocksWsHub()
