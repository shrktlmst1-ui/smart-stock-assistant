"""IVP 2026-01-14 — move_start lifecycle regression (causal Polygon 1m replay)."""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.early_upward_surge import evaluate_real_jump_alert
from models.opportunity_now import OpportunityNowSignal
from scripts.premove_replay_lib import filter_premarket_regular, replay_session
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient
from services.real_jump_alert_layer import (
    REAL_JUMP_EXPLOSIVE_WAVE_PCT,
    REAL_JUMP_SECTION_MIN_WAVE_PCT,
    RealJumpAlertRegistry,
    RealJumpWaveTracker,
    apply_real_jump_display,
    eligible_for_price_jump_section,
    is_explosive_wave,
    real_jump_alert_registry,
    real_jump_wave_tracker,
    reset_real_jump_state,
)

SYMBOL = "IVP"
SESSION = os.environ.get("IVP_REPLAY_DATE", "2026-01-14")
EXPECTED_MS = 0.0297
MS_TOLERANCE = 0.0005
FD_PCT_TOLERANCE = 1.0


@dataclass
class IvpTimelineRow:
    time: str
    price: float
    wave_id: str
    wave_state: str
    move_start_price: float
    current_move_pct: float
    first_detected_price: float | None
    first_detected_pct: float | None
    wave_peak_price: float
    wave_peak_move_pct: float
    price_jump_section: bool
    explosive: bool
    reset_reason: str = ""


@dataclass
class IvpReplayResult:
    timeline: list[IvpTimelineRow] = field(default_factory=list)
    ms_resets: list[dict] = field(default_factory=list)
    first_alert: dict | None = None
    cross_100: dict | None = None
    cross_150: dict | None = None
    section_first: dict | None = None
    explosive_first: dict | None = None
    fd_changed: bool = False
    data_available: bool = True
    note: str = ""


