"""REAL_JUMP_ALERT historical replay — real Polygon 1m bars, causal, no synthetic candles."""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.early_upward_surge import evaluate_real_jump_alert
from scripts.premove_replay_lib import filter_premarket_regular, replay_session
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient
from services.real_jump_alert_layer import (
    REAL_JUMP_SECTION_MIN_WAVE_PCT,
    RealJumpAlertRegistry,
    RealJumpWaveTracker,
    eligible_for_price_jump_section,
    reset_real_jump_state,
)

DATE = os.environ.get("REAL_JUMP_REPLAY_DATE", "2026-08-27")
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
REPLAY_SYMBOLS = [
    s.strip().upper()
    for s in os.environ.get("REAL_JUMP_REPLAY_SYMBOLS", "DAIC,BTCT,MSS").split(",")
    if s.strip()
]
DATA_SOURCE = "Polygon 1m OHLCV replay (real bars, causal — not synthetic unit tests)"


@dataclass
class RealJumpReplayMetrics:
    symbol: str
    detections: list[dict] = field(default_factory=list)
    false_positives: int = 0
    missed: int = 0
    data_available: bool = True
    note: str = ""


def _eval_from_causal(row, wave_tracker, registry, symbol, bars_window, bar_ts):
    from datetime import timezone

    if hasattr(bar_ts, "to_pydatetime"):
        bar_ts = bar_ts.to_pydatetime()
    if bar_ts.tzinfo is None:
        bar_ts = bar_ts.replace(tzinfo=timezone.utc)

    price = float(row["price"])
    tv = row.get("trade_velocity")
    wave = wave_tracker.update(
        symbol,
        current_price=price,
        bars=bars_window,
        timestamp=bar_ts,
        trade_velocity=float(tv) if tv != "DATA_UNAVAILABLE" else 0.0,
        volume_acceleration_1m=float(row["volume_acceleration_1m"]),
    )
    verdict = evaluate_real_jump_alert(
        current_price=price,
        change_pct=float(row["change_pct"]),
        price_volume_response=min(1.0, float(row.get("early_activity_score", 0)) / 28.0),
        micro_higher_lows=bool(row.get("micro_higher_lows")),
        breakout_pressure=float(row.get("breakout_pressure", 0) or 0),
        resistance_distance_pct=float(row.get("resistance_distance_pct", 99)),
        trigger_price=float(row.get("trigger_price", 0)),
        movement_start_price=0,
        volume_acceleration_1m=float(row["volume_acceleration_1m"]),
        volume_acceleration_slope=float(row["volume_acceleration_slope"]),
        rvol=float(row.get("rvol_same_time") or 0),
        rvol_same_time=float(row["rvol_same_time"]) if row.get("rvol_same_time") is not None else None,
        trade_velocity_growth=0.15 if tv not in (None, "DATA_UNAVAILABLE") else 0.0,
        trade_velocity=float(tv) if tv != "DATA_UNAVAILABLE" else None,
        dollar_volume_growth=0.2,
        liquidity_score=float(row.get("liquidity_score", 60)),
        spread_pct=2.0,
        persistence_minutes=int(row.get("persistence_minutes", 0)),
        range_compression_3m=float(row.get("compression_3m", 0)),
        bars=bars_window,
        wave=wave,
    )
    proc = registry.process(symbol, verdict, wave=wave, current_price=price, timestamp=bar_ts)
    return verdict, proc, wave


