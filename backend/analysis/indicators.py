"""Technical indicators: RSI, MACD, EMA, VWAP, Support/Resistance."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def last_ema(close: pd.Series, period: int) -> float:
    if len(close) == 0:
        return 0.0
    if len(close) < period:
        return float(close.iloc[-1])
    return round(float(ema(close, period).iloc[-1]), 2)


def rsi(close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 1:
        return 50.0
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    last = value.iloc[-1]
    return float(last) if not np.isnan(last) else 50.0


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    if len(close) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 1:
        return float((high - low).tail(period).mean()) if len(high) else 0.0
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> float:
    if volume.sum() == 0:
        return float(close.iloc[-1])
    typical = (high + low + close) / 3
    return float((typical * volume).sum() / volume.sum())


def support_resistance(
    high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = 20
) -> tuple[float, float]:
    if len(close) < lookback:
        price = float(close.iloc[-1])
        return price * 0.98, price * 1.02
    recent_low = float(low.tail(lookback).min())
    recent_high = float(high.tail(lookback).max())
    return recent_low, recent_high


def compute_indicators(minute_df: pd.DataFrame, daily_df: pd.DataFrame | None = None):
    """Compute all indicators from minute + daily OHLCV."""
    from models.alerts import TechnicalIndicators

    close = minute_df["close"]
    high = minute_df["high"]
    low = minute_df["low"]
    volume = minute_df["volume"]

    macd_val, macd_sig, macd_hist = macd(close)
    support, resistance = support_resistance(high, low, close)

    ema_200 = last_ema(daily_df["close"], 200) if daily_df is not None and not daily_df.empty else last_ema(close, 200)

    return TechnicalIndicators(
        rsi=round(rsi(close), 2),
        macd=round(macd_val, 4),
        macd_signal=round(macd_sig, 4),
        macd_histogram=round(macd_hist, 4),
        ema_9=last_ema(close, 9),
        ema_20=last_ema(close, 20),
        ema_50=last_ema(close, 50),
        ema_200=ema_200,
        sma_20=round(float(sma(close, 20).iloc[-1]) if len(close) >= 20 else float(close.iloc[-1]), 2),
        vwap=round(vwap(high, low, close, volume), 2),
        support=round(support, 2),
        resistance=round(resistance, 2),
    )
