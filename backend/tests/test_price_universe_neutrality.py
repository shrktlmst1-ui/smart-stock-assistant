"""Price-universe neutrality — same wave % treated equally across price bands."""

from __future__ import annotations

import pytest

from analysis.early_upward_surge import neutral_surge_rank
from config import SCANNER_MAX_PRICE, SCANNER_MIN_PRICE
from services.price_universe import passes_universe_price, price_universe_reject_reason
from services.real_jump_alert_layer import (
    DISTINGUISHED_JUMP_MIN_WAVE_PCT,
    eligible_for_distinguished_jump_section,
)
from tests.test_distinguished_jump_section import _active_wave


@pytest.mark.parametrize(
    "price",
    [0.25, 0.75, 1.5, 4.0, 7.5, 9.95],
)
def test_universe_includes_penny_through_nine_dollars(price: float):
    assert passes_universe_price(price) is True
    assert price_universe_reject_reason(price) is None


@pytest.mark.parametrize("price", [0.005, 10.01, 15.0, 0.0])
def test_universe_rejects_outside_band(price: float):
    assert passes_universe_price(price) is False
    assert price_universe_reject_reason(price) is not None


@pytest.mark.parametrize(
    "move_start,current",
    [
        (0.40, 0.62),
        (1.00, 1.55),
        (3.00, 4.65),
        (5.00, 7.55),
        (6.00, 9.00),
    ],
)
def test_same_fifty_pct_wave_eligible_at_all_prices(move_start: float, current: float):
    assert passes_universe_price(current)
    wave = _active_wave(
        move_start_price=move_start,
        current_price=current,
        current_move_pct=(current - move_start) / move_start * 100.0,
        wave_peak_price=current * 1.01,
    )
    assert eligible_for_distinguished_jump_section(wave, current_price=current) is True


@pytest.mark.parametrize(
    "move_start,current",
    [
        (0.40, 0.52),
        (2.00, 2.80),
        (6.00, 8.40),
    ],
)
def test_same_sub_fifty_pct_wave_rejected_at_all_prices(move_start: float, current: float):
    wave = _active_wave(
        move_start_price=move_start,
        current_price=current,
        current_move_pct=(current - move_start) / move_start * 100.0,
    )
    assert eligible_for_distinguished_jump_section(wave, current_price=current) is False


def test_neutral_surge_rank_same_wave_pct_same_score_regardless_of_price_level():
    """Rank uses percent move only — not absolute dollar move."""
    low = neutral_surge_rank(wave_move_pct=55.0, rvol=2.0)
    mid = neutral_surge_rank(wave_move_pct=55.0, rvol=2.0)
    high = neutral_surge_rank(wave_move_pct=55.0, rvol=2.0)
    assert low == pytest.approx(mid)
    assert mid == pytest.approx(high)


def test_neutral_surge_rank_prefers_wave_over_session_change():
    wave_rank = neutral_surge_rank(wave_move_pct=8.0, session_change_pct=3.0, rvol=2.0)
    session_only = neutral_surge_rank(wave_move_pct=0.0, session_change_pct=3.0, rvol=2.0)
    assert wave_rank > session_only


def test_config_band_matches_product_requirement():
    assert SCANNER_MIN_PRICE <= 0.01
    assert SCANNER_MAX_PRICE == pytest.approx(10.0)
    assert DISTINGUISHED_JUMP_MIN_WAVE_PCT == pytest.approx(50.0)
