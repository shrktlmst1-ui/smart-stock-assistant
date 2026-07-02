"""Institutional coarse scorer — 0-100 from live snapshot metrics (no placeholders)."""

from __future__ import annotations

import math

from config import SCANNER_MIN_MARKET_CAP
from services.scanner_filters import TickerMetrics, _safe_float


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def compute_coarse_institutional_score(
    m: TickerMetrics,
    snapshot_item: dict,
) -> float:
    """
    Score 0-100 from snapshot-only data before deep bar analysis.
    Factors: RVOL, volume spike, momentum, gap, premarket, VWAP, ATR proxy, liquidity.
    """
    day = snapshot_item.get("day") or {}
    prev = snapshot_item.get("prevDay") or {}
    prev_close = _safe_float(prev.get("c"), m.price)
    vwap = _safe_float(day.get("vw"), m.price)

    gap_pct = 0.0
    if prev_close > 0 and m.day_open > 0:
        gap_pct = (m.day_open - prev_close) / prev_close * 100

    atr_pct = m.spread_pct
    price_vs_vwap = (m.price - vwap) / vwap * 100 if vwap else 0.0

    score = 0.0

    # Relative volume (0-18)
    score += _clamp(min(m.relative_volume, 4) / 4 * 18)

    # Average volume strength (0-12)
    avg_vol = m.prev_volume or m.volume
    score += _clamp(math.log10(max(avg_vol, 1)) / 7 * 12)

    # Volume spike (0-10)
    if m.volume_spike:
        score += 10
    elif m.relative_volume >= 1.5:
        score += 5

    # Momentum (0-12)
    score += _clamp(min(abs(m.change_percent), 12) / 12 * 12)

    # Premarket activity (0-10)
    score += _clamp(min(abs(m.premarket_change_pct), 5) / 5 * 10)

    # Gap % (0-8)
    score += _clamp(min(abs(gap_pct), 6) / 6 * 8)

    # VWAP alignment (0-10)
    if m.change_percent > 0 and price_vs_vwap > 0:
        score += _clamp(min(price_vs_vwap, 3) / 3 * 10)
    elif m.change_percent < 0 and price_vs_vwap < 0:
        score += _clamp(min(abs(price_vs_vwap), 3) / 3 * 10)
    else:
        score += 3

    # ATR / volatility sweet spot (0-8) — moderate intraday range
    if 0.4 <= atr_pct <= 4.0:
        score += 8
    elif atr_pct <= 6.0:
        score += 4

    # Float / cap quality (0-6)
    if m.market_cap >= 500_000_000:
        score += 6
    elif m.market_cap >= SCANNER_MIN_MARKET_CAP:
        score += 3

    # Opening range breakout bonus (0-6)
    if m.opening_range_breakout:
        score += 6

    return round(_clamp(score), 1)
