"""Pre-Move breakout pressure — distance to key resistance levels."""

from __future__ import annotations

import pandas as pd

from analysis.structure import find_swing_points
from models.pre_move import PreMoveBreakoutMetrics


def compute_breakout_metrics(
    bars: pd.DataFrame,
    price: float,
    *,
    premarket_high: float = 0.0,
    day_high: float = 0.0,
    prev_day_high: float = 0.0,
) -> PreMoveBreakoutMetrics:
    m = PreMoveBreakoutMetrics(
        premarket_high=premarket_high,
        day_high=day_high,
        prev_day_high=prev_day_high,
    )
    candidates: list[float] = []
    if premarket_high > 0:
        candidates.append(premarket_high)
    if day_high > 0:
        candidates.append(day_high)
    if prev_day_high > 0:
        candidates.append(prev_day_high)

    if not bars.empty:
        pm_high = float(bars["high"].astype(float).max())
        candidates.append(pm_high)
        swings = find_swing_points(bars.tail(60))
        high_swings = [s.price for s in swings if s.kind == "high"]
        if high_swings:
            candidates.append(max(high_swings))
        m.support = round(float(bars["low"].astype(float).tail(15).min()), 4)

    candidates = [c for c in candidates if c > price * 0.995]
    if not candidates:
        m.resistance = round(price * 1.03, 4)
    else:
        m.resistance = round(min(candidates), 4)

    if price > 0 and m.resistance > price:
        m.distance_to_breakout_pct = round((m.resistance - price) / price * 100.0, 2)
    else:
        m.distance_to_breakout_pct = 0.0

    return m


def score_breakout_pressure(b: PreMoveBreakoutMetrics, *, max_pts: float = 15.0) -> float:
    pts = 0.0
    d = b.distance_to_breakout_pct
    if 0.5 <= d <= 2.5:
        pts += 10.0
    elif 2.5 < d <= 4.0:
        pts += 7.0
    elif 4.0 < d <= 6.0:
        pts += 4.0
    elif d <= 0.5:
        pts += 5.0
    elif d > 8.0:
        pts += 1.0
    return min(max_pts, round(pts, 1))
