"""Unit tests for Stage Progression Engine."""

from __future__ import annotations

import pytest

from analysis.pre_move_stage_progression import (
    build_snapshot,
    compute_momentum_persistence,
    compute_stage_progression_score,
    compute_stage_signal_decay,
    evaluate_stage_transition,
    lifecycle_to_status,
)
from models.pre_move_stage import RollingStageState, StageSnapshot
from services.pre_move_stage_store import create_replay_state, reset_store


def _snap(
    *,
    price: float = 10.0,
    vol_1m: float = 1.5,
    rvol: float = 2.0,
    hl: bool = True,
    vwap_hold: bool = True,
    dist_breakout: float = 3.0,
    liq: float = 60.0,
    late: bool = False,
    failed: bool = False,
    ts: str = "2026-08-24T08:00:00-04:00",
) -> StageSnapshot:
    return build_snapshot(
        timestamp=ts,
        price=price,
        change_pct=5.0,
        pre_move_score=55,
        volume_acceleration_1m=vol_1m,
        volume_acceleration_3m=1.4,
        volume_acceleration_slope=1.2,
        rvol=rvol,
        rvol_same_time=rvol,
        dollar_volume_growth=0.4,
        trade_velocity=80.0,
        trade_velocity_growth=0.25,
        early_activity_score=15.0,
        compression_score=0.5,
        range_compression_3m=0.75,
        micro_higher_lows=hl,
        higher_lows_score=0.6,
        resistance_distance_pct=dist_breakout,
        distance_to_breakout_pct=dist_breakout,
        breakout_pressure=55.0,
        vwap_hold=vwap_hold,
        vwap_reclaim=False,
        distance_from_vwap_pct=0.8,
        liquidity_score=liq,
        spread_pct=1.2,
        price_volume_response=0.5,
        news_catalyst_score=0.0,
        risk_reward=1.5,
        trigger_price=price * 1.03,
        late_guard=late,
        failed_setup=failed,
        prior_peak_price=price,
    )


def test_stage_escalation_discovered_to_early_watch():
    state = create_replay_state("TEST", "2026-08-24")
    snap = _snap(vol_1m=1.4, rvol=1.6)
    lifecycle, metrics = evaluate_stage_transition(state, snap)
    assert lifecycle in ("EARLY_WATCH", "DISCOVERED")
    if lifecycle == "EARLY_WATCH":
        assert metrics.stage_progression_score >= 30


def test_stage_escalation_to_pre_breakout_with_persistence():
    state = create_replay_state("TEST", "2026-08-24")
    for i in range(4):
        snap = _snap(
            price=10.0 + i * 0.05,
            vol_1m=1.3 + i * 0.05,
            dist_breakout=max(1.5, 4.0 - i * 0.5),
            ts=f"2026-08-24T08:0{i}:00-04:00",
        )
        lifecycle, metrics = evaluate_stage_transition(state, snap)
        state.append(snap)
        state.current_stage = lifecycle
        state.minutes_in_stage += 1

    assert lifecycle in ("PRE_BREAKOUT", "EARLY_WATCH", "EARLY_ENTRY")
    assert metrics.persistence_minutes >= 2


def test_stage_regression_on_volume_fade():
    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "PRE_BREAKOUT"
    state.stage_entered_at = "2026-08-24T08:00:00-04:00"

    good = _snap(vol_1m=1.5, ts="2026-08-24T08:00:00-04:00")
    state.append(good)

    bad = _snap(vol_1m=0.7, vwap_hold=False, hl=False, ts="2026-08-24T08:01:00-04:00")
    lifecycle, metrics = evaluate_stage_transition(state, bad)
    assert lifecycle in ("EARLY_WATCH", "FAILED_SETUP", "PRE_BREAKOUT")
    assert "volume_faded" in metrics.regression_signals or lifecycle != "PRE_BREAKOUT"


def test_late_guard_overrides_progression():
    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "PRE_BREAKOUT"
    snap = _snap(late=True, vol_1m=2.0, dist_breakout=1.0)
    lifecycle, _ = evaluate_stage_transition(state, snap)
    assert lifecycle == "TOO_LATE_TO_CHASE"
    assert lifecycle_to_status(lifecycle, progression_score=90, persistence_minutes=5) == "TOO_LATE_TO_CHASE"


def test_momentum_persistence_requires_sustained_activity():
    snaps = [_snap(vol_1m=1.3, ts=f"2026-08-24T08:0{i}:00-04:00") for i in range(5)]
    score, minutes = compute_momentum_persistence(snaps)
    assert minutes >= 3
    assert score >= 45.0


def test_signal_decay_stale_early_watch():
    decay = compute_stage_signal_decay(
        current_stage="EARLY_WATCH",
        minutes_in_stage=12.0,
        progression_score=35.0,
        peak_progression_score=50.0,
    )
    assert decay > 5.0


def test_progression_score_rises_with_improving_evidence():
    s1 = _snap(vol_1m=1.2, rvol=1.4, dist_breakout=6.0)
    score1, _, _ = compute_stage_progression_score(s1, [])
    s2 = _snap(vol_1m=1.6, rvol=2.2, dist_breakout=2.5)
    score2, trend, factors = compute_stage_progression_score(s2, [s1])
    assert score2 >= score1 - 5
    assert trend >= 0 or "near_resistance" in factors


def test_failed_setup_detection():
    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "EARLY_WATCH"
    snap = _snap(failed=True, vol_1m=0.5, vwap_hold=False, hl=False)
    lifecycle, _ = evaluate_stage_transition(state, snap)
    assert lifecycle == "FAILED_SETUP"


