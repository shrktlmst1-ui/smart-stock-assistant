"""Pre-Move price compression and structure pressure metrics."""

from __future__ import annotations

import pandas as pd

from analysis.indicators import atr as calc_atr
from analysis.structure import analyze_structure, find_swing_points
from analysis.smc import analyze_smc
from models.pre_move import PreMoveCompressionMetrics


def compute_compression_metrics(bars: pd.DataFrame, price: float) -> PreMoveCompressionMetrics:
    m = PreMoveCompressionMetrics()
    if bars.empty or len(bars) < 3:
        return m

    highs = bars["high"].astype(float)
    lows = bars["low"].astype(float)
    closes = bars["close"].astype(float)

    recent = bars.tail(min(10, len(bars)))
    prior = bars.iloc[-25:-10] if len(bars) >= 25 else bars.iloc[:-min(10, len(bars))]
    if not prior.empty and len(bars) >= 6:
        recent_range = float(recent["high"].max() - recent["low"].min())
        prior_range = float(prior["high"].max() - prior["low"].min()) or 1.0
        m.range_contraction = round(max(0.0, 1.0 - recent_range / prior_range), 2)
    elif len(bars) >= 4:
        r3 = float(highs.tail(3).max() - lows.tail(3).min())
        r_old = float(highs.iloc[:-3].max() - lows.iloc[:-3].min()) if len(bars) > 3 else r3
        if r_old > 0:
            m.range_contraction = round(max(0.0, 1.0 - r3 / r_old), 2)

    try:
        if len(bars) >= 20:
            recent_atr = calc_atr(
                recent["high"].astype(float),
                recent["low"].astype(float),
                recent["close"].astype(float),
                period=min(14, len(recent) - 1),
            )
            prior_atr = calc_atr(
                prior["high"].astype(float),
                prior["low"].astype(float),
                prior["close"].astype(float),
                period=min(14, len(prior) - 1),
            ) or recent_atr
            m.atr_contraction = round(max(0.0, 1.0 - recent_atr / prior_atr), 2) if prior_atr else 0.0
    except Exception:
        pass

    swings = find_swing_points(bars.tail(min(40, len(bars))))
    low_swings = [s.price for s in swings if s.kind == "low"]
    if len(low_swings) >= 2:
        higher = sum(1 for i in range(1, len(low_swings)) if low_swings[i] > low_swings[i - 1])
        m.higher_lows_score = round(higher / max(len(low_swings) - 1, 1), 2)
    elif len(bars) >= 3:
        micro_lows = lows.tail(min(6, len(bars))).tolist()
        higher = sum(1 for i in range(1, len(micro_lows)) if micro_lows[i] >= micro_lows[i - 1] * 0.998)
        m.higher_lows_score = round(higher / max(len(micro_lows) - 1, 1), 2)

    high_swings = [s.price for s in swings if s.kind == "high"]
    if high_swings:
        resistance = max(high_swings)
        if resistance > 0 and price > 0:
            dist = (resistance - price) / price * 100.0
            if 0 < dist <= 3.0:
                m.resistance_pressure = round(1.0 - dist / 3.0, 2)
            elif dist <= 0:
                m.resistance_pressure = 0.3

    m.compression_score = round(
        (m.range_contraction * 0.35 + m.atr_contraction * 0.25 + m.higher_lows_score * 0.25 + m.resistance_pressure * 0.15),
        2,
    )
    return m


def score_structure_component(
    compression: PreMoveCompressionMetrics,
    bars: pd.DataFrame,
    price: float,
    *,
    max_pts: float = 20.0,
) -> float:
    pts = compression.compression_score * max_pts * 0.5

    if not bars.empty and len(bars) >= 20:
        struct = analyze_structure(bars, price)
        smc, _ = analyze_smc(bars, price)
        if struct.bos and struct.bos_direction == "bullish":
            pts += 4.0
        if struct.choch and struct.choch_direction == "bullish":
            pts += 3.0
        if smc.liquidity_sweep and smc.sweep_direction == "bullish":
            pts += 4.0
        if smc.order_blocks:
            pts += 2.0
        if smc.fair_value_gaps:
            pts += 1.0

    return min(max_pts, round(pts, 1))
