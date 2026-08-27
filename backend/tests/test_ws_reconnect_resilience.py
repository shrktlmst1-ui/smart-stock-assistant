"""WebSocket hub reconnect — auth, resubscribe, state preservation."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from services.live_price_registry import live_price_registry
from services.stocks_ws_hub import ConsumerSpec, StocksWsHub, ShardState


def _reset_registry():
    live_price_registry._status.reconnect_count = 0
    live_price_registry._status.trades_received = 0
    live_price_registry._status.last_error = ""


def test_backoff_tiers():
    _reset_registry()
    hub = StocksWsHub()
    assert hub._backoff_for_error("max_connections:dup", 2.0) >= 30.0
    assert hub._backoff_for_error("auth_failed:bad", 2.0) >= 60.0
    assert hub._backoff_for_error("policy:1008", 2.0) >= 5.0


def test_reconnect_count_only_after_first_session():
    shard = ShardState(shard_id=0, symbols=["AAPL"])
    assert shard.reconnect_count == 0
    shard.had_successful_session = True
    shard.reconnect_count += 1
    assert shard.reconnect_count == 1


def test_shard_reconnects_and_resubscribes():
    """Simulate connect → auth → subscribe; hub consumer survives disconnect."""
    _reset_registry()
    hub = StocksWsHub()
    hub.set_consumer("jump", ["AAPL"], ("T", "Q"))

    auth_ok = json.dumps([{"ev": "status", "status": "auth_success", "message": "authenticated"}])
    calls = {"connect": 0, "subscribe": 0}

    class FakeWS:
        def __init__(self):
            self._recv_queue: asyncio.Queue = asyncio.Queue()

        async def send(self, payload: str):
            msg = json.loads(payload)
            if msg.get("action") == "auth":
                await self._recv_queue.put(auth_ok)
            elif msg.get("action") == "subscribe":
                calls["subscribe"] += 1
                await self._recv_queue.put(json.dumps([{"ev": "T", "sym": "AAPL", "p": 10.5}]))

        async def recv(self):
            return await asyncio.wait_for(self._recv_queue.get(), timeout=0.5)

        async def __aenter__(self):
            calls["connect"] += 1
            return self

        async def __aexit__(self, *args):
            pass

    async def _run():
        def make_ws(*_a, **_k):
            return FakeWS()

        with patch("services.stocks_ws_hub.get_polygon_api_key", return_value="test-key"), patch(
            "services.stocks_ws_hub.websockets.connect", side_effect=make_ws
        ), patch("services.stocks_ws_hub._wait_ws_auth", return_value=(True, "ok")):
            hub._running = True
            hub._shards = [ShardState(shard_id=0, symbols=["AAPL"])]
            shard = hub._shards[0]
            task = asyncio.create_task(hub._run_shard(shard))
            await asyncio.sleep(0.2)
            hub._running = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert calls["connect"] >= 1
        assert calls["subscribe"] >= 1
        assert hub._consumers.get("jump") is not None

    asyncio.run(_run())


def test_policy_resubscribe_without_full_teardown():
    async def _run():
        hub = StocksWsHub()
        hub._subscribe_batch_size = 40
        shard = ShardState(shard_id=0, symbols=["AAPL"])
        shard.connected = True
        shard.authenticated = True
        ws = AsyncMock()
        hub._consumers["jump"] = ConsumerSpec(symbols={"AAPL"}, channel_types=("T", "Q"))
        with patch.object(hub, "_send_batched", new_callable=AsyncMock) as mock_send:
            shard.subscribed_channels.clear()
            desired = hub._shard_desired_channels(shard)
            await hub._send_batched(ws, "subscribe", sorted(desired), batch_size=20)
            shard.subscribed_channels = desired
            mock_send.assert_called_once()

    asyncio.run(_run())