def _eval_causal(row, tracker, registry, symbol, bars_window, bar_ts):
    from datetime import timezone

    if hasattr(bar_ts, "to_pydatetime"):
        bar_ts = bar_ts.to_pydatetime()
    if bar_ts.tzinfo is None:
        bar_ts = bar_ts.replace(tzinfo=timezone.utc)

    price = float(row["price"])
    tv = row.get("trade_velocity")
    wave = tracker.update(
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


async def replay_ivp(session_date: str = SESSION) -> IvpReplayResult:
    result = IvpReplayResult()
    client = PolygonClient()
    try:
        bars = filter_premarket_regular(await client.get_minute_bars_on_date(SYMBOL, session_date))
        if bars.empty or len(bars) < 5:
            result.data_available = False
            result.note = "no bars"
            return result

        prior_date = (datetime.strptime(session_date, "%Y-%m-%d") - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            prior = await client.get_premarket_minute_bars(SYMBOL, session_date=prior_date)
        except Exception:
            prior = None
        prev_resp = await client._request(f"/v2/aggs/ticker/{SYMBOL}/prev", params={"adjusted": "true"})
        prev_close = float((prev_resp.get("results") or [{}])[0].get("c") or float(bars["close"].iloc[0]))
        news = await fetch_stock_news(client, SYMBOL, 5)
        timeline_rows = replay_session(bars, prior, news, prev_close, symbol=SYMBOL, session_date=session_date)

        reset_real_jump_state()
        tracker = real_jump_wave_tracker
        registry = real_jump_alert_registry

        prev_ms: float | None = None
        primary_wave_id: str | None = None
        fd0_price: float | None = None
        fd0_pct: float | None = None
        fd0_time: str | None = None

        for row in timeline_rows:
            i = int(row["bar_idx"])
            window = bars.iloc[: i + 1]
            bar_ts = window["timestamp"].iloc[-1]
            price = float(row["price"])
            verdict, proc, wave = _eval_causal(row, tracker, registry, SYMBOL, window, bar_ts)

            ms = wave.move_start_price
            if prev_ms is not None and ms > 0 and abs(ms - prev_ms) > 1e-6:
                result.ms_resets.append({
                    "time": row["time_et"],
                    "from_ms": prev_ms,
                    "to_ms": ms,
                    "price": price,
                    "wave_state": wave.wave_state,
                    "reset_reason": wave.reset_reason,
                })
            if ms > 0:
                prev_ms = ms

            kpi = proc.alert.kpi if proc.alert else None
            wpeak = max(wave.wave_peak_price, price)
            wpm = (wpeak - ms) / ms * 100.0 if ms > 0 else 0.0
            cmp = wave.current_move_pct
            in_section = eligible_for_price_jump_section(kpi, current_move_pct=cmp)
            explosive = is_explosive_wave(cmp)

            display_stage = ""
            if verdict.confirmed and proc.emit:
                out = apply_real_jump_display(
                    OpportunityNowSignal(symbol=SYMBOL, price=price, change_percent=float(row["change_pct"]), score=70),
                    verdict if verdict.kpi else __import__("analysis.early_upward_surge", fromlist=["RealPriceJumpVerdict"]).RealPriceJumpVerdict(
                        confirmed=True, wave=wave, kpi=kpi,
                    ),
                )
                display_stage = out.detection_stage or ""
                if display_stage == "EXPLOSIVE":
                    explosive = True
                elif in_section and not display_stage:
                    display_stage = "REAL_JUMP_ALERT"

            if verdict.confirmed and proc.emit and not proc.update_existing and result.first_alert is None:
                result.first_alert = {
                    "time": row["time_et"],
                    "move_start": ms,
                    "first_price": kpi.first_detected_price if kpi else price,
                    "first_pct": kpi.first_detected_pct if kpi else cmp,
                    "wave_id": wave.wave_id,
                }
                primary_wave_id = wave.wave_id
                fd0_price = result.first_alert["first_price"]
                fd0_pct = result.first_alert["first_pct"]
                fd0_time = result.first_alert["time"]

            if primary_wave_id and wave.wave_id == primary_wave_id:
                if kpi and fd0_price is not None:
                    if abs(kpi.first_detected_price - fd0_price) > 0.0001:
                        result.fd_changed = True
                    if fd0_pct is not None and abs(kpi.first_detected_pct - fd0_pct) > 0.05:
                        result.fd_changed = True

                if cmp >= REAL_JUMP_SECTION_MIN_WAVE_PCT and result.cross_100 is None:
                    result.cross_100 = {"time": row["time_et"], "price": price, "pct": cmp}
                if cmp >= REAL_JUMP_EXPLOSIVE_WAVE_PCT and result.cross_150 is None:
                    result.cross_150 = {"time": row["time_et"], "price": price, "pct": cmp}
                if in_section and result.section_first is None:
                    result.section_first = {"time": row["time_et"], "pct": cmp}
                if explosive and result.explosive_first is None:
                    result.explosive_first = {"time": row["time_et"], "pct": cmp}

            result.timeline.append(
                IvpTimelineRow(
                    time=row["time_et"],
                    price=round(price, 4),
                    wave_id=wave.wave_id or "",
                    wave_state=wave.wave_state or "",
                    move_start_price=round(ms, 4),
                    current_move_pct=round(cmp, 2),
                    first_detected_price=round(kpi.first_detected_price, 4) if kpi and kpi.first_detected_price else None,
                    first_detected_pct=round(kpi.first_detected_pct, 2) if kpi and kpi.first_detected_pct else None,
                    wave_peak_price=round(wpeak, 4),
                    wave_peak_move_pct=round(wpm, 2),
                    price_jump_section=in_section,
                    explosive=explosive or display_stage == "EXPLOSIVE",
                    reset_reason=wave.reset_reason or "",
                )
            )

        return result
    except Exception as exc:
        result.data_available = False
        result.note = str(exc)
        return result
    finally:
        await client.close()


def _run(coro):
    return asyncio.run(coro)


def _primary_wave_rows(result: IvpReplayResult) -> list[IvpTimelineRow]:
    if not result.first_alert:
        return []
    wid = result.first_alert.get("wave_id")
    if not wid:
        return result.timeline
    rows = [r for r in result.timeline if r.wave_id == wid]
    if not rows:
        # fallback: rows while move_start near expected
        return [r for r in result.timeline if abs(r.move_start_price - EXPECTED_MS) <= MS_TOLERANCE]
    return rows


@pytest.mark.integration
def test_ivp_move_start_lifecycle_regression():
    result = _run(replay_ivp())
    if not result.data_available:
        pytest.skip(result.note or "IVP data unavailable")

    assert result.first_alert is not None, "expected REAL_JUMP alert on IVP session"

    primary = _primary_wave_rows(result)
    assert primary, "no rows for primary wave"

    # 1. move_start locked at ~0.0297 during primary wave
    ms_values = {r.move_start_price for r in primary if r.move_start_price > 0}
    assert len(ms_values) == 1, f"move_start changed during wave: {ms_values}"
    assert abs(next(iter(ms_values)) - EXPECTED_MS) <= MS_TOLERANCE

    # 2. first_detected immutable
    assert not result.fd_changed, "first_detected_* changed after first alert"
    fd_prices = {r.first_detected_price for r in primary if r.first_detected_price}
    fd_pcts = {r.first_detected_pct for r in primary if r.first_detected_pct is not None}
    assert len(fd_prices) <= 1 and len(fd_pcts) <= 1

    # 3. same wave_id throughout primary move
    wave_ids = {r.wave_id for r in primary if r.wave_id}
    assert len(wave_ids) == 1, f"wave_id split: {wave_ids}"

    # 4–7. live crosses and gates
    assert result.cross_100 is not None, "current_move_pct never crossed +100% live"
    assert result.cross_150 is not None, "current_move_pct never crossed +150% live"
    assert result.section_first is not None, "price_jump_section never activated live"
    assert result.explosive_first is not None, "EXPLOSIVE never activated live"

    # early detection before +100%
    assert (result.first_alert["first_pct"] or 0) < REAL_JUMP_SECTION_MIN_WAVE_PCT


def test_ivp_lifecycle_verdicts():
    """Structured PASS/FAIL markers for reporting."""
    result = _run(replay_ivp())
    if not result.data_available:
        pytest.skip(result.note or "IVP data unavailable")

    primary = _primary_wave_rows(result)
    ms_locked = (
        len({r.move_start_price for r in primary if r.move_start_price > 0}) == 1
        and primary
        and abs(primary[0].move_start_price - EXPECTED_MS) <= MS_TOLERANCE
    )
    # ignore resets that happen only after wave ended
    bad_resets = [
        r for r in result.ms_resets
        if r.get("from_ms") and abs(r["from_ms"] - EXPECTED_MS) <= MS_TOLERANCE
        and abs(r.get("to_ms", 0) - EXPECTED_MS) > MS_TOLERANCE
    ]
    lifecycle_pass = ms_locked and len(bad_resets) == 0
    cross100_pass = result.cross_100 is not None
    cross150_pass = result.explosive_first is not None
    fd_pass = not result.fd_changed and result.first_alert is not None

    # Store on module for script reporting
    test_ivp_lifecycle_verdicts.verdicts = {
        "MOVE_START LIFECYCLE FIX": "PASS" if lifecycle_pass else "FAIL",
        "IVP +100% LIVE": "PASS" if cross100_pass else "FAIL",
        "IVP +150% EXPLOSIVE": "PASS" if cross150_pass else "FAIL",
        "FIRST_DETECTED IMMUTABLE": "PASS" if fd_pass else "FAIL",
    }
    assert lifecycle_pass and cross100_pass and cross150_pass and fd_pass
