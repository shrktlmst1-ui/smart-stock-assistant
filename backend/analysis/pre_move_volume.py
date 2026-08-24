"""Pre-Move volume acceleration metrics from real minute bars."""

from __future__ import annotations

import pandas as pd

from analysis.pre_move_early_activity import compute_enhanced_volume_acceleration
from models.pre_move import PreMoveVolumeMetrics


def compute_volume_metrics(bars: pd.DataFrame) -> PreMoveVolumeMetrics:
    """Compute volume metrics from OHLCV minute bars. Empty bars → zeros."""
    m = PreMoveVolumeMetrics()
    if bars.empty or "volume" not in bars.columns:
        return m

    vols = bars["volume"].astype(float)
    n = len(vols)
    if n == 0:
        return m

    m.volume_1m = int(vols.iloc[-1])
    m.volume_3m = int(vols.tail(min(3, n)).sum())
    m.volume_5m = int(vols.tail(min(5, n)).sum())
    m.volume_10m = int(vols.tail(min(10, n)).sum())

    if n >= 6:
        prior_avg = float(vols.iloc[-6:-1].mean()) or 1.0
        m.volume_acceleration = round(m.volume_1m / prior_avg, 2)
    elif n >= 2:
        prior_avg = float(vols.iloc[:-1].mean()) or 1.0
        m.volume_acceleration = round(m.volume_1m / prior_avg, 2)

    if n >= 6:
        prev_1m = float(vols.iloc[-2]) or 1.0
        m.volume_vs_previous_1m = round((m.volume_1m - prev_1m) / prev_1m, 2)
    if n >= 10:
        prev_5m = float(vols.iloc[-10:-5].sum()) or 1.0
        m.volume_growth_rate = round((m.volume_5m - prev_5m) / prev_5m, 2)
        m.volume_vs_previous_5m = m.volume_growth_rate

    if n >= 25:
        buckets = [float(vols.iloc[i : i + 5].sum()) for i in range(n - 25, n - 5, 5)]
        avg_5m = sum(buckets) / len(buckets) if buckets else float(m.volume_5m) or 1.0
        m.rvol = round(m.volume_5m / avg_5m, 2) if avg_5m else 0.0
    elif n >= 10:
        prior = float(vols.iloc[:-5].tail(20).sum()) / max(len(vols.iloc[:-5].tail(20)) / 5, 1)
        m.rvol = round(m.volume_5m / prior, 2) if prior else 0.0
    else:
        avg = float(vols.mean()) or 1.0
        m.rvol = round(m.volume_1m / avg, 2)

    enhanced = compute_enhanced_volume_acceleration(bars)
    m.volume_acceleration_1m = float(enhanced.get("volume_acceleration_1m", 0.0))
    m.volume_acceleration_3m = float(enhanced.get("volume_acceleration_3m", 0.0))
    m.volume_acceleration_slope = float(enhanced.get("volume_acceleration_slope", 0.0))
    m.vol_1m_prev = int(enhanced.get("vol_1m_prev", 0))
    m.vol_3m_current = int(enhanced.get("vol_3m_current", 0))
    m.dollar_volume_1m = float(enhanced.get("dollar_volume_1m", 0.0))
    m.dollar_volume_3m = float(enhanced.get("dollar_volume_3m", 0.0))
    m.dollar_volume_growth = float(enhanced.get("dollar_volume_growth", 0.0))
    # Prefer slope-based accel for scoring when available
    if m.volume_acceleration_slope >= 1.1:
        m.volume_acceleration = max(m.volume_acceleration, m.volume_acceleration_slope)

    return m


def compute_rvol_same_time(
    today_bars: pd.DataFrame,
    prior_day_bars: pd.DataFrame | None,
) -> float | None:
    """RVOL at same time-of-day vs prior session. Uses 1m + 5m when available."""
    if today_bars.empty or prior_day_bars is None or prior_day_bars.empty:
        return None
    if "timestamp" not in today_bars.columns or "timestamp" not in prior_day_bars.columns:
        return None

    last_ts = today_bars["timestamp"].iloc[-1]
    try:
        t = last_ts.time()
    except Exception:
        return None

    prior = prior_day_bars.copy()
    prior_ts = prior["timestamp"]
    try:
        mask = prior_ts.dt.time <= t
        prior_slice = prior.loc[mask]
    except Exception:
        return None

    if prior_slice.empty:
        return None

    today_1m = float(today_bars["volume"].astype(float).iloc[-1])
    prior_1m = float(prior_slice["volume"].astype(float).iloc[-1]) if len(prior_slice) >= 1 else 0.0
    today_5m = float(today_bars["volume"].astype(float).tail(5).sum())
    prior_5m = float(prior_slice["volume"].astype(float).tail(5).sum())

    ratios: list[float] = []
    if prior_1m > 0 and today_1m > 0:
        ratios.append(today_1m / prior_1m)
    if prior_5m > 0 and today_5m > 0:
        ratios.append(today_5m / prior_5m)

    if not ratios:
        return None
    return round(max(ratios), 2)


def score_volume_component(m: PreMoveVolumeMetrics, *, max_pts: float = 12.0) -> float:
    """Legacy volume component — complements Early Activity (absolute + growth)."""
    pts = 0.0
    accel = max(m.volume_acceleration, m.volume_acceleration_1m, m.volume_acceleration_slope)
    if accel >= 2.5:
        pts += 5.0
    elif accel >= 1.5:
        pts += 3.5
    elif accel >= 1.2:
        pts += 2.0
    elif accel >= 1.0:
        pts += 1.0

    rvol = m.rvol_same_time if m.rvol_same_time is not None else m.rvol
    if rvol >= 3.0:
        pts += 3.0
    elif rvol >= 2.0:
        pts += 2.0
    elif rvol >= 1.5:
        pts += 1.5
    elif rvol >= 1.2:
        pts += 1.0

    if m.dollar_volume_growth >= 0.8:
        pts += 2.0
    elif m.dollar_volume_growth >= 0.4:
        pts += 1.0

    if m.volume_growth_rate >= 1.0:
        pts += 1.5
    elif m.volume_growth_rate >= 0.5:
        pts += 0.5

    return min(max_pts, round(pts, 1))
