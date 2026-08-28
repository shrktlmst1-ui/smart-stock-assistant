"""Live feed pipeline — non-blocking WS reader, bounded queue, analysis workers.

Reader enqueues raw events only. Workers update wave tracker, buy pressure, and live gate.
Session transitions (PRE→REG) do not disconnect — session label changes only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from services.aggregate_wave_tracker import aggregate_wave_tracker
from services.executed_buy_pressure import executed_buy_pressure_registry
from services.live_data_gate import live_data_gate
from services.session_price import _ns_to_datetime
from services.stocks_ws_hub import stocks_ws_hub

logger = logging.getLogger(__name__)

QUEUE_MAX = int(__import__("os").getenv("LIVE_FEED_QUEUE_MAX", "8000"))
WORKER_COUNT = int(__import__("os").getenv("LIVE_FEED_WORKERS", "2"))


@dataclass
class PipelineStats:
    enqueued: int = 0
    processed: int = 0
    dropped: int = 0
    queue_high_water: int = 0
    aggregates: int = 0
    trades: int = 0
    quotes: int = 0
    deep_subscribe_requests: int = 0


class LiveFeedPipeline:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[float, dict]] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._deep_symbols: set[str] = set()
        self.stats = PipelineStats()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        stocks_ws_hub.add_raw_handler(self._enqueue_only)
        stocks_ws_hub.set_consumer("aggregates", [], channel_types=(), wildcards=("A.*",))
        self._workers = [asyncio.create_task(self._worker(i)) for i in range(WORKER_COUNT)]
        logger.info("[LIVE_FEED] pipeline started workers=%d queue_max=%d", WORKER_COUNT, QUEUE_MAX)

    async def stop(self) -> None:
        self._running = False
        stocks_ws_hub.remove_raw_handler(self._enqueue_only)
        stocks_ws_hub.clear_consumer("aggregates")
        for t in self._workers:
            if not t.done():
                t.cancel()
        for t in self._workers:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._workers.clear()
        self._deep_symbols.clear()

    async def _enqueue_only(self, payload: list | dict) -> None:
        """Fast path — never block WS recv loop on analysis."""
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("ev") == "status":
                continue
            self.stats.enqueued += 1
            try:
                self._queue.put_nowait((time.monotonic(), item))
            except asyncio.QueueFull:
                self.stats.dropped += 1
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    self._queue.put_nowait((time.monotonic(), item))
                except asyncio.QueueFull:
                    self.stats.dropped += 1
            qs = self._queue.qsize()
            if qs > self.stats.queue_high_water:
                self.stats.queue_high_water = qs
        live_data_gate.note_queue(size=self._queue.qsize(), dropped=self.stats.dropped)

    async def _worker(self, worker_id: int) -> None:
        while self._running:
            try:
                _, item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                self._process_event(item)
            except Exception as exc:
                logger.debug("[LIVE_FEED] worker=%d error %s", worker_id, type(exc).__name__)
            finally:
                self._queue.task_done()
                self.stats.processed += 1

    def _process_event(self, item: dict) -> None:
        ev = item.get("ev") or item.get("event")
        sym = (item.get("sym") or item.get("symbol") or "").upper()
        if ev == "A":
            close = float(item.get("c") or item.get("close") or item.get("p") or 0)
            if close <= 0 or not sym:
                return
            ts = _parse_ts(item.get("s") or item.get("e") or item.get("t"))
            aggregate_wave_tracker.ingest_aggregate(
                sym,
                close=close,
                open_=float(item.get("o") or item.get("open") or close),
                high=float(item.get("h") or item.get("high") or close),
                low=float(item.get("l") or item.get("low") or close),
                volume=int(item.get("v") or item.get("volume") or 0),
                exchange_ts=ts,
            )
            self.stats.aggregates += 1
            live_data_gate.metrics.note_aggregate()
            wave = aggregate_wave_tracker.get(sym)
            if wave and wave.phase.value == "BUILDING" and sym not in self._deep_symbols:
                self._deep_symbols.add(sym)
                self.stats.deep_subscribe_requests += 1
                self._request_deep(sym)
        elif ev == "T" and sym:
            price = float(item.get("p") or item.get("price") or 0)
            size = int(item.get("s") or item.get("size") or 0)
            if price > 0:
                executed_buy_pressure_registry.ingest_trade(sym, price, size)
                self.stats.trades += 1
                live_data_gate.metrics.note_trade()
        elif ev == "Q" and sym:
            bid = float(item.get("bp") or item.get("p") or 0)
            ask = float(item.get("ap") or item.get("P") or 0)
            if bid > 0 and ask > 0:
                executed_buy_pressure_registry.ingest_quote(sym, bid, ask)
                self.stats.quotes += 1

    def _request_deep(self, symbol: str) -> None:
        """Subscribe T/Q for symbol when movement begins — via hub consumer merge."""
        current = list(self._deep_symbols)
        jump_syms = stocks_ws_hub.get_consumer_symbols("jump")
        merged = list(dict.fromkeys(jump_syms + current))[:120]
        stocks_ws_hub.set_consumer("jump", merged, ("T", "Q"))

    def status_dict(self) -> dict:
        hub = stocks_ws_hub.status_dict()
        gate = live_data_gate.metrics.to_dict()
        return {
            "pipeline": {
                "enqueued": self.stats.enqueued,
                "processed": self.stats.processed,
                "dropped": self.stats.dropped,
                "queue_size": self._queue.qsize(),
                "queue_high_water": self.stats.queue_high_water,
                "aggregates": self.stats.aggregates,
                "trades": self.stats.trades,
                "quotes": self.stats.quotes,
                "deep_symbols": len(self._deep_symbols),
            },
            "gate": gate,
            "hub": hub,
        }


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    try:
        ts_f = float(raw)
    except (TypeError, ValueError):
        return None
    if ts_f > 1e15:
        return _ns_to_datetime(ts_f)
    if ts_f > 1e12:
        return datetime.fromtimestamp(ts_f / 1000.0, tz=timezone.utc)
    return datetime.fromtimestamp(ts_f, tz=timezone.utc)


live_feed_pipeline = LiveFeedPipeline()
