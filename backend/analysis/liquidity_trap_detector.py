"""Liquidity Trap Detector — bull/bear traps, fake breakouts, stop hunts."""

from __future__ import annotations

import pandas as pd

from analysis.structure import MarketStructure
from models.trading import LiquidityEngine, LiquidityTrapAnalysis, SMCAnalysis


def detect_liquidity_traps(
    df: pd.DataFrame,
    price: float,
    structure: MarketStructure,
    smc: SMCAnalysis,
    liquidity: LiquidityEngine,
) -> LiquidityTrapAnalysis:
    if len(df) < 10:
        return LiquidityTrapAnalysis(summary="بيانات غير كافية")

    last = df.iloc[-1]
    prev = df.iloc[-2]
    vol_avg = float(df["volume"].tail(20).mean()) or 1
    vol_ratio = float(last["volume"]) / vol_avg

    bull_trap = False
    bear_trap = False
    fake_breakout = False
    fake_breakdown = False
    stop_hunt = smc.liquidity_sweep
    liquidity_grab = liquidity.liquidity_grab
    pump_and_dump = False
    fake_momentum = False

    # Bull trap: pierced swing high / resistance then closed back below
    if structure.last_swing_high:
        pierced_high = float(last["high"]) > structure.last_swing_high
        closed_below = float(last["close"]) < structure.last_swing_high
        prev_below = float(prev["close"]) < structure.last_swing_high
        bull_trap = pierced_high and closed_below and prev_below and vol_ratio >= 1.2

    # Bear trap: pierced swing low then closed back above
    if structure.last_swing_low:
        pierced_low = float(last["low"]) < structure.last_swing_low
        closed_above = float(last["close"]) > structure.last_swing_low
        prev_above = float(prev["close"]) > structure.last_swing_low
        bear_trap = pierced_low and closed_above and prev_above and vol_ratio >= 1.2

    # Fake breakout: BOS on prior bar reversed on current bar
    if len(df) >= 3:
        prev2 = df.iloc[-3]
        if smc.bos and smc.bos_direction == "bullish":
            fake_breakout = float(last["close"]) < float(prev2["high"]) and float(prev["close"]) > float(prev2["high"])
        elif smc.bos and smc.bos_direction == "bearish":
            fake_breakout = float(last["close"]) > float(prev2["low"]) and float(prev["close"]) < float(prev2["low"])

    # Fake breakdown: break below support then reclaim
    if structure.last_swing_low:
        broke_low = float(prev["close"]) < structure.last_swing_low
        reclaimed = float(last["close"]) > structure.last_swing_low
        fake_breakdown = broke_low and reclaimed and vol_ratio >= 1.1

    # Pump & dump: sharp spike then reversal on high volume
    if len(df) >= 6:
        w = df.tail(6)
        peak_idx = int(w["high"].idxmax())
        peak_pos = w.index.get_loc(peak_idx)
        if peak_pos <= 3:
            spike_pct = (float(w["high"].max()) - float(w["close"].iloc[0])) / price * 100
            dump_pct = (float(w["high"].max()) - float(w["close"].iloc[-1])) / price * 100
            pump_and_dump = spike_pct > 1.0 and dump_pct > spike_pct * 0.6 and vol_ratio >= 1.5

    # Fake momentum: RSI-style momentum without volume confirmation
    if len(df) >= 10:
        roc = (float(df["close"].iloc[-1]) - float(df["close"].iloc[-5])) / price * 100
        fake_momentum = abs(roc) > 0.8 and vol_ratio < 1.0 and (bull_trap or bear_trap)

    # Spoofing: high volume, wide wicks both sides, close near middle — fake liquidity
    spoofing = False
    if len(df) >= 5:
        rng = float(last["high"]) - float(last["low"])
        if rng > 0:
            upper = (float(last["high"]) - float(last["close"])) / rng
            lower = (float(last["close"]) - float(last["low"])) / rng
            spoofing = vol_ratio >= 1.8 and upper > 0.35 and lower > 0.35 and abs(float(last["close"]) - float(last["open"])) / rng < 0.25

    # CHOCH after sweep often marks stop hunt
    if smc.liquidity_sweep and smc.choch:
        stop_hunt = True

    trap_dir = "none"
    if bull_trap or (liquidity_grab and liquidity.grab_direction == "bearish"):
        trap_dir = "bearish"
    elif bear_trap or (liquidity_grab and liquidity.grab_direction == "bullish"):
        trap_dir = "bullish"

    severity = 0.0
    flags = [bull_trap, bear_trap, fake_breakout, fake_breakdown, stop_hunt, liquidity_grab, pump_and_dump, fake_momentum, spoofing]
    severity += sum(15 for f in flags if f)
    if liquidity.liquidity_trap:
        severity += 15
    severity = min(100.0, severity)

    parts: list[str] = []
    if bull_trap:
        parts.append("Bull Trap")
    if bear_trap:
        parts.append("Bear Trap")
    if fake_breakout:
        parts.append("Fake Breakout")
    if fake_breakdown:
        parts.append("Fake Breakdown")
    if stop_hunt:
        parts.append("Stop Hunt")
    if liquidity_grab:
        parts.append(f"Liquidity Grab {liquidity.grab_direction}")
    if pump_and_dump:
        parts.append("Pump & Dump")
    if fake_momentum:
        parts.append("Fake Momentum")
    if spoofing:
        parts.append("Spoofing")

    return LiquidityTrapAnalysis(
        bull_trap=bull_trap,
        bear_trap=bear_trap,
        fake_breakout=fake_breakout,
        fake_breakdown=fake_breakdown,
        stop_hunt=stop_hunt,
        liquidity_grab=liquidity_grab,
        pump_and_dump=pump_and_dump,
        fake_momentum=fake_momentum,
        spoofing=spoofing,
        delta_imbalance=False,
        trap_direction=trap_dir,
        severity=round(severity, 1),
        summary=" | ".join(parts) if parts else "لا فخاخ سيولة نشطة",
    )
