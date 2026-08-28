"""One-off REAL_JUMP historical replay — 2026-08-27 ET. Read-only, no logic changes."""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.early_upward_surge import (
    BUY_PRESSURE_SOURCE_PROXY,
    DATA_QUALITY_PROXY,
    evaluate_real_jump_alert,
)
from scripts.premove_replay_lib import ET, filter_premarket_regular, replay_session
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient
from services.real_jump_alert_layer import (
    RealJumpAlertRegistry,
    RealJumpWaveTracker,
    reset_real_jump_state,
)

DATE = "2026-08-27"
SYMBOLS = ["CHOW", "AAME", "AZIO", "ADCT"]
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass
class TimelineEvent:
    session: str
    event_time: str
    move_start_time: str = ""
    move_start_price: float = 0.0
    first_detected_time: str = ""
    first_detected_price: float | str = ""
    first_detected_pct: float | str = ""
    current_price: float = 0.0
    current_move_pct: float = 0.0
    wave_peak_time: str = ""
    wave_peak_price: float = 0.0
    price_acceleration: str = ""
    buy_pressure: float | str = ""
    buy_volume_vs_sell: str = DATA_UNAVAILABLE
    trade_velocity: float | str = DATA_UNAVAILABLE
    volume_acceleration: float = 0.0
    same_time_rvol: float | str = DATA_UNAVAILABLE
    spread: float = 0.0
    real_jump_wave_state: str = ""
    entry_status: str = ""
    wave_id: str = ""
    confirmed: bool = False
    reject_reason: str = ""
    exit_reason: str = ""
    event_tag: str = ""
    data_quality: str = DATA_QUALITY_PROXY
    buy_pressure_source: str = BUY_PRESSURE_SOURCE_PROXY


@dataclass
class SymbolReplay:
    symbol: str
    data_available: bool = True
    trades_quotes_note: str = ""
    timeline: list[TimelineEvent] = field(default_factory=list)
    first_detection_price: float | None = None
    first_detection_time: str | None = None
    peak_after_detection: float = 0.0
    final_state: str = ""
    any_confirmed: bool = False
    wave_id: str = ""
    wave_peak_price: float = 0.0
    first_real_jump_count: int = 0
    entry_status_final: str = ""
    data_quality: str = DATA_QUALITY_PROXY
    buy_pressure_source: str = BUY_PRESSURE_SOURCE_PROXY
    note: str = ""


def _session_label(time_et: str) -> str:
    t = datetime.strptime(time_et.split()[1], "%H:%M:%S").time()
    from datetime import datetime as dt
    if t < dt.strptime("09:30", "%H:%M").time():
        return "PRE_MARKET"
    if t < dt.strptime("16:00", "%H:%M").time():
        return "REGULAR"
    return "AFTER_HOURS"


async def probe_trades_quotes(client: PolygonClient, symbol: str) -> tuple[bool, str]:
    sym = symbol.upper()
    try:
        trades = await client._request(
            f"/v3/trades/{sym}",
            params={
                "timestamp.gte": f"{DATE}T13:30:00Z",
                "timestamp.lte": f"{DATE}T20:00:00Z",
                "limit": 5,
                "sort": "timestamp",
                "order": "asc",
            },
        )
        n_tr = len(trades.get("results") or [])
        quotes = await client._request(
            f"/v3/quotes/{sym}",
            params={
                "timestamp.gte": f"{DATE}T13:30:00Z",
                "timestamp.lte": f"{DATE}T20:00:00Z",
                "limit": 5,
                "sort": "timestamp",
                "order": "asc",
            },
        )
        n_q = len(quotes.get("results") or [])
        return (n_tr > 0 or n_q > 0), f"trades={n_tr}, quotes={n_q} (tick buy/sell split: {DATA_UNAVAILABLE} in 1m replay)"
    except Exception as exc:
        return False, f"{DATA_UNAVAILABLE}: {exc}"


