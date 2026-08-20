"""Tests for position sizing calculator."""

from analysis.position_sizer import calculate_position_size


def test_basic_position_size():
    r = calculate_position_size(
        capital=100_000,
        risk_pct=0.5,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=115.0,
    )
    assert r.valid
    assert r.risk_amount == 500.0
    assert r.loss_per_share == 5.0
    assert r.shares == 100
    assert r.position_value == 10_000.0
    assert r.expected_profit_tp1 == 1_000.0
    assert r.expected_profit_tp2 == 1_500.0
    assert not r.capped_by_capital


def test_position_capped_by_capital():
    r = calculate_position_size(
        capital=5_000,
        risk_pct=2.0,
        entry_price=50.0,
        stop_loss=49.0,
        take_profit_1=55.0,
        take_profit_2=60.0,
    )
    assert r.valid
    assert r.position_value <= 5_000
    assert r.capped_by_capital


def test_invalid_stop_equals_entry():
    r = calculate_position_size(
        capital=10_000,
        risk_pct=1.0,
        entry_price=100.0,
        stop_loss=100.0,
    )
    assert not r.valid
    assert r.shares == 0
    assert r.error


def test_short_direction_profit():
    r = calculate_position_size(
        capital=50_000,
        risk_pct=1.0,
        entry_price=200.0,
        stop_loss=210.0,
        take_profit_1=180.0,
        take_profit_2=170.0,
        direction="short",
    )
    assert r.valid
    assert r.loss_per_share == 10.0
    assert r.expected_profit_tp1 == r.shares * 20
    assert r.expected_profit_tp2 == r.shares * 30


def test_zero_capital():
    r = calculate_position_size(
        capital=0,
        risk_pct=0.5,
        entry_price=100.0,
        stop_loss=95.0,
    )
    assert not r.valid
    assert "رأس المال" in r.error
