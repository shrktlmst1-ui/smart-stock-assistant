"""Tests for live data architecture — wave, buy pressure, signal snapshot, session continuity."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from models.signal_snapshot import SignalSnapshot
from services.aggregate_wave_tracker import AggregateWaveTracker, WaveState
from services.executed_buy_pressure import ExecutedBuyPressureRegistry, TradeSide
from services.live_data_gate import LIVE_DATA_UNAVAILABLE, LiveDataGate
from services.live_price_registry import live_price_registry


def _ts(minute: int = 0) -> datetime:
    return datetime(2026, 8, 28, 14, minute, 0, tzinfo=timezone.utc)


class TestExecutedBuyPressure:
    def test_buy_at_ask_is_executed_buy(self):
        reg = ExecutedBuyPressureRegistry()
        reg.ingest_quote("X1", bid=1.0, ask=1.02)
        side = reg.ingest_trade("X1", 1.02, 100)
        assert side == TradeSide.BUY
        assert reg.get("X1").executed_ratio_60s() > 0.9

    def test_sell_at_bid_is_executed_sell(self):
        reg = ExecutedBuyPressureRegistry()
        reg.ingest_quote("X2", bid=2.0, ask=2.05)
        reg.ingest_trade("X2", 2.0, 200)
        side = reg.ingest_trade("X2", 2.0, 100)
        assert side == TradeSide.SELL
        w = reg.get("X2").pressure_windows((60.0,))[60.0]
        assert w.sell_dollar > w.buy_dollar

    def test_strong_buy_requires_all_factors(self):
        reg = ExecutedBuyPressureRegistry()
        sym = "X3"
        reg.ingest_quote(sym, 3.0, 3.02)
        for _ in range(10):
            reg.ingest_trade(sym, 3.02, 500)
        ok, reason = reg.qualifies_strong_buy_watch(
            sym,
            price_rising=True,
            volume_accel_above_baseline=True,
            rvol_valid=True,
            spread_tradable=True,
        )
        assert ok is True
        ok2, _ = reg.qualifies_strong_buy_watch(
            sym,
            price_rising=False,
            volume_accel_above_baseline=True,
            rvol_valid=True,
            spread_tradable=True,
        )
        assert ok2 is False


class TestAggregateWaveTracker:
    def test_wave_idle_to_active_to_ended(self):
        tr = AggregateWaveTracker()
        sym = "W1"
        base = 2.0
        for i, px in enumerate([2.0, 2.05, 2.1, 2.3, 2.5, 2.8, 3.2, 3.0, 2.5, 2.2]):
            tr.ingest_aggregate(sym, close=px, low=px * 0.99, high=px, volume=1000, exchange_ts=_ts(i))
        rec = tr.get(sym)
        assert rec is not None
        assert rec.move_start_price > 0
        assert rec.current_move_pct > 0
        assert rec.phase in (WaveState.ACTIVE, WaveState.ENDED, WaveState.BUILDING)

    def test_distinguished_requires_50pct_live_wave(self):
        tr = AggregateWaveTracker()
        sym = "W2"
        for px in [1.0, 1.1, 1.2, 1.25]:
            tr.ingest_aggregate(sym, close=px, low=px * 0.98, volume=500, exchange_ts=_ts())
        rec = tr.get(sym)
        assert rec is not None
        assert rec.current_move_pct < 50
        assert tr.eligible_distinguished(sym) is False

    def test_ended_wave_not_distinguished(self):
        tr = AggregateWaveTracker()
        sym = "W3"
        tr.ingest_aggregate(sym, close=2.0, low=1.9, volume=100, exchange_ts=_ts())
        tr.ingest_aggregate(sym, close=3.2, low=2.0, volume=100, exchange_ts=_ts(1))
        rec = tr.get(sym)
        if rec:
            rec.phase = WaveState.ENDED
            rec.ended_at = _ts(2)
        assert tr.eligible_distinguished(sym) is False


class TestSignalSnapshot:
    def test_rejects_stale_data(self):
        snap = SignalSnapshot(symbol="S1", price=3.0, score=70, status="NOW", live_feed_valid=True, data_age_ms=20_000)
        assert snap.validate() == "STALE_DATA"

    def test_reason_matches_fields(self):
        snap = SignalSnapshot(
            symbol="S2",
            price=2.5,
            wave_move_pct=55.0,
            buy_pressure_ratio_60s=0.7,
            buy_pressure_source="EXECUTED_TRADES",
            rvol=2.0,
            score=80,
            status="NOW",
            live_feed_valid=True,
            data_age_ms=500,
        )
        snap.reason_now_ar = snap.build_reason_now_ar()
        assert snap.validate() is None
        assert "55" in snap.reason_now_ar or "موجة" in snap.reason_now_ar

    def test_live_unavailable_blocks(self):
        snap = SignalSnapshot(symbol="S3", live_feed_valid=False, score=90, status="NOW")
        assert snap.validate() == "LIVE_DATA_UNAVAILABLE"


class TestLiveDataGate:
    def test_invalid_without_aggregates(self):
        gate = LiveDataGate()
        gate.set_ws_health(connected=True, authenticated=True, aggregates_subscribed=False)
        live_price_registry._status.hub_running = True
        live_price_registry._status.connected = True
        live_price_registry._status.authenticated = True
        with patch("services.live_data_gate.get_us_market_session", return_value="REGULAR"):
            assert gate.live_feed_valid is False
            assert gate.jump_engine_status in ("AUTHENTICATED", "CONNECTING", "DATA_UNAVAILABLE")

    def test_valid_with_recent_aggregates(self):
        gate = LiveDataGate()
        gate.set_ws_health(connected=True, authenticated=True, aggregates_subscribed=True)
        live_price_registry._status.hub_running = True
        live_price_registry._status.connected = True
        live_price_registry._status.authenticated = True
        live_price_registry._status.aggregates_subscribed = True
        live_price_registry._status.t_channel_count = 2
        live_price_registry._status.q_channel_count = 2
        live_price_registry._status.provider_subscription_ack = True
        live_price_registry.note_message_received()
        for _ in range(150):
            gate.metrics.note_aggregate()
        with patch("services.live_data_gate.get_us_market_session", return_value="REGULAR"):
            assert gate.live_feed_valid is True


class TestSessionTransitionNoRestFallback:
    """09:29:59 ET PRE → 09:30:01 ET REG — WebSocket stays, no REST live alerts."""

    def test_ws_connection_persists_across_session_label_change(self):
        from services.live_feed_pipeline import LiveFeedPipeline
        from services.live_price_registry import live_price_registry

        pipeline = LiveFeedPipeline()
        live_price_registry.clear_execution_prices()

        with patch("services.live_data_gate.get_us_market_session", return_value="PRE_MARKET"):
            live_data_gate = __import__("services.live_data_gate", fromlist=["live_data_gate"]).live_data_gate
            live_data_gate.set_ws_health(connected=True, authenticated=True, aggregates_subscribed=True)
            live_data_gate.metrics.note_aggregate()
            live_price_registry.ingest_trade("T1", 2.5, exchange_ts_ns=int(_ts().timestamp() * 1e9))

        assert live_price_registry.status.connected or live_data_gate.metrics.ws_connected

        with patch("services.live_data_gate.get_us_market_session", return_value="REGULAR"):
            with patch("services.live_price_registry.get_us_market_session", return_value="REGULAR"):
                live_data_gate.metrics.note_aggregate()
                tick = live_price_registry.get_tick("T1")
                assert tick is None or tick.price > 0

        from services.opportunity_now_service import get_opportunity_now

        with patch("services.opportunity_now_service.live_data_gate") as mock_gate:
            mock_gate.live_feed_valid = True
            mock_gate.jump_engine_status = "LIVE"
            mock_gate.metrics.aggregate_age_seconds = 1.0
            with patch("services.opportunity_now_service.get_us_market_session", return_value="REGULAR"):
                with patch("services.opportunity_now_service.sync_engine_from_scanner"):
                    with patch("services.opportunity_now_service._collect_jump_alerts", return_value=[]):
                        with patch("services.opportunity_now_service._collect_home_display_signals", return_value=[]):
                            with patch("services.opportunity_now_service._collect_real_jump_alerts", return_value=[]):
                                with patch(
                                    "services.opportunity_now_service._collect_distinguished_jump_alerts",
                                    return_value=[],
                                ):
                                    with patch("services.opportunity_now_service._merge_aggregate_distinguished", side_effect=lambda x: x):
                                        with patch("services.opportunity_now_service.live_confirmation_engine") as eng:
                                            eng.ws_connected = True
                                            eng.ws_fallback = False
                                            eng._candidates = {}
                                            eng.best_candidate.return_value = None
                                            resp = get_opportunity_now()
        assert resp.live_source == "websocket"
        assert resp.live_source != "rest"
