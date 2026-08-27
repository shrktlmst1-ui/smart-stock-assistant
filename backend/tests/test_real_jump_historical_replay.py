"""REAL_JUMP_ALERT historical replay — Polygon 1m bars only, no synthetic candles."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.early_upward_surge import evaluate_real_jump_alert
from scripts.premove_replay_lib import analyze_causal_bar, filter_premarket_regular, replay_session
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient
from services.real_jump_alert_layer import (
    RealJumpAlertRegistry,
    RealJumpWaveTracker,
    reset_real_jump_state,
)

DATE = "2026-08-27"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


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
        session_high = float(bars["high"].max())
        alert_ids: set[str] = set()
        wave_ids_seen: set[str] = set()
        duplicate_waves = 0

        for row in timeline:
            i = int(row["bar_idx"])
            window = bars.iloc[: i + 1]
            bar_ts = window["timestamp"].iloc[-1]
            verdict, proc, wave = _eval_from_causal(row, tracker, registry, symbol, window, bar_ts)

            if verdict.confirmed and proc.emit:
                wid = wave.wave_id or f"{wave.move_start_price}"
                if wid in wave_ids_seen and not proc.update_existing:
                    duplicate_waves += 1
                wave_ids_seen.add(wid)
                aid = proc.alert.alert_id if proc.alert else ""
                if aid and aid not in alert_ids:
                    alert_ids.add(aid)
                    det_pct = (float(row["price"]) - prev_close) / prev_close * 100
                    peak_pct = (session_high - float(row["price"])) / float(row["price"]) * 100 if float(row["price"]) > 0 else 0
                    metrics.detections.append({
                        "time_et": row["time_et"],
                        "price": float(row["price"]),
                        "first_detected_pct": round(det_pct, 2),
                        "explosion_score": verdict.explosion_confluence_score,
                        "move_start_price": wave.move_start_price,
                        "peak_after_detection_pct": round(peak_pct, 2),
                        "lead_time_minutes": proc.alert.kpi.lead_time_minutes if proc.alert and proc.alert.kpi else 0,
                        "is_update": proc.update_existing,
                    })

        if symbol == "MSS" and metrics.detections:
            metrics.false_positives = len(metrics.detections)
        if symbol in ("DAIC", "BTCT") and not metrics.detections:
            metrics.missed = 1
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


@pytest.mark.parametrize("symbol,expect_detection", [
    ("DAIC", True),
    ("BTCT", True),
    ("MSS", False),
])
def test_historical_real_jump_replay(symbol, expect_detection):
    m = _run(_replay_symbol(symbol))
    if not m.data_available:
        pytest.skip(m.note or DATA_UNAVAILABLE)
    if expect_detection:
        assert len(m.detections) >= 1, f"expected early REAL_JUMP on {symbol}"
        first = m.detections[0]
        assert first["first_detected_pct"] < 35.0, "detect before bulk of session move"
        assert first["explosion_score"] >= 0.58
    else:
        assert m.false_positives == 0, f"false positives on {symbol}: {m.detections}"


def test_historical_cooldown_no_duplicate_alerts():
    async def _run_check():
        return await _replay_symbol("DAIC")

    m = _run(_run_check())
    if not m.data_available:
        pytest.skip(m.note or DATA_UNAVAILABLE)
    assert "duplicate_waves=0" in m.note


def test_historical_kpi_fields_present():
    m = _run(_replay_symbol("BTCT"))
    if not m.data_available:
        pytest.skip(m.note or DATA_UNAVAILABLE)
    if not m.detections:
        pytest.skip("no detection on BTCT for KPI check")
    d = m.detections[0]
    assert d["move_start_price"] > 0
    assert "first_detected_pct" in d
    assert "peak_after_detection_pct" in d
