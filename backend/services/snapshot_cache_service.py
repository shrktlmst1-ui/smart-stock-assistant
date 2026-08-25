"""Atomic snapshot cache — fast API reads, background refresh."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from config import PREMOVE_DATA_MAX_AGE_SECONDS
from models.scanner import MarketScanState, OpportunitiesResponse
from services.best_opportunities_service import (
    PREMARKET_EMPTY_SUB,
    PREMARKET_EMPTY_TITLE,
    build_opportunities_from_scans,
    run_opportunities_scans,
)
from services.market_session import session_explanation

logger = logging.getLogger(__name__)

ApiStatus = Literal[
    "OK",
    "REFRESHING",
    "NO_OPPORTUNITIES",
    "PARTIAL_DATA",
    "DATA_STALE",
    "AUTH_ERROR",
    "PROVIDER_TIMEOUT",
    "SERVER_ERROR",
]

_snapshot_lock = threading.Lock()
_refresh_guard = threading.Lock()
_refresh_in_progress = False
_cache_hits = 0
_cache_misses = 0
_refresh_skipped = 0
_last_refresh_ms: float = 0.0

_refresh_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="opp-snapshot")


@dataclass
class CachedOpportunities:
    response: OpportunitiesResponse
    generated_mono: float
    generated_at_iso: str
    scan_id: str
    session: str
    symbols_scanned: int = 0
    candidates_count: int = 0
    deep_analysis_count: int = 0
    partial_data: bool = False
    failed_symbols_count: int = 0


_cached: CachedOpportunities | None = None


def cache_stats() -> dict:
    return {
        "cache_hits": _cache_hits,
        "cache_misses": _cache_misses,
        "refresh_skipped": _refresh_skipped,
        "refresh_in_progress": _refresh_in_progress,
        "last_refresh_ms": _last_refresh_ms,
        "has_snapshot": _cached is not None,
    }


def _age_seconds(entry: CachedOpportunities | None) -> float:
    if entry is None:
        return float("inf")
    return max(0.0, time.monotonic() - entry.generated_mono)


def _api_status(
    *,
    has_data: bool,
    age_s: float,
    refreshing: bool,
    partial: bool,
) -> ApiStatus:
    if refreshing and not has_data:
        return "REFRESHING"
    if partial:
        return "PARTIAL_DATA"
    if age_s > PREMOVE_DATA_MAX_AGE_SECONDS:
        return "DATA_STALE"
    if not has_data:
        return "NO_OPPORTUNITIES"
    return "OK"


def _decorate_response(
    base: OpportunitiesResponse,
    *,
    entry: CachedOpportunities | None,
    cache_hit: bool,
    age_s: float,
    session: str,
    refreshing: bool,
) -> OpportunitiesResponse:
    partial = entry.partial_data if entry else False
    status = _api_status(
        has_data=bool(base.opportunities or base.watchlist_candidates),
        age_s=age_s,
        refreshing=refreshing,
        partial=partial,
    )
    if status == "OK" and not base.opportunities and not base.watchlist_candidates:
        status = "NO_OPPORTUNITIES"

    data = base.model_dump()
    data.update(
        {
            "api_status": status,
            "generated_at": entry.generated_at_iso if entry else datetime.now(timezone.utc).isoformat(),
            "data_timestamp": entry.generated_at_iso if entry else "",
            "data_age_seconds": round(age_s, 1) if entry else 0.0,
            "scan_id": entry.scan_id if entry else "",
            "session": session,
            "symbols_scanned": entry.symbols_scanned if entry else 0,
            "candidates_count": entry.candidates_count if entry else 0,
            "deep_analysis_count": entry.deep_analysis_count if entry else 0,
            "is_refreshing": refreshing,
            "partial_data": partial,
            "failed_symbols_count": entry.failed_symbols_count if entry else 0,
            "cache_hit": cache_hit,
        }
    )
    return OpportunitiesResponse(**data)


def _empty_response(session: str, state: MarketScanState | None) -> OpportunitiesResponse:
    return OpportunitiesResponse(
        market_status=session,  # type: ignore[arg-type]
        opportunities=[],
        watchlist_candidates=[],
        explanation=session_explanation(session),  # type: ignore[arg-type]
        no_signal_reason=f"{PREMARKET_EMPTY_TITLE}\n{PREMARKET_EMPTY_SUB}",
        debug=state.debug if state else None,
    )


def get_opportunities_response(
    *,
    limit: int,
    state: MarketScanState | None,
    session: str,
    trigger_refresh: bool = True,
    force_refresh: bool = False,
) -> OpportunitiesResponse:
    """Return cached snapshot immediately; optionally schedule background refresh."""
    global _cache_hits, _cache_misses

    t0 = time.monotonic()
    with _snapshot_lock:
        entry = _cached
        refreshing = _refresh_in_progress

    age_s = _age_seconds(entry)
    stale = age_s > PREMOVE_DATA_MAX_AGE_SECONDS

    if entry is not None and not stale:
        _cache_hits += 1
        cache_hit = True
        response = _decorate_response(
            entry.response,
            entry=entry,
            cache_hit=True,
            age_s=age_s,
            session=session,
            refreshing=refreshing,
        )
        if trigger_refresh and force_refresh:
            schedule_opportunities_refresh(session=session, state=state)
    elif entry is not None:
        _cache_hits += 1
        cache_hit = True
        response = _decorate_response(
            entry.response,
            entry=entry,
            cache_hit=True,
            age_s=age_s,
            session=session,
            refreshing=refreshing,
        )
        if trigger_refresh and (stale or force_refresh):
            schedule_opportunities_refresh(session=session, state=state)
    else:
        _cache_misses += 1
        cache_hit = False
        response = _decorate_response(
            _empty_response(session, state),
            entry=None,
            cache_hit=False,
            age_s=float("inf"),
            session=session,
            refreshing=refreshing or trigger_refresh,
        )
        if trigger_refresh:
            schedule_opportunities_refresh(session=session, state=state)

    # Apply limit to opportunities in response
    if len(response.opportunities) > limit:
        data = response.model_dump()
        data["opportunities"] = response.opportunities[:limit]
        response = OpportunitiesResponse(**data)

    api_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "[PERF] opportunities_api_ms=%.0f cache_hit=%s age=%.0fs concurrent_scans=%d",
        api_ms,
        cache_hit,
        age_s if entry else -1,
        1 if _refresh_in_progress else 0,
    )
    return response


def invalidate_opportunities_cache() -> None:
    """Clear cached opportunities snapshot (e.g. on session transition)."""
    global _cached
    with _snapshot_lock:
        _cached = None
    logger.info("Opportunities snapshot cache cleared")


def schedule_opportunities_refresh(
    *,
    session: str | None = None,
    state: MarketScanState | None = None,
    snapshot_raw: dict | None = None,
) -> bool:
    """Single-flight background refresh — returns False if already running."""
    global _refresh_in_progress, _refresh_skipped

    with _refresh_guard:
        if _refresh_in_progress:
            _refresh_skipped += 1
            logger.info("[PERF] concurrent_scans=0 refresh_skipped=%d", _refresh_skipped)
            return False
        _refresh_in_progress = True

    def _job() -> None:
        global _refresh_in_progress, _last_refresh_ms
        t0 = time.monotonic()
        try:
            _run_refresh(session=session, state=state, snapshot_raw=snapshot_raw)
        except Exception as exc:
            logger.warning("[PERF] opportunities refresh failed: %s", type(exc).__name__)
        finally:
            _last_refresh_ms = round((time.monotonic() - t0) * 1000, 1)
            with _refresh_guard:
                _refresh_in_progress = False
            logger.info("[PERF] scanner_total_ms=%.0f concurrent_scans=0", _last_refresh_ms)

    _refresh_executor.submit(_job)
    return True


def _run_refresh(
    *,
    session: str | None,
    state: MarketScanState | None,
    snapshot_raw: dict | None,
) -> None:
    from services.market_scanner_service import market_scanner
    from services.market_session import get_us_market_session

    raw = snapshot_raw if snapshot_raw is not None else market_scanner._snapshot_raw
    st = state or market_scanner.get_state()
    sess = session or (st.market_status if st and st.market_status else get_us_market_session())

    pre_move, premarket, partial, failed = run_opportunities_scans(raw, sess)

    response = build_opportunities_from_scans(
        pre_move,
        premarket,
        limit=20,
        state=st,
        session=sess,
    )

    entry = CachedOpportunities(
        response=response,
        generated_mono=time.monotonic(),
        generated_at_iso=datetime.now(timezone.utc).isoformat(),
        scan_id=str(uuid.uuid4())[:8],
        session=sess,
        symbols_scanned=pre_move.stats.scanned,
        candidates_count=pre_move.stats.early_candidates,
        deep_analysis_count=pre_move.stats.deep_analyzed + (premarket.filtered if sess == "PRE_MARKET" else 0),
        partial_data=partial,
        failed_symbols_count=failed,
    )

    with _snapshot_lock:
        global _cached
        _cached = entry

    logger.info(
        "[PERF] snapshot_updated scan_id=%s scanned=%d candidates=%d deep=%d partial=%s",
        entry.scan_id,
        entry.symbols_scanned,
        entry.candidates_count,
        entry.deep_analysis_count,
        entry.partial_data,
    )
