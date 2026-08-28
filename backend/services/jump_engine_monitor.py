"""Jump Engine diagnostic monitor — heartbeat, stage tracing, self-healing state."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from services.market_session import get_us_market_session, is_regular_session
from services.ws_feed_state import DATA_UNAVAILABLE, resolve_feed_state

logger = logging.getLogger(__name__)

LOG_INTERVAL_SEC = 30.0


def _resolve_jump_engine_status(
    *,
    feed_state: str,
    session: str,
) -> str:
    """Expose feed lifecycle state — LIVE only after real market-data messages."""
    if session == "CLOSED":
        return DATA_UNAVAILABLE
    return feed_state


@dataclass
class JumpEngineSnapshot:
    status: str = "STOPPED"
    jump_engine_status: str = DATA_UNAVAILABLE
    market_open: bool = False
    current_session: str = "CLOSED"
    scanner_task_alive: bool = False
    websocket_connected: bool = False
    last_ws_message_time: str = ""
    last_scan_time: str = ""
    cycle_number: int = 0
    scanned_count: int = 0
    candidate_count: int = 0
    stage3_count: int = 0
    alerts_generated: int = 0
    last_error: str = ""
    reconnect_count: int = 0
    refresh_in_progress: bool = False
    refresh_skipped: int = 0
    last_status_log_mono: float = 0.0
    feed_state: str = DATA_UNAVAILABLE
    last_message_age_seconds: float | None = None
    ws_url: str = ""
    subscribed_symbol_count: int = 0
    t_channel_count: int = 0
    q_channel_count: int = 0


class JumpEngineMonitor:
    """Thread-safe Jump Engine heartbeat + per-symbol stage audit trail."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap = JumpEngineSnapshot()
        self._cycle_stage3: int = 0
        self._cycle_alerts: int = 0

    def reset_cycle_counters(self) -> None:
        with self._lock:
            self._cycle_stage3 = 0
            self._cycle_alerts = 0

    def record_error(self, msg: str) -> None:
        with self._lock:
            self._snap.last_error = msg[:300]

    def record_reconnect(self) -> None:
        with self._lock:
            self._snap.reconnect_count += 1

    def tick_started(
        self,
        *,
        scanner_task_alive: bool,
        feed_state: str,
        websocket_connected: bool,
        last_ws_message_time: str,
        last_message_age_seconds: float | None,
        reconnect_count: int,
        refresh_in_progress: bool,
        refresh_skipped: int,
        ws_url: str = "",
        subscribed_symbol_count: int = 0,
        t_channel_count: int = 0,
        q_channel_count: int = 0,
    ) -> None:
        with self._lock:
            self._snap.cycle_number += 1
            session = get_us_market_session()
            self._snap.status = "RUNNING"
            self._snap.current_session = session
            self._snap.market_open = is_regular_session(session)
            self._snap.feed_state = feed_state
            self._snap.jump_engine_status = _resolve_jump_engine_status(
                feed_state=feed_state,
                session=session,
            )
            self._snap.scanner_task_alive = scanner_task_alive
            self._snap.websocket_connected = websocket_connected
            self._snap.last_ws_message_time = last_ws_message_time
            self._snap.last_message_age_seconds = last_message_age_seconds
            self._snap.reconnect_count = reconnect_count
            self._snap.refresh_in_progress = refresh_in_progress
            self._snap.refresh_skipped = refresh_skipped
            self._snap.last_scan_time = datetime.now(timezone.utc).isoformat()
            self._snap.ws_url = ws_url
            self._snap.subscribed_symbol_count = subscribed_symbol_count
            self._snap.t_channel_count = t_channel_count
            self._snap.q_channel_count = q_channel_count
            self._cycle_stage3 = 0
            self._cycle_alerts = 0

    def tick_finished(
        self,
        *,
        scanned_count: int,
        candidate_count: int,
    ) -> None:
        with self._lock:
            self._snap.scanned_count = scanned_count
            self._snap.candidate_count = candidate_count
            self._snap.stage3_count = self._cycle_stage3
            self._snap.alerts_generated = self._cycle_alerts
        self._maybe_log_status()

    def mark_stopped(self) -> None:
        with self._lock:
            self._snap.status = "STOPPED"
            self._snap.scanner_task_alive = False

    def log_stage2(self, symbol: str) -> None:
        logger.info("[JUMP] %s → STAGE2", symbol.upper())

    def log_promoted_stage3(self, symbol: str) -> None:
        with self._lock:
            self._cycle_stage3 += 1
        logger.info("[JUMP] %s → PROMOTED_TO_STAGE3", symbol.upper())

    def log_rejected_stage3(self, symbol: str, reason: str) -> None:
        logger.info("[JUMP] %s → REJECTED_STAGE3 → %s", symbol.upper(), reason or "unknown")

    def log_jump_qualified(self, symbol: str) -> None:
        with self._lock:
            self._cycle_alerts += 1
        logger.info("[JUMP] %s → JUMP_QUALIFIED", symbol.upper())

    def log_jump_rejected(self, symbol: str, reason: str) -> None:
        logger.info("[JUMP] %s → JUMP_REJECTED → %s", symbol.upper(), reason or "unknown")

    def get_snapshot(self) -> JumpEngineSnapshot:
        with self._lock:
            return JumpEngineSnapshot(**self._snap.__dict__)

    def _maybe_log_status(self) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._snap.last_status_log_mono < LOG_INTERVAL_SEC:
                return
            self._snap.last_status_log_mono = now
            s = self._snap
        logger.info(
            "JUMP_ENGINE_STATUS status=%s jump_engine_status=%s feed_state=%s market_open=%s "
            "current_session=%s scanner_task_alive=%s websocket_connected=%s ws_url=%s "
            "subscribed_symbols=%d t_channels=%d q_channels=%d last_ws_message_time=%s "
            "last_message_age=%s last_scan_time=%s cycle_number=%d scanned_count=%d "
            "candidate_count=%d stage3_count=%d alerts_generated=%d last_error=%s "
            "reconnect_count=%d refresh_in_progress=%s refresh_skipped=%d",
            s.status,
            s.jump_engine_status,
            s.feed_state,
            s.market_open,
            s.current_session,
            s.scanner_task_alive,
            s.websocket_connected,
            s.ws_url or "none",
            s.subscribed_symbol_count,
            s.t_channel_count,
            s.q_channel_count,
            s.last_ws_message_time or "none",
            f"{s.last_message_age_seconds:.1f}s" if s.last_message_age_seconds is not None else "none",
            s.last_scan_time or "none",
            s.cycle_number,
            s.scanned_count,
            s.candidate_count,
            s.stage3_count,
            s.alerts_generated,
            s.last_error or "none",
            s.reconnect_count,
            s.refresh_in_progress,
            s.refresh_skipped,
        )


jump_engine_monitor = JumpEngineMonitor()
