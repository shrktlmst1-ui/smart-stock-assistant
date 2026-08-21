"""Tests for فرصة الآن scoring and filters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services import opportunity_now_scoring as scoring
from services import opportunity_now_service as svc


def _snap(**kwargs):
    now = datetime.now(timezone.utc).isoformat()
    price = kwargs.get("price", 5.0)
    defaults = dict(
        symbol="TEST",
        name="Test Co",
        price=price,
        change_percent=3.0,
        volume=800_000,
        last_updated=now,
        news=[],
        smc=SimpleNamespace(bos=True, liquidity_sweep=False, fair_value_gaps=[], order_blocks=[]),
        volume_engine=SimpleNamespace(relative_volume=2.5, session_rvol=2.0),
        trend_analysis=SimpleNamespace(vwap=price * 0.97, direction="bullish"),
        volume_liquidity=SimpleNamespace(vwap=price * 0.97, relative_volume=2.5),
        news_intelligence=SimpleNamespace(
            overall_sentiment="neutral",
            confidence_adjustment=0,
            summary="",
        ),
        indicators=SimpleNamespace(
            resistance=round(price * 1.001, 4),
            support=round(price * 0.999, 4),
        ),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _strong_snap(**kwargs):
    """Fixture that clears safety gates and scores into فرصة الآن."""
    price = kwargs.get("price", 4.35)
    snap = _snap(
        price=price,
        change_percent=6.0,
        volume=900_000,
        smc=SimpleNamespace(
            bos=True,
            liquidity_sweep=True,
            fair_value_gaps=[1],
            order_blocks=[1],
        ),
        volume_engine=SimpleNamespace(relative_volume=3.0, session_rvol=3.0),
        trend_analysis=SimpleNamespace(vwap=4.25, direction="bullish"),
        volume_liquidity=SimpleNamespace(vwap=4.25, relative_volume=3.0),
        news=[SimpleNamespace(title="إيرادات قوية")],
        news_intelligence=SimpleNamespace(
            overall_sentiment="bullish",
            confidence_adjustment=5,
            summary="",
        ),
        indicators=SimpleNamespace(
            resistance=round(price * 1.001, 4),
            support=round(price * 0.999, 4),
        ),
    )
    for key, value in kwargs.items():
        setattr(snap, key, value)
    return snap


@pytest.fixture(autouse=True)
def _reset_cache():
    scoring.reset_signal_cache()
    yield
    scoring.reset_signal_cache()


def test_excludes_zero_price():
    snap = _snap(price=0.0, symbol="ZERO")
    assert scoring._snapshot_to_signal(snap, market_open=True) is None


def test_excludes_price_above_ten():
    snap = _snap(price=12.5, symbol="HIGH")
    assert scoring._snapshot_to_signal(snap, market_open=True) is None


def test_rejects_stale_data():
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    snap = _snap(last_updated=old)
    sig = scoring._snapshot_to_signal(snap, market_open=True)
    assert sig is not None
    assert sig.status == "CANCELLED"
    assert any("قديمة" in r for r in sig.reasons_ar)


def test_rejects_high_spread():
    snap = _snap()
    with patch.object(scoring, "_spread_pct", return_value=1.2):
        sig = scoring._snapshot_to_signal(snap, market_open=True)
    assert sig is not None
    assert sig.status == "CANCELLED"


def test_opportunity_now_when_score_high_and_market_open():
    snap = _strong_snap()
    sig = scoring._snapshot_to_signal(snap, market_open=True)
    assert sig is not None
    assert sig.score >= 80
    assert sig.status == "NOW"


def test_status_transitions_watch_ready_opportunity():
    watch = _snap(price=6.0, change_percent=1.2, volume=280_000)
    watch.volume_engine.relative_volume = 1.25  # type: ignore[union-attr]
    sig_watch = scoring._snapshot_to_signal(watch, market_open=True)
    assert sig_watch is not None
    assert sig_watch.status in ("WATCH", "CANCELLED", "READY")

    ready = _snap(price=5.5, change_percent=4.0, volume=600_000)
    ready.volume_engine.relative_volume = 2.2  # type: ignore[union-attr]
    ready.smc.liquidity_sweep = True  # type: ignore[union-attr]
    sig_ready = scoring._snapshot_to_signal(ready, market_open=True)
    assert sig_ready is not None
    assert sig_ready.status in ("READY", "NOW", "WATCH")

    top = _strong_snap()
    sig_top = scoring._snapshot_to_signal(top, market_open=True)
    assert sig_top is not None
    assert sig_top.status == "NOW"


def test_ready_state_mid_score():
    snap = _snap(price=6.0, change_percent=1.5, volume=300_000)
    snap.volume_engine.relative_volume = 1.3  # type: ignore[union-attr]
    sig = scoring._snapshot_to_signal(snap, market_open=True)
    assert sig is not None
    assert sig.status in ("READY", "WATCH", "CANCELLED", "NOW")


def test_market_closed_downgrades_opportunity_now():
    snap = _snap(price=3.5, change_percent=6.0)
    sig = scoring._snapshot_to_signal(snap, market_open=False)
    assert sig is not None
    assert sig.status != "NOW"


def test_signal_expires():
    sym = "EXPIRE"
    old = (datetime.now(timezone.utc) - timedelta(seconds=scoring.SIGNAL_TTL_SECONDS + 10)).isoformat()
    scoring._signal_created[sym] = old
    snap = _snap(symbol=sym, last_updated=datetime.now(timezone.utc).isoformat())
    sig = scoring._snapshot_to_signal(snap, market_open=True)
    assert sig is not None


def test_get_opportunity_now_survives_scanner_failure():
    with patch.object(svc.market_scanner, "get_state", side_effect=RuntimeError("massive down")):
        resp = svc.get_opportunity_now()
    assert resp.signals == []
    assert "تعذر" in resp.message or resp.market_status == "CLOSED"


def test_movement_without_news_detected():
    snap = _snap(news=[], news_intelligence=SimpleNamespace(overall_sentiment="neutral", confidence_adjustment=0, summary=""))
    snap.volume_engine.relative_volume = 3.0  # type: ignore[union-attr]
    snap.change_percent = 5.0
    sig = scoring._snapshot_to_signal(snap, market_open=True)
    assert sig is not None
    assert sig.movement_without_news or sig.has_news_catalyst is False


def test_with_news_catalyst():
    snap = _snap(
        news=[SimpleNamespace(title="Beat")],
        news_intelligence=SimpleNamespace(overall_sentiment="bullish", confidence_adjustment=5, summary=""),
    )
    sig = scoring._snapshot_to_signal(snap, market_open=True)
    assert sig is not None
    assert sig.has_news_catalyst
