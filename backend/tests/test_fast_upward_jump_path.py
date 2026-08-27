"""FAST_UPWARD_JUMP_PATH + REARMED + display trust tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncio

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.early_upward_surge import evaluate_fast_upward_jump, relative_surge_detected
from analysis.pre_move_stage_progression import build_snapshot, evaluate_stage_transition
from models.pre_move import (
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from scripts.premove_replay_lib import filter_premarket_regular, replay_session, summarize_replay
from services.display_buy_pressure_filter import (
    DISPLAY_JUMP_ALERT,
    DISPLAY_STRONG_BUY_WATCH,
    evaluate_premove_display,
)
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient
from services.pre_move_stage_store import create_replay_state, reset_store

DATE = "2026-08-27"


def _snap(**kw) -> "StageSnapshot":
    defaults = dict(
        timestamp="2026-08-27T04:09:00-04:00",
        price=5.47,
        change_pct=6.2,
        pre_move_score=61,
        volume_acceleration_1m=2.72,
        volume_acceleration_3m=2.0,
        volume_acceleration_slope=1.2,
        rvol=0.11,
        rvol_same_time=0.11,
        dollar_volume_growth=0.3,
        trade_velocity=121.0,
        trade_velocity_growth=0.2,
        early_activity_score=15.0,
        compression_score=0.5,
        range_compression_3m=0.7,
        micro_higher_lows=True,
        higher_lows_score=0.6,
        resistance_distance_pct=0.2,
        distance_to_breakout_pct=0.2,
        breakout_pressure=45.0,
        vwap_hold=True,
        vwap_reclaim=False,
        distance_from_vwap_pct=0.5,
        liquidity_score=70.0,
        spread_pct=2.0,
        price_volume_response=1.0,
        news_catalyst_score=0.0,
        risk_reward=1.5,
        trigger_price=5.5,
        late_guard=False,
        failed_setup=True,
    )
    defaults.update(kw)
    return build_snapshot(**defaults)


@pytest.fixture(autouse=True)
def _clean_stage_store():
    reset_store()
    yield
    reset_store()


def test_soft_rvol_allows_surge_without_hard_rvol():
    ok = relative_surge_detected(
        change_percent=8.0,
        volume_acceleration_1m=2.5,
        volume_acceleration_slope=1.15,
        rvol=0.2,
        rvol_same_time=0.2,
        trade_velocity_growth=0.2,
        price_volume_response=0.5,
        micro_higher_lows=True,
        allow_soft_rvol=True,
    )
    assert ok is True


def test_volume_spike_without_price_accel_rejected():
    v = evaluate_fast_upward_jump(
        _snap(volume_acceleration_1m=3.0, price_volume_response=0.05, change_pct=1.0),
        lifecycle="FAILED_SETUP",
    )
    assert v.qualified is False


def test_failed_setup_rearms_on_reacceleration():
    state = create_replay_state("DAIC", DATE)
    for i, price in enumerate([5.37, 5.35, 5.42, 5.44, 5.45]):
        snap = _snap(
            timestamp=f"2026-08-27T04:0{i+2}:00-04:00",
            price=price,
            change_pct=4.0,
            volume_acceleration_1m=0.5 if i < 3 else 2.8,
            failed_setup=i >= 2,
        )
        lifecycle, _ = evaluate_stage_transition(state, snap)
        state.append(snap)
        state.current_stage = lifecycle
    surge = _snap(price=5.47, change_pct=6.2, volume_acceleration_1m=2.72, failed_setup=True)
    lifecycle, _ = evaluate_stage_transition(state, surge)
    assert lifecycle in ("REARMED", "EARLY_WATCH", "PRE_BREAKOUT")


def test_display_trusts_backend_confirmed_signal():
    sig = PreMoveSignal(
        signal_id="DAIC:x",
        symbol="DAIC",
        current_price=5.47,
        change_percent=6.2,
        pre_move_score=61,
        status="FAILED_SETUP",
        lifecycle="FAILED_SETUP",
        display_confirmed=True,
        display_type=DISPLAY_STRONG_BUY_WATCH,
        buy_pressure_score=12.0,
        confluence_count=6,
        confluence_factors=["volume_acceleration", "rvol_soft"],
        volume=PreMoveVolumeMetrics(volume_acceleration_1m=2.72, rvol=0.11),
        early_activity=PreMoveEarlyActivityMetrics(price_volume_response=1.0, micro_higher_lows=True),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=70, spread_percent=2.0),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(stage_lifecycle="REARMED"),
    )
    verdict = evaluate_premove_display(sig)
    assert verdict.show is True
    assert verdict.display_type == DISPLAY_STRONG_BUY_WATCH


def test_late_move_without_early_detection_stays_rejected():
    sig = PreMoveSignal(
        signal_id="LATE:x",
        symbol="LATE",
        current_price=8.0,
        change_percent=22.0,
        pre_move_score=40,
        status="TOO_LATE_TO_CHASE",
        lifecycle="TOO_LATE_TO_CHASE",
        volume=PreMoveVolumeMetrics(volume_acceleration_1m=0.3, rvol=1.5),
        early_activity=PreMoveEarlyActivityMetrics(),
        vwap=PreMoveVwapMetrics(),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=60, spread_percent=2.0),
        late_move=PreMoveLateMoveMetrics(is_too_late=True),
        stage_progression=PreMoveStageProgressionMetrics(stage_lifecycle="TOO_LATE_TO_CHASE"),
    )
    assert evaluate_premove_display(sig).show is False


def test_daic_replay_shows_strong_buy_before_peak():
    async def _run():
        client = PolygonClient()
        try:
            bars = filter_premarket_regular(await client.get_premarket_minute_bars("DAIC", session_date=DATE))
            prior = await client.get_premarket_minute_bars("DAIC", session_date="2026-08-26")
            pc = float((await client._request("/v2/aggs/ticker/DAIC/prev")).get("results", [{}])[0].get("c") or 0)
            tl = replay_session(bars, prior, await fetch_stock_news(client, "DAIC", 5), pc, symbol="DAIC", session_date=DATE)
            sm = summarize_replay("DAIC", DATE, bars, tl, pc)
            high = float(bars["high"].max())
            det = next(t for t in tl if t.get("display_confirmed"))
            assert det["display_type"] == DISPLAY_STRONG_BUY_WATCH
            assert det["price"] < high * 0.92
            too_late = sm.get("too_late_time")
            if too_late:
                assert det["time_et"] < too_late
            move_at_det = (det["price"] - pc) / pc * 100
            assert move_at_det < 15.0
        finally:
            await client.close()

    asyncio.run(_run())


def test_btct_replay_early_entry_and_display_parity():
    async def _run():
        client = PolygonClient()
        try:
            bars = filter_premarket_regular(await client.get_premarket_minute_bars("BTCT", session_date=DATE))
            prior = await client.get_premarket_minute_bars("BTCT", session_date="2026-08-26")
            pc = float((await client._request("/v2/aggs/ticker/BTCT/prev")).get("results", [{}])[0].get("c") or 0)
            tl = replay_session(bars, prior, await fetch_stock_news(client, "BTCT", 5), pc, symbol="BTCT", session_date=DATE)
            ee = next(t for t in tl if t.get("lifecycle") == "EARLY_ENTRY")
            disp = next((t for t in tl if t.get("display_confirmed")), None)
            assert ee is not None
            assert disp is not None
            assert disp["display_type"] == DISPLAY_JUMP_ALERT
            assert disp["time_et"] <= ee["time_et"]
        finally:
            await client.close()

    asyncio.run(_run())


def test_mss_negative_breakout_not_displayed():
    async def _run():
        client = PolygonClient()
        try:
            bars = filter_premarket_regular(await client.get_premarket_minute_bars("MSS", session_date=DATE))
            prior = await client.get_premarket_minute_bars("MSS", session_date="2026-08-26")
            pc = float((await client._request("/v2/aggs/ticker/MSS/prev")).get("results", [{}])[0].get("c") or 0)
            tl = replay_session(bars, prior, await fetch_stock_news(client, "MSS", 5), pc, symbol="MSS", session_date=DATE)
            assert not any(t.get("display_confirmed") for t in tl)
        finally:
            await client.close()

    asyncio.run(_run())
