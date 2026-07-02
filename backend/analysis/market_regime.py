"""Market Regime — classify trend environment from real candle data."""

from __future__ import annotations

import pandas as pd

from models.trading import MarketRegime, MarketRegimeType, TrendAnalysis


def _adx_proxy(df: pd.DataFrame, period: int = 14) -> float:
    """Directional strength proxy without extra dependencies."""
    if len(df) < period + 2:
        return 20.0
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    plus_dm = []
    minus_dm = []
    tr_list = []
    for i in range(1, len(close)):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        tr_list.append(tr)
    if not tr_list:
        return 20.0
    atr = sum(tr_list[-period:]) / period
    if atr == 0:
        return 20.0
    pdi = 100 * sum(plus_dm[-period:]) / (period * atr)
    mdi = 100 * sum(minus_dm[-period:]) / (period * atr)
    dx = abs(pdi - mdi) / max(pdi + mdi, 0.001) * 100
    return float(dx)


def classify_regime(
    df: pd.DataFrame,
    trend: TrendAnalysis,
    ai_score: float,
    momentum_score: float,
) -> MarketRegime:
    if len(df) < 20:
        return MarketRegime(regime="Neutral", score=50.0, summary="بيانات غير كافية")

    adx = _adx_proxy(df)
    atr_pct = trend.atr / float(df["close"].iloc[-1]) * 100 if float(df["close"].iloc[-1]) else 1.0

    if atr_pct > 2.5:
        vol_regime = "high"
    elif atr_pct < 0.8:
        vol_regime = "low"
    else:
        vol_regime = "normal"

    # Composite bullishness 0-100
    score = (
        ai_score * 0.35
        + trend.trend_strength * 0.30
        + momentum_score * 0.20
        + min(100, adx) * 0.15
    )

    if trend.direction == "bullish":
        score += 8
    elif trend.direction == "bearish":
        score -= 8

    if trend.ema_stack_bullish:
        score += 5
    elif trend.ema_stack_bearish:
        score -= 5

    score = max(0.0, min(100.0, score))

    if score >= 80:
        regime: MarketRegimeType = "Strong Bullish"
    elif score >= 65:
        regime = "Bullish"
    elif score >= 45:
        regime = "Neutral"
    elif score >= 30:
        regime = "Bearish"
    else:
        regime = "Strong Bearish"

    trend_quality = min(100.0, adx * 1.2 + (20 if trend.ema_stack_bullish or trend.ema_stack_bearish else 0))

    return MarketRegime(
        regime=regime,
        score=round(score, 1),
        volatility_regime=vol_regime,
        trend_quality=round(trend_quality, 1),
        summary=f"{regime} | ADX~{adx:.0f} | Vol {vol_regime}",
    )
