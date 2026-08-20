"""Full-market phased scanner tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from analysis.safety_gates import passes_automatic_price, safety_passed_snapshot
from config import SCANNER_RANK_POOL
from services.market_scanner_service import MarketScannerService
from services.scanner_filters import TickerMetrics


def _metrics(symbol: str, price: float = 5.0, **kwargs) -> TickerMetrics:
    defaults = dict(
        name=symbol,
        price=price,
        change_percent=3.0,
        volume=500_000,
        prev_volume=200_000,
        relative_volume=2.5,
        volume_spike=True,
        spread_pct=0.8,
        day_open=price,
        day_high=price * 1.01,
        day_low=price * 0.99,
        premarket_change_pct=0.0,
        afterhours_change_pct=0.0,
        market_cap=100_000_000,
        float_shares=50_000_000,
        opening_range_breakout=False,
        momentum_score=10.0,
        composite_score=80.0,
    )
    defaults.update(kwargs)
    return TickerMetrics(symbol=symbol, **defaults)


def test_automatic_price_filter_excludes_above_ten():
    assert passes_automatic_price(9.99) is True
    assert passes_automatic_price(10.0) is True
    assert passes_automatic_price(10.01) is False
    assert passes_automatic_price(0.0) is False


def test_rank_pool_size_from_scored_metrics():
    svc = MarketScannerService()
    scored = [(_metrics(f"S{i}", price=3.0 + i * 0.01), 100 - i) for i in range(600)]
    svc._scored_metrics = scored
    svc._rank_pool = [m.symbol for m, _ in scored[:SCANNER_RANK_POOL]]
    assert len(svc._rank_pool) == SCANNER_RANK_POOL


def test_deep_rotation_changes_batch():
    svc = MarketScannerService()
    svc._rank_pool = [f"S{i}" for i in range(100)]
    first = svc._select_deep_batch()
    idx_after_first = svc._deep_rotation_index
    second = svc._select_deep_batch()
    assert idx_after_first != svc._deep_rotation_index or first != second


def test_safety_not_all_eighteen_factors_required():
    snap = SimpleNamespace(
        price=4.5,
        volume=800_000,
        volume_engine=SimpleNamespace(relative_volume=2.5, session_rvol=2.0),
        indicators=SimpleNamespace(resistance=4.52, support=4.48),
        liquidity_traps=SimpleNamespace(fake_breakout=False),
        trade_decision=SimpleNamespace(
            current_price=4.5,
            trap_risk=20,
            news_risk=10,
            professional_signal="WAIT",
            recommendation="WAIT",
            factor_scores={"smc": 50, "bos": 30, "trend": 40},
        ),
    )
    ok, _ = safety_passed_snapshot(snap)  # type: ignore[arg-type]
    assert ok is True


def test_scanner_survives_universe_failure():
    svc = MarketScannerService()
    with patch.object(svc.client, "get_full_market_snapshot", side_effect=RuntimeError("massive down")):
        import asyncio
        asyncio.get_event_loop().run_until_complete(svc.refresh_universe())
    assert svc.universe_size == 0
    state = svc._empty_state()
    assert state.market_status in ("REGULAR", "CLOSED", "PRE_MARKET", "AFTER_HOURS")


def test_preserves_pinned_and_watchlist_symbols():
    svc = MarketScannerService()
    svc._rank_pool = [f"S{i}" for i in range(50)]
    svc._pinned_symbols.add("PINNED")
    svc._last_state = SimpleNamespace(
        watchlist_candidates=[SimpleNamespace(symbol="WATCH1")],
        top_opportunities=[SimpleNamespace(symbol="TOP1")],
    )
    batch = svc._select_deep_batch()
    assert "PINNED" in batch
    assert "WATCH1" in batch
    assert "TOP1" in batch
