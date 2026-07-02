"""Market structure — swing points, HH/HL/LH/LL, BOS, CHOCH."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

TrendBias = Literal["bullish", "bearish", "neutral"]
_STRUCTURE_LOOKBACK = 120


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: Literal["high", "low"]


@dataclass
class MarketStructure:
    swings: list[SwingPoint]
    trend: TrendBias
    last_swing_high: float | None
    last_swing_low: float | None
    prev_swing_high: float | None
    prev_swing_low: float | None
    bos: bool
    bos_direction: Literal["bullish", "bearish", "none"]
    choch: bool
    choch_direction: Literal["bullish", "bearish", "none"]
    mss: bool = False
    mss_direction: Literal["bullish", "bearish", "none"] = "none"


def find_swing_points(df: pd.DataFrame, left: int = 3, right: int = 3) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    if len(df) < left + right + 1:
        return swings

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    n = len(highs)
    offset = max(0, n - _STRUCTURE_LOOKBACK)
    start = max(left, offset)

    for i in range(start, n - right):
        hi = highs[i - left : i + right + 1]
        lo = lows[i - left : i + right + 1]
        if highs[i] >= hi.max():
            swings.append(SwingPoint(index=i, price=float(highs[i]), kind="high"))
        if lows[i] <= lo.min():
            swings.append(SwingPoint(index=i, price=float(lows[i]), kind="low"))

    swings.sort(key=lambda s: s.index)
    return swings


def _trend_from_swings(swings: list[SwingPoint]) -> TrendBias:
    highs = [s.price for s in swings if s.kind == "high"]
    lows = [s.price for s in swings if s.kind == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return "neutral"
    hh = highs[-1] > highs[-2]
    hl = lows[-1] > lows[-2]
    lh = highs[-1] < highs[-2]
    ll = lows[-1] < lows[-2]
    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "neutral"


def analyze_structure(df: pd.DataFrame, price: float) -> MarketStructure:
    window = df.tail(_STRUCTURE_LOOKBACK) if len(df) > _STRUCTURE_LOOKBACK else df
    swings = find_swing_points(window)
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    last_sh = highs[-1].price if highs else None
    prev_sh = highs[-2].price if len(highs) >= 2 else None
    last_sl = lows[-1].price if lows else None
    prev_sl = lows[-2].price if len(lows) >= 2 else None

    trend = _trend_from_swings(swings)
    close = float(df["close"].iloc[-1])

    bos = False
    bos_dir: Literal["bullish", "bearish", "none"] = "none"
    choch = False
    choch_dir: Literal["bullish", "bearish", "none"] = "none"

    if last_sh is not None and close > last_sh:
        if trend == "bullish":
            bos = True
            bos_dir = "bullish"
        else:
            choch = True
            choch_dir = "bullish"

    if last_sl is not None and close < last_sl:
        if trend == "bearish":
            bos = True
            bos_dir = "bearish"
        else:
            choch = True
            choch_dir = "bearish"

    # MSS — structural shift after sweep + break of prior swing sequence
    mss = False
    mss_dir: Literal["bullish", "bearish", "none"] = "none"
    if len(df) >= 5:
        last_bar = df.iloc[-1]
        swept_low = (
            last_sl is not None
            and float(last_bar["low"]) < last_sl
            and float(last_bar["close"]) > last_sl
        )
        swept_high = (
            last_sh is not None
            and float(last_bar["high"]) > last_sh
            and float(last_bar["close"]) < last_sh
        )

        if swept_low and choch and choch_dir == "bullish":
            mss = True
            mss_dir = "bullish"
        elif swept_high and choch and choch_dir == "bearish":
            mss = True
            mss_dir = "bearish"
        elif choch and prev_sh and prev_sl:
            if choch_dir == "bullish" and close > prev_sh and trend == "bearish":
                mss = True
                mss_dir = "bullish"
            elif choch_dir == "bearish" and close < prev_sl and trend == "bullish":
                mss = True
                mss_dir = "bearish"

    return MarketStructure(
        swings=swings,
        trend=trend,
        last_swing_high=last_sh,
        last_swing_low=last_sl,
        prev_swing_high=prev_sh,
        prev_swing_low=prev_sl,
        bos=bos,
        bos_direction=bos_dir,
        choch=choch,
        choch_direction=choch_dir,
        mss=mss,
        mss_direction=mss_dir,
    )
