"""Pre-Move VWAP analysis."""

from __future__ import annotations

import pandas as pd

from analysis.indicators import vwap as calc_vwap
from models.pre_move import PreMoveVwapMetrics


def compute_vwap_metrics(bars: pd.DataFrame, price: float) -> PreMoveVwapMetrics:
    m = PreMoveVwapMetrics()
    if bars.empty or price <= 0:
        return m

    vwap_val = float(calc_vwap(
        bars["high"].astype(float),
        bars["low"].astype(float),
        bars["close"].astype(float),
        bars["volume"].astype(float),
    ))
    m.vwap = round(vwap_val, 4)
    if m.vwap <= 0:
        return m

    m.distance_from_vwap_pct = round((price - m.vwap) / m.vwap * 100.0, 2)

    closes = bars["close"].astype(float)
    if len(closes) >= 5:
        was_below = float(closes.iloc[-5]) < m.vwap * 0.998
        now_above = price >= m.vwap * 0.999
        m.vwap_reclaim = was_below and now_above
        m.vwap_hold = price >= m.vwap and float(closes.iloc[-3:].min()) >= m.vwap * 0.995

    if len(bars) >= 8:
        recent = bars.tail(3)
        touched = any(float(row["low"]) <= m.vwap * 1.002 for _, row in recent.iterrows())
        bounced = float(recent["close"].iloc[-1]) > float(recent["open"].iloc[-1])
        m.vwap_support_test = touched and bounced and price >= m.vwap * 0.998

    return m


def score_vwap_component(v: PreMoveVwapMetrics, *, max_pts: float = 15.0) -> float:
    if v.vwap <= 0:
        return 0.0
    pts = 0.0
    if v.vwap_reclaim:
        pts += 6.0
    if v.vwap_hold:
        pts += 4.0
    if v.vwap_support_test:
        pts += 3.0
    dist = abs(v.distance_from_vwap_pct)
    if dist <= 1.0:
        pts += 2.0
    elif dist <= 2.5:
        pts += 1.0
    elif v.distance_from_vwap_pct < -5.0:
        pts -= 3.0
    return max(0.0, min(max_pts, round(pts, 1)))
