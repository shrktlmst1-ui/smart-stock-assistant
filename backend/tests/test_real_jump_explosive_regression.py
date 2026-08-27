"""Explosive-move regression for REAL_JUMP_ALERT — behavioral patterns, not tickers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from analysis.early_upward_surge import evaluate_real_jump_alert
from config import STAGE_EE_MAX_EXTENSION_PCT
from services.real_jump_alert_layer import real_jump_wave_tracker

ET = ZoneInfo("America/New_York")


@dataclass
class ExplosiveScanResult:
    first_detected_price: float | None
    first_detected_pct: float | None
    peak_after_detection: float
    lead_time_bars: int | None
    false_positives: int = 0


def _bars_from_closes(closes: list[float], volumes: list[int]) -> pd.DataFrame:
    rows = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        rows.append({
            "timestamp": pd.Timestamp(f"2026-08-27 04:{i+2:02d}:00", tz=ET),
            "open": c * 0.998,
            "high": c * 1.012,
            "low": c * 0.995,
            "close": c,
            "volume": v,
        })
    return pd.DataFrame(rows)


def _eval_bar(
    window: pd.DataFrame,
    *,
    price: float,
    prev_close: float,
    bar_idx: int,
    volumes: list[int],
) -> "RealPriceJumpVerdict":
    from analysis.early_upward_surge import RealPriceJumpVerdict  # noqa: F401

    change_pct = (price - prev_close) / prev_close * 100
    prev_vol = volumes[max(0, bar_idx - 1)]
    vol_ratio = volumes[bar_idx] / max(prev_vol, 1)
    wave = real_jump_wave_tracker.update("EXP", current_price=price, bars=window)
    return evaluate_real_jump_alert(
        current_price=price,
        change_pct=change_pct,
        price_volume_response=min(0.25 + wave.current_move_pct * 0.035, 0.92),
        micro_higher_lows=bar_idx >= 4,
        vwap_hold=bar_idx >= 5,
        vwap_reclaim=bar_idx >= 6,
        breakout_pressure=28.0 + wave.current_move_pct * 2.5,
        resistance_distance_pct=max(0.4, 4.0 - wave.current_move_pct * 0.25),
        trigger_price=prev_close * 1.03,
        movement_start_price=wave.move_start_price or prev_close,
        volume_acceleration_1m=min(vol_ratio * 1.35, 4.5),
        volume_acceleration_slope=1.06 + bar_idx * 0.015,
        rvol=1.0 + bar_idx * 0.12,
        rvol_same_time=1.3 + bar_idx * 0.18,
        trade_velocity_growth=0.08 + bar_idx * 0.025,
        trade_velocity=4.0 + bar_idx * 1.5,
        dollar_volume_growth=0.12 + bar_idx * 0.04,
        liquidity_score=68.0,
        spread_pct=1.6,
        persistence_minutes=max(0, bar_idx - 3),
        move_from_base_pct=wave.current_move_pct,
        range_compression_3m=0.58 if bar_idx < 9 else 0.25,
        bars=window,
        wave=wave,
    )


def scan_explosive_pattern(
    closes: list[float],
    volumes: list[int],
    *,
    prev_close: float,
    expect_detection: bool = True,
) -> ExplosiveScanResult:
    real_jump_wave_tracker.reset()
    bars = _bars_from_closes(closes, volumes)
    peak = max(closes)
    first_price: float | None = None
    first_pct: float | None = None
    lead: int | None = None
    false_positives = 0

    for i in range(3, len(closes)):
        window = bars.iloc[: i + 1]
        verdict = _eval_bar(
            window, price=closes[i], prev_close=prev_close, bar_idx=i, volumes=volumes,
        )
        if verdict.confirmed:
            if first_price is None:
                first_price = closes[i]
                first_pct = (closes[i] - prev_close) / prev_close * 100
                lead = len(closes) - 1 - i
            elif not expect_detection:
                false_positives += 1

    return ExplosiveScanResult(
        first_detected_price=first_price,
        first_detected_pct=first_pct,
        peak_after_detection=peak,
        lead_time_bars=lead,
        false_positives=false_positives,
    )


def test_explosive_pattern_detected_before_major_extension():
    prev = 2.0
    base = [2.00, 2.01, 2.02, 2.01, 2.02, 2.03]
    blast = [2.07, 2.14, 2.26, 2.42, 2.62, 3.08, 3.75]
    closes = base + blast
    vols = [700, 750, 800, 780, 820, 850, 2500, 5500, 11000, 18000, 32000, 48000, 52000]
    result = scan_explosive_pattern(closes, vols, prev_close=prev)

    assert result.first_detected_price is not None, "expected early REAL_JUMP_ALERT"
    assert result.first_detected_pct is not None
    assert result.first_detected_pct < 35.0, "detect before bulk of move"
    assert result.first_detected_price < result.peak_after_detection * 0.75
    assert result.lead_time_bars is not None and result.lead_time_bars >= 2
    peak_pct = (result.peak_after_detection - prev) / prev * 100
    assert peak_pct >= 70.0


def test_small_move_three_to_ten_pct_no_real_jump():
    prev = 3.0
    closes = [3.00, 3.03, 3.06, 3.08, 3.10, 3.12]
    vols = [1200, 1300, 1250, 1280, 1310, 1290]
    result = scan_explosive_pattern(closes, vols, prev_close=prev, expect_detection=False)
    assert result.first_detected_price is None
    assert result.false_positives == 0


def test_volume_only_without_price_expansion_rejected():
    prev = 4.0
    closes = [4.00, 4.01, 4.00, 4.01, 4.00, 4.02]
    vols = [2000, 8000, 12000, 15000, 18000, 22000]
    result = scan_explosive_pattern(closes, vols, prev_close=prev, expect_detection=False)
    assert result.first_detected_price is None


def test_too_late_extension_rejected():
    from analysis.early_upward_surge import RealJumpWaveSnapshot

    v = evaluate_real_jump_alert(
        current_price=4.8,
        change_pct=5.0,
        price_volume_response=0.6,
        micro_higher_lows=True,
        volume_acceleration_1m=3.0,
        volume_acceleration_slope=1.2,
        rvol_same_time=2.5,
        trade_velocity_growth=0.2,
        trade_velocity=10.0,
        dollar_volume_growth=0.4,
        liquidity_score=70.0,
        spread_pct=1.5,
        persistence_minutes=4,
        move_from_base_pct=16.0,
        range_compression_3m=0.3,
        late_guard=True,
        wave=RealJumpWaveSnapshot(
            move_start_price=4.0,
            current_move_pct=STAGE_EE_MAX_EXTENSION_PCT + 2,
            price_acceleration_1m=0.15,
            price_acceleration_3m=0.3,
            price_acceleration_5m=0.35,
            wave_active=True,
        ),
    )
    assert v.confirmed is False
    assert v.reject_reason == "too_late_to_chase"


def test_usde_style_wide_spread_rejected():
    v = evaluate_real_jump_alert(
        current_price=3.8,
        change_pct=12.0,
        price_volume_response=0.5,
        micro_higher_lows=True,
        volume_acceleration_1m=3.0,
        volume_acceleration_slope=1.2,
        rvol_same_time=5.0,
        trade_velocity_growth=0.25,
        trade_velocity=8.0,
        dollar_volume_growth=0.3,
        liquidity_score=25.0,
        spread_pct=8.5,
        persistence_minutes=3,
        move_from_base_pct=12.0,
        range_compression_3m=0.5,
    )
    assert v.confirmed is False


def _eval_bar_weak(
    window: pd.DataFrame,
    *,
    price: float,
    prev_close: float,
    bar_idx: int,
    volumes: list[int],
):
    change_pct = (price - prev_close) / prev_close * 100
    prev_vol = volumes[max(0, bar_idx - 1)]
    vol_ratio = volumes[bar_idx] / max(prev_vol, 1)
    wave = real_jump_wave_tracker.update("NEG", current_price=price, bars=window)
    return evaluate_real_jump_alert(
        current_price=price,
        change_pct=change_pct,
        price_volume_response=0.12,
        micro_higher_lows=False,
        volume_acceleration_1m=vol_ratio,
        volume_acceleration_slope=1.02,
        rvol=0.9,
        rvol_same_time=0.85,
        trade_velocity_growth=0.03,
        trade_velocity=2.0,
        dollar_volume_growth=0.05,
        liquidity_score=60.0,
        spread_pct=2.0,
        persistence_minutes=0,
        move_from_base_pct=wave.current_move_pct,
        range_compression_3m=0.1,
        bars=window,
        wave=wave,
    )


def scan_negative_pattern(
    closes: list[float],
    volumes: list[int],
    *,
    prev_close: float,
) -> ExplosiveScanResult:
    real_jump_wave_tracker.reset()
    bars = _bars_from_closes(closes, volumes)
    peak = max(closes)
    for i in range(3, len(closes)):
        window = bars.iloc[: i + 1]
        verdict = _eval_bar_weak(
            window, price=closes[i], prev_close=prev_close, bar_idx=i, volumes=volumes,
        )
        if verdict.confirmed:
            return ExplosiveScanResult(
                first_detected_price=closes[i],
                first_detected_pct=(closes[i] - prev_close) / prev_close * 100,
                peak_after_detection=peak,
                lead_time_bars=0,
                false_positives=1,
            )
    return ExplosiveScanResult(None, None, peak, None, 0)


def test_false_positive_count_on_negative_patterns():
    negatives = [
        ([2.0, 2.05, 2.08, 2.10], [1000, 1100, 1050, 1080]),
        ([5.0, 5.02, 5.01, 5.03], [5000, 12000, 15000, 18000]),
        ([3.0, 2.95, 2.98, 3.02, 3.01], [900, 850, 880, 920, 910]),
    ]
    total_fp = 0
    for closes, vols in negatives:
        r = scan_negative_pattern(closes, vols, prev_close=closes[0])
        total_fp += r.false_positives
        assert r.first_detected_price is None
    assert total_fp == 0
