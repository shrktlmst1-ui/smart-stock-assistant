"""Tests for Real-Time Premarket Opportunity Scanner."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from services.premarket_opportunity_scanner import (
    PremarketMetrics,
    PremarketSnapshotRow,
    _compute_metrics,
    _evaluate_early_momentum,
    _evaluate_long_breakout,
    _evaluate_long_pullback,
    _parse_premarket_row,
    _passes_initial_filter,
    diagnose_symbol,
    scan_premarket_async,
)

ET = ZoneInfo("America/New_York")


def _pm_item(
    *,
    price: float = 5.5,
    prev: float = 4.0,
    pre_vol: int = 200_000,
    last_trade_p: float | None = None,
) -> dict:
    now_ns = int(datetime.now(ET).timestamp() * 1_000_000_000)
    return {
        "ticker": "TEST",
        "prevDay": {"c": prev, "v": 1_000_000},
        "preMarket": {"c": price, "v": pre_vol},
        "lastTrade": {"p": last_trade_p or price, "t": now_ns},
        "type": "CS",
        "primary_exchange": "XNAS",
    }


def _synthetic_breakout_bars(base: float = 5.0, breakout: float = 5.6) -> pd.DataFrame:
    rows = []
    t0 = datetime(2026, 8, 24, 8, 0, tzinfo=ET).astimezone(timezone.utc)
    price = base
    for i in range(30):
        ts = t0 + pd.Timedelta(minutes=i)
        vol = 5000 if i < 28 else 25000
        h = price + 0.05
        l = price - 0.03
        c = price + 0.02
        if i >= 28:
            h = breakout + 0.02
            c = breakout
            price = breakout
        rows.append({"open": l, "high": h, "low": l, "close": c, "volume": vol, "timestamp": ts})
    return pd.DataFrame(rows)


def test_parse_premarket_uses_live_price_not_prev_close():
    with patch("services.premarket_opportunity_scanner._is_trade_in_extended_session", return_value=True):
        with patch("services.premarket_opportunity_scanner._is_trade_fresh", return_value=True):
            row = _parse_premarket_row("TEST", _pm_item(price=5.5, prev=4.0))
    assert row is not None
    assert row.current_price == 5.5
    assert abs(row.premarket_change_percent - 37.5) < 0.1
    assert row.premarket_volume == 200_000


def test_initial_filter_rejects_low_volume():
    row = PremarketSnapshotRow(
        symbol="X", current_price=5.0, previous_close=4.0,
        premarket_change_percent=8.0, premarket_volume=50_000,
        last_trade_ns=1, trade_fresh=True,
    )
    assert _passes_initial_filter(row) == "LOW_VOLUME"


def test_initial_filter_rejects_zero_change():
    row = PremarketSnapshotRow(
        symbol="X", current_price=5.0, previous_close=5.0,
        premarket_change_percent=0.0, premarket_volume=200_000,
        last_trade_ns=1, trade_fresh=True,
    )
    assert _passes_initial_filter(row) == "NO_BREAKOUT"


def test_long_breakout_trigger_fires():
    row = PremarketSnapshotRow(
        symbol="BRK", current_price=5.62, previous_close=4.0,
        premarket_change_percent=40.5, premarket_volume=500_000,
        last_trade_ns=1, trade_fresh=True,
    )
    bars = _synthetic_breakout_bars(base=5.0, breakout=5.62)
    m = _compute_metrics(row, bars, {"p": 5.61, "P": 5.63})
    m.current_price = 5.62
    m.premarket_high = 5.55
    m.last_bar_close = 5.62
    m.volume_1m = 25000
    m.avg_1m_volume_prior = 5000
    m.vwap = 5.30
    m.spread_percent = 0.4
    m.relative_volume = 2.0

    ok, reason, ex = _evaluate_long_breakout(m)
    assert ok is True
    assert ex is None
    assert "breakout" in reason.lower()


def test_long_breakout_rejects_below_vwap():
    m = PremarketMetrics(
        symbol="X", current_price=5.6, premarket_change_percent=10,
        premarket_volume=200_000, premarket_high=5.5, last_bar_close=5.6,
        volume_1m=20000, avg_1m_volume_prior=5000, vwap=5.8, spread_percent=0.5,
        relative_volume=2.0, trade_fresh=True,
    )
    ok, _, ex = _evaluate_long_breakout(m)
    assert ok is False
    assert ex == "BELOW_VWAP"


def test_long_pullback_requires_10pct_gain():
    m = PremarketMetrics(
        symbol="X", current_price=5.2, premarket_change_percent=8.0,
        premarket_volume=300_000, vwap=5.18, spread_percent=0.5,
        trade_fresh=True, bars=_synthetic_breakout_bars(),
    )
    ok, _, ex = _evaluate_long_pullback(m)
    assert ok is False


def test_early_momentum_pmi_like_without_pm_high_break():
    """Strong gap + volume below PM high should qualify as EARLY_MOMENTUM."""
    m = PremarketMetrics(
        symbol="PMI",
        current_price=4.64,
        premarket_change_percent=44.55,
        premarket_volume=3_698_634,
        premarket_high=5.11,
        premarket_low=4.34,
        vwap=4.738,
        volume_1m=5918,
        volume_5m=88523,
        relative_volume=1.39,
        spread_percent=0.2,
        volume_acceleration=0.21,
        distance_from_premarket_high_pct=9.2,
        momentum_acceleration=0.5,
        trade_fresh=True,
        bars=_synthetic_breakout_bars(base=4.2, breakout=4.64),
    )
    ok, reason, ex = _evaluate_early_momentum(m)
    assert ok is True
    assert ex is None
    assert "تسارع مبكر" in reason


def test_early_momentum_rejects_weak_gap():
    m = PremarketMetrics(
        symbol="WEAK", current_price=5.1, premarket_change_percent=3.0,
        premarket_volume=200_000, premarket_high=5.2, vwap=5.0,
        relative_volume=0.8, spread_percent=0.5, volume_acceleration=0.5,
        distance_from_premarket_high_pct=2.0, momentum_acceleration=-1.0,
        trade_fresh=True, bars=_synthetic_breakout_bars(),
    )
    ok, _, ex = _evaluate_early_momentum(m)
    assert ok is False


@pytest.mark.asyncio
async def test_scan_returns_watch_when_no_trigger():
    raw = {"WATCHME": _pm_item(price=5.2, prev=4.8, pre_vol=150_000)}
    bars = _synthetic_breakout_bars(base=5.0, breakout=5.05)

    with patch("services.premarket_opportunity_scanner.get_us_market_session", return_value="PRE_MARKET"):
        with patch("services.premarket_opportunity_scanner._fetch_bars_cached", new=AsyncMock(return_value=bars)):
            with patch("services.premarket_opportunity_scanner._fetch_nbbo_cached", new=AsyncMock(return_value={"p": 5.19, "P": 5.21})):
                with patch("services.polygon_client.PolygonClient") as mock_cls:
                    mock_cls.return_value.close = AsyncMock()
                    result = await scan_premarket_async(raw, focus_symbols=["WATCHME"])

    assert result.filtered >= 1


@pytest.mark.asyncio
async def test_pmi_diagnostic_2026_08_24():
    """Picard Medical (PMI) — logs exclusion reasons from live Polygon when available."""
    try:
        from services.polygon_client import PolygonClient
        client = PolygonClient()
    except ValueError:
        pytest.skip("Polygon API key not configured")

    try:
        snap = await client.get_snapshot("PMI")
        diag = await diagnose_symbol("PMI", snap, session_date="2026-08-24")
    finally:
        await client.close()

    assert diag["symbol"] == "PMI"
    if diag.get("parsed"):
        p = diag["parsed"]
        assert p["current_price"] > 0
        if p["premarket_volume"] > 0:
            assert p["premarket_change_percent"] != 0.0

    if diag.get("parsed") and diag["parsed"]["premarket_change_percent"] >= 5:
        if diag["parsed"]["premarket_volume"] >= 100_000:
            assert diag.get("metrics") is not None
        elif diag.get("metrics"):
            assert diag["metrics"]["premarket_volume_enriched"] >= 0
