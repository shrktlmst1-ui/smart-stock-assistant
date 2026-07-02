"""Institutional Flow Engine — institutional candles, accumulation, absorption."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.engine_log import EngineLogger
from analysis.smart_money_tracker import analyze_smart_money, smart_money_score
from models.trading import InstitutionalFlowAnalysis, SmartMoneyTracker


def _institutional_candle(df: pd.DataFrame, price: float) -> bool:
    """Wide range + high volume bar — institutional participation."""
    if len(df) < 20:
        return False
    last = df.iloc[-1]
    vol_avg = float(df["volume"].tail(20).mean()) or 1
    vol_ratio = float(last["volume"]) / vol_avg
    rng_pct = (float(last["high"]) - float(last["low"])) / price * 100
    return vol_ratio >= 2.0 and rng_pct >= 0.5


def _sell_absorption(df: pd.DataFrame) -> bool:
    """Down pressure absorbed — lower wick, close in upper half, high volume."""
    if len(df) < 5:
        return False
    last = df.iloc[-1]
    rng = float(last["high"]) - float(last["low"])
    if rng <= 0:
        return False
    vol_avg = float(df["volume"].tail(20).mean()) or 1
    lower_wick = (float(last["close"]) - float(last["low"])) / rng
    return float(last["volume"]) / vol_avg >= 1.5 and lower_wick > 0.55 and float(last["close"]) > float(last["open"])


def _buy_absorption(df: pd.DataFrame) -> bool:
    """Up pressure absorbed — upper wick rejection, close in lower half, high volume."""
    if len(df) < 5:
        return False
    last = df.iloc[-1]
    rng = float(last["high"]) - float(last["low"])
    if rng <= 0:
        return False
    vol_avg = float(df["volume"].tail(20).mean()) or 1
    upper_wick = (float(last["high"]) - float(last["close"])) / rng
    return float(last["volume"]) / vol_avg >= 1.5 and upper_wick > 0.55 and float(last["close"]) < float(last["open"])


def _abnormal_volume_price(df: pd.DataFrame, price: float) -> bool:
    if len(df) < 20:
        return False
    vols = df["volume"].tail(20).to_numpy(dtype=float)
    z = (float(vols[-1]) - float(np.mean(vols))) / max(float(np.std(vols)), 1)
    chg = abs(float(df["close"].iloc[-1]) - float(df["close"].iloc[-2])) / price * 100
    return z > 2.0 and chg > 0.4


def analyze_institutional_flow(
    df: pd.DataFrame,
    price: float,
    logger: EngineLogger | None = None,
) -> tuple[InstitutionalFlowAnalysis, SmartMoneyTracker]:
    smart = analyze_smart_money(df, price)
    score = smart_money_score(smart)

    inst_candle = _institutional_candle(df, price)
    sell_abs = _sell_absorption(df)
    buy_abs = _buy_absorption(df)
    abnormal = _abnormal_volume_price(df, price)

    flow_dir = smart.flow_direction
    if sell_abs and not buy_abs:
        flow_dir = "bullish"
    elif buy_abs and not sell_abs:
        flow_dir = "bearish"

    parts: list[str] = []
    if inst_candle:
        parts.append("Institutional Candle")
    if smart.hidden_accumulation:
        parts.append("Accumulation")
    if smart.hidden_distribution:
        parts.append("Distribution")
    if sell_abs:
        parts.append("Sell Absorption")
    if buy_abs:
        parts.append("Buy Absorption")
    if abnormal:
        parts.append("Abnormal Vol/Price")

    result = InstitutionalFlowAnalysis(
        institutional_candle=inst_candle,
        accumulation=smart.hidden_accumulation,
        distribution=smart.hidden_distribution,
        sell_absorption=sell_abs,
        buy_absorption=buy_abs,
        abnormal_volume_price=abnormal,
        flow_score=round(score, 1),
        flow_direction=flow_dir,
        summary=" | ".join(parts) if parts else smart.summary,
    )

    if logger:
        logger.log(
            "InstitutionalFlow",
            {"bars": len(df), "price": price, "whale": smart.whale_order},
            f"score={score:.1f}, flow={flow_dir}",
            result.summary,
            "Institutional patterns from volume profile and smart money tracker",
        )
    return result, smart
