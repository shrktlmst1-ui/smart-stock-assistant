"""Tests for WS feed lifecycle, stale reconnect, bootstrap, and REGULAR liquidity."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.jump_engine_monitor import JumpEngineMonitor
from services.live_price_registry import FeedStatus, live_price_registry
from services.live_symbol_ranker import note_live_trade, reset_live_ranks, top_live_symbols
from services.market_scanner_service import MarketScannerService
from services.scanner_filters import parse_snapshot_item, passes_liquidity_filter
from services.stocks_ws_hub import ShardState, StocksWsHub
from services.ws_bootstrap_symbols import bootstrap_symbols_from_snapshot
from services.ws_feed_state import (
    DATA_UNAVAILABLE,
    LIVE,
    STALE,
    SUBSCRIBED,
    resolve_feed_state,
)


def _reset_registry() -> None:
    live_price_registry._status = FeedStatus()
    reset_live_ranks()


@pytest.fixture(autouse=True)
def clean_registry():
    _reset_registry()
    yield
    _reset_registry()


class TestFeedStateMachine:
    def test_not_live_without_market_message(self):
        state = resolve_feed_state(
            session="REGULAR",
            hub_running=True,
            connected=True,
            authenticated=True,
            subscribed=True,
            last_message_at=None,
            subscribed_at_mono=time.monotonic(),
        )
        assert state == SUBSCRIBED
        assert state != LIVE

    def test_live_after_market_message(self):
        now = datetime.now(timezone.utc)
        state = resolve_feed_state(
            session="REGULAR",
            hub_running=True,
            connected=True,
            authenticated=True,
            subscribed=True,
            last_message_at=now,
        )
        assert state == LIVE

    def test_stale_after_15s_without_messages(self):
        state = resolve_feed_state(
            session="REGULAR",
            hub_running=True,
            connected=True,
            authenticated=True,
            subscribed=True,
            last_message_at=None,
            subscribed_at_mono=time.monotonic() - 20.0,
        )
        assert state == STALE

    def test_jump_monitor_not_live_without_message(self):
        mon = JumpEngineMonitor()
        with patch("services.jump_engine_monitor.get_us_market_session", return_value="REGULAR"):
            mon.tick_started(
                scanner_task_alive=True,
                feed_state=SUBSCRIBED,
                websocket_connected=True,
                last_ws_message_time="",
                last_message_age_seconds=None,
                reconnect_count=0,
                refresh_in_progress=False,
                refresh_skipped=0,
            )
        snap = mon.get_snapshot()
        assert snap.jump_engine_status == SUBSCRIBED
        assert snap.jump_engine_status != LIVE

    def test_jump_monitor_live_after_message(self):
        mon = JumpEngineMonitor()
        ts = datetime.now(timezone.utc).isoformat()
        with patch("services.jump_engine_monitor.get_us_market_session", return_value="REGULAR"):
            mon.tick_started(
                scanner_task_alive=True,
                feed_state=LIVE,
                websocket_connected=True,
                last_ws_message_time=ts,
                last_message_age_seconds=1.0,
                reconnect_count=0,
                refresh_in_progress=False,
                refresh_skipped=0,
            )
        assert mon.get_snapshot().jump_engine_status == LIVE


class TestStaleReconnect:
    def test_stale_triggers_reconnect(self):
        hub = StocksWsHub()
        shard = ShardState(shard_id=0, symbols=[])
        shard.connected = True
        shard.authenticated = True
        shard.subscribed_channels = {"A.*", "T.AAPL", "Q.AAPL"}
        shard.subscribed_at_mono = time.monotonic() - 20.0
        force, reason = hub._should_force_stale_reconnect(shard)
        assert force is True
        assert "stale_feed" in reason
        assert "attempt=1" in reason


def _snapshot_item(ticker: str, price: float, volume: int, prev_vol: int) -> dict:
    now_ns = int(time.time() * 1_000_000_000)
    return {
        "ticker": ticker,
        "updated": now_ns,
        "lastTrade": {"p": price, "t": now_ns},
        "day": {"c": price, "h": price * 1.005, "l": price * 0.995, "v": volume, "o": price * 0.99},
        "prevDay": {"c": price * 0.95, "v": prev_vol},
    }


class TestBootstrapSymbols:
    def test_bootstrap_from_snapshot_not_rank_pool(self):
        raw = {
            "AAA": _snapshot_item("AAA", 2.0, 500_000, 1_000_000),
            "BBB": _snapshot_item("BBB", 5.0, 100_000, 200_000),
        }
        with patch("services.ws_bootstrap_symbols.resolve_session_price") as mock_sp:
            from datetime import datetime, timezone

            from services.session_price import SessionPrice

            def _sp(item, session=None):
                sym = item["ticker"]
                price = raw[sym]["day"]["c"]
                vol = raw[sym]["day"]["v"]
                return SessionPrice(
                    price=price,
                    volume=vol,
                    change=0.1,
                    change_percent=5.0,
                    timestamp=datetime.now(timezone.utc),
                    session="REGULAR",
                    source="day_bar",
                    is_stale=False,
                    stale_reason="",
                )

            mock_sp.side_effect = _sp
            symbols = bootstrap_symbols_from_snapshot(raw, {"AAA", "BBB"}, min_volume=50_000)
        assert symbols[0] == "AAA"
        assert "AAA" in symbols


class TestRegularLiquidityRvol:
    def test_old_rvol_formula_would_fail_all_stocks(self):
        item = _snapshot_item("TST", 3.0, 400_000, 5_000_000)
        with patch("services.scanner_filters.resolve_session_price") as mock_sp:
            from datetime import datetime, timezone

            from services.session_price import SessionPrice

            mock_sp.return_value = SessionPrice(
                price=3.0,
                volume=400_000,
                change=0.2,
                change_percent=7.0,
                timestamp=datetime.now(timezone.utc),
                session="REGULAR",
                source="last_trade",
                is_stale=False,
                stale_reason="",
            )
            m = parse_snapshot_item(item, {"market_cap": 100_000_000}, session="REGULAR")
        assert m is not None
        assert m.rvol_available is False
        assert m.relative_volume == 0.0

    def test_adv30_rvol_allows_liquid_stocks(self):
        from services.volume_cache import set_cached_adv30

        item = _snapshot_item("LIQ", 2.0, 600_000, 5_000_000)
        set_cached_adv30("LIQ", 400_000)
        with patch("services.scanner_filters.resolve_session_price") as mock_sp:
            from datetime import datetime, timezone

            from services.session_price import SessionPrice

            mock_sp.return_value = SessionPrice(
                price=2.0,
                volume=600_000,
                change=0.1,
                change_percent=5.0,
                timestamp=datetime.now(timezone.utc),
                session="REGULAR",
                source="last_trade",
                is_stale=False,
                stale_reason="",
            )
            m = parse_snapshot_item(item, {"market_cap": 80_000_000}, session="REGULAR")
        assert m is not None
        assert m.rvol_available is True
        assert m.relative_volume == pytest.approx(1.5, rel=0.01)
        assert passes_liquidity_filter(m, session="REGULAR") is True

    def test_missing_rvol_uses_dollar_volume_not_fake_rvol(self):
        item = _snapshot_item("DRV", 4.0, 300_000, 0)
        with patch("services.scanner_filters.resolve_session_price") as mock_sp:
            from datetime import datetime, timezone

            from services.session_price import SessionPrice

            mock_sp.return_value = SessionPrice(
                price=4.0,
                volume=300_000,
                change=0.1,
                change_percent=5.0,
                timestamp=datetime.now(timezone.utc),
                session="REGULAR",
                source="last_trade",
                is_stale=False,
                stale_reason="",
            )
            m = parse_snapshot_item(item, {"market_cap": 90_000_000}, session="REGULAR")
        assert m is not None
        assert m.rvol_available is False
        assert m.relative_volume == 0.0
        assert passes_liquidity_filter(m, session="REGULAR") is True


class TestDataUnavailableScanner:
    def test_empty_state_shows_data_unavailable_without_live_feed(self):
        svc = MarketScannerService()
        svc.universe_size = 13160
        svc._scored_metrics = []
        svc._rank_pool = []
        svc._snapshot_raw = {"X": {"ticker": "X"}}
        live_price_registry._status.connected = True
        live_price_registry._status.authenticated = True
        live_price_registry._status.hub_running = True
        live_price_registry._status.aggregates_subscribed = True
        live_price_registry._status.t_channel_count = 2
        live_price_registry._status.q_channel_count = 2
        live_price_registry._status.subscribed_at_mono = time.monotonic() - 5

        with patch("services.market_scanner_service.get_us_market_session", return_value="REGULAR"):
            state = svc._empty_state()

        assert state.no_signal_reason == DATA_UNAVAILABLE
        assert "لم يجتز أي رمز" not in state.no_signal_reason


class TestLiveRankPool:
    def test_live_trades_feed_rank_pool(self):
        note_live_trade("ZETA", 2.5, 1000)
        note_live_trade("ALFA", 3.0, 5000)
        ranked = top_live_symbols(5)
        assert ranked[0] == "ALFA"


class TestClosedLoopBroken:
    def test_monitor_symbols_uses_bootstrap_when_rank_pool_empty(self):
        from services.market_scanner_service import market_scanner
        from services.market_stream import MarketStream

        ms = MarketStream()
        raw = {"BOOT": _snapshot_item("BOOT", 1.5, 800_000, 1_000_000)}
        market_scanner._rank_pool = []
        market_scanner._snapshot_raw = raw
        market_scanner.get_state = MagicMock(return_value=None)
        with patch("services.universe_manager.universe_manager") as um:
            um.symbol_set = {"BOOT"}
            with patch("services.ws_bootstrap_symbols.resolve_session_price") as mock_sp:
                from datetime import datetime, timezone
                from services.session_price import SessionPrice

                mock_sp.return_value = SessionPrice(
                    price=1.5,
                    volume=800_000,
                    change=0.1,
                    change_percent=5.0,
                    timestamp=datetime.now(timezone.utc),
                    session="REGULAR",
                    source="day_bar",
                    is_stale=False,
                    stale_reason="",
                )
                syms = ms._monitor_symbols()
        assert "BOOT" in syms
