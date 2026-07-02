"""Smart Money Concepts — real structure-based BOS, CHOCH, OB, FVG, Sweep."""

from __future__ import annotations

import pandas as pd

from analysis.indicators import atr
from analysis.structure import MarketStructure, analyze_structure, find_swing_points
from models.trading import FairValueGap, OrderBlock, SMCAnalysis


_STRUCTURE_WINDOW = 80


def _detect_fvg(df: pd.DataFrame) -> list[FairValueGap]:
    gaps: list[FairValueGap] = []
    price = float(df["close"].iloc[-1])
    start = max(2, len(df) - _STRUCTURE_WINDOW)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    for i in range(start, len(df)):
        c0h = highs[i - 2]
        c0l = lows[i - 2]
        c2l = lows[i]
        c2h = highs[i]
        if c2l > c0h:
            gaps.append(FairValueGap(
                type="bullish",
                top=float(c2l),
                bottom=float(c0h),
                filled=price <= c0h,
            ))
        if c2h < c0l:
            gaps.append(FairValueGap(
                type="bearish",
                top=float(c0l),
                bottom=float(c2h),
                filled=price >= c0l,
            ))
    return gaps[-5:]


def _detect_order_blocks(df: pd.DataFrame) -> list[OrderBlock]:
    blocks: list[OrderBlock] = []
    if len(df) < 10:
        return blocks

    atr_val = atr(df["high"], df["low"], df["close"], 14)
    if atr_val <= 0:
        return blocks

    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    start = max(2, len(df) - _STRUCTURE_WINDOW)

    for i in range(start, len(df)):
        displacement = abs(closes[i] - opens[i])
        if displacement < atr_val * 1.2:
            continue

        bullish_move = closes[i] > opens[i]
        if bullish_move and closes[i - 1] < opens[i - 1]:
            strength = min(100.0, (displacement / atr_val) * 25)
            blocks.append(OrderBlock(
                type="bullish",
                high=float(highs[i - 1]),
                low=float(lows[i - 1]),
                strength=round(strength, 1),
            ))
        elif not bullish_move and closes[i - 1] > opens[i - 1]:
            strength = min(100.0, (displacement / atr_val) * 25)
            blocks.append(OrderBlock(
                type="bearish",
                high=float(highs[i - 1]),
                low=float(lows[i - 1]),
                strength=round(strength, 1),
            ))
    return blocks[-3:]


def _detect_liquidity_sweep(df: pd.DataFrame, structure: MarketStructure) -> tuple[bool, str]:
    if len(df) < 3:
        return False, "none"
    last = df.iloc[-1]
    vol_avg = float(df["volume"].tail(20).mean()) or 1
    vol_ratio = float(last["volume"]) / vol_avg

    if structure.last_swing_high and float(last["high"]) > structure.last_swing_high:
        if float(last["close"]) < structure.last_swing_high and vol_ratio >= 1.2:
            return True, "bearish"

    if structure.last_swing_low and float(last["low"]) < structure.last_swing_low:
        if float(last["close"]) > structure.last_swing_low and vol_ratio >= 1.2:
            return True, "bullish"

    return False, "none"


def _detect_breaker_mitigation_blocks(
    df: pd.DataFrame, order_blocks: list[OrderBlock],
) -> tuple[list[OrderBlock], list[OrderBlock]]:
    """Breaker = failed OB broken through; Mitigation = price retests unfilled OB."""
    breakers: list[OrderBlock] = []
    mitigations: list[OrderBlock] = []
    if len(df) < 5 or not order_blocks:
        return breakers, mitigations

    price = float(df["close"].iloc[-1])
    for ob in order_blocks[-5:]:
        mid = (ob.high + ob.low) / 2
        if ob.type == "bullish":
            if price < ob.low:
                breakers.append(OrderBlock(
                    type="bearish", high=ob.high, low=ob.low,
                    strength=min(100.0, ob.strength + 10),
                ))
            elif ob.low <= price <= ob.high:
                mitigations.append(ob)
        else:
            if price > ob.high:
                breakers.append(OrderBlock(
                    type="bullish", high=ob.high, low=ob.low,
                    strength=min(100.0, ob.strength + 10),
                ))
            elif ob.low <= price <= ob.high:
                mitigations.append(ob)
    return breakers[-2:], mitigations[-2:]


