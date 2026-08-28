"""Real-time market stream — US scanner with 15s fast tick + shared WS hub."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import SCANNER_TICK_SECONDS, WEBSOCKET_ENABLED, get_polygon_api_key
from services.connection_service import get_connection_status
from services.jump_engine_monitor import jump_engine_monitor
from services.live_feed_pipeline import live_feed_pipeline
from services.live_data_gate import live_data_gate, LIVE_DATA_UNAVAILABLE
from services.live_confirmation_engine import live_confirmation_engine
from services.live_price_registry import live_price_registry
from services.live_symbol_ranker import top_live_symbols
from services.market_scanner_service import market_scanner
from services.opportunity_now_service import sync_engine_from_scanner
from services.polygon_client import PolygonClient
from services.stocks_ws_hub import stocks_ws_hub
from services.ws_bootstrap_symbols import bootstrap_symbols_from_snapshot
from services.ws_feed_state import STALE

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]


class MarketStream:
    def __init__(self) -> None:
        self.client = PolygonClient()
        self._running = False
        self._hub_started = False
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
        use_ws = WEBSOCKET_ENABLED and bool(get_polygon_api_key())
        if use_ws and not status.websocket_available:
            logger.info("[LIVE_PRICE] WebSocket enabled — shared hub (pre-check not required)")

        self._tick_task = asyncio.create_task(self._run_fast_tick())
        self._watchdog_task = asyncio.create_task(self._run_watchdog())

        if use_ws:
            self.mode = "websocket_scanner"
            stocks_ws_hub.add_raw_handler(self._handle_ws_payload)
            await stocks_ws_hub.start()
            await live_feed_pipeline.start()
            self._hub_started = True
            live_confirmation_engine.set_ws_status(connected=True, fallback=False)
        else:
            self.mode = "scanner_rest"

        symbols = self._monitor_symbols()
        if use_ws:
            if symbols:
                stocks_ws_hub.set_consumer("jump", symbols, ("T", "Q"))
                live_confirmation_engine.set_monitor_symbols(symbols)
            elif market_scanner._snapshot_raw:
                from services.universe_manager import universe_manager

                boot = bootstrap_symbols_from_snapshot(
                    market_scanner._snapshot_raw,
                    universe_manager.symbol_set,
                )
                if boot:
                    stocks_ws_hub.set_consumer("jump", boot, ("T", "Q"))
                    live_confirmation_engine.set_monitor_symbols(boot)
                    logger.info("[LIVE_PRICE] bootstrap WS jump symbols=%d", len(boot))

        monitor_count = len(stocks_ws_hub.get_consumer_symbols("jump"))
        logger.info(
            "Institutional scanner stream: mode=%s tick=%ss monitor_symbols=%d hub=%s",
            self.mode,
            SCANNER_TICK_SECONDS,
            monitor_count,
            stocks_ws_hub.status_dict(),
        )

    async def stop(self) -> None:
        self._running = False
        jump_engine_monitor.mark_stopped()
        if self._hub_started:
            stocks_ws_hub.remove_raw_handler(self._handle_ws_payload)
            stocks_ws_hub.clear_consumer("jump")
            await live_feed_pipeline.stop()
            await stocks_ws_hub.stop()
            self._hub_started = False
        for task in (self._tick_task, self._watchdog_task):
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
            "stocks_ws_hub": stocks_ws_hub.status_dict(),
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
        """Self-healing — restart scanner tick / WS hub if feed stalls."""
        hub_down_since: float | None = None
        stale_feed_since: float | None = None
        last_trades = 0
        while self._running:
            await asyncio.sleep(15)
            if not self._running:
                break
            if self._tick_task and self._tick_task.done():
                exc = self._tick_task.exception()
                err = f"tick_task_died:{exc!r}" if exc else "tick_task_died"
                jump_engine_monitor.record_error(err)
                logger.error("[JUMP] Scanner tick task died (%s) — auto-restarting", exc)
                self._tick_task = asyncio.create_task(self._run_fast_tick())
            if WEBSOCKET_ENABLED and self._hub_started:
                if not stocks_ws_hub.is_running:
                    jump_engine_monitor.record_error("stocks_ws_hub_stopped")
                    logger.error("[JUMP] Stocks WS hub stopped — auto-restarting")
                    stocks_ws_hub.add_raw_handler(self._handle_ws_payload)
                    await stocks_ws_hub.start()
                else:
                    connected = stocks_ws_hub.shards_connected
                    now = time.monotonic()
                    if connected == 0:
                        if hub_down_since is None:
                            hub_down_since = now
                        elif now - hub_down_since >= 15:
                            jump_engine_monitor.record_error("ws_shards_down")
                            logger.warning("[JUMP] WS shards disconnected — forcing resync")
                            await stocks_ws_hub.recover_shards()
                            hub_down_since = None
                    else:
                        hub_down_since = None

                    trades = live_price_registry.status.trades_received
                    msg_age = live_price_registry.last_message_age_seconds()
                    feed_state = live_price_registry.feed_state()
                    if feed_state == STALE:
                        jump_engine_monitor.record_error(f"ws_feed_stale age={msg_age}")
                        logger.warning("[JUMP] WS feed STALE — forcing shard reconnect")
                        await stocks_ws_hub.force_stale_reconnect_all()
                        stale_feed_since = None
                    elif trades > 0 and msg_age is not None and msg_age > 90:
                        if stale_feed_since is None:
                            stale_feed_since = now
                        elif now - stale_feed_since >= 30:
                            jump_engine_monitor.record_error(f"ws_stale_feed age={msg_age:.0f}s")
                            logger.warning("[JUMP] WS feed stale (%.0fs) — recover", msg_age)
                            await stocks_ws_hub.recover_shards()
                            stale_feed_since = None
                    elif trades > last_trades or (msg_age is not None and msg_age <= 45):
                        stale_feed_since = None
                    last_trades = trades

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
                    feed_state=live_price_registry.feed_state(),
                    websocket_connected=live_price_registry.status.connected,
                    last_ws_message_time=live_price_registry.last_message_iso(),
                    last_message_age_seconds=live_price_registry.last_message_age_seconds(),
                    reconnect_count=live_price_registry.status.reconnect_count,
                    refresh_in_progress=cs.get("refresh_in_progress", False),
                    refresh_skipped=cs.get("refresh_skipped", 0),
                    ws_url=live_price_registry.status.ws_url,
                    subscribed_symbol_count=len(live_price_registry.status.subscribed_symbols),
                    t_channel_count=live_price_registry.status.t_channel_count,
                    q_channel_count=live_price_registry.status.q_channel_count,
                )

                if self._hub_started:
                    symbols = self._monitor_symbols()
                    if symbols:
                        stocks_ws_hub.set_consumer("jump", symbols, ("T", "Q"))
                        live_confirmation_engine.set_monitor_symbols(symbols)
                    ws_ok = live_price_registry.feed_state() == LIVE and live_data_gate.live_feed_valid
                    live_confirmation_engine.set_ws_status(connected=ws_ok, fallback=not ws_ok)

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

    @staticmethod
    def _patch_snapshot_trade(sym: str, price: float, ts_raw: object) -> None:
        """Keep scanner snapshot lastTrade aligned with WS for Jump price resolution."""
        raw = market_scanner._snapshot_raw
        entry = raw.get(sym)
        if not entry:
            return
        try:
            ts_ns = int(ts_raw) if ts_raw is not None else int(time.time() * 1_000_000_000)
        except (TypeError, ValueError):
            ts_ns = int(time.time() * 1_000_000_000)
        patched = dict(entry)
        patched["lastTrade"] = {"p": price, "t": ts_ns}
        patched["updated"] = ts_ns
        raw[sym] = patched

    def _monitor_symbols(self) -> list[str]:
        from services.pre_move_predictor_service import get_premove_monitor_symbols

        premove = get_premove_monitor_symbols()
        rank = list(market_scanner._rank_pool[:50])
        live = top_live_symbols(30)
        pool = list(dict.fromkeys(rank + live + premove))
        if pool:
            return pool
        state = market_scanner.get_state()
        if state and state.snapshots:
            return [s.symbol for s in state.snapshots[:72]]
        if market_scanner._snapshot_raw:
            from services.universe_manager import universe_manager

            boot = bootstrap_symbols_from_snapshot(
                market_scanner._snapshot_raw,
                universe_manager.symbol_set,
            )
            if boot:
                return boot
        return []

    async def _handle_ws_payload(self, payload: list | dict) -> None:
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
                    self._patch_snapshot_trade(sym, price, item.get("t"))
                    live_confirmation_engine.ingest_ws_trade(sym, price, size)
            elif ev == "Q":
                bid = float(item.get("bp") or item.get("p") or 0)
                ask = float(item.get("ap") or item.get("P") or 0)
                if bid > 0 and ask > 0:
                    live_price_registry.ingest_quote(
                        sym, bid, ask, exchange_ts_ns=item.get("t"),
                    )
                    mid = round((bid + ask) / 2, 4)
                    self._patch_snapshot_trade(sym, mid, item.get("t"))
            elif ev in ("AM", "A"):
                price = float(item.get("c") or item.get("close") or item.get("p") or 0)
                vol = int(item.get("v") or item.get("volume") or 0)
                if price > 0:
                    live_confirmation_engine.ingest_ws_trade(sym, price, vol)
