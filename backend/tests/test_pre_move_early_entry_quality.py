"""Unit tests for EARLY_ENTRY Quality Gate."""

from __future__ import annotations

import pandas as pd
import pytest

from analysis.pre_move_early_entry_quality import (
    compute_liquidity_consistency,
    compute_rejection_score,
    compute_volume_efficiency,
    evaluate_early_entry_quality_gate,
)
from analysis.pre_move_stage_progression import build_snapshot, evaluate_early_entry_gate
from services.pre_move_stage_store import create_replay_state


def _bars(
    *,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
) -> pd.DataFrame:
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


def _snap(**kwargs) -> object:
    defaults = dict(
        timestamp="2026-08-24T08:05:00-04:00",
        price=10.0,
        change_pct=5.0,
        pre_move_score=60,
        volume_acceleration_1m=1.5,
        volume_acceleration_3m=1.4,
        volume_acceleration_slope=1.2,
        rvol=2.0,
        rvol_same_time=2.0,
        dollar_volume_growth=0.4,
        trade_velocity=80.0,
        trade_velocity_growth=0.25,
        early_activity_score=15.0,
        compression_score=0.55,
        range_compression_3m=0.78,
        micro_higher_lows=True,
        higher_lows_score=0.6,
        resistance_distance_pct=1.8,
        distance_to_breakout_pct=1.8,
        breakout_pressure=60.0,
        vwap_hold=True,
        vwap_reclaim=False,
        distance_from_vwap_pct=0.8,
        liquidity_score=55.0,
        spread_pct=1.2,
        price_volume_response=0.5,
        news_catalyst_score=0.0,
        risk_reward=2.2,
        trigger_price=10.18,
        late_guard=False,
        failed_setup=False,
        prior_peak_price=10.0,
        base_price=9.6,
        prior_lows=[9.85, 9.88, 9.92, 9.95],
    )
    defaults.update(kwargs)
    return build_snapshot(**defaults)


def test_rejection_wick_blocks_near_resistance():
    micro = {"upper_wick_ratio": 0.62, "close_position": 0.25, "body_pct": 0.5}
    score = compute_rejection_score(micro, near_resistance=True)
    assert score >= 58


def test_churn_volume_low_efficiency():
    bars = _bars(
        opens=[10.0, 10.0],
        highs=[10.02, 10.03],
        lows=[9.99, 9.99],
        closes=[10.0, 10.005],
        volumes=[1000, 2500],
    )
    eff = compute_volume_efficiency(bars)
    assert eff <= 15


def test_price_holding_mandatory_rejection():
    snap = _snap(prior_peak_price=10.5, price=10.0)
    snap.price_holding_score = 40.0
    bars = _bars(
        opens=[9.9, 9.95, 10.0],
        highs=[10.0, 10.05, 10.08],
        lows=[9.88, 9.92, 9.96],
        closes=[9.98, 10.02, 10.0],
        volumes=[800, 900, 1000],
    )
    m = evaluate_early_entry_quality_gate(
        snap, [], bars,
        stop_loss=9.7, tp1=10.5, trigger_price=10.18, persist_min=3,
    )
    assert not m.quality_gate_passed
    assert any("churn_volume" in b or "price_holding" in b for b in m.block_reasons)


def test_spread_widening_blocks():
    hist = [
        _snap(spread_pct=1.0, price=9.95),
        _snap(spread_pct=1.5, price=9.98),
        _snap(spread_pct=2.2, price=10.0),
    ]
    snap = _snap(spread_pct=4.5)
    bars = _bars(
        opens=[9.9, 9.95, 10.0],
        highs=[10.0, 10.05, 10.08],
        lows=[9.88, 9.92, 9.96],
        closes=[9.98, 10.02, 10.0],
        volumes=[800, 900, 1000],
    )
    m = evaluate_early_entry_quality_gate(
        snap, hist, bars,
        stop_loss=9.7, tp1=10.5, trigger_price=10.18, persist_min=3,
    )
    assert not m.quality_gate_passed
    assert any("spread" in b for b in m.block_reasons)


def test_liquidity_consistency_single_spike():
    bars = _bars(
        opens=[10.0, 10.0, 10.0, 10.0],
        highs=[10.02, 10.02, 10.02, 10.02],
        lows=[9.99, 9.99, 9.99, 9.99],
        closes=[10.0, 10.0, 10.0, 10.0],
        volumes=[200, 180, 210, 5000],
    )
    score = compute_liquidity_consistency(bars)
    assert score <= 35


