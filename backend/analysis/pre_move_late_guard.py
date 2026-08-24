"""Late Move Guard — prevent chasing extended moves."""

from __future__ import annotations

import pandas as pd

from analysis.indicators import rsi as calc_rsi
from config import PREMOVE_LATE_EXTENSION_PCT, PREMOVE_LATE_RSI
from models.pre_move import PreMoveLateMoveMetrics


def compute_late_move_guard(
    bars: pd.DataFrame,
    price: float,
    change_percent: float,
    *,
    vwap: float = 0.0,
    base_price: float = 0.0,
    spread_percent: float = 0.0,
    risk_reward: float = 0.0,
) -> PreMoveLateMoveMetrics:
    m = PreMoveLateMoveMetrics()
    factors = 0

    if bars.empty or price <= 0:
        return m

    closes = bars["close"].astype(float)
    highs = bars["high"].astype(float)
    vols = bars["volume"].astype(float)

    rsi_val: float | None = None
    if len(closes) >= 15:
        rsi_val = calc_rsi(closes, period=14)
        m.rsi = round(rsi_val, 1)
        if rsi_val >= PREMOVE_LATE_RSI:
            factors += 1
            m.reasons.append(f"RSI {rsi_val:.0f} overbought")

    if vwap > 0:
        m.distance_from_vwap_pct = round((price - vwap) / vwap * 100.0, 2)
        if m.distance_from_vwap_pct >= 12.0:
            factors += 1
            m.reasons.append(f"{m.distance_from_vwap_pct:.1f}% above VWAP")

    if base_price > 0:
        m.extension_from_base_pct = round((price - base_price) / base_price * 100.0, 2)
        if m.extension_from_base_pct >= PREMOVE_LATE_EXTENSION_PCT:
            factors += 1
            m.reasons.append(f"+{m.extension_from_base_pct:.1f}% from base")

    if change_percent >= 20.0:
        factors += 1
        m.reasons.append(f"Session move +{change_percent:.1f}%")

    green_streak = 0
    for i in range(len(closes) - 1, max(len(closes) - 8, -1), -1):
        body_pct = (float(closes.iloc[i]) - float(bars["open"].astype(float).iloc[i])) / price * 100
        if body_pct > 1.5:
            green_streak += 1
        else:
            break
    m.consecutive_expansion_candles = green_streak
    if green_streak >= 4:
        factors += 1
        m.reasons.append(f"{green_streak} expansion candles")

    if len(vols) >= 10:
        peak = float(vols.tail(10).max())
        recent = float(vols.iloc[-1])
        if peak > 0 and recent < peak * 0.55 and price >= float(closes.iloc[-5:].max()) * 0.98:
            m.volume_exhaustion = True
            factors += 1
            m.reasons.append("Volume climax / exhaustion")

    if spread_percent > 2.5:
        factors += 1
        m.reasons.append(f"Spread widened to {spread_percent:.1f}%")

    if 0 < risk_reward < 1.0:
        factors += 1
        m.reasons.append(f"Poor R:R {risk_reward:.1f}")

    m.late_move_score = round(min(100.0, factors * 18.0), 1)
    m.is_too_late = factors >= 3 or (
        factors >= 2 and (m.rsi or 0) >= 80 and m.extension_from_base_pct >= 15
    )
    return m
