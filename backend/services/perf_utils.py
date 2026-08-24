"""Lightweight performance and memory helpers — no trading logic."""

from __future__ import annotations

import gc
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def rss_mb() -> float:
    """Best-effort process RSS in MB (0 if unavailable)."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        if sys.platform == "darwin":
            return rss / (1024 * 1024)
        return rss / 1024
    except Exception:
        return 0.0


@dataclass
class PerfSnapshot:
    memory_before_mb: float = 0.0
    memory_peak_mb: float = 0.0
    memory_after_mb: float = 0.0
    elapsed_ms: float = 0.0
    extras: dict = field(default_factory=dict)


@contextmanager
def perf_timer(label: str, **extras):
    snap = PerfSnapshot(memory_before_mb=rss_mb(), extras=dict(extras))
    t0 = time.monotonic()
    try:
        yield snap
    finally:
        snap.elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        snap.memory_after_mb = rss_mb()
        snap.memory_peak_mb = max(snap.memory_before_mb, snap.memory_after_mb)
        gc.collect()
        parts = " ".join(f"{k}={v}" for k, v in snap.extras.items())
        logger.info(
            "[PERF] %s ms=%.0f memory_before=%.0fMB peak=%.0fMB after=%.0fMB %s",
            label,
            snap.elapsed_ms,
            snap.memory_before_mb,
            snap.memory_peak_mb,
            snap.memory_after_mb,
            parts.strip(),
        )


def cache_sizes() -> dict[str, int]:
    sizes: dict[str, int] = {}
    try:
        from services import stock_service

        sizes["symbol_cache"] = len(stock_service._symbol_cache)
        sizes["ticker_meta_cache"] = len(stock_service._ticker_meta_cache)
        sizes["name_cache"] = len(stock_service._name_cache)
    except Exception:
        pass
    try:
        from services import pre_move_predictor_service as pm

        sizes["premove_bar_cache"] = len(pm._bar_cache)
    except Exception:
        pass
    try:
        from services import premarket_opportunity_scanner as pms

        sizes["premarket_bar_cache"] = len(pms._bar_cache)
        sizes["premarket_nbbo_cache"] = len(pms._nbbo_cache)
    except Exception:
        pass
    return sizes
