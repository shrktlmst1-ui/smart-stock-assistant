"""Volume & Liquidity Engine — RVOL, delta, VWAP, gaps, inflow/outflow, pressure."""

from __future__ import annotations

import pandas as pd

from analysis.engine_log import EngineLogger
from analysis.indicators import vwap as calc_vwap
from models.trading import VolumeLiquidityAnalysis


def _cumulative_delta(df: pd.DataFrame) -> tuple[float, str]:
    """Approximate delta from OHLCV — buy volume when close > open."""
    if len(df) < 5:
        return 0.0, "neutral"
    w = df.tail(30)
    delta = 0.0
    for _, row in w.iterrows():
        vol = float(row["volume"])
        if float(row["close"]) > float(row["open"]):
            delta += vol
        elif float(row["close"]) < float(row["open"]):
            delta -= vol
    direction = "bullish" if delta > 0 else "bearish" if delta < 0 else "neutral"
    return round(delta, 0), direction


def _premarket_volume(df: pd.DataFrame) -> tuple[int, float]:
    """Estimate premarket from first bars of session (before 09:30 ET ≈ first 30 min bars)."""
    if df.empty:
        return 0, 1.0
    pre = df.head(min(30, len(df)))
    pm_vol = int(pre["volume"].sum())
    avg_bar = float(df["volume"].mean()) or 1
    pm_rvol = pm_vol / (avg_bar * len(pre)) if len(pre) else 1.0
    return pm_vol, round(pm_rvol, 2)


def _gap_scanner(df: pd.DataFrame, daily_df: pd.DataFrame | None) -> tuple[float, str]:
    if daily_df is not None and len(daily_df) >= 2:
        prev_close = float(daily_df["close"].iloc[-2])
        today_open = float(daily_df["open"].iloc[-1])
    elif len(df) >= 2:
        prev_close = float(df["close"].iloc[-2])
        today_open = float(df["open"].iloc[-1])
    else:
        return 0.0, "none"
    if prev_close <= 0:
        return 0.0, "none"
    gap_pct = (today_open - prev_close) / prev_close * 100
    if gap_pct > 0.3:
        return round(gap_pct, 2), "gap_up"
    if gap_pct < -0.3:
        return round(gap_pct, 2), "gap_down"
    return round(gap_pct, 2), "none"


def analyze_volume_liquidity(
    df: pd.DataFrame,
    daily_df: pd.DataFrame | None,
    price: float,
    logger: EngineLogger | None = None,
) -> VolumeLiquidityAnalysis:
    if len(df) < 10:
        result = VolumeLiquidityAnalysis(summary="بيانات غير كافية")
        if logger:
            logger.log("VolumeLiquidity", {"bars": len(df)}, "skip", "insufficient", "Need >= 10 bars")
        return result

    vol_avg = float(df["volume"].tail(20).mean()) or 1
    last_vol = float(df["volume"].iloc[-1])
    rvol = last_vol / vol_avg
    spike = rvol >= 2.0

    cum_delta, delta_dir = _cumulative_delta(df)
    vwap_val = calc_vwap(df["high"], df["low"], df["close"], df["volume"])
    if price > vwap_val * 1.001:
        pvv = "above"
    elif price < vwap_val * 0.999:
        pvv = "below"
    else:
        pvv = "at"

    pm_vol, pm_rvol = _premarket_volume(df)
    gap_pct, gap_type = _gap_scanner(df, daily_df)

    # Buyer/seller pressure from recent candle bodies + volume
    w = df.tail(10)
    buy_vol = sell_vol = 0.0
    for _, row in w.iterrows():
        v = float(row["volume"])
        if float(row["close"]) >= float(row["open"]):
            buy_vol += v
        else:
            sell_vol += v
    total = buy_vol + sell_vol or 1
    buyer_pressure = round(buy_vol / total * 100, 1)
    seller_pressure = round(sell_vol / total * 100, 1)

    # Inflow/outflow from delta + rvol weighted
    inflow = min(100.0, max(0.0, 50 + (buyer_pressure - 50) * 0.6 + min(rvol - 1, 2) * 10))
    outflow = min(100.0, max(0.0, 50 + (seller_pressure - 50) * 0.6 + min(rvol - 1, 2) * 10))

    parts = []
    if spike:
        parts.append(f"Volume Spike RVOL {rvol:.1f}x")
    parts.append(f"Delta {delta_dir}")
    if gap_type != "none":
        parts.append(f"Gap {gap_type} {gap_pct:+.1f}%")
    parts.append(f"Inflow {inflow:.0f}% / Outflow {outflow:.0f}%")

    result = VolumeLiquidityAnalysis(
        relative_volume=round(rvol, 2),
        volume_spike=spike,
        cumulative_delta=cum_delta,
        delta_direction=delta_dir,
        vwap=round(vwap_val, 2),
        price_vs_vwap=pvv,
        premarket_volume=pm_vol,
        premarket_rvol=pm_rvol,
        gap_percent=gap_pct,
        gap_type=gap_type,
        liquidity_inflow=round(inflow, 1),
        liquidity_outflow=round(outflow, 1),
        buyer_pressure=buyer_pressure,
        seller_pressure=seller_pressure,
        summary=" | ".join(parts),
    )

    if logger:
        logger.log(
            "VolumeLiquidity",
            {"bars": len(df), "price": price, "last_vol": last_vol, "vol_avg": round(vol_avg, 0)},
            f"RVOL={rvol:.2f}, delta={cum_delta}, buyer={buyer_pressure}%, seller={seller_pressure}%",
            result.summary,
            "Computed from OHLCV volume distribution and session gap",
        )
    return result
