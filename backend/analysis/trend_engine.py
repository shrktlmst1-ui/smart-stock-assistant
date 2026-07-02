"""Trend Engine — EMA20/50/200, VWAP, ATR from real candles."""

from __future__ import annotations

import pandas as pd

from analysis.indicators import atr, ema, last_ema, vwap
from models.trading import TrendAnalysis


def analyze_trend(minute_df: pd.DataFrame, daily_df: pd.DataFrame | None, price: float) -> TrendAnalysis:
    close = minute_df["close"]
    high = minute_df["high"]
    low = minute_df["low"]
    volume = minute_df["volume"]

    ema20 = last_ema(close, 20)
    ema50 = last_ema(close, 50)
    ema200 = (
        last_ema(daily_df["close"], 200)
        if daily_df is not None and len(daily_df) >= 50
        else last_ema(close, min(200, len(close)))
    )
    vwap_val = round(vwap(high, low, close, volume), 2)
    atr_val = round(atr(high, low, close, 14), 4)

    # Direction from EMA stack
    bullish_stack = ema20 > ema50 > ema200
    bearish_stack = ema20 < ema50 < ema200

    if bullish_stack and price > vwap_val:
        direction = "bullish"
    elif bearish_stack and price < vwap_val:
        direction = "bearish"
    else:
        direction = "neutral"

    # Score 0-100 from measurable alignment
    score = 0.0
    if price > ema20:
        score += 20
    else:
        score -= 20
    if price > ema50:
        score += 20
    else:
        score -= 20
    if price > ema200:
        score += 15
    else:
        score -= 15
    if price > vwap_val:
        score += 15
    else:
        score -= 15
    if ema20 > ema50:
        score += 15
    else:
        score -= 15
    if ema50 > ema200:
        score += 15
    else:
        score -= 15

    trend_strength = max(0.0, min(100.0, 50.0 + score))

    parts = []
    if bullish_stack:
        parts.append("EMA stack صاعد")
    elif bearish_stack:
        parts.append("EMA stack هابط")
    parts.append(f"ATR {atr_val}")

    return TrendAnalysis(
        ema_20=ema20,
        ema_50=ema50,
        ema_200=ema200,
        vwap=vwap_val,
        atr=atr_val,
        direction=direction,
        trend_strength=round(trend_strength, 1),
        price_above_vwap=price > vwap_val,
        ema_stack_bullish=bullish_stack,
        ema_stack_bearish=bearish_stack,
        summary=" | ".join(parts),
    )
