"""Tests for Market Pulse runtime and WebSocket — Phase 2."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from market_pulse.engine import MarketPulseEngine
from market_pulse.runtime import MarketPulseRuntime
from market_pulse.service import reset_market_pulse_engine, reset_market_pulse_runtime


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_runtime_does_not_start_when_disabled():
    engine = MarketPulseEngine(enabled=False)
    runtime = MarketPulseRuntime(engine=engine)
    await runtime.start()
    assert runtime.mode == "disabled"
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_start_stop_fixture_mode():
    engine = MarketPulseEngine(enabled=True)
    runtime = MarketPulseRuntime(engine=engine)
    with patch("market_pulse.runtime.is_pytest_running", return_value=False):
        with patch("market_pulse.runtime.is_market_pulse_fixture_allowed", return_value=True):
            with patch("market_pulse.runtime.MARKET_PULSE_ENABLED", True):
                await runtime.start()
                assert runtime.mode == "fixture"
                alerts = engine.list_alerts()
                assert len(alerts) >= 1
                await runtime.stop()
                assert runtime.mode == "disabled"


@pytest.mark.asyncio
async def test_runtime_skips_under_pytest():
    engine = MarketPulseEngine(enabled=True)
    runtime = MarketPulseRuntime(engine=engine)
    with patch("market_pulse.runtime.is_pytest_running", return_value=True):
        with patch("market_pulse.runtime.is_market_pulse_fixture_allowed", return_value=True):
            await runtime.start()
            assert runtime.mode == "disabled"


def test_fixture_blocked_in_production():
    from config import is_market_pulse_fixture_allowed

    with patch("config.MARKET_PULSE_FIXTURE_MODE", True):
        with patch("config.is_production_release", return_value=True):
            assert is_market_pulse_fixture_allowed() is False


def test_ws_market_pulse_health_message(client, auth_headers):
    reset_market_pulse_engine(MarketPulseEngine(enabled=False))
    reset_market_pulse_runtime(None)
    token = auth_headers["Authorization"].split(" ", 1)[1]
    with client.websocket_connect("/ws/market-pulse") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": token}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "pulse_health"
        assert "apiKey" not in json.dumps(msg)
        list_msg = json.loads(ws.receive_text())
        assert list_msg["type"] == "pulse_list"


@pytest.mark.asyncio
async def test_runtime_broadcast_emits_safe_payload():
    engine = MarketPulseEngine(enabled=True)
    runtime = MarketPulseRuntime(engine=engine)
    sent: list[dict] = []

    async def capture(msg: dict) -> None:
        sent.append(msg)

    runtime.set_broadcast(capture)
    with patch("market_pulse.runtime.is_pytest_running", return_value=False):
        with patch("market_pulse.runtime.is_market_pulse_fixture_allowed", return_value=True):
            with patch("market_pulse.runtime.MARKET_PULSE_ENABLED", True):
                await runtime.start()
                await runtime._emit_updates()
                await runtime.stop()
    assert sent
    payload = json.dumps(sent[0])
    assert "apiKey" not in payload
    assert sent[0]["type"] == "pulse_list"


def test_health_disabled_via_api(client, auth_headers):
    reset_market_pulse_engine(MarketPulseEngine(enabled=False))
    reset_market_pulse_runtime(None)
    resp = client.get("/market-pulse/health", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"
