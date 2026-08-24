"""Pre-Move entry levels — trigger, entry range, stop, targets."""

from __future__ import annotations

import pandas as pd

from analysis.indicators import atr as calc_atr
from models.pre_move import PreMoveBreakoutMetrics


def compute_trade_levels(
    price: float,
    breakout: PreMoveBreakoutMetrics,
    bars: pd.DataFrame,
    *,
    vwap: float = 0.0,
) -> tuple[float, float, float, float, float, float, float]:
    """Returns trigger, entry_low, entry_high, stop, tp1, tp2, rrr."""
    trigger = breakout.resistance if breakout.resistance > price else round(price * 1.015, 4)
    entry_low = round(trigger, 4)
    entry_high = round(trigger * 1.02, 4)

    supports = [breakout.support] if breakout.support > 0 else []
    if vwap > 0:
        supports.append(vwap * 0.995)
    if not bars.empty:
        supports.append(float(bars["low"].astype(float).tail(15).min()) * 0.99)
        try:
            atr_val = calc_atr(
                bars["high"].astype(float),
                bars["low"].astype(float),
                bars["close"].astype(float),
                period=14,
            )
            supports.append(price - atr_val * 1.2)
        except Exception:
            pass

    stop = round(max(s for s in supports if s > 0 and s < price) if supports else price * 0.96, 4)
    risk = max(entry_low - stop, price * 0.015)

    tp1 = round(entry_low + risk * 1.5, 4)
    tp2 = round(entry_low + risk * 2.5, 4)

    candidates_tp = [c for c in [breakout.premarket_high, breakout.day_high, breakout.prev_day_high] if c > entry_low]
    if candidates_tp:
        nearest = min(candidates_tp, key=lambda x: abs(x - tp1))
        if nearest > entry_low:
            tp1 = round(nearest, 4)
            tp2 = round(tp1 + risk * 1.5, 4)

    rrr = round((tp1 - entry_low) / risk, 2) if risk > 0 else 0.0
    return trigger, entry_low, entry_high, stop, tp1, tp2, rrr
