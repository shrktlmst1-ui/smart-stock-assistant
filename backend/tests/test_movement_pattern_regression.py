"""Movement-pattern regression — tests jump fingerprint, not ticker names."""

from __future__ import annotations

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from analysis.early_upward_surge import DISPLAY_JUMP_ALERT, DISPLAY_STRONG_BUY_WATCH, evaluate_fast_upward_jump
from analysis.pre_move_stage_progression import build_snapshot, evaluate_stage_transition
from scripts.premove_replay_lib import replay_session
from services.display_buy_pressure_filter import evaluate_premove_display
from services.pre_move_stage_store import create_replay_state, reset_store
from models.pre_move import (
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)

ET = ZoneInfo("America/New_York")


def _bars_from_closes(closes: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    vols = volumes or [1000 + i * 500 for i in range(len(closes))]
    rows = []
    for i, (c, v) in enumerate(zip(closes, vols)):
        rows.append({
            "timestamp": pd.Timestamp(f"2026-08-27 04:{i+2:02d}:00", tz=ET),
            "open": c * 0.998,
            "high": c * 1.008,
            "low": c * 0.995,
            "close": c,
            "volume": v,
        })
    return pd.DataFrame(rows)


def _replay_pattern(closes: list[float], volumes: list[int] | None = None, prev_close: float = 5.0):
    bars = _bars_from_closes(closes, volumes)
    tl = replay_session(bars, None, [], prev_close, symbol="PAT", session_date="2026-08-27")
    peak = max(closes)
    det = next((t for t in tl if t.get("display_confirmed")), None)
    return tl, det, peak


@pytest.fixture(autouse=True)
def _reset():
    reset_store()
    yield
    reset_store()


def test_pattern_early_surge_yields_watch_before_peak():
    closes = [5.05, 5.08, 5.12, 5.18, 5.28, 5.42, 5.55]
    vols = [2000, 2500, 4000, 8000, 15000, 22000, 18000]
    tl, det, peak = _replay_pattern(closes, vols, prev_close=5.0)
    assert det is not None, f"no display; last={tl[-1] if tl else None}"
    assert det["display_type"] == DISPLAY_STRONG_BUY_WATCH
    assert det["price"] < peak * 0.95


def test_pattern_reacceleration_after_failed_setup():
    state = create_replay_state("PAT", "2026-08-27")
    seq = [
        (5.05, 1.2, False),
        (5.02, 0.8, True),
        (5.04, 2.5, True),
        (5.15, 3.0, False),
    ]
    lifecycle = "DISCOVERED"
    for i, (price, vol_a, failed) in enumerate(seq):
        snap = build_snapshot(
            timestamp=f"2026-08-27T04:{i+2:02}:00-04:00",
            price=price, change_pct=(price - 5.0) / 5.0 * 100,
            pre_move_score=50, volume_acceleration_1m=vol_a,
            volume_acceleration_3m=vol_a, volume_acceleration_slope=1.1,
            rvol=0.3, rvol_same_time=0.3, dollar_volume_growth=0.3,
            trade_velocity=50.0, trade_velocity_growth=0.2,
            early_activity_score=15, compression_score=0.5, range_compression_3m=0.7,
            micro_higher_lows=True, higher_lows_score=0.6,
            resistance_distance_pct=1.0, distance_to_breakout_pct=1.0,
            breakout_pressure=40, vwap_hold=True, vwap_reclaim=False,
            distance_from_vwap_pct=0.5, liquidity_score=65, spread_pct=2.0,
            price_volume_response=0.5, news_catalyst_score=0, risk_reward=1.5,
            trigger_price=price * 1.02, late_guard=False, failed_setup=failed,
        )
        lifecycle, _ = evaluate_stage_transition(state, snap)
        state.append(snap)
        state.current_stage = lifecycle
    assert lifecycle in ("REARMED", "EARLY_WATCH", "PRE_BREAKOUT")


def test_pattern_volume_spike_without_price_accel_rejected():
    v = evaluate_fast_upward_jump(
        build_snapshot(
            timestamp="t", price=5.1, change_pct=2.0, pre_move_score=30,
            volume_acceleration_1m=4.0, volume_acceleration_3m=3.0,
            volume_acceleration_slope=1.2, rvol=0.5, rvol_same_time=0.5,
            dollar_volume_growth=0.1, trade_velocity=10.0, trade_velocity_growth=0.05,
            early_activity_score=5, compression_score=0, range_compression_3m=0,
            micro_higher_lows=False, higher_lows_score=0, resistance_distance_pct=5,
            distance_to_breakout_pct=5, breakout_pressure=10, vwap_hold=False,
            vwap_reclaim=False, distance_from_vwap_pct=3, liquidity_score=60,
            spread_pct=2, price_volume_response=0.05, news_catalyst_score=0,
            risk_reward=1, trigger_price=5.2, late_guard=False, failed_setup=False,
        ),
    )
    assert v.qualified is False


def test_pattern_late_extended_without_early_stays_too_late():
    snap = build_snapshot(
        timestamp="t", price=7.0, change_pct=28.0, pre_move_score=35,
        volume_acceleration_1m=0.4, volume_acceleration_3m=0.3,
        volume_acceleration_slope=0.9, rvol=1.5, rvol_same_time=1.5,
        dollar_volume_growth=0.1, trade_velocity=20.0, trade_velocity_growth=0.05,
        early_activity_score=5, compression_score=0, range_compression_3m=0,
        micro_higher_lows=False, higher_lows_score=0, resistance_distance_pct=8,
        distance_to_breakout_pct=8, breakout_pressure=10, vwap_hold=False,
        vwap_reclaim=False, distance_from_vwap_pct=5, liquidity_score=60,
        spread_pct=2, price_volume_response=0.2, news_catalyst_score=0,
        risk_reward=0.5, trigger_price=7.2, late_guard=True, failed_setup=False,
    )
    state = create_replay_state("PAT", "2026-08-27")
    lifecycle, _ = evaluate_stage_transition(state, snap)
    assert lifecycle == "TOO_LATE_TO_CHASE"


def test_display_confirmed_survives_scan_rejection_logic():
    sig = PreMoveSignal(
        signal_id="PAT:1", symbol="PAT", current_price=5.4, change_percent=8.0,
        pre_move_score=55, status="FAILED_SETUP", lifecycle="REARMED",
        display_confirmed=True, display_type=DISPLAY_STRONG_BUY_WATCH,
        buy_pressure_score=10, confluence_count=6,
        volume=PreMoveVolumeMetrics(volume_acceleration_1m=2.5, rvol=0.3),
        early_activity=PreMoveEarlyActivityMetrics(price_volume_response=0.8, micro_higher_lows=True),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=65, spread_percent=2.0),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(stage_lifecycle="REARMED"),
    )
    assert evaluate_premove_display(sig).show is True


def test_pattern_strong_continuation_gets_display():
    closes = [2.0, 2.02, 2.05, 2.12, 2.22, 2.35]
    vols = [5000, 6000, 9000, 14000, 20000, 25000]
    bars = _bars_from_closes(closes, vols)
    tl = replay_session(bars, None, [], 1.95, symbol="PAT", session_date="2026-08-27")
    watch = next((t for t in tl if t.get("display_confirmed")), None)
    assert watch is not None
