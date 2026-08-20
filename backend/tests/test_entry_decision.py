"""Tests for entry decision engine."""

from datetime import datetime, timedelta, timezone

from analysis.entry_decision import (
    EntryDecisionConfig,
    check_data_freshness,
    compute_signal_expiry,
    evaluate_entry_decision,
    is_signal_expired,
    is_stop_broken,
)


def _base_kwargs(**overrides):
    now = datetime.now(timezone.utc)
    defaults = dict(
        price=100.0,
        ai_score=85.0,
        rrr=2.5,
        rvol=2.0,
        spread_pct=0.3,
        volume=1_000_000,
        entry_low=99.0,
        entry_high=101.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=115.0,
        direction="long",
        trap_risk=10.0,
        news_risk=10.0,
        professional_signal="BUY",
        recommendation="ENTRY CONFIRMED",
        failed_factors=[],
        devils_advocate="لا مخاوف رئيسية — راقب إدارة المخاطر",
        last_updated=now.isoformat(),
        signal_created_at=now.isoformat(),
    )
    defaults.update(overrides)
    return defaults


def test_enter_now_all_conditions_met():
    r = evaluate_entry_decision(**_base_kwargs())
    assert r.state == "ENTER_NOW"
    assert r.label_ar == "ادخل الآن"
    assert len(r.entry_reasons) >= 2


def test_wait_price_outside_entry_zone():
    r = evaluate_entry_decision(**_base_kwargs(price=105.0))
    assert r.state == "WAIT_PRICE"
    assert r.label_ar == "انتظر السعر"


def test_avoid_high_trap_risk():
    r = evaluate_entry_decision(**_base_kwargs(trap_risk=55.0))
    assert r.state == "AVOID"
    assert r.label_ar == "تجنب"


def test_stale_data_blocks_enter_now():
    old = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    r = evaluate_entry_decision(**_base_kwargs(last_updated=old))
    assert r.state == "STALE_DATA"
    assert r.label_ar == "البيانات متأخرة — للمراقبة فقط"
    assert not r.data_fresh


def test_signal_expired():
    created = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    cfg = EntryDecisionConfig(signal_expiry_candles=3, timeframe_minutes=15)
    assert is_signal_expired(created, cfg=cfg) if False else is_signal_expired(
        created, candles=3, timeframe_minutes=15,
    )
    r = evaluate_entry_decision(**_base_kwargs(signal_created_at=created))
    assert r.state == "EXPIRED"
    assert r.label_ar == "انتهت الإشارة"


def test_stop_broken_expires_signal():
    r = evaluate_entry_decision(**_base_kwargs(price=94.0, stop_loss=95.0))
    assert r.state == "EXPIRED"
    assert any("كسر" in w for w in r.warnings)


def test_check_data_freshness():
    now = datetime.now(timezone.utc)
    fresh_ts = now.isoformat()
    stale_ts = (now - timedelta(seconds=200)).isoformat()
    assert check_data_freshness(fresh_ts, max_age_seconds=120)[0] is True
    assert check_data_freshness(stale_ts, max_age_seconds=120)[0] is False


def test_compute_signal_expiry():
    created = "2026-08-19T10:00:00+00:00"
    exp = compute_signal_expiry(created, candles=3, timeframe_minutes=15)
    assert "10:45" in exp or "T10:45" in exp


def test_is_stop_broken_long():
    assert is_stop_broken(94.0, 95.0, "long") is True
    assert is_stop_broken(96.0, 95.0, "long") is False


def test_low_ai_score_avoid():
    r = evaluate_entry_decision(**_base_kwargs(ai_score=50.0, professional_signal="WAIT"))
    assert r.state == "AVOID"