def analyze_smc(df: pd.DataFrame, price: float) -> tuple[SMCAnalysis, MarketStructure]:
    if len(df) < 30:
        empty = SMCAnalysis(summary="بيانات غير كافية لـ SMC")
        return empty, analyze_structure(df, price)

    structure = analyze_structure(df, price)
    order_blocks = _detect_order_blocks(df)
    breakers, mitigations = _detect_breaker_mitigation_blocks(df, order_blocks)
    fvgs = _detect_fvg(df)
    sweep, sweep_dir = _detect_liquidity_sweep(df, structure)

    parts = []
    if structure.bos:
        parts.append(f"BOS {'صاعد' if structure.bos_direction == 'bullish' else 'هابط'}")
    if structure.choch:
        parts.append(f"CHOCH {'صاعد' if structure.choch_direction == 'bullish' else 'هابط'}")
    if structure.mss:
        parts.append(f"MSS {'صاعد' if structure.mss_direction == 'bullish' else 'هابط'}")
    if sweep:
        parts.append(f"Liquidity Sweep {'صاعد' if sweep_dir == 'bullish' else 'هابط'}")
    if order_blocks:
        parts.append(f"{len(order_blocks)} Order Block")
    if breakers:
        parts.append(f"{len(breakers)} Breaker Block")
    if mitigations:
        parts.append(f"{len(mitigations)} Mitigation Block")
    unfilled = [g for g in fvgs if not g.filled]
    if unfilled:
        parts.append(f"{len(unfilled)} FVG نشط")

    smc = SMCAnalysis(
        bos=structure.bos,
        bos_direction=structure.bos_direction,
        choch=structure.choch,
        choch_direction=structure.choch_direction,
        mss=structure.mss,
        mss_direction=structure.mss_direction,
        order_blocks=order_blocks,
        fair_value_gaps=fvgs,
        breaker_blocks=breakers,
        mitigation_blocks=mitigations,
        liquidity_sweep=sweep,
        sweep_direction=sweep_dir if sweep else "none",
        summary=" | ".join(parts) if parts else "بنية محايدة",
    )
    return smc, structure


def smc_score(smc: SMCAnalysis, structure: MarketStructure) -> float:
    """0-100 bullishness score from SMC."""
    score = 50.0
    if structure.bos and structure.bos_direction == "bullish":
        score += 25
    elif structure.bos and structure.bos_direction == "bearish":
        score -= 25
    if structure.choch and structure.choch_direction == "bullish":
        score += 20
    elif structure.choch and structure.choch_direction == "bearish":
        score -= 20
    if structure.mss and structure.mss_direction == "bullish":
        score += 18
    elif structure.mss and structure.mss_direction == "bearish":
        score -= 18
    if smc.liquidity_sweep and smc.sweep_direction == "bullish":
        score += 15
    elif smc.liquidity_sweep and smc.sweep_direction == "bearish":
        score -= 15
    bull_obs = sum(1 for ob in smc.order_blocks if ob.type == "bullish")
    bear_obs = sum(1 for ob in smc.order_blocks if ob.type == "bearish")
    score += (bull_obs - bear_obs) * 5
    bull_fvg = sum(1 for g in smc.fair_value_gaps if g.type == "bullish" and not g.filled)
    bear_fvg = sum(1 for g in smc.fair_value_gaps if g.type == "bearish" and not g.filled)
    score += (bull_fvg - bear_fvg) * 3
    return max(0.0, min(100.0, score))
