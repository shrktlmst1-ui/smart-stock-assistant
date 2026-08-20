"""Market Pulse runtime — background news polling, stream, and WS broadcast."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import (
    MARKET_PULSE_BROADCAST_INTERVAL_SECONDS,
    MARKET_PULSE_ENABLED,
    MARKET_PULSE_FIXTURE_MODE,
    MARKET_PULSE_NEWS_POLL_SECONDS,
    is_market_pulse_fixture_allowed,
    is_pytest_running,
)
from market_pulse.engine import MarketPulseEngine
from market_pulse.fixtures import fixture_news_items, push_fixture_ticks
from market_pulse.models import MarketPulseHealth, MarketPulseListResponse

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]


class MarketPulseRuntime:
    """Manages safe startup/shutdown of pulse background tasks."""

    def __init__(self, engine: MarketPulseEngine | None = None):
        self.engine = engine or MarketPulseEngine()
        self.mode: str = "disabled"
        self._running = False
        self._broadcast: BroadcastFn | None = None
        self._news_task: asyncio.Task | None = None
        self._broadcast_task: asyncio.Task | None = None
        self._backoff = 2.0
        self._max_backoff = 60.0
        self.last_broadcast_at: datetime | None = None
        self.last_error: str | None = None

    def set_broadcast(self, fn: BroadcastFn) -> None:
        self._broadcast = fn

    def should_run(self) -> bool:
        if is_pytest_running():
            return False
        if is_market_pulse_fixture_allowed():
            return True
        if not MARKET_PULSE_ENABLED:
            return False
        return self.engine.has_credentials()

    async def start(self) -> None:
        if self._running or not self.should_run():
            self.mode = "disabled" if not MARKET_PULSE_ENABLED else "idle"
            return

        self._running = True
        if is_market_pulse_fixture_allowed():
            self.mode = "fixture"
            self.engine.enabled = True
            self.engine.stream.connected = True
            await self._seed_fixture()
        elif self.engine.has_credentials():
            self.mode = "live"
            await self.engine.refresh_news()
            await self.engine.start()
        else:
            self.mode = "idle"
            self._running = False
            return

        self._news_task = asyncio.create_task(self._news_loop())
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("Market Pulse runtime started mode=%s", self.mode)

    async def stop(self) -> None:
        self._running = False
        for task in (self._news_task, self._broadcast_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._news_task = None
        self._broadcast_task = None
        if self.mode == "live":
            await self.engine.stop()
        self.mode = "disabled"
        logger.info("Market Pulse runtime stopped")

    async def _seed_fixture(self) -> None:
        self.engine.ingest_news_batch(fixture_news_items())
        push_fixture_ticks(self.engine)

    async def _news_loop(self) -> None:
        while self._running:
            try:
                if self.mode == "fixture":
                    self.engine.ingest_news_batch(fixture_news_items())
                    push_fixture_ticks(self.engine)
                else:
                    await self.engine.refresh_news()
                self._backoff = 2.0
                self.last_error = None
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.debug("Market pulse news loop error: %s", self.last_error)
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, self._max_backoff)
                continue
            try:
                await asyncio.sleep(MARKET_PULSE_NEWS_POLL_SECONDS)
            except asyncio.CancelledError:
                break

    async def _broadcast_loop(self) -> None:
        while self._running:
            try:
                await self._emit_updates()
                await asyncio.sleep(MARKET_PULSE_BROADCAST_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def _emit_updates(self) -> None:
        if not self._broadcast:
            return
        health = self.health()
        alerts = self.engine.list_alerts()
        payload = MarketPulseListResponse(
            enabled=MARKET_PULSE_ENABLED,
            alerts=alerts,
            count=len(alerts),
        )
        self.last_broadcast_at = datetime.now(timezone.utc)
        await self._broadcast({
            "type": "pulse_list",
            "data": payload.model_dump(),
            "timestamp": self.last_broadcast_at.isoformat(),
        })
        await self._broadcast({
            "type": "pulse_health",
            "data": health.model_dump(),
            "timestamp": self.last_broadcast_at.isoformat(),
        })

    def health(self) -> MarketPulseHealth:
        base = self.engine.health()
        if not MARKET_PULSE_ENABLED:
            return base
        if is_market_pulse_fixture_allowed():
            return MarketPulseHealth(
                enabled=True,
                status="ok",
                has_api_key=False,
                subscribed_symbols=self.engine._subs.count(),
                max_symbols=base.max_symbols,
                stream_connected=True,
                last_news_fetch=datetime.now(timezone.utc).isoformat(),
                message="وضع fixture للتطوير — بيانات تجريبية",
            )
        if self.mode == "live":
            base.message = base.message or f"runtime={self.mode}"
        elif self.mode == "idle":
            base.status = "idle"
            base.message = "الميزة مفعّلة لكن لا يوجد API key"
        return base
