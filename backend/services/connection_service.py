"""Connection verification — auth, subscription, REST, WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import websockets

from config import POLYGON_PLAN, POLYGON_WS_URL, WEBSOCKET_ENABLED, get_polygon_api_key
from services.polygon_client import PolygonAPIError, PolygonClient

logger = logging.getLogger(__name__)


class ConnectionStatus:
    def __init__(self):
        self.api_connected: bool = False
        self.authentication_status: str = "pending"
        self.subscription_status: str = "pending"
        self.live_market_data_status: str = "pending"
        self.data_mode: str = "initializing"
        self.plan: str = POLYGON_PLAN
        self.symbols_tested: list[str] = []
        self.symbols_ok: list[str] = []
        self.symbols_failed: list[str] = []
        self.errors: list[str] = []
        self.last_check: str = ""
        self.websocket_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_connected": self.api_connected,
            "authentication_status": self.authentication_status,
            "subscription_status": self.subscription_status,
            "live_market_data_status": self.live_market_data_status,
            "data_mode": self.data_mode,
            "plan": self.plan,
            "websocket_enabled": WEBSOCKET_ENABLED,
            "websocket_available": self.websocket_available,
            "symbols_tested": self.symbols_tested,
            "symbols_ok": self.symbols_ok,
            "symbols_failed": self.symbols_failed,
            "errors": self.errors,
            "last_check": self.last_check,
        }


_status = ConnectionStatus()


def get_connection_status() -> ConnectionStatus:
    return _status


async def _wait_ws_auth(ws, timeout: float = 8.0) -> tuple[bool, str]:
    """Read status messages until auth_success or auth_failed."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
        events = json.loads(raw)
        if not isinstance(events, list):
            events = [events]
        for ev in events:
            if ev.get("ev") != "status":
                continue
            st = ev.get("status", "")
            if st == "auth_success":
                return True, "authenticated"
            if st == "auth_failed":
                return False, ev.get("message", "auth_failed")
    return False, "timeout"


async def test_websocket(timeout: float = 8.0) -> tuple[bool, str]:
    api_key = get_polygon_api_key()
    if not api_key:
        return False, "no_api_key"

    try:
        async with websockets.connect(POLYGON_WS_URL) as ws:
            await ws.send(json.dumps({"action": "auth", "params": api_key}))
            return await _wait_ws_auth(ws, timeout)
    except asyncio.TimeoutError:
        return False, "timeout"
    except Exception as e:
        logger.warning("WebSocket test failed: %s", e)
        return False, str(e)


async def verify_connection(symbols: list[str] | None = None) -> ConnectionStatus:
    global _status
    _status = ConnectionStatus()
    _status.last_check = datetime.now(timezone.utc).isoformat()

    try:
        client = PolygonClient()
    except ValueError as e:
        _status.authentication_status = "failed"
        _status.api_connected = False
        _status.errors.append(str(e))
        return _status

    # 1) Authenticate
    try:
        auth = await client.verify_authentication()
        if auth.get("authenticated"):
            _status.authentication_status = "authenticated"
            _status.api_connected = True
            _status.subscription_status = f"active ({POLYGON_PLAN})"
        else:
            _status.authentication_status = "failed"
            _status.errors.append(f"API status: {auth.get('status')}")
    except PolygonAPIError as e:
        _status.authentication_status = "failed"
        _status.api_connected = False
        _status.errors.append(e.message)
        await client.close()
        return _status
    except Exception as e:
        _status.authentication_status = "failed"
        _status.errors.append(str(e))
        await client.close()
        return _status

    # 2) Full US market snapshot (primary) + optional symbol spot-check
    try:
        universe = await client.get_full_market_snapshot()
        _status.symbols_tested = ["US_MARKET_SCAN"]
        if len(universe) >= 100:
            _status.symbols_ok = [
                (t.get("ticker") or "").upper()
                for t in universe[:8]
                if t.get("ticker")
            ]
            _status.live_market_data_status = "live"
        else:
            _status.symbols_failed.append("US_MARKET_SCAN")
            _status.errors.append(f"Market scan returned only {len(universe)} tickers")
    except Exception as e:
        _status.errors.append(f"Market scan: {e}")
        if symbols:
            _status.symbols_tested = list(symbols)
            try:
                batch = await client.get_snapshots_batch(symbols)
                for sym in symbols:
                    if batch.get(sym.upper()):
                        _status.symbols_ok.append(sym.upper())
            except Exception as e2:
                _status.errors.append(f"REST fallback: {e2}")

    if _status.symbols_ok and _status.live_market_data_status != "live":
        _status.live_market_data_status = "live"
    elif _status.api_connected and not _status.symbols_ok:
        _status.live_market_data_status = "degraded"

    # 3) WebSocket test
    if WEBSOCKET_ENABLED:
        ws_ok, ws_msg = await test_websocket()
        _status.websocket_available = ws_ok
        if ws_ok:
            _status.data_mode = "websocket"
            _status.live_market_data_status = "live"
        else:
            _status.data_mode = "rest_polling"
            _status.errors.append(f"WebSocket unavailable ({ws_msg}) — using REST polling")
    else:
        _status.data_mode = "rest_polling"

    await client.close()
    _status.last_check = datetime.now(timezone.utc).isoformat()
    logger.info(
        "Connection verified: api=%s auth=%s live=%s mode=%s ok=%s",
        _status.api_connected,
        _status.authentication_status,
        _status.live_market_data_status,
        _status.data_mode,
        _status.symbols_ok,
    )
    return _status
