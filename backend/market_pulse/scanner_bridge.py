"""Merge scanner snapshot prices into Market Pulse metrics — no per-symbol API calls."""

from __future__ import annotations

from datetime import datetime, timezone

from market_pulse.metrics import PulseMetrics
from market_pulse.state import SymbolPulseState
from models.stock import StockSnapshot
from services.market_scanner_service import market_scanner


def _find_scanner_snapshot(symbol: str) -> StockSnapshot | None:
    sym = symbol.upper()
    cached = market_scanner._snapshots.get(sym)
    if cached and cached.price > 0:
        return cached
    state = market_scanner.get_state()
    if not state:
        return None
    for snap in state.snapshots:
        if snap.symbol.upper() == sym and snap.price > 0:
            return snap
    return None


def enrich_metrics_from_scanner(
    symbol: str,
    state: SymbolPulseState,
    metrics: PulseMetrics,
) -> PulseMetrics:
    """Fill missing live fields from the institutional scanner cache."""
    snap = _find_scanner_snapshot(symbol)
    if not snap:
        return metrics

    if metrics.price <= 0:
        metrics.price = snap.price
        state.last_price = snap.price

    vwap = 0.0
    if snap.trend_analysis and snap.trend_analysis.vwap:
        vwap = snap.trend_analysis.vwap
    elif snap.volume_liquidity and snap.volume_liquidity.vwap:
        vwap = snap.volume_liquidity.vwap

    if vwap > 0 and metrics.vwap <= 0:
        metrics.vwap = vwap
    if metrics.vwap > 0 and metrics.price > 0:
        metrics.price_vs_vwap_pct = (metrics.price - metrics.vwap) / metrics.vwap * 100.0

    if metrics.spread_bps >= 500 and snap.volume_engine:
        est_spread = min(500.0, max(5.0, (snap.volume_engine.relative_volume or 1.0) * 8.0))
        metrics.spread_bps = est_spread

    if metrics.rvol <= 0 and snap.volume_engine:
        metrics.rvol = snap.volume_engine.relative_volume or snap.volume_engine.session_rvol or 0.0

    if metrics.data_age_seconds >= 9999 and snap.last_updated:
        try:
            ts = snap.last_updated.replace("Z", "+00:00")
            updated = datetime.fromisoformat(ts)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            metrics.data_age_seconds = max(
                0.0,
                (datetime.now(timezone.utc) - updated).total_seconds(),
            )
        except ValueError:
            pass

    if not state.linked_news and snap.news:
        headline = snap.news[0].title if snap.news else ""
        if headline and not metrics.breakout:
            metrics.breakout = snap.smc.bos if snap.smc else False

    return metrics


def scanner_snapshots_by_symbol() -> dict[str, StockSnapshot]:
    out: dict[str, StockSnapshot] = {}
    for sym, snap in market_scanner._snapshots.items():
        if snap.price > 0:
            out[sym.upper()] = snap
    state = market_scanner.get_state()
    if state:
        for snap in state.snapshots:
            if snap.price > 0:
                out[snap.symbol.upper()] = snap
    return out
