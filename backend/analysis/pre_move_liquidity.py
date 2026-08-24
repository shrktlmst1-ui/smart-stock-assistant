"""Pre-Move liquidity scoring."""

from __future__ import annotations

from models.pre_move import PreMoveLiquidityMetrics


def compute_liquidity_metrics(
    price: float,
    volume: int,
    spread_percent: float,
    *,
    bar_count: int = 0,
) -> PreMoveLiquidityMetrics:
    m = PreMoveLiquidityMetrics(
        spread_percent=round(spread_percent, 2),
        dollar_volume=round(price * volume, 2),
        trade_frequency=round(bar_count / max(bar_count, 1), 2) if bar_count else 0.0,
    )
    pts = 100.0

    if spread_percent > 3.0:
        pts -= 40.0
    elif spread_percent > 2.0:
        pts -= 25.0
    elif spread_percent > 1.0:
        pts -= 10.0

    dollar = m.dollar_volume
    if dollar < 50_000:
        pts -= 35.0
    elif dollar < 150_000:
        pts -= 20.0
    elif dollar < 500_000:
        pts -= 8.0

    if volume < 50_000:
        pts -= 25.0
    elif volume < 100_000:
        pts -= 12.0

    m.liquidity_score = max(0.0, min(100.0, round(pts, 1)))
    return m


def score_liquidity_component(liq: PreMoveLiquidityMetrics, *, max_pts: float = 10.0) -> float:
    return min(max_pts, round(liq.liquidity_score / 100.0 * max_pts, 1))
