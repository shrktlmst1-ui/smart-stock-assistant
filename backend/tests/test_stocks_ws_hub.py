"""Unit tests for stocks WS hub subscription batching."""

from __future__ import annotations

from services.stocks_ws_hub import (
    StocksWsHub,
    _channels_for_symbols,
    _partition_symbols,
)


def test_channels_for_symbols_tq():
    ch = _channels_for_symbols({"AAPL", "TSLA"}, ("T", "Q"))
    assert ch == {"T.AAPL", "Q.AAPL", "T.TSLA", "Q.TSLA"}


def test_partition_single_connection():
    syms = [f"S{i}" for i in range(120)]
    parts = _partition_symbols(syms, max_shards=1, per_shard=60)
    assert len(parts) == 1
    assert len(parts[0]) == 120


def test_partition_multi_shard_when_allowed():
    syms = [f"S{i}" for i in range(120)]
    parts = _partition_symbols(syms, max_shards=3, per_shard=40)
    assert len(parts) == 3
    assert sum(len(p) for p in parts) == 120


def test_hub_merges_consumers():
    hub = StocksWsHub()
    hub.set_consumer("jump", ["AAPL", "TSLA"], ("T", "Q"))
    hub.set_consumer("pulse", ["NVDA"], ("T", "Q", "A"))
    desired = hub._desired_channels()
    assert "T.AAPL" in desired
    assert "Q.TSLA" in desired
    assert "A.NVDA" in desired
    assert len(hub._desired_symbols) == 3


def test_set_consumer_idempotent():
    hub = StocksWsHub()
    hub.set_consumer("jump", ["AAPL"], ("T", "Q"))
    before = hub._desired_symbols.copy()
    hub.set_consumer("jump", ["AAPL"], ("T", "Q"))
    assert hub._desired_symbols == before