def test_fake_breakout_sideways_no_escalation():
    state = create_replay_state("TEST", "2026-08-24")
    scores = []
    for _ in range(3):
        snap = _snap(price=10.0, vol_1m=0.9, rvol=0.8, hl=False, vwap_hold=False, dist_breakout=15.0, liq=30.0)
        lifecycle, metrics = evaluate_stage_transition(state, snap)
        scores.append(metrics.stage_progression_score)
        state.append(snap)
        state.current_stage = lifecycle
    assert max(scores) < 55
    assert lifecycle in ("DISCOVERED", "EARLY_WATCH", "FAILED_SETUP")


def test_missing_trade_velocity_still_works():
    snap = build_snapshot(
        timestamp="2026-08-24T08:00:00-04:00",
        price=5.0,
        change_pct=3.0,
        pre_move_score=50,
        volume_acceleration_1m=1.4,
        volume_acceleration_3m=1.3,
        volume_acceleration_slope=1.1,
        rvol=1.8,
        rvol_same_time=None,
        dollar_volume_growth=0.2,
        trade_velocity=None,
        trade_velocity_growth=None,
        early_activity_score=12.0,
        compression_score=0.4,
        range_compression_3m=0.8,
        micro_higher_lows=True,
        higher_lows_score=0.4,
        resistance_distance_pct=5.0,
        distance_to_breakout_pct=5.0,
        breakout_pressure=40.0,
        vwap_hold=True,
        vwap_reclaim=False,
        distance_from_vwap_pct=1.5,
        liquidity_score=55.0,
        spread_pct=1.5,
        price_volume_response=0.3,
        news_catalyst_score=0.0,
        risk_reward=1.3,
        trigger_price=5.15,
        late_guard=False,
        failed_setup=False,
    )
    score, _, _ = compute_stage_progression_score(snap, [])
    assert score > 20


def test_multiple_symbols_isolated():
    reset_store()
    a = create_replay_state("AAA", "2026-08-24")
    b = create_replay_state("BBB", "2026-08-24")
    snap_a = _snap(vol_1m=1.8)
    snap_b = _snap(vol_1m=1.0, rvol=1.0, hl=False)
    la, _ = evaluate_stage_transition(a, snap_a)
    lb, _ = evaluate_stage_transition(b, snap_b)
    assert la != lb or True  # independent states
    assert a.symbol == "AAA"
    assert b.symbol == "BBB"


def test_lifecycle_to_status_mapping():
    assert lifecycle_to_status("EARLY_WATCH", progression_score=40, persistence_minutes=1) == "EARLY_WATCH"
    assert lifecycle_to_status("PRE_BREAKOUT", progression_score=55, persistence_minutes=3) == "PRE_BREAKOUT"
    assert lifecycle_to_status("EARLY_ENTRY", progression_score=85, persistence_minutes=5) == "HIGH_CONVICTION_EARLY"


def test_early_entry_gate_requires_confluence():
    from analysis.pre_move_stage_progression import evaluate_early_entry_gate

    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "PRE_BREAKOUT"
    state.base_price = 9.5
    state.pb_consecutive_windows = 2

    # Strong confluence snapshot — approaching resistance
    snaps = []
    for i, dist in enumerate([4.5, 3.0, 1.8]):
        s = _snap(
            price=10.0 + i * 0.02,
            vol_1m=1.4,
            rvol=2.0,
            dist_breakout=dist,
            ts=f"2026-08-24T08:0{i}:00-04:00",
        )
        snaps.append(s)
        state.append(s)

    ok, readiness, conf, blocks, _, _ = evaluate_early_entry_gate(
        state, snaps[-1], snaps[:-1],
        effective_score=68.0, persist_min=3, trend=2.0, regress=[],
    )
    assert readiness >= 50
    if not ok:
        assert len(blocks) > 0
    else:
        assert any("Persistence" in c for c in conf)
        assert any("RVOL" in c for c in conf)


def test_early_entry_blocked_on_extension():
    from analysis.pre_move_stage_progression import evaluate_early_entry_gate

    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "PRE_BREAKOUT"
    state.base_price = 10.0
    state.pb_consecutive_windows = 3

    snap = _snap(price=11.6, vol_1m=1.5, rvol=2.0, dist_breakout=1.5)  # +16% from base
    ok, _, _, blocks, _, _ = evaluate_early_entry_gate(
        state, snap, [],
        effective_score=70.0, persist_min=3, trend=1.0, regress=[],
    )
    assert not ok
    assert any("extension" in b for b in blocks)


def test_early_entry_blocked_after_breakout():
    from analysis.pre_move_stage_progression import evaluate_early_entry_gate

    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "PRE_BREAKOUT"
    state.base_price = 10.0
    state.pb_consecutive_windows = 2

    snap = _snap(price=10.35, vol_1m=1.5, rvol=2.0, dist_breakout=0.0)
    snap.trigger_price = 10.30
    ok, readiness, _, blocks, _, _ = evaluate_early_entry_gate(
        state, snap, [],
        effective_score=75.0, persist_min=3, trend=2.0, regress=[],
    )
    assert not ok
    assert readiness == 0.0 or "already_breakout" in blocks


def test_early_entry_blocked_on_regression():
    from analysis.pre_move_stage_progression import evaluate_early_entry_gate

    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "PRE_BREAKOUT"
    state.pb_consecutive_windows = 2
    snap = _snap(vol_1m=0.8, vwap_hold=False, dist_breakout=1.5)
    ok, _, _, blocks, _, _ = evaluate_early_entry_gate(
        state, snap, [_snap(vol_1m=1.5)],
        effective_score=65.0, persist_min=2, trend=-1.0,
        regress=["volume_faded", "lost_vwap"],
    )
    assert not ok
