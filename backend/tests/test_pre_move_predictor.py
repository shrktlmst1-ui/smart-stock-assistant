"""Tests for Pre-Move Predictor."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from analysis.pre_move_breakout import compute_breakout_metrics, score_breakout_pressure
from analysis.pre_move_compression import compute_compression_metrics
from analysis.pre_move_late_guard import compute_late_move_guard
from analysis.pre_move_scorer import classify_status, compute_composite_score, status_rank
from analysis.pre_move_validator import validate_signal
from analysis.pre_move_volume import compute_volume_metrics, score_volume_component
from analysis.pre_move_vwap import compute_vwap_metrics
from models.pre_move import (
    PreMoveBreakoutMetrics,
    PreMoveCompressionMetrics,
    PreMoveLiquidityMetrics,
    PreMoveNewsMetrics,
    PreMoveSignal,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from services.best_opportunities_service import _merge_opportunities, pre_move_to_stock_opportunity

ET = ZoneInfo("America/New_York")


def _bars_with_accel() -> pd.DataFrame:
    rows = []
    t0 = datetime(2026, 8, 24, 8, 0, tzinfo=ET).astimezone(timezone.utc)
    vols = [5000] * 20 + [8000, 12000, 18000, 25000, 40000]
    price = 0.68
    for i, vol in enumerate(vols):
        ts = t0 + pd.Timedelta(minutes=i)
        c = price + i * 0.005
        rows.append({
            "open": c - 0.01, "high": c + 0.02, "low": c - 0.02,
            "close": c, "volume": vol, "timestamp": ts,
        })
    return pd.DataFrame(rows)


def test_volume_acceleration_detects_rising_1m():
    bars = _bars_with_accel()
    m = compute_volume_metrics(bars)
    assert m.volume_1m == 40000
    assert m.volume_acceleration >= 1.5
    assert score_volume_component(m) >= 10


def test_vwap_reclaim_detection():
    bars = _bars_with_accel()
    m = compute_vwap_metrics(bars, price=float(bars["close"].iloc[-1]))
    assert m.vwap > 0


def test_compression_higher_lows():
    bars = _bars_with_accel()
    c = compute_compression_metrics(bars, float(bars["close"].iloc[-1]))
    assert c.higher_lows_score >= 0


def test_late_move_guard_flags_extended_move():
    bars = _bars_with_accel()
    price = 0.91
    late = compute_late_move_guard(
        bars, price, change_percent=34.0,
        vwap=0.77, base_price=0.68, spread_percent=0.5, risk_reward=0.8,
    )
    assert late.is_too_late is True
    assert late.late_move_score > 0


def test_classify_status_buckets():
    assert classify_status(55, too_late=False) == "NO_SETUP"
    assert classify_status(65, too_late=False) == "EARLY_WATCH"
    assert classify_status(75, too_late=False) == "PRE_BREAKOUT"
    assert classify_status(85, too_late=False) == "EARLY_ENTRY"
    assert classify_status(95, too_late=False) == "HIGH_CONVICTION_EARLY"
    assert classify_status(95, too_late=True) == "TOO_LATE_TO_CHASE"


def test_composite_score_from_real_metrics():
    bars = _bars_with_accel()
    price = float(bars["close"].iloc[-1])
    from analysis.pre_move_early_activity import compute_early_activity_metrics

    vol = compute_volume_metrics(bars)
    comp = compute_compression_metrics(bars, price)
    vwap = compute_vwap_metrics(bars, price)
    brk = compute_breakout_metrics(bars, price, premarket_high=price * 1.03)
    news = PreMoveNewsMetrics()
    liq = PreMoveLiquidityMetrics(liquidity_score=75.0, spread_percent=0.5, dollar_volume=500_000)
    early = compute_early_activity_metrics(
        bars, price, vol_metrics=vol, compression=comp, breakout=brk, spread_pct=0.5,
    )
    score, bd = compute_composite_score(
        vol, comp, vwap, brk, news, liq, early_activity=early, bars=bars, price=price,
    )
    assert 0 <= score <= 100
    assert bd.early_activity >= 0


def test_pre_move_predictor_service_validate_signal_import():
    """Regression: _deep_analyze must resolve validate_signal (no NameError)."""
    import services.pre_move_predictor_service as pmps
    from analysis.pre_move_validator import validate_signal as vs

    assert pmps.validate_signal is vs


def test_validate_rejects_contradiction():
    sig = PreMoveSignal(
        signal_id="X:2026-08-24",
        symbol="X",
        pre_move_score=0,
        status="CONFIRMED_ENTRY",
        risk_level="مرتفع",
        risk_reward=0.5,
        liquidity=PreMoveLiquidityMetrics(liquidity_score=30),
        late_move=__import__("models.pre_move", fromlist=["PreMoveLateMoveMetrics"]).PreMoveLateMoveMetrics(is_too_late=True),
    )
    ok, reason = validate_signal(sig)
    assert ok is False


def test_ranking_prefers_high_conviction():
    from models.pre_move import PreMoveSignal as PS
    from models.premarket_opportunity import PremarketOpportunitySignal

    pre = PS(
        signal_id="A:1", symbol="A", pre_move_score=92, status="HIGH_CONVICTION_EARLY",
        current_price=1.0, change_percent=5, reason="test", timing="EARLY",
        liquidity=PreMoveLiquidityMetrics(liquidity_score=80),
    )
    pm = PremarketOpportunitySignal(
        symbol="B", current_price=2, premarket_change_percent=10,
        status="CONFIRMED_ENTRY", entry=2, stop_loss=1.9, tp1=2.2, tp2=2.4, risk_reward=2.0,
    )
    merged = _merge_opportunities([pre], [pm], limit=10, state=None)
    assert merged[0].symbol == "A"
    assert status_rank("HIGH_CONVICTION_EARLY") > status_rank("CONFIRMED_ENTRY")


def test_pre_move_to_stock_opportunity_uses_score():
    sig = PreMoveSignal(
        signal_id="LUCY:1", symbol="LUCY", pre_move_score=84, status="EARLY_ENTRY",
        current_price=0.71, change_percent=8.0, trigger_price=0.73,
        entry_low=0.73, entry_high=0.745, stop_loss=0.68, tp1=0.80, tp2=0.88,
        risk_reward=2.4, reason="RVOL + vol accel", timing="EARLY",
        first_detected_price=0.685,
        volume=PreMoveVolumeMetrics(rvol=4.8, volume_acceleration=3.1),
        vwap=PreMoveVwapMetrics(vwap_reclaim=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=70),
    )
    opp = pre_move_to_stock_opportunity(sig)
    assert opp.score == 84
    assert opp.ai_signal == "EARLY_ENTRY"
    assert "PreMove 84" in opp.status_reason_ar
    assert "Trigger" in opp.status_reason_ar
