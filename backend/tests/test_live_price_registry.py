"""Tests for central live price registry and WS integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.live_price_registry import LivePriceRegistry, live_price_registry
from services.session_price import (
    REGULAR_LAST_TRADE_MAX_AGE_SECONDS,
    REGULAR_QUOTE_MAX_AGE_SECONDS,
    STALE_PRICE_STATUS,
    resolve_session_price,
)


def _ns_ago(seconds: float) -> int:
    return int((datetime.now(timezone.utc) - timedelta(seconds=seconds)).timestamp() * 1_000_000_000)


@pytest.fixture
def registry() -> LivePriceRegistry:
    return LivePriceRegistry()


@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_live_trade_fresh_used(_mock, registry: LivePriceRegistry):
    registry.ingest_trade("BTCT", 1.88, exchange_ts_ns=_ns_ago(1))
    sp = registry.resolve_live("BTCT", prev_close=1.5)
    assert sp is not None
    assert sp.is_valid
    assert sp.source == "live_trade"
    assert sp.price == pytest.approx(1.88, rel=1e-3)


@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_live_trade_stale_not_used(_mock, registry: LivePriceRegistry):
    registry.ingest_trade("BTCT", 1.88, exchange_ts_ns=_ns_ago(20))
    sp = registry.resolve_live("BTCT", prev_close=1.5)
    assert sp is None


@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_live_quote_fresh_fallback(_mock, registry: LivePriceRegistry):
    registry.ingest_quote("BTCT", 1.87, 1.89, exchange_ts_ns=_ns_ago(3))
    sp = registry.resolve_live("BTCT", prev_close=1.5)
    assert sp is not None
    assert sp.source == "live_quote"
    assert sp.price == pytest.approx(1.88, rel=1e-3)


@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_live_quote_stale_rejected(_mock, registry: LivePriceRegistry):
    registry.ingest_quote("BTCT", 1.87, 1.89, exchange_ts_ns=_ns_ago(8))
    sp = registry.resolve_live("BTCT", prev_close=1.5)
    assert sp is None


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_resolve_prefers_live_trade_over_delayed_snapshot(_mock_lp, _mock_sp):
    live_price_registry.ingest_trade(
        "BTCT", 1.91, exchange_ts_ns=int(datetime.now(timezone.utc).timestamp() * 1_000_000_000),
    )
    item = {
        "ticker": "BTCT",
        "prevDay": {"c": 1.5, "v": 100_000},
        "lastTrade": {"p": 2.07, "t": _ns_ago(900)},
        "day": {"c": 2.07, "v": 100_000},
        "updated": _ns_ago(900),
    }
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.is_valid
    assert sp.source == "live_trade"
    assert sp.price == pytest.approx(1.91, rel=1e-3)
    live_price_registry.clear_execution_prices()


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_delayed_snapshot_stale_without_live(_mock):
    live_price_registry.clear_execution_prices()
    item = {
        "ticker": "BTCT",
        "prevDay": {"c": 1.5, "v": 100_000},
        "lastTrade": {"p": 1.88, "t": _ns_ago(900)},
        "day": {"c": 1.88, "v": 100_000},
        "updated": _ns_ago(900),
    }
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.is_stale
    assert sp.stale_reason == STALE_PRICE_STATUS


@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_feed_disconnect_stale_after_freshness(_mock, registry: LivePriceRegistry):
    registry.ingest_trade("X", 2.0, exchange_ts_ns=_ns_ago(1))
    registry.set_connected(True, authenticated=True)
    registry.set_connected(False)
    registry.mark_stale_if_feed_down()
    sp = registry.resolve_live("X", prev_close=1.0)
    assert sp is not None  # tick still in memory
    registry.ingest_trade("X", 2.0, exchange_ts_ns=_ns_ago(REGULAR_LAST_TRADE_MAX_AGE_SECONDS + 5))
    assert registry.resolve_live("X", prev_close=1.0) is None


@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_reconnect_restores_live(_mock, registry: LivePriceRegistry):
    registry.set_connected(False)
    registry.set_connected(True, authenticated=True)
    registry.ingest_trade("Y", 3.0, exchange_ts_ns=int(datetime.now(timezone.utc).timestamp() * 1_000_000_000))
    sp = registry.resolve_live("Y", prev_close=2.0)
    assert sp is not None and sp.is_valid


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_premarket_not_used_during_regular_with_live(_mock_lp, _mock_sp):
    live_price_registry.clear_execution_prices()
    item = {
        "ticker": "BTCT",
        "prevDay": {"c": 1.5, "v": 100_000},
        "preMarket": {"c": 2.07, "v": 50_000},
        "lastTrade": {"p": 2.07, "t": _ns_ago(3600)},
        "day": {"c": 0, "v": 0},
        "updated": _ns_ago(120),
    }
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.is_stale


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_unified_price_for_analysis_path(_mock_lp, _mock_sp):
    live_price_registry.ingest_trade(
        "Z", 4.25, exchange_ts_ns=int(datetime.now(timezone.utc).timestamp() * 1_000_000_000),
    )
    item = {
        "ticker": "Z",
        "prevDay": {"c": 4.0, "v": 100_000},
        "lastTrade": {"p": 3.0, "t": _ns_ago(500)},
        "day": {"c": 3.0, "v": 100_000},
        "updated": _ns_ago(500),
    }
    sp = resolve_session_price(item, session="REGULAR")
    meta = sp.to_metadata()
    assert sp.price == meta["price"]
    assert sp.source == meta["price_source"] == "live_trade"
    live_price_registry.clear_execution_prices()


def test_freshness_constants():
    assert REGULAR_LAST_TRADE_MAX_AGE_SECONDS == 15
    assert REGULAR_QUOTE_MAX_AGE_SECONDS == 5
