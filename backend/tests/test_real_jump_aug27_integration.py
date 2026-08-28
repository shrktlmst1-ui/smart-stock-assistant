"""REAL_JUMP Aug-27 replay integration — wave lifecycle vs entry status."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.early_upward_surge import (
    ENTRY_STATUS_TOO_LATE,
    WAVE_STATE_ACTIVE_UPWARD,
    WAVE_STATE_ENDED_LABEL,
    compute_real_jump_entry_status,
    evaluate_real_jump_live_exit,
)
from scripts.real_jump_aug27_replay import (
    grade_chow,
    grade_reject,
    replay_symbol,
)
from services.polygon_client import PolygonClient
from services.real_jump_alert_layer import RealJumpAlertRegistry, RealJumpWaveTracker, reset_real_jump_state


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset():
    reset_real_jump_state()
    yield
    reset_real_jump_state()


def test_entry_status_separate_from_wave_state():
    from analysis.early_upward_surge import RealJumpWaveSnapshot

    wave = RealJumpWaveSnapshot(wave_active=True, current_move_pct=20.0, wave_peak_price=0.5)
    status = compute_real_jump_entry_status(
        wave=wave, spread_pct=6.0, liquidity_score=65.0, is_alert_update=True,
    )
    assert status == ENTRY_STATUS_TOO_LATE or status == "BAD_SPREAD"
    end, reason, state = evaluate_real_jump_live_exit(
        wave=wave,
        current_price=0.48,
        price_volume_response=0.55,
        trade_velocity_growth=0.15,
        trade_velocity=20.0,
        volume_acceleration_1m=2.0,
        spread_pct=6.0,
        liquidity_score=65.0,
    )
    assert end is False
    assert state != WAVE_STATE_ENDED_LABEL or not end


def test_registry_keeps_wave_on_spread_extension_only():
    from analysis.early_upward_surge import RealJumpWaveSnapshot, RealPriceJumpVerdict

    registry = RealJumpAlertRegistry()
    tracker = RealJumpWaveTracker()
    wave = tracker.update("T", current_price=0.42, trade_velocity=100.0, volume_acceleration_1m=3.0)
    wave.wave_id = "T:0.38:2026"
    wave.wave_active = True
    v = RealPriceJumpVerdict(confirmed=True, wave=wave)
    r1 = registry.process(
        "T", v, wave=wave, current_price=0.42,
        price_volume_response=0.85, trade_velocity_growth=0.2, trade_velocity=100.0,
        volume_acceleration_1m=3.0, spread_pct=2.0, liquidity_score=65.0,
    )
    assert r1.emit and registry.get("T")
    wave = tracker.update("T", current_price=0.46, trade_velocity=200.0, volume_acceleration_1m=2.5)
    wave.wave_peak_price = 0.46
    v2 = RealPriceJumpVerdict(confirmed=False, reject_reason="wave_too_extended", wave=wave)
    r2 = registry.process(
        "T", v2, wave=wave, current_price=0.46,
        price_volume_response=0.9, trade_velocity_growth=0.2, trade_velocity=200.0,
        volume_acceleration_1m=2.5, spread_pct=6.5, liquidity_score=65.0,
    )
    assert registry.get("T") is not None
    assert r2.update_existing
    assert registry.get("T").kpi.wave_peak_price >= 0.46


@pytest.mark.integration
@pytest.mark.parametrize("symbol,grader", [
    ("CHOW", grade_chow),
    ("AAME", grade_reject),
    ("AZIO", grade_reject),
    ("ADCT", grade_reject),
])
def test_aug27_replay_case(symbol, grader):
    async def _go():
        client = PolygonClient()
        try:
            return await replay_symbol(client, symbol)
        finally:
            await client.close()

    result = _run(_go())
    if not result.data_available:
        pytest.skip(result.note or "DATA_UNAVAILABLE")
    assert grader(result) == "PASS", (
        f"{symbol}: first={result.first_detection_time}@{result.first_detection_price} "
        f"peak={result.wave_peak_price} jumps={result.first_real_jump_count} "
        f"final={result.final_state}"
    )


def test_aug27_chow_single_wave_id_and_peak():
    async def _go():
        client = PolygonClient()
        try:
            return await replay_symbol(client, "CHOW")
        finally:
            await client.close()

    result = _run(_go())
    if not result.data_available:
        pytest.skip(result.note)
    assert result.first_real_jump_count == 1
    assert result.first_detection_price is not None and result.first_detection_price < 0.55
    assert max(result.peak_after_detection, result.wave_peak_price) >= 0.85
    assert result.wave_id
    active_rows = [t for t in result.timeline if t.real_jump_wave_state == WAVE_STATE_ACTIVE_UPWARD]
    assert len(active_rows) >= 2