def _eval_bar(row, tracker, registry, symbol, bars_window, bar_ts, existing_alert):
    from datetime import timezone

    if hasattr(bar_ts, "to_pydatetime"):
        bar_ts = bar_ts.to_pydatetime()
    if bar_ts.tzinfo is None:
        bar_ts = bar_ts.replace(tzinfo=timezone.utc)

    px = float(row["price"])
    tv = row.get("trade_velocity")
    pvr = min(1.0, float(row.get("early_activity_score", 0)) / 28.0)
    if row.get("price_volume_response") is not None:
        pvr = float(row["price_volume_response"])
    spread_pct = float(row.get("spread_pct") or 0)
    if spread_pct <= 0 and len(bars_window):
        spread_pct = (
            (float(bars_window.iloc[-1]["high"]) - float(bars_window.iloc[-1]["low"])) / px * 100.0
            if px else 0.0
        )
    wave = tracker.update(
        symbol,
        current_price=px,
        bars=bars_window,
        timestamp=bar_ts,
        trade_velocity=float(tv) if tv != DATA_UNAVAILABLE else 0.0,
        volume_acceleration_1m=float(row["volume_acceleration_1m"]),
    )
    verdict = evaluate_real_jump_alert(
        current_price=px,
        change_pct=float(row["change_pct"]),
        price_volume_response=pvr,
        micro_higher_lows=bool(row.get("micro_higher_lows")),
        breakout_pressure=float(row.get("breakout_pressure", 0) or 0),
        resistance_distance_pct=float(row.get("resistance_distance_pct", 99)),
        trigger_price=float(row.get("trigger_price", 0)),
        movement_start_price=0,
        volume_acceleration_1m=float(row["volume_acceleration_1m"]),
        volume_acceleration_slope=float(row["volume_acceleration_slope"]),
        rvol=float(row.get("rvol_same_time") or 0),
        rvol_same_time=float(row["rvol_same_time"]) if row.get("rvol_same_time") is not None else None,
        trade_velocity_growth=float(row.get("trade_velocity_growth") or 0.15) if tv != DATA_UNAVAILABLE else 0.0,
        trade_velocity=float(tv) if tv != DATA_UNAVAILABLE else None,
        dollar_volume_growth=float(row.get("dollar_volume_growth") or 0.2),
        liquidity_score=float(row.get("liquidity_score", 60)),
        spread_pct=spread_pct,
        persistence_minutes=int(row.get("persistence_minutes", 0)),
        range_compression_3m=float(row.get("compression_3m", 0)),
        bars=bars_window,
        wave=wave,
        data_age_seconds=30.0,
        is_alert_update=existing_alert is not None,
    )
    proc = registry.process(
        symbol,
        verdict,
        wave=wave,
        current_price=px,
        timestamp=bar_ts,
        price_volume_response=pvr,
        trade_velocity_growth=float(row.get("trade_velocity_growth") or 0.15) if tv != DATA_UNAVAILABLE else 0.0,
        trade_velocity=float(tv) if tv != DATA_UNAVAILABLE else None,
        volume_acceleration_1m=float(row["volume_acceleration_1m"]),
        spread_pct=spread_pct,
        liquidity_score=float(row.get("liquidity_score", 60)),
        bars=bars_window,
    )
    return verdict, proc, wave, pvr


