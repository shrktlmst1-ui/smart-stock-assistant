"""Liquidity Engine — swing-based buy/sell-side liquidity."""

from __future__ import annotations

import pandas as pd

from analysis.structure import MarketStructure
from models.trading import LiquidityEngine


def analyze_liquidity(
    df: pd.DataFrame,
    price: float,
    structure: MarketStructure,
) -> LiquidityEngine:
    if len(df) < 15:
        return LiquidityEngine(summary="بيانات غير كافية")

    last = df.iloc[-1]
    vol_avg = float(df["volume"].tail(20).mean()) or 1
    vol_ratio = float(last["volume"]) / vol_avg

    buy_side = 50.0
    sell_side = 50.0

    if structure.last_swing_high:
        dist_pct = (structure.last_swing_high - price) / price * 100
        buy_side = max(0.0, min(100.0, 100 - dist_pct * 20))

    if structure.last_swing_low:
        dist_pct = (price - structure.last_swing_low) / price * 100
        sell_side = max(0.0, min(100.0, 100 - dist_pct * 20))

    grab = False
    grab_dir = "none"
    if structure.last_swing_high and float(last["high"]) > structure.last_swing_high:
        if float(last["close"]) < structure.last_swing_high and vol_ratio >= 1.2:
            grab = True
            grab_dir = "bearish"
    if structure.last_swing_low and float(last["low"]) < structure.last_swing_low:
        if float(last["close"]) > structure.last_swing_low and vol_ratio >= 1.2:
            grab = True
            grab_dir = "bullish"

    trap = grab and vol_ratio >= 2.0 and (
        (grab_dir == "bearish" and float(last["close"]) < float(last["open"]))
        or (grab_dir == "bullish" and float(last["close"]) > float(last["open"]))
    )

    parts = []
    if buy_side > 60:
        parts.append(f"Buy-side liquidity عند {structure.last_swing_high:.2f}" if structure.last_swing_high else "Buy-side")
    if sell_side > 60:
        parts.append(f"Sell-side liquidity عند {structure.last_swing_low:.2f}" if structure.last_swing_low else "Sell-side")
    if grab:
        parts.append(f"Liquidity Grab {grab_dir}")
    if trap:
        parts.append("Liquidity Trap")

    return LiquidityEngine(
        buy_side_liquidity=round(buy_side, 1),
        sell_side_liquidity=round(sell_side, 1),
        liquidity_grab=grab,
        liquidity_trap=trap,
        grab_direction=grab_dir,
        summary=" | ".join(parts) if parts else "سيولة متوازنة",
    )


def liquidity_score(liq: LiquidityEngine, direction: str) -> float:
    score = 50.0
    if direction == "bullish":
        score += (liq.buy_side_liquidity - liq.sell_side_liquidity) * 0.2
        if liq.liquidity_grab and liq.grab_direction == "bullish":
            score += 20
        if liq.liquidity_grab and liq.grab_direction == "bearish":
            score -= 15
    elif direction == "bearish":
        score += (liq.sell_side_liquidity - liq.buy_side_liquidity) * 0.2
        if liq.liquidity_grab and liq.grab_direction == "bearish":
            score += 20
        if liq.liquidity_grab and liq.grab_direction == "bullish":
            score -= 15
    if liq.liquidity_trap:
        score -= 25
    return max(0.0, min(100.0, score))
