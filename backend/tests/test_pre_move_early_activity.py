"""Tests for Early Activity Engine."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from analysis.pre_move_breakout import compute_breakout_metrics
from analysis.pre_move_compression import compute_compression_metrics
from analysis.pre_move_early_activity import (
    compute_early_activity_metrics,
    compute_enhanced_volume_acceleration,
    passes_early_activity_fast_gate,
)
from analysis.pre_move_volume import compute_volume_metrics

ET = ZoneInfo("America/New_York")


def _xpon_style_bars() -> pd.DataFrame:
    """Simulate XPON 08:25-08:28 pattern: low vol then acceleration near $3.5."""
    rows = []
    t0 = datetime(2026, 8, 24, 5, 17, tzinfo=ET).astimezone(timezone.utc)
    specs = [
        (3.32, 587),
        (3.315, 143),
        (3.934, 13435),
        (3.55, 37310),
        (3.692, 36706),
    ]
    for i, (close, vol) in enumerate(specs):
        ts = t0 + pd.Timedelta(minutes=i * 44 if i > 1 else i * 44)
        if i == 2:
            ts = datetime(2026, 8, 24, 8, 25, tzinfo=ET).astimezone(timezone.utc)
        elif i == 3:
            ts = datetime(2026, 8, 24, 8, 26, tzinfo=ET).astimezone(timezone.utc)
        elif i == 4:
            ts = datetime(2026, 8, 24, 8, 27, tzinfo=ET).astimezone(timezone.utc)
        rows.append({
            "open": close - 0.05,
            "high": close + 0.1,
            "low": close - 0.08,
            "close": close,
            "volume": vol,
            "timestamp": ts,
        })
    return pd.DataFrame(rows)


def test_volume_acceleration_detects_small_base_ramp():
    bars = _xpon_style_bars()
    accel = compute_enhanced_volume_acceleration(bars)
    assert accel["volume_acceleration_slope"] >= 1.1


def test_early_activity_scores_acceleration_before_absolute_volume():
    bars = _xpon_style_bars()
    price = float(bars["close"].iloc[-1])
    vol = compute_volume_metrics(bars)
    comp = compute_compression_metrics(bars, price)
    brk = compute_breakout_metrics(bars, price)
    early = compute_early_activity_metrics(
        bars, price, vol_metrics=vol, compression=comp, breakout=brk, spread_pct=1.0,
    )
    assert early.early_activity_score >= 8.0
    assert early.activity_deviation_score > 0


def test_fast_gate_passes_volume_accel_pattern():
    bars = _xpon_style_bars()
    price = float(bars["close"].iloc[-1])
    vol = compute_volume_metrics(bars)
    comp = compute_compression_metrics(bars, price)
    brk = compute_breakout_metrics(bars, price)
    early = compute_early_activity_metrics(
        bars, price, vol_metrics=vol, compression=comp, breakout=brk,
    )
    assert passes_early_activity_fast_gate(early, vol_metrics=vol) is True
