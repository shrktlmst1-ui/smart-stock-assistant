"""
XPON Pre-Move Replay — causal bar-by-bar, no look-ahead.
Run: python scripts/replay_xpon_premove.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.pre_move_breakout import compute_breakout_metrics
from analysis.pre_move_compression import compute_compression_metrics
from analysis.pre_move_late_guard import compute_late_move_guard
from analysis.pre_move_levels import compute_trade_levels
from analysis.pre_move_liquidity import compute_liquidity_metrics
from analysis.pre_move_news import compute_news_metrics
from analysis.pre_move_scorer import classify_status, compute_composite_score
from analysis.pre_move_volume import compute_rvol_same_time, compute_volume_metrics
from analysis.pre_move_vwap import compute_vwap_metrics
from models.stock import NewsItem
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient

ET = ZoneInfo("America/New_York")
SYMBOL = "XPON"
SESSION_DATE = "2026-08-24"
MIN_BARS = 10


def _filter_premarket_regular(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    et = df["timestamp"].dt.tz_convert(ET)
    mask = (
        ((et.dt.time >= datetime.strptime("04:00", "%H:%M").time()) & (et.dt.time < datetime.strptime("09:30", "%H:%M").time()))
        | ((et.dt.time >= datetime.strptime("09:30", "%H:%M").time()) & (et.dt.time < datetime.strptime("16:00", "%H:%M").time()))
    )
    return df.loc[mask].copy().reset_index(drop=True)


def _parse_news(items: list[NewsItem], as_of: datetime) -> list[NewsItem]:
    out: list[NewsItem] = []
    for n in items:
        try:
            pub = datetime.fromisoformat(n.published_at.replace(" UTC", "").replace("Z", "+00:00"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub <= as_of:
                out.append(n)
        except Exception:
            continue
    return out


def analyze_causal(
    bars: pd.DataFrame,
    prior_bars: pd.DataFrame | None,
    news_all: list[NewsItem],
    previous_close: float,
    bar_idx: int,
) -> dict:
    """Analyze using only bars[0:bar_idx+1] — strictly causal."""
    window = bars.iloc[: bar_idx + 1].copy()
    price = float(window["close"].iloc[-1])
    bar_ts = window["timestamp"].iloc[-1]
    if hasattr(bar_ts, "to_pydatetime"):
        bar_ts = bar_ts.to_pydatetime()
    if bar_ts.tzinfo is None:
        bar_ts = bar_ts.replace(tzinfo=timezone.utc)

    change_pct = (price - previous_close) / previous_close * 100.0 if previous_close > 0 else 0.0
    cum_vol = int(window["volume"].astype(float).sum())

    # Causal highs — from bars seen so far only
    pm_mask = window["timestamp"].dt.tz_convert(ET).dt.time < datetime.strptime("09:30", "%H:%M").time()
    pm_bars = window.loc[pm_mask]
    reg_bars = window.loc[~pm_mask]

    pm_high = float(pm_bars["high"].max()) if not pm_bars.empty else 0.0
    day_high = float(reg_bars["high"].max()) if not reg_bars.empty else float(window["high"].max())

    last = window.iloc[-1]
    spread = round((float(last["high"]) - float(last["low"])) / price * 100.0, 2) if price else 0.5

    vol_metrics = compute_volume_metrics(window)
    vol_metrics.rvol_same_time = compute_rvol_same_time(window, prior_bars)

    compression = compute_compression_metrics(window, price)
    vwap_m = compute_vwap_metrics(window, price)
    breakout = compute_breakout_metrics(
        window, price,
        premarket_high=pm_high,
        day_high=day_high,
        prev_day_high=0.0,
    )
    liq = compute_liquidity_metrics(price, cum_vol, spread, bar_count=len(window))
    news_m = compute_news_metrics(_parse_news(news_all, bar_ts), change_pct)

    base_price = float(window["low"].astype(float).head(max(5, len(window) // 4)).min()) or price * 0.95
    _, _, _, _, _, _, rrr = compute_trade_levels(price, breakout, window, vwap=vwap_m.vwap)

    late = compute_late_move_guard(
        window, price, change_pct,
        vwap=vwap_m.vwap,
        base_price=base_price,
        spread_percent=spread,
        risk_reward=rrr,
    )

    late_penalty = late.late_move_score * 0.15 if late.is_too_late else 0.0
    score, bd = compute_composite_score(
        vol_metrics, compression, vwap_m, breakout, news_m, liq,
        bars=window, price=price, late_penalty=late_penalty,
    )
    status = classify_status(score, too_late=late.is_too_late)

    return {
        "bar_idx": bar_idx,
        "time_et": bar_ts.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S"),
        "price": round(price, 4),
        "change_pct": round(change_pct, 2),
        "score": score,
        "status": status,
        "late_guard": late.is_too_late,
        "late_score": late.late_move_score,
        "late_reasons": late.reasons,
        "vol_accel": vol_metrics.volume_acceleration,
        "rvol": vol_metrics.rvol,
        "rvol_st": vol_metrics.rvol_same_time,
        "trigger": breakout.resistance,
        "dist_breakout_pct": breakout.distance_to_breakout_pct,
        "breakdown": bd.model_dump(),
    }


async def main() -> dict:
    client = PolygonClient()
    try:
        bars = await client.get_minute_bars_on_date(SYMBOL, SESSION_DATE)
        prior_date = (datetime.strptime(SESSION_DATE, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        prior_bars = await client.get_minute_bars_on_date(SYMBOL, prior_date)
        snap = await client.get_snapshot(SYMBOL)
        news_raw = await fetch_stock_news(client, SYMBOL, limit=20)
    finally:
        await client.close()

    bars = _filter_premarket_regular(bars)
    if bars.empty:
        return {"error": "No bars for session date"}

    prev = snap.get("prevDay") or {}
    previous_close = float(prev.get("c") or 0)
    if previous_close <= 0 and not prior_bars.empty:
        previous_close = float(prior_bars["close"].iloc[-1])

    timeline: list[dict] = []
    for i in range(MIN_BARS - 1, len(bars)):
        timeline.append(analyze_causal(bars, prior_bars, news_raw, previous_close, i))

    # Milestones
    first_detect = next((t for t in timeline if t["score"] >= 60), None)
    early_watch = next((t for t in timeline if t["status"] == "EARLY_WATCH" or (t["score"] >= 60 and not t["late_guard"])), None)
    pre_breakout = next((t for t in timeline if t["status"] == "PRE_BREAKOUT"), None)
    early_entry = next((t for t in timeline if t["status"] in ("EARLY_ENTRY", "HIGH_CONVICTION_EARLY")), None)
    too_late = next((t for t in timeline if t["status"] == "TOO_LATE_TO_CHASE"), None)
    late_guard_on = next((t for t in timeline if t["late_guard"]), None)

    # Main breakout: first close breaks prior running high (causal)
    breakout_evt = None
    for i in range(MIN_BARS, len(bars)):
        window = bars.iloc[: i + 1]
        prior_high = float(window["high"].iloc[:-1].max()) if len(window) > 1 else 0.0
        close = float(window["close"].iloc[-1])
        if prior_high > 0 and close > prior_high * 1.005:
            ts = window["timestamp"].iloc[-1]
            breakout_evt = {
                "time_et": ts.tz_convert(ET).strftime("%Y-%m-%d %H:%M:%S"),
                "price": round(close, 4),
                "prior_high": round(prior_high, 4),
            }
            break

    ref_idx = first_detect["bar_idx"] if first_detect else 0
    highs_after = bars.iloc[ref_idx:]["high"].astype(float)
    max_high_after = float(highs_after.max()) if not highs_after.empty else 0.0

    lead_min = None
    if first_detect and breakout_evt:
        t0 = datetime.strptime(first_detect["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        t1 = datetime.strptime(breakout_evt["time_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        lead_min = round((t1 - t0).total_seconds() / 60.0, 1)

    pct_before_entry = None
    if early_entry and previous_close > 0:
        pct_before_entry = round((early_entry["price"] - previous_close) / previous_close * 100.0, 2)

    session_low = float(bars["low"].min())
    session_high = float(bars["high"].max())

    return {
        "symbol": SYMBOL,
        "session_date": SESSION_DATE,
        "previous_close": previous_close,
        "session_low": session_low,
        "session_high": session_high,
        "bar_count": len(bars),
        "first_detection": first_detect,
        "early_watch": early_watch,
        "pre_breakout": pre_breakout,
        "early_entry": early_entry,
        "main_breakout": breakout_evt,
        "highest_after_first_signal": max_high_after,
        "early_detection_lead_minutes": lead_min,
        "pct_move_before_early_entry": pct_before_entry,
        "late_move_guard_first": late_guard_on,
        "too_late_to_chase": too_late,
        "timeline_sample": timeline[:: max(1, len(timeline) // 20)],
        "score_peaks": sorted(timeline, key=lambda x: x["score"], reverse=True)[:5],
    }


if __name__ == "__main__":
    result = asyncio.run(main())
    print(json.dumps(result, ensure_ascii=False, indent=2))
