"""Tests for session-aware price resolution and REGULAR freshness guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from services.session_price import (
    REGULAR_DAY_BAR_MAX_AGE_SECONDS,
    REGULAR_LAST_TRADE_MAX_AGE_SECONDS,
    REGULAR_QUOTE_MAX_AGE_SECONDS,
    STALE_PRICE_REASON_AR,
    STALE_PRICE_STATUS,
    inspect_price_sources,
    resolve_session_price,
)

ET = ZoneInfo("America/New_York")


def _now_ns() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)


def _ns_ago(seconds: float) -> int:
    return int((datetime.now(timezone.utc) - timedelta(seconds=seconds)).timestamp() * 1_000_000_000)


def _ns_at(hour: int, minute: int) -> int:
    now_et = datetime.now(ET)
    dt = datetime(now_et.year, now_et.month, now_et.day, hour, minute, tzinfo=ET)
    return int(dt.timestamp() * 1_000_000_000)


def _regular_item(**overrides) -> dict:
    base = {
        "ticker": "TEST",
        "prevDay": {"c": 1.50, "v": 500_000},
        "day": {"c": 1.88, "v": 200_000, "o": 1.85, "h": 1.95, "l": 1.80},
        "min": {"c": 1.88, "v": 5000, "t": int(datetime.now(timezone.utc).timestamp() * 1000)},
        "updated": _now_ns(),
        "lastTrade": {"p": 1.90, "t": _now_ns()},
    }
    base.update(overrides)
    return base


def _btct_stale_premarket_item() -> dict:
    return {
        "ticker": "BTCT",
        "prevDay": {"c": 1.50, "v": 500_000},
        "preMarket": {"c": 2.07, "h": 2.10, "v": 100_000},
        "lastTrade": {"p": 2.07, "t": _ns_at(8, 45)},
        "day": {"c": 1.88, "v": 200_000, "o": 1.85, "h": 1.95, "l": 1.80},
        "min": {"c": 1.88, "v": 5000, "t": int(datetime.now(timezone.utc).timestamp() * 1000)},
        "updated": _now_ns(),
    }


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_last_trade_10s_accepted(_mock_session):
    item = _regular_item(lastTrade={"p": 1.91, "t": _ns_ago(10)})
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.is_valid
    assert sp.source == "last_trade"
    assert sp.price == pytest.approx(1.91, rel=1e-3)


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_last_trade_20s_rejected(_mock_session):
    item = _regular_item(lastTrade={"p": 1.91, "t": _ns_ago(20)})
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.source in ("day_bar", "quote", "none")
    assert sp.source != "last_trade"


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_quote_3s_accepted(_mock_session):
    item = _regular_item(lastTrade={"p": 1.91, "t": _ns_ago(30)})
    nbbo = {"p": 1.89, "P": 1.91, "t": _ns_ago(3)}
    sp = resolve_session_price(item, session="REGULAR", nbbo=nbbo)
    assert sp.is_valid
    assert sp.source == "quote"
    assert sp.price == pytest.approx(1.90, rel=1e-3)


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_quote_8s_rejected(_mock_session):
    item = _regular_item(lastTrade={"p": 1.91, "t": _ns_ago(30)}, updated=_ns_ago(45))
    nbbo = {"p": 1.89, "P": 1.91, "t": _ns_ago(8)}
    sp = resolve_session_price(item, session="REGULAR", nbbo=nbbo)
    assert sp.source != "quote"


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_day_bar_45s_accepted(_mock_session):
    item = _regular_item(
        lastTrade={"p": 1.91, "t": _ns_ago(30)},
        updated=_ns_ago(45),
    )
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.is_valid
    assert sp.source == "day_bar"
    assert sp.price == pytest.approx(1.88, rel=1e-3)


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_day_bar_90s_rejected(_mock_session):
    item = _regular_item(
        lastTrade={"p": 1.91, "t": _ns_ago(120)},
        updated=_ns_ago(90),
    )
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.is_stale
    assert sp.stale_reason == STALE_PRICE_STATUS


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_no_fresh_source_stale_price(_mock_session):
    item = {
        "ticker": "XYZ",
        "prevDay": {"c": 2.0, "v": 100_000},
        "preMarket": {"c": 2.5, "v": 50_000},
        "lastTrade": {"p": 2.5, "t": _ns_at(7, 30)},
        "day": {"c": 0, "v": 0},
        "min": {"c": 0, "v": 0},
        "updated": _ns_ago(120),
    }
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.is_stale
    assert sp.stale_reason == STALE_PRICE_STATUS
    assert sp.price == 0.0


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_premarket_not_selected_during_regular(_mock_session):
    item = _btct_stale_premarket_item()
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.price == pytest.approx(1.88, rel=1e-3)
    assert sp.source == "day_bar"
    assert sp.price != pytest.approx(2.07, rel=1e-3)


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_btct_fresh_last_trade_priority(_mock_session):
    item = _btct_stale_premarket_item()
    item["lastTrade"] = {"p": 1.90, "t": _now_ns()}
    sp = resolve_session_price(item, session="REGULAR")
    assert sp.source == "last_trade"
    assert sp.price == pytest.approx(1.90, rel=1e-3)


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_priority_last_trade_over_quote_and_day(_mock_session):
    item = _regular_item(lastTrade={"p": 1.95, "t": _now_ns()}, updated=_now_ns())
    nbbo = {"p": 1.89, "P": 1.91, "t": _now_ns()}
    sp = resolve_session_price(item, session="REGULAR", nbbo=nbbo)
    assert sp.source == "last_trade"
    assert sp.price == pytest.approx(1.95, rel=1e-3)


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_priority_quote_over_day_when_last_trade_stale(_mock_session):
    item = _regular_item(lastTrade={"p": 1.95, "t": _ns_ago(20)}, updated=_now_ns())
    nbbo = {"p": 1.89, "P": 1.91, "t": _now_ns()}
    sp = resolve_session_price(item, session="REGULAR", nbbo=nbbo)
    assert sp.source == "quote"


@patch("services.session_price.get_us_market_session", return_value="REGULAR")
def test_analysis_uses_same_resolved_price_metadata(_mock_session):
    from services.stock_service import _resolve_snapshot_price

    item = _regular_item(lastTrade={"p": 2.05, "t": _now_ns()})
    price, volume, change, change_pct, sp = _resolve_snapshot_price(item)
    meta = sp.to_metadata()
    assert price == meta["price"]
    assert sp.source == meta["price_source"]
    assert sp.session == meta["price_session"]
    assert meta["price_timestamp"]


@pytest.mark.asyncio
@patch("services.stock_service.get_client")
@patch("services.session_price.get_us_market_session", return_value="REGULAR")
async def test_stale_price_blocks_entry_recommendation_in_premove(
    _mock_session, mock_get_client,
):
    """STALE_PRICE must not produce actionable entry levels."""
    from unittest.mock import AsyncMock

    from services.live_price_registry import live_price_registry
    from services.pre_move_predictor_service import _deep_analyze

    live_price_registry.clear_execution_prices()
    mock_client = AsyncMock()
    mock_client.get_last_nbbo.return_value = {}
    mock_get_client.return_value = mock_client

    candidate = {
        "symbol": "BTCT",
        "name": "BTCT",
        "price": 2.07,
        "change_percent": 10.0,
        "volume": 100_000,
        "spread_pct": 1.0,
        "day_high": 2.10,
        "item": _btct_stale_premarket_item(),
    }
    item = candidate["item"]
    item["updated"] = _ns_ago(120)
    item["lastTrade"] = {"p": 2.07, "t": _ns_at(8, 45)}
    item["min"] = {"c": 1.88, "v": 5000, "t": int(_ns_ago(120) / 1_000_000)}

    sig = await _deep_analyze(candidate, "REGULAR")
    assert sig is not None
    assert sig.status == STALE_PRICE_STATUS
    assert sig.current_price == 0.0
    assert sig.entry_low == 0.0
    assert sig.stop_loss == 0.0
    assert sig.tp1 == 0.0
    assert STALE_PRICE_REASON_AR in (sig.reason or "")


@patch("services.session_price.get_us_market_session", return_value="PRE_MARKET")
def test_premarket_uses_premarket_price(_mock_session):
    item = _btct_stale_premarket_item()
    with patch("services.session_price._is_trade_fresh", return_value=True):
        sp = resolve_session_price(item, session="PRE_MARKET")
    assert sp.price == pytest.approx(2.07, rel=1e-3)
    assert sp.source == "premarket"


def test_premarket_to_regular_preserves_jump_caches():
    """PRE_MARKET→REGULAR must not wipe WS ticks or opportunities snapshot."""
    import services.session_price as sp_mod
    from services.live_price_registry import live_price_registry
    from services.snapshot_cache_service import invalidate_opportunities_cache

    sp_mod._last_known_session = "PRE_MARKET"
    live_price_registry.ingest_trade("BTCT", 2.10, exchange_ts_ns=_now_ns())
    assert live_price_registry.get_tick("BTCT") is not None

    with patch("services.session_price.get_us_market_session", return_value="REGULAR"):
        with patch(
            "services.snapshot_cache_service.invalidate_opportunities_cache",
        ) as mock_invalidate_opps:
            session = sp_mod.ensure_session_cache_valid()

    assert session == "REGULAR"
    assert live_price_registry.get_tick("BTCT") is not None
    mock_invalidate_opps.assert_not_called()
    assert sp_mod._last_known_session == "REGULAR"


def test_other_session_transition_still_clears_jump_caches():
    """Non PRE_MARKET→REGULAR transitions must still invalidate jump caches."""
    import services.session_price as sp_mod
    from services.live_price_registry import live_price_registry

    sp_mod._last_known_session = "REGULAR"
    live_price_registry.ingest_trade("BTCT", 2.10, exchange_ts_ns=_now_ns())

    with patch("services.session_price.get_us_market_session", return_value="AFTER_HOURS"):
        with patch(
            "services.snapshot_cache_service.invalidate_opportunities_cache",
        ) as mock_invalidate_opps:
            with patch.object(live_price_registry, "clear_execution_prices") as mock_clear:
                sp_mod.ensure_session_cache_valid()

    mock_invalidate_opps.assert_called_once()
    mock_clear.assert_called_once()


def test_freshness_constants():
    assert REGULAR_LAST_TRADE_MAX_AGE_SECONDS == 15
    assert REGULAR_QUOTE_MAX_AGE_SECONDS == 5
    assert REGULAR_DAY_BAR_MAX_AGE_SECONDS == 60


def test_stale_reason_ar():
    assert "غير محدث" in STALE_PRICE_REASON_AR


def test_inspect_price_sources_structure():
    item = _regular_item()
    report = inspect_price_sources(item, session="REGULAR")
    assert report["symbol"] == "TEST"
    assert "last_trade" in report
    assert "quote" in report
    assert "day_bar" in report
    assert "resolved" in report


def test_exchange_timestamp_milliseconds_ws_age():
    from services.session_price import _age_seconds, _exchange_ts_to_epoch_seconds, _ns_to_datetime

    now = datetime.now(timezone.utc)
    ms = int(now.timestamp() * 1000)
    dt = _ns_to_datetime(ms)
    assert dt is not None
    age = _age_seconds(dt)
    assert age < 2.0
    secs = _exchange_ts_to_epoch_seconds(ms)
    assert secs is not None
    assert abs(secs - now.timestamp()) < 0.001


def test_exchange_timestamp_milliseconds_10s_ago():
    from services.session_price import _age_seconds, _ns_to_datetime

    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    ms = int(past.timestamp() * 1000)
    dt = _ns_to_datetime(ms)
    assert dt is not None
    age = _age_seconds(dt)
    assert 8.0 <= age <= 12.0


def test_exchange_timestamp_nanoseconds_rest_snapshot():
    from services.session_price import _age_seconds, _ns_to_datetime

    now = datetime.now(timezone.utc)
    ns = int(now.timestamp() * 1_000_000_000)
    dt = _ns_to_datetime(ns)
    assert dt is not None
    age = _age_seconds(dt)
    assert age < 2.0


@patch("services.live_price_registry.get_us_market_session", return_value="REGULAR")
def test_live_registry_ws_millisecond_trade_is_fresh(_mock):
    from services.live_price_registry import LivePriceRegistry
    from services.session_price import REGULAR_LAST_TRADE_MAX_AGE_SECONDS

    registry = LivePriceRegistry()
    ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    registry.ingest_trade("BTCT", 2.10, exchange_ts_ns=ms)
    resolved = registry.resolve_live("BTCT")
    assert resolved is not None
    assert resolved.source == "live_trade"
    assert not resolved.is_stale
    tick = registry.get_tick("BTCT")
    assert tick is not None
    assert tick.age_seconds <= REGULAR_LAST_TRADE_MAX_AGE_SECONDS