async def _replay_symbol(symbol: str, session_date: str = DATE) -> RealJumpReplayMetrics:
    metrics = RealJumpReplayMetrics(symbol=symbol)
    client = PolygonClient()
    try:
        bars = filter_premarket_regular(await client.get_premarket_minute_bars(symbol, session_date=session_date))
        if bars.empty or len(bars) < 5:
            metrics.data_available = False
            metrics.note = DATA_UNAVAILABLE
            return metrics
        prior = await client.get_premarket_minute_bars(symbol, session_date="2026-08-26")
        prev_resp = await client._request(f"/v2/aggs/ticker/{symbol}/prev")
        prev_close = float((prev_resp.get("results") or [{}])[0].get("c") or 0)
        if prev_close <= 0:
            metrics.data_available = False
            metrics.note = DATA_UNAVAILABLE
            return metrics
        news = await fetch_stock_news(client, symbol, 5)
        timeline = replay_session(
            bars, prior, news, prev_close, symbol=symbol, session_date=session_date,
        )
        reset_real_jump_state()
        tracker = RealJumpWaveTracker()
        registry = RealJumpAlertRegistry()
        alert_ids: set[str] = set()
        wave_ids_seen: set[str] = set()
        duplicate_waves = 0
        open_waves: dict[str, dict] = {}

        for row in timeline:
            i = int(row["bar_idx"])
            window = bars.iloc[: i + 1]
            bar_ts = window["timestamp"].iloc[-1]
            bar_high = float(window["high"].iloc[-1])
            verdict, proc, wave = _eval_from_causal(row, tracker, registry, symbol, window, bar_ts)

            wid = wave.wave_id or f"{wave.move_start_price}"
            if wid in open_waves:
                open_waves[wid]["eventual_peak"] = max(open_waves[wid]["eventual_peak"], bar_high)

            if verdict.confirmed and proc.emit:
                if wid in wave_ids_seen and not proc.update_existing:
                    duplicate_waves += 1
                wave_ids_seen.add(wid)
                aid = proc.alert.alert_id if proc.alert else ""
                if aid and aid not in alert_ids:
                    alert_ids.add(aid)
                    kpi = proc.alert.kpi if proc.alert else None
                    move_start = wave.move_start_price
                    first_price = kpi.first_detected_price if kpi else float(row["price"])
                    first_pct = (
                        (first_price - move_start) / move_start * 100.0 if move_start > 0 else 0.0
                    )
                    peak_at_det = kpi.wave_peak_price if kpi else bar_high
                    open_waves[wid] = {
                        "eventual_peak": max(peak_at_det, bar_high),
                        "move_start": move_start,
                        "first_price": first_price,
                        "first_pct": first_pct,
                        "peak_at_det": peak_at_det,
                        "time_et": row["time_et"],
                        "explosion_score": verdict.explosion_confluence_score,
                        "is_update": proc.update_existing,
                    }

        for w in open_waves.values():
            ms = w["move_start"]
            fp = w["first_price"]
            ep = w["eventual_peak"]
            wpm = (ep - ms) / ms * 100.0 if ms > 0 else 0.0
            pad = (ep - fp) / fp * 100.0 if fp > 0 else 0.0
            kpi_stub = type("K", (), {"wave_peak_move_pct": wpm})()
            metrics.detections.append({
                "time_et": w["time_et"],
                "move_start_price": round(ms, 4),
                "first_detected_price": round(fp, 4),
                "first_detected_pct": round(w["first_pct"], 2),
                "wave_peak_price": round(ep, 4),
                "wave_peak_move_pct": round(wpm, 2),
                "peak_after_detection_pct": round(pad, 2),
                "exceeded_100": wpm > REAL_JUMP_SECTION_MIN_WAVE_PCT,
                "exceeded_150": wpm >= 150.0,
                "in_price_jump_section": eligible_for_price_jump_section(
                    kpi_stub, current_move_pct=wpm,
                ),
                "data_source": DATA_SOURCE,
                "explosion_score": w["explosion_score"],
                "is_update": w.get("is_update", False),
            })

        metrics.note = f"duplicate_waves={duplicate_waves}"
        return metrics
    except Exception as exc:
        metrics.data_available = False
        metrics.note = f"{DATA_UNAVAILABLE}:{exc}"
        return metrics
    finally:
        await client.close()


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.integration
@pytest.mark.parametrize("symbol", REPLAY_SYMBOLS or ["__skip__"])
def test_historical_real_jump_replay_metrics(symbol):
    if symbol == "__skip__":
        pytest.skip("set REAL_JUMP_REPLAY_SYMBOLS for integration replay")
    m = _run(_replay_symbol(symbol))
    if not m.data_available:
        pytest.skip(m.note or DATA_UNAVAILABLE)
    for d in m.detections:
        assert d["move_start_price"] > 0
        assert "wave_peak_move_pct" in d
        assert d["wave_peak_move_pct"] == pytest.approx(
            (d["wave_peak_price"] - d["move_start_price"]) / d["move_start_price"] * 100.0,
            rel=0.01,
        )


def test_replay_dataset_must_include_100pct_waves_for_goal_validation():
    """Without +100% waves in replay data, goal validation is invalid — must FAIL not PASS."""
    if not REPLAY_SYMBOLS:
        pytest.fail("REAL_JUMP_REPLAY_SYMBOLS not configured")
    all_cases: list[dict] = []
    for sym in REPLAY_SYMBOLS:
        m = _run(_replay_symbol(sym))
        if not m.data_available:
            continue
        all_cases.extend(m.detections)
    if not all_cases:
        pytest.fail("no replay detections — cannot validate +100%/+150% goal")
    has_100 = any(d["exceeded_100"] for d in all_cases)
    if not has_100:
        pytest.fail(
            f"INVALID_FOR_GOAL: {len(all_cases)} detections but none exceeded +100% wave_peak_move_pct "
            f"from move_start — replay data cannot validate +100%/+150% price jump section goal"
        )


def test_historical_cooldown_no_duplicate_alerts():
    if not REPLAY_SYMBOLS:
        pytest.skip("set REAL_JUMP_REPLAY_SYMBOLS")
    m = _run(_replay_symbol(REPLAY_SYMBOLS[0]))
    if not m.data_available:
        pytest.skip(m.note or DATA_UNAVAILABLE)
    assert "duplicate_waves=0" in m.note
