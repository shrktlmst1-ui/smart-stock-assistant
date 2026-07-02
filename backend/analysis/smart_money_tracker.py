"""Smart Money Tracker — whale orders, accumulation, distribution, absorption, iceberg."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.trading import SmartMoneyTracker


def _whale_detected(volumes: np.ndarray, z: float) -> bool:
    mean_v = float(np.mean(volumes))
    return z > 2.5 or float(volumes[-1]) > mean_v * 3.0


def _hidden_accumulation(df: pd.DataFrame) -> bool:
    """Flat/soft price with rising volume and closes in upper range — stealth buying."""
    if len(df) < 15:
        return False
    w = df.tail(10)
    price_chg = (float(w["close"].iloc[-1]) - float(w["close"].iloc[0])) / float(w["close"].iloc[0]) * 100
    vol_trend = float(w["volume"].iloc[-3:].mean()) / max(float(w["volume"].iloc[:3].mean()), 1)
    upper_closes = 0
    for _, row in w.iterrows():
        rng = float(row["high"]) - float(row["low"])
        if rng <= 0:
            continue
        if (float(row["close"]) - float(row["low"])) / rng > 0.55:
            upper_closes += 1
    return price_chg < 0.5 and vol_trend > 1.25 and upper_closes >= 6


def _hidden_distribution(df: pd.DataFrame) -> bool:
    """Price holds/up slightly with rising volume and lower-range closes — stealth selling."""
    if len(df) < 15:
        return False
    w = df.tail(10)
    price_chg = (float(w["close"].iloc[-1]) - float(w["close"].iloc[0])) / float(w["close"].iloc[0]) * 100
    vol_trend = float(w["volume"].iloc[-3:].mean()) / max(float(w["volume"].iloc[:3].mean()), 1)
    lower_closes = 0
    for _, row in w.iterrows():
        rng = float(row["high"]) - float(row["low"])
        if rng <= 0:
            continue
        if (float(row["close"]) - float(row["low"])) / rng < 0.45:
            lower_closes += 1
    return price_chg > -0.3 and vol_trend > 1.25 and lower_closes >= 6


def _absorption(df: pd.DataFrame, price: float) -> bool:
    """High volume with tight range — supply/demand absorbed at level."""
    if len(df) < 10:
        return False
    last5 = df.tail(5)
    vol_avg = float(df["volume"].tail(20).mean()) or 1
    vol_ratio = float(last5["volume"].mean()) / vol_avg
    ranges = (last5["high"] - last5["low"]) / price * 100
    avg_range = float(ranges.mean())
    return vol_ratio >= 1.8 and avg_range < 0.35


def _iceberg_activity(df: pd.DataFrame) -> bool:
    """Repeated similar-volume prints at stable price — iceberg order slicing."""
    if len(df) < 12:
        return False
    w = df.tail(8)
    vols = w["volume"].to_numpy(dtype=float)
    if float(np.std(vols)) == 0:
        return False
    vol_cv = float(np.std(vols) / np.mean(vols))  # coefficient of variation
    prices = w["close"].to_numpy(dtype=float)
    price_range_pct = (float(prices.max()) - float(prices.min())) / float(prices.mean()) * 100
    high_vol = float(np.mean(vols)) > float(df["volume"].tail(30).mean()) * 1.3
    return high_vol and vol_cv < 0.35 and price_range_pct < 0.25


def analyze_smart_money(df: pd.DataFrame, price: float) -> SmartMoneyTracker:
    if len(df) < 20:
        return SmartMoneyTracker(summary="بيانات غير كافية")

    volumes = df["volume"].tail(30).to_numpy(dtype=float)
    mean_v = float(np.mean(volumes))
    std_v = float(np.std(volumes)) or 1.0
    z = (float(volumes[-1]) - mean_v) / std_v

    whale = _whale_detected(volumes, z)
    accum = _hidden_accumulation(df)
    distrib = _hidden_distribution(df)
    absorb = _absorption(df, price)
    iceberg = _iceberg_activity(df)

    score = 50.0
    if whale:
        score += 18
    if accum:
        score += 15
    if distrib:
        score -= 15
    if absorb:
        score += 10
    if iceberg:
        score += 8

    last = df.iloc[-1]
    rng = float(last["high"]) - float(last["low"])
    close_pos = (float(last["close"]) - float(last["low"])) / rng if rng > 0 else 0.5
    if float(last["close"]) > float(last["open"]):
        score += close_pos * 8
    else:
        score -= (1 - close_pos) * 8

    score = max(0.0, min(100.0, score))

    if accum or (whale and float(last["close"]) > float(last["open"])):
        flow = "bullish"
    elif distrib or (whale and float(last["close"]) < float(last["open"])):
        flow = "bearish"
    else:
        flow = "neutral"

    parts: list[str] = []
    if whale:
        parts.append("Whale Order")
    if accum:
        parts.append("Hidden Accumulation")
    if distrib:
        parts.append("Hidden Distribution")
    if absorb:
        parts.append("Absorption")
    if iceberg:
        parts.append("Iceberg Activity")

    return SmartMoneyTracker(
        whale_order=whale,
        hidden_accumulation=accum,
        hidden_distribution=distrib,
        absorption=absorb,
        iceberg_activity=iceberg,
        activity_score=round(score, 1),
        flow_direction=flow,
        summary=" | ".join(parts) if parts else f"Smart Money {score:.0f}/100",
    )


def smart_money_score(smt: SmartMoneyTracker) -> float:
    return smt.activity_score
