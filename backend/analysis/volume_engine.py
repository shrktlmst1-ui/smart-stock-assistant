"""Volume Engine — real RVOL, spike, divergence from Massive candles."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.trading import VolumeEngine


def _volume_divergence(df: pd.DataFrame) -> tuple[bool, str]:
    """Detect price/volume divergence over two windows."""
    if len(df) < 40:
        return False, "none"

    w1 = df.iloc[-20:-10]
    w2 = df.tail(10)
    if w1.empty or w2.empty:
        return False, "none"

    h1, h2 = float(w1["high"].max()), float(w2["high"].max())
    l1, l2 = float(w1["low"].min()), float(w2["low"].min())
    v1, v2 = float(w1["volume"].sum()), float(w2["volume"].sum())

    # Bearish divergence: higher high, lower volume
    if h2 > h1 * 1.002 and v2 < v1 * 0.85:
        return True, "bearish"
    # Bullish divergence: lower low, lower volume on decline
    if l2 < l1 * 0.998 and v2 < v1 * 0.85:
        return True, "bullish"
    return False, "none"


def analyze_volume(df: pd.DataFrame) -> VolumeEngine:
    if len(df) < 20:
        return VolumeEngine(summary="بيانات غير كافية")

    volumes = df["volume"].astype(float)
    curr_vol = float(volumes.iloc[-1])

    # RVOL: current bar vs 20-period SMA (standard intraday measure)
    avg_vol = float(volumes.tail(20).mean())
    rel_vol = curr_vol / avg_vol if avg_vol > 0 else 1.0

    # Session RVOL: compare to same-length rolling median for stability
    median_vol = float(volumes.tail(50).median()) if len(volumes) >= 50 else avg_vol
    session_rvol = curr_vol / median_vol if median_vol > 0 else rel_vol

    spike = rel_vol >= 2.0
    unusual = rel_vol >= 2.5 or session_rvol >= 2.5

    div, div_dir = _volume_divergence(df)

    # Z-score for institutional activity (real statistical measure)
    vol_arr = volumes.tail(30).values
    mean_v = float(np.mean(vol_arr))
    std_v = float(np.std(vol_arr)) or 1.0
    z = (curr_vol - mean_v) / std_v
    dark_pool_est = 0.0
    last = df.iloc[-1]
    range_pct = (float(last["high"]) - float(last["low"])) / float(last["close"]) * 100 if last["close"] else 1
    if z > 1.5 and range_pct < 0.4:
        dark_pool_est = min(100.0, z * 20 + (0.4 - range_pct) * 50)

    parts = [f"RVOL {rel_vol:.2f}x"]
    if spike:
        parts.append("Volume Spike")
    if unusual:
        parts.append("Unusual Volume")
    if div:
        parts.append(f"Divergence {div_dir}")

    return VolumeEngine(
        volume_spike=spike,
        relative_volume=round(rel_vol, 3),
        unusual_volume=unusual,
        volume_divergence=div,
        divergence_direction=div_dir if div else "none",
        session_rvol=round(session_rvol, 3),
        volume_zscore=round(z, 2),
        dark_pool_estimate=round(dark_pool_est, 1),
        summary=" | ".join(parts),
    )


def volume_score(vol: VolumeEngine, price_direction: float) -> float:
    """0-100 — high when volume confirms price direction."""
    score = 50.0
    rvol = vol.relative_volume
    if price_direction > 0:
        score += min(25, (rvol - 1) * 15) if rvol > 1 else -10
    elif price_direction < 0:
        score -= min(25, (rvol - 1) * 15) if rvol > 1 else 10

    if vol.volume_divergence and vol.divergence_direction == "bullish":
        score += 15
    elif vol.volume_divergence and vol.divergence_direction == "bearish":
        score -= 15

    if vol.unusual_volume and not vol.volume_divergence:
        score += 5 if price_direction > 0 else -5 if price_direction < 0 else 0

    return max(0.0, min(100.0, score))