def test_bad_rrr_rejection():
    snap = _snap(risk_reward=1.2)
    bars = _bars(
        opens=[9.9, 9.95, 10.0],
        highs=[10.0, 10.05, 10.08],
        lows=[9.88, 9.92, 9.96],
        closes=[9.98, 10.02, 10.0],
        volumes=[800, 900, 1000],
    )
    m = evaluate_early_entry_quality_gate(
        snap, [], bars,
        stop_loss=9.7, tp1=10.25, trigger_price=10.18, persist_min=3,
    )
    assert not m.quality_gate_passed
    assert any("rrr" in b for b in m.block_reasons)


def test_fake_breakout_high_failure_risk():
    hist = []
    for i, p in enumerate([10.0, 10.02, 10.01, 10.03, 10.02]):
        s = _snap(
            price=p,
            volume_acceleration_1m=1.6,
            spread_pct=1.0 + i * 0.3,
        )
        s.price_holding_score = 45.0
        hist.append(s)
    snap = _snap(
        price=10.02,
        volume_acceleration_1m=1.1,
        spread_pct=3.8,
    )
    snap.price_holding_score = 42.0
    bars = _bars(
        opens=[10.0, 10.02, 10.03, 10.04, 10.02],
        highs=[10.15, 10.16, 10.17, 10.18, 10.12],
        lows=[9.98, 10.0, 10.01, 10.02, 10.0],
        closes=[10.02, 10.03, 10.04, 10.05, 10.02],
        volumes=[900, 1100, 1200, 1300, 1400],
    )
    m = evaluate_early_entry_quality_gate(
        snap, hist, bars,
        stop_loss=9.75, tp1=10.5, trigger_price=10.18, persist_min=3,
    )
    assert not m.quality_gate_passed


def test_successful_quality_gate_passes():
    snap = _snap(liquidity_score=55.0, risk_reward=2.4, news_catalyst_score=50.0)
    snap.price_holding_score = 72.0
    bars = _bars(
        opens=[9.9, 9.95, 10.0],
        highs=[10.0, 10.10, 10.18],
        lows=[9.88, 9.93, 9.98],
        closes=[9.95, 10.04, 10.15],
        volumes=[800, 850, 900],
    )
    m = evaluate_early_entry_quality_gate(
        snap, [snap], bars,
        stop_loss=9.75, tp1=10.6, trigger_price=10.18, persist_min=3,
        has_fresh_news=True, news_catalyst_score=50.0,
    )
    assert m.quality_gate_passed
    assert m.confluence_quality_score >= 56


def test_full_gate_blocks_weak_quality_without_timing_delay():
    """Timing gate may pass confluence, but quality gate should reject weak holding."""
    state = create_replay_state("TEST", "2026-08-24")
    state.current_stage = "PRE_BREAKOUT"
    state.base_price = 9.6
    state.pb_consecutive_windows = 3

    history = []
    for i in range(3):
        s = _snap(
            price=10.0 + i * 0.01,
            resistance_distance_pct=1.5 - i * 0.2,
            distance_to_breakout_pct=1.5 - i * 0.2,
            timestamp=f"2026-08-24T08:0{i}:00-04:00",
        )
        s.price_holding_score = 48.0
        history.append(s)
        state.append(s)

    snap = _snap(price=10.03, resistance_distance_pct=1.2, distance_to_breakout_pct=1.2)
    snap.price_holding_score = 48.0
    bars = _bars(
        opens=[9.95, 10.0, 10.02],
        highs=[10.05, 10.08, 10.12],
        lows=[9.93, 9.98, 10.0],
        closes=[10.0, 10.03, 10.02],
        volumes=[900, 1200, 1800],
    )

    ok, _, _, blocks, quality, _ = evaluate_early_entry_gate(
        state, snap, history,
        effective_score=70.0, persist_min=3, trend=2.0, regress=[],
        bars=bars, stop_loss=9.75, tp1=10.6,
    )
    assert not ok
    assert quality is not None
    assert not quality.quality_gate_passed
    assert any("price_holding" in b or "vol_efficiency" in b for b in blocks)
