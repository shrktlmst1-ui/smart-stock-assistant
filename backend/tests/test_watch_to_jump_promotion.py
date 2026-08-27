"""STRONG_BUY_WATCH → JUMP_QUALIFIED → JUMP_ALERT promotion tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.early_upward_surge import (
    DISPLAY_JUMP_ALERT,
    DISPLAY_STRONG_BUY_WATCH,
    evaluate_fast_upward_jump,
    evaluate_watch_to_jump_confirmation,
)
from analysis.pre_move_stage_progression import build_snapshot
from analysis.upward_jump_gate import evaluate_upward_jump
from models.pre_move import (
    PreMoveBreakoutMetrics,
    PreMoveCompressionMetrics,
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from services.pre_move_stage_store import create_replay_state, reset_store


def _strong_snap(**kw):
    defaults = dict(
        timestamp="2026-08-27T09:20:00-04:00",
        price=9.05,
        change_pct=7.5,
        pre_move_score=64,
        volume_acceleration_1m=2.4,
        volume_acceleration_3m=1.8,
        volume_acceleration_slope=1.3,
        rvol=1.5,
        rvol_same_time=2.1,
        dollar_volume_growth=0.35,
        trade_velocity=12.0,
        trade_velocity_growth=0.25,
        early_activity_score=15.0,
        compression_score=0.5,
        range_compression_3m=0.7,
        micro_higher_lows=True,
        higher_lows_score=0.6,
        resistance_distance_pct=0.5,
        distance_to_breakout_pct=0.5,
        breakout_pressure=48.0,
        vwap_hold=True,
        vwap_reclaim=False,
        distance_from_vwap_pct=0.5,
        liquidity_score=72.0,
        spread_pct=1.5,
        price_volume_response=0.8,
        news_catalyst_score=0.0,
        risk_reward=1.5,
        trigger_price=9.0,
        late_guard=False,
        failed_setup=False,
    )
    defaults.update(kw)
    return build_snapshot(**defaults)


@pytest.fixture(autouse=True)
def _clean():
    reset_store()
    yield
    reset_store()


def test_strong_buy_promotes_with_confirmation_evidence():
    snap = _strong_snap()
    promo = evaluate_watch_to_jump_confirmation(snap, lifecycle="PRE_BREAKOUT")
    assert promo.promote is True
    assert promo.evidence_count >= 4


def test_faded_momentum_does_not_promote():
    snap = _strong_snap(
        volume_acceleration_1m=0.3,
        volume_acceleration_3m=0.2,
        volume_acceleration_slope=0.8,
        price_volume_response=0.05,
        trade_velocity_growth=-0.3,
        change_pct=0.5,
        breakout_pressure=10.0,
        micro_higher_lows=False,
        vwap_hold=False,
        vwap_reclaim=False,
        trigger_price=12.0,
        rvol=0.2,
        rvol_same_time=0.2,
    )
    promo = evaluate_watch_to_jump_confirmation(snap, lifecycle="PRE_BREAKOUT")
    assert promo.promote is False
    assert promo.reject_reason in (
        "momentum_faded",
        "insufficient_confirmation_0<4",
        "insufficient_confirmation_1<4",
        "insufficient_confirmation_2<4",
        "insufficient_confirmation_3<4",
        "momentum_lost",
    )


def test_too_late_blocks_promotion():
    snap = _strong_snap(late_guard=True)
    promo = evaluate_watch_to_jump_confirmation(snap, lifecycle="PRE_BREAKOUT")
    assert promo.promote is False
    assert promo.reject_reason == "too_late_to_chase"


def _pm_signal(**kw) -> PreMoveSignal:
    snap = _strong_snap()
    base = PreMoveSignal(
        signal_id="SKHL:2026-08-27",
        symbol="SKHL",
        current_price=snap.price,
        change_percent=snap.change_pct,
        display_confirmed=True,
        display_type=DISPLAY_STRONG_BUY_WATCH,
        fast_upward_path=True,
        trigger_price=snap.trigger_price,
        volume=PreMoveVolumeMetrics(
            volume_acceleration_1m=snap.volume_acceleration_1m,
            volume_acceleration=snap.volume_acceleration_1m,
            rvol=snap.rvol,
            rvol_same_time=snap.rvol_same_time,
        ),
        early_activity=PreMoveEarlyActivityMetrics(
            micro_higher_lows=True,
            breakout_pressure_score=snap.breakout_pressure,
            trade_velocity=snap.trade_velocity,
        ),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        compression=PreMoveCompressionMetrics(higher_lows_score=0.6),
        breakout=PreMoveBreakoutMetrics(distance_to_breakout_pct=0.5),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=snap.liquidity_score, spread_pct=snap.spread_pct),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(stage_lifecycle="PRE_BREAKOUT"),
    )
    for k, v in kw.items():
        setattr(base, k, v)
    return base


def test_full_path_strong_buy_to_jump_gate():
    sig = _pm_signal()
    promo = evaluate_watch_to_jump_confirmation(_strong_snap(), lifecycle="PRE_BREAKOUT")
    assert promo.promote
    up_ok, _ = evaluate_upward_jump(sig)
    assert up_ok is True


def test_stage_state_preserved_across_locked_watch():
    state = create_replay_state("PAT", "2026-08-27")
    state.fast_watch_locked = True
    state.fast_watch_at = "2026-08-27T09:10:00Z"
    state.fast_watch_price = 5.0
    state.first_detected_at = "2026-08-27T09:08:00Z"
    state.first_detected_price = 4.8
    snap = _strong_snap(price=9.1, change_pct=8.0)
    verdict = evaluate_fast_upward_jump(
        snap, lifecycle="PRE_BREAKOUT", early_watch_locked=True,
    )
    assert verdict.qualified
    assert verdict.display_type == DISPLAY_STRONG_BUY_WATCH
    assert state.first_detected_at == "2026-08-27T09:08:00Z"
    assert state.first_detected_price == 4.8
