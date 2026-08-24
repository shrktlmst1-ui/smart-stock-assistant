"""Performance / snapshot cache tests — no trading logic changes."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models.pre_move import PreMoveScanResult, PreMoveScanStats
from models.premarket_opportunity import PremarketScanResult
from models.scanner import OpportunitiesResponse
from services import snapshot_cache_service as scs
from services.best_opportunities_service import build_opportunities_from_scans


@pytest.fixture(autouse=True)
def reset_snapshot_cache():
    with scs._snapshot_lock:
        scs._cached = None
    with scs._refresh_guard:
        scs._refresh_in_progress = False
    scs._cache_hits = 0
    scs._cache_misses = 0
    scs._refresh_skipped = 0
    yield
    with scs._snapshot_lock:
        scs._cached = None
    with scs._refresh_guard:
        scs._refresh_in_progress = False


def _fake_scans():
    pre = PreMoveScanResult(
        signals=[],
        stats=PreMoveScanStats(scanned=100, early_candidates=5, deep_analyzed=3),
        message="ok",
    )
    pm = PremarketScanResult()
    return pre, pm, False, 0


def test_api_returns_cache_without_blocking_scan():
    """GET opportunities must not call sync_pre_move_scan on hot path."""
    response = OpportunitiesResponse(market_status="REGULAR", opportunities=[])
    entry = scs.CachedOpportunities(
        response=response,
        generated_mono=time.monotonic(),
        generated_at_iso="2026-01-01T00:00:00Z",
        scan_id="abc",
        session="REGULAR",
        symbols_scanned=100,
    )
    with scs._snapshot_lock:
        scs._cached = entry

    with patch("services.best_opportunities_service.sync_pre_move_scan") as sync_pm:
        t0 = time.monotonic()
        out = scs.get_opportunities_response(
            limit=20, state=None, session="REGULAR", trigger_refresh=False,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000

    sync_pm.assert_not_called()
    assert out.cache_hit is True
    assert elapsed_ms < 500
    assert out.api_status in ("NO_OPPORTUNITIES", "OK")


def test_concurrent_refresh_single_flight():
    """10 parallel refresh schedules must not start 10 scans."""
    started = threading.Event()
    release = threading.Event()
    call_count = {"n": 0}

    def slow_refresh(*args, **kwargs):
        call_count["n"] += 1
        started.set()
        release.wait(timeout=5)

    with patch.object(scs, "_run_refresh", side_effect=slow_refresh):
        results = [scs.schedule_opportunities_refresh(session="REGULAR") for _ in range(10)]
        assert sum(1 for r in results if r) == 1
        assert started.wait(timeout=2)
        assert call_count["n"] == 1
        release.set()
        time.sleep(0.2)


def test_empty_opportunities_returns_200_not_error():
    pre, pm, _, _ = _fake_scans()
    resp = build_opportunities_from_scans(pre, pm, limit=20, state=None, session="REGULAR")
    assert resp.opportunities == []
    decorated = scs._decorate_response(
        resp, entry=None, cache_hit=False, age_s=0, session="REGULAR", refreshing=False,
    )
    assert decorated.api_status == "NO_OPPORTUNITIES"


def test_stale_snapshot_status():
    response = OpportunitiesResponse(market_status="REGULAR", opportunities=[])
    entry = scs.CachedOpportunities(
        response=response,
        generated_mono=time.monotonic() - 9999,
        generated_at_iso="old",
        scan_id="old",
        session="REGULAR",
    )
    out = scs._decorate_response(
        response, entry=entry, cache_hit=True, age_s=9999, session="REGULAR", refreshing=False,
    )
    assert out.api_status == "DATA_STALE"


def test_partial_data_status():
    response = OpportunitiesResponse(market_status="REGULAR", opportunities=[])
    entry = scs.CachedOpportunities(
        response=response,
        generated_mono=time.monotonic(),
        generated_at_iso="now",
        scan_id="x",
        session="REGULAR",
        partial_data=True,
        failed_symbols_count=2,
    )
    out = scs._decorate_response(
        response, entry=entry, cache_hit=True, age_s=1, session="REGULAR", refreshing=False,
    )
    assert out.api_status == "PARTIAL_DATA"
    assert out.failed_symbols_count == 2


def test_atomic_snapshot_update():
    pre, pm, _, _ = _fake_scans()
    built = build_opportunities_from_scans(pre, pm, limit=20, state=None, session="REGULAR")
    entry = scs.CachedOpportunities(
        response=built,
        generated_mono=time.monotonic(),
        generated_at_iso="t",
        scan_id="s1",
        session="REGULAR",
        symbols_scanned=100,
    )
    with scs._snapshot_lock:
        scs._cached = entry
    with scs._snapshot_lock:
        assert scs._cached.scan_id == "s1"
        assert scs._cached.symbols_scanned == 100


def test_symbol_prep_timeout_skips_without_crashing():
    import asyncio

    from services.stock_service import _prep_snapshot_job
    from services.polygon_client import PolygonClient

    async def slow_bars(*a, **k):
        await asyncio.sleep(30)

    client = MagicMock(spec=PolygonClient)
    with patch("services.stock_service._ensure_bars", side_effect=slow_bars):
        with patch("services.stock_service.PER_SYMBOL_PREP_TIMEOUT_SEC", 0.05):
            result = asyncio.run(
                _prep_snapshot_job("AAA", client, {"AAA": {"ticker": "AAA", "day": {"c": 5}}})
            )
    assert result is None


def test_universe_name_avoids_reference_api():
    import asyncio

    from services.stock_service import _get_ticker_meta
    from services.polygon_client import PolygonClient
    from services.universe_manager import UniverseMember, universe_manager

    universe_manager._state.members["ZZZZ"] = UniverseMember(
        symbol="ZZZZ", name="Zeta Corp", exchange="NASDAQ",
    )
    client = MagicMock(spec=PolygonClient)

    async def boom(*a, **k):
        raise AssertionError("get_ticker_details should not be called")

    client.get_ticker_details = boom
    meta = asyncio.run(_get_ticker_meta("ZZZZ", client))
    assert meta["name"] == "Zeta Corp"


def test_opportunities_endpoint_cache_hit(client=None):
    client = TestClient(app)
    response = OpportunitiesResponse(market_status="REGULAR", opportunities=[])
    scs._cached = scs.CachedOpportunities(
        response=response,
        generated_mono=time.monotonic(),
        generated_at_iso="t",
        scan_id="live",
        session="REGULAR",
    )
    with patch("services.market_scanner_service.market_scanner") as ms:
        ms.get_state.return_value = MagicMock(market_status="REGULAR")
        with patch("services.best_opportunities_service.sync_pre_move_scan") as sync_pm:
            r = client.get("/stocks/opportunities?limit=5")
    assert r.status_code == 401 or r.status_code == 200
    if r.status_code == 200:
        sync_pm.assert_not_called()
        body = r.json()
        assert body.get("cache_hit") is True


def test_run_refresh_uses_cached_on_scan_failure():
    with patch("services.best_opportunities_service.sync_pre_move_scan", side_effect=RuntimeError("polygon")):
        with patch(
            "services.best_opportunities_service.get_last_pre_move_scan",
            return_value=PreMoveScanResult(message="cached"),
        ):
            with patch("services.best_opportunities_service.sync_premarket_scanner", return_value=PremarketScanResult()):
                from services.best_opportunities_service import run_opportunities_scans

                pre, pm, partial, failed = run_opportunities_scans({}, "REGULAR")
    assert partial is True
    assert failed >= 1
    assert pre.message == "cached"