async def replay_symbol(client: PolygonClient, symbol: str) -> SymbolReplay:
    out = SymbolReplay(symbol=symbol)
    tq_ok, tq_note = await probe_trades_quotes(client, symbol)
    out.trades_quotes_note = tq_note

    bars = filter_premarket_regular(await client.get_minute_bars_on_date(symbol, DATE))
    if bars.empty or len(bars) < 5:
        out.data_available = False
        out.note = DATA_UNAVAILABLE
        return out

    prior_date = "2026-08-26"
    try:
        prior = await client.get_premarket_minute_bars(symbol, session_date=prior_date)
    except Exception:
        prior = None
    prev_resp = await client._request(f"/v2/aggs/ticker/{symbol.upper()}/prev", params={"adjusted": "true"})
    prev_close = float((prev_resp.get("results") or [{}])[0].get("c") or float(bars["close"].iloc[0]))
    news = await fetch_stock_news(client, symbol, 5)
    timeline_rows = replay_session(bars, prior, news, prev_close, symbol=symbol, session_date=DATE)

    reset_real_jump_state()
    tracker = RealJumpWaveTracker()
    registry = RealJumpAlertRegistry()

    first_det_time = ""
    first_det_price: float | None = None
    peak_after = 0.0
    wave_peak_time = ""
    wave_peak_price = 0.0
    move_start_time = ""
    move_start_price = 0.0
    final_state = ""
    milestones: list[TimelineEvent] = []
    alert_active = False
    first_jump_count = 0
    locked_wave_id = ""

    for row in timeline_rows:
        i = int(row["bar_idx"])
        window = bars.iloc[: i + 1]
        bar_ts = window["timestamp"].iloc[-1]
        existing = registry.get(symbol)
        verdict, proc, wave, pvr = _eval_bar(row, tracker, registry, symbol, window, bar_ts, existing)

        px = float(row["price"])
        if wave.move_start_price > 0:
            move_start_price = wave.move_start_price
            if wave.move_start_time:
                move_start_time = wave.move_start_time.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S")
        if px >= wave_peak_price:
            wave_peak_price = max(wave_peak_price, px, wave.wave_peak_price)
            wave_peak_time = row["time_et"]

        if proc.emit and not proc.update_existing:
            if first_det_price is None:
                first_det_price = px
                first_det_time = row["time_et"]
            alert_active = True
            first_jump_count += 1
            locked_wave_id = wave.wave_id or locked_wave_id

        if first_det_price is not None:
            peak_after = max(peak_after, wave.wave_peak_price, px)

        if proc.clear:
            alert_active = False
            final_state = wave.wave_state or wave.reset_reason or "WAVE_ENDED"
            exit_reason = wave.reset_reason or verdict.reject_reason
        elif registry.get(symbol):
            final_state = wave.wave_state or "ACTIVE_UPWARD_WAVE"

        tv = row.get("trade_velocity")
        acc = f"1m={wave.price_acceleration_1m:.3f},3m={wave.price_acceleration_3m:.3f},5m={wave.price_acceleration_5m:.3f}"
        rvol = row.get("rvol_same_time")
        spread = float(row.get("spread_pct") or (float(window.iloc[-1]["high"]) - float(window.iloc[-1]["low"])) / px * 100 if px else 0)

        tag = ""
        if proc.emit and not proc.update_existing:
            tag = "FIRST_REAL_JUMP"
        elif proc.clear:
            tag = "EXIT"
        elif proc.emit and proc.update_existing:
            tag = "UPDATE"

        if tag or (i % max(1, len(timeline_rows) // 25) == 0) or verdict.confirmed or registry.get(symbol):
            fd_p = first_det_price if first_det_price else ""
            fd_pct = ""
            if first_det_price and move_start_price > 0:
                fd_pct = round((first_det_price - move_start_price) / move_start_price * 100, 2)
            milestones.append(
                TimelineEvent(
                    session=_session_label(row["time_et"]),
                    event_time=row["time_et"],
                    move_start_time=move_start_time,
                    move_start_price=round(move_start_price, 4),
                    first_detected_time=first_det_time,
                    first_detected_price=round(fd_p, 4) if fd_p else "",
                    first_detected_pct=fd_pct,
                    current_price=round(px, 4),
                    current_move_pct=round(wave.current_move_pct, 2),
                    wave_peak_time=wave_peak_time,
                    wave_peak_price=round(wave_peak_price, 4),
                    price_acceleration=acc,
                    buy_pressure=round(pvr, 3),
                    buy_volume_vs_sell=DATA_UNAVAILABLE,
                    trade_velocity=tv if tv != DATA_UNAVAILABLE else DATA_UNAVAILABLE,
                    volume_acceleration=round(float(row["volume_acceleration_1m"]), 3),
                    same_time_rvol=round(float(rvol), 3) if rvol is not None else DATA_UNAVAILABLE,
                    spread=round(spread, 3),
                    real_jump_wave_state=wave.wave_state or "",
                    entry_status=verdict.entry_status or wave.entry_status or "",
                    wave_id=wave.wave_id or locked_wave_id,
                    confirmed=verdict.confirmed or bool(registry.get(symbol)),
                    reject_reason=verdict.reject_reason if not verdict.confirmed and not registry.get(symbol) else "",
                    exit_reason=wave.reset_reason if proc.clear else "",
                    event_tag=tag,
                    data_quality=DATA_QUALITY_PROXY,
                    buy_pressure_source=BUY_PRESSURE_SOURCE_PROXY,
                )
            )

    hist = tracker._get(symbol)
    out.timeline = milestones
    out.first_detection_price = first_det_price
    out.first_detection_time = first_det_time or None
    out.peak_after_detection = round(peak_after, 4)
    out.wave_peak_price = round(hist.locked.wave_peak_price, 4)
    out.wave_id = hist.locked.wave_id or locked_wave_id
    out.first_real_jump_count = first_jump_count
    out.final_state = final_state or (registry.get(symbol) and "ACTIVE_UPWARD_WAVE") or "NO_ALERT"
    out.entry_status_final = (registry.get(symbol) and registry.get(symbol).verdict.entry_status) or ""
    out.any_confirmed = first_jump_count > 0
    out.data_quality = DATA_QUALITY_PROXY
    out.buy_pressure_source = BUY_PRESSURE_SOURCE_PROXY
    out.note = f"bars={len(bars)} trades_quotes={tq_ok} {tq_note}"
    return out


def grade_chow(r: SymbolReplay) -> str:
    if not r.data_available:
        return "FAIL"
    if not r.first_detection_price or r.first_detection_price > 0.55:
        return "FAIL"
    peak = max(r.peak_after_detection, r.wave_peak_price)
    if peak < 0.80:
        return "FAIL"
    if r.first_real_jump_count != 1:
        return "FAIL"
    return "PASS"


def grade_reject(r: SymbolReplay) -> str:
    if not r.data_available:
        return "FAIL"
    return "PASS" if r.first_real_jump_count == 0 else "FAIL"


async def main() -> None:
    client = PolygonClient()
    results: dict[str, SymbolReplay] = {}
    try:
        for sym in SYMBOLS:
            print(f"Replaying {sym}...", flush=True)
            results[sym] = await replay_symbol(client, sym)
    finally:
        await client.close()

    summary = []
    expected = {
        "CHOW": "ACCEPT early then WAVE_ENDED",
        "AAME": "REJECT stalled after 1.69",
        "AZIO": "REJECT stalled after 1.55",
        "ADCT": "REJECT weak buy / no live rise",
    }
    graders = {"CHOW": grade_chow, "AAME": grade_reject, "AZIO": grade_reject, "ADCT": grade_reject}

    for sym, r in results.items():
        pf = "PASS" if r.data_available and graders[sym](r) == "PASS" else ("DATA_UNAVAILABLE" if not r.data_available else "FAIL")
        summary.append({
            "Symbol": sym,
            "Expected": expected[sym],
            "Actual": "REAL_JUMP" if r.any_confirmed else "NO_REAL_JUMP",
            "First Detection": f"{r.first_detection_time} @ {r.first_detection_price}" if r.first_detection_price else "—",
            "Peak After Detection": r.peak_after_detection,
            "Final State": r.final_state,
            "PASS/FAIL": pf,
        })

    out_path = Path(__file__).with_name("real_jump_aug27_replay_report.json")
    payload = {
        "date": DATE,
        "timezone": "America/New_York",
        "data_source": "Polygon 1m OHLCV causal replay + premove_replay_lib metrics",
        "buy_sell_volume": DATA_UNAVAILABLE,
        "symbols": {k: {**asdict(v), "timeline": [asdict(t) for t in v.timeline]} for k, v in results.items()},
        "summary_table": summary,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"summary": summary, "report": str(out_path)}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
