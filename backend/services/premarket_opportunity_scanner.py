"""Real-Time Premarket Opportunity Scanner — Polygon live data, trigger-based."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import pandas as pd

from analysis.indicators import vwap as calc_vwap
from models.premarket_opportunity import PremarketOpportunitySignal, PremarketScanResult
from services.extended_hours_gap_detector import (
    STALE_TRADE_SECONDS,
    _is_trade_fresh,
    _is_trade_in_extended_session,
    _ns_to_datetime,
    _safe_float,
    is_eligible_extended_gap_symbol,
)
from services.market_session import ET, PRE_MARKET_OPEN, REGULAR_OPEN, get_us_market_session

logger = logging.getLogger(__name__)

MIN_PRICE = 0.50
MAX_PRICE = 10.00
MIN_PM_CHANGE_PCT = 5.0
MIN_PM_VOLUME = 100_000
MAX_SPREAD_PCT = 2.0
VOL_ACCEL_MULT = 1.5
MIN_PULLBACK_GAIN_PCT = 10.0
DEEP_SCAN_TOP_N = 40
BAR_CACHE_TTL = 60
WEAK_VOLUME_RVOL = 0.5

ExclusionReason = Literal[
    "LOW_VOLUME",
    "NO_BREAKOUT",
    "BELOW_VWAP",
    "HIGH_SPREAD",
    "NO_VOLUME_ACCELERATION",
    "PRICE_OUT_OF_RANGE",
    "STALE_DATA",
]

_bar_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_nbbo_cache: dict[str, tuple[float, dict]] = {}
_last_scan: PremarketScanResult | None = None


@dataclass
class PremarketSnapshotRow:
    symbol: str
    current_price: float
    previous_close: float
    premarket_change_percent: float
    premarket_volume: int
    last_trade_ns: int | None
    trade_fresh: bool


@dataclass
class PremarketMetrics:
    symbol: str
    current_price: float
    premarket_change_percent: float
    premarket_volume: int
    premarket_high: float = 0.0
    premarket_low: float = 0.0
    vwap: float = 0.0
    volume_1m: int = 0
    volume_5m: int = 0
    avg_5m_volume_20m: float = 0.0
    relative_volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread_percent: float = 0.0
    distance_from_premarket_high_pct: float = 0.0
    momentum_acceleration: float = 0.0
    volume_acceleration: float = 0.0
    last_bar_close: float = 0.0
    avg_1m_volume_prior: float = 0.0
    swing_low: float = 0.0
    trade_fresh: bool = True
    bars: pd.DataFrame = field(default_factory=pd.DataFrame)


def get_last_premarket_scan() -> PremarketScanResult | None:
    return _last_scan


def _log_exclusion(
    symbol: str,
    reason: ExclusionReason,
    detail: str = "",
    *,
    status: str = "WATCH",
) -> None:
    msg = f"PREMARKET_SCANNER symbol={symbol} status={status} reason={reason}"
    if detail:
        msg += f" detail={detail}"
    logger.info(msg)


def _parse_premarket_row(symbol: str, item: dict) -> PremarketSnapshotRow | None:
    prev = item.get("prevDay") or {}
    previous_close = _safe_float(prev.get("c"))
    if previous_close <= 0:
        return None

    pre = item.get("preMarket") or {}
    last = item.get("lastTrade") or {}
    min_bar = item.get("min") or {}
    last_trade_ns = last.get("t") or item.get("updated")

    current_price = _safe_float(pre.get("c") or pre.get("h"))
    if current_price <= 0 and _is_trade_in_extended_session(last_trade_ns, "PRE_MARKET"):
        current_price = _safe_float(last.get("p"))
    if current_price <= 0:
        current_price = _safe_float(min_bar.get("c"))
    if current_price <= 0:
        return None

    pre_vol_raw = pre.get("v")
    premarket_volume = int(pre_vol_raw) if pre_vol_raw is not None and int(pre_vol_raw or 0) > 0 else 0

    change_pct = round((current_price - previous_close) / previous_close * 100.0, 2)
    trade_fresh = _is_trade_fresh(last_trade_ns)

    return PremarketSnapshotRow(
        symbol=symbol.upper(),
        current_price=round(current_price, 4),
        previous_close=round(previous_close, 4),
        premarket_change_percent=change_pct,
        premarket_volume=premarket_volume,
        last_trade_ns=int(last_trade_ns) if last_trade_ns else None,
        trade_fresh=trade_fresh,
    )


def _passes_initial_filter(
    row: PremarketSnapshotRow,
    *,
    require_volume: bool = True,
    ignore_stale: bool = False,
) -> ExclusionReason | None:
    if row.current_price < MIN_PRICE or row.current_price > MAX_PRICE:
        return "PRICE_OUT_OF_RANGE"
    if not ignore_stale and not row.trade_fresh:
        return "STALE_DATA"
    if row.premarket_change_percent < MIN_PM_CHANGE_PCT:
        return "NO_BREAKOUT"
    if require_volume and row.premarket_volume < MIN_PM_VOLUME:
        return "LOW_VOLUME"
    return None


def _filter_premarket_bars(df: pd.DataFrame, session_date) -> pd.DataFrame:
    if df.empty:
        return df
    et = df["timestamp"].dt.tz_convert(ET)
    mask = (
        (et.dt.date == session_date)
        & (et.dt.time >= PRE_MARKET_OPEN)
        & (et.dt.time < REGULAR_OPEN)
    )
    return df.loc[mask].copy()


def _compute_metrics(row: PremarketSnapshotRow, bars: pd.DataFrame, nbbo: dict) -> PremarketMetrics:
    session_date = datetime.now(ET).date()
    pm_bars = _filter_premarket_bars(bars, session_date)

    m = PremarketMetrics(
        symbol=row.symbol,
        current_price=row.current_price,
        premarket_change_percent=row.premarket_change_percent,
        premarket_volume=row.premarket_volume,
        trade_fresh=row.trade_fresh,
        bars=pm_bars,
    )

    if pm_bars.empty:
        return m

    if m.premarket_volume <= 0:
        m.premarket_volume = int(pm_bars["volume"].sum())

    m.premarket_high = round(float(pm_bars["high"].max()), 4)
    m.premarket_low = round(float(pm_bars["low"].min()), 4)
    m.vwap = round(float(calc_vwap(pm_bars["high"], pm_bars["low"], pm_bars["close"], pm_bars["volume"])), 4)

    vols = pm_bars["volume"].astype(float)
    m.volume_1m = int(vols.iloc[-1]) if len(vols) else 0
    m.volume_5m = int(vols.tail(5).sum()) if len(vols) else 0
    m.last_bar_close = round(float(pm_bars["close"].iloc[-1]), 4)

    if len(vols) >= 6:
        m.avg_1m_volume_prior = float(vols.iloc[:-1].mean()) or 1.0
    else:
        m.avg_1m_volume_prior = float(vols.mean()) or 1.0

    if len(vols) >= 25:
        prev_20 = vols.iloc[-25:-5]
        buckets = [prev_20.iloc[i : i + 5].sum() for i in range(0, 20, 5)]
        m.avg_5m_volume_20m = float(sum(buckets) / len(buckets)) if buckets else 1.0
    elif len(vols) >= 10:
        m.avg_5m_volume_20m = float(vols.iloc[:-5].tail(20).sum() / max(len(vols.iloc[:-5].tail(20)) / 5, 1))
    else:
        m.avg_5m_volume_20m = float(m.volume_5m) or 1.0

    m.relative_volume = round(m.volume_5m / m.avg_5m_volume_20m, 2) if m.avg_5m_volume_20m else 0.0
    m.volume_acceleration = round(m.volume_1m / m.avg_1m_volume_prior, 2) if m.avg_1m_volume_prior else 0.0

    if m.premarket_high > 0:
        m.distance_from_premarket_high_pct = round(
            (m.premarket_high - m.current_price) / m.premarket_high * 100.0, 2,
        )

    closes = pm_bars["close"].astype(float)
    if len(closes) >= 6:
        recent = (float(closes.iloc[-1]) - float(closes.iloc[-3])) / float(closes.iloc[-3]) * 100
        prior = (float(closes.iloc[-4]) - float(closes.iloc[-6])) / float(closes.iloc[-6]) * 100
        m.momentum_acceleration = round(recent - prior, 2)
    elif len(closes) >= 3:
        m.momentum_acceleration = round(
            (float(closes.iloc[-1]) - float(closes.iloc[-3])) / float(closes.iloc[-3]) * 100, 2,
        )

    m.swing_low = round(float(pm_bars["low"].tail(15).min()), 4)

    m.bid = round(m.current_price * 0.999, 4)
    m.ask = round(m.current_price * 1.001, 4)
    mid = m.current_price
    m.spread_percent = round((m.ask - m.bid) / mid * 100.0, 2) if mid > 0 else 99.0

    return m


def _fix_nbbo_parse(m: PremarketMetrics, nbbo: dict) -> None:
    """Polygon last/nbbo uses P=ask, p=bid in some responses."""
    bid = _safe_float(nbbo.get("p"))
    ask = _safe_float(nbbo.get("P"))
    if bid <= 0 or ask <= 0:
        bid = _safe_float(nbbo.get("bid"))
        ask = _safe_float(nbbo.get("ask"))
    if bid > 0 and ask > 0:
        m.bid = round(bid, 4)
        m.ask = round(ask, 4)
        mid = (m.bid + m.ask) / 2
        m.spread_percent = round((m.ask - m.bid) / mid * 100.0, 2) if mid > 0 else m.spread_percent


def _levels(m: PremarketMetrics, trigger: str) -> tuple[float, float, float, float, float]:
    entry = m.current_price
    if trigger == "LONG_BREAKOUT":
        stop = round(min(m.premarket_high * 0.985, m.vwap * 0.995, m.premarket_low), 4)
    else:
        stop = round(min(m.swing_low * 0.99, m.vwap * 0.985), 4)
    risk = max(entry - stop, entry * 0.02)
    tp1 = round(entry + risk * 1.5, 4)
    tp2 = round(entry + risk * 2.5, 4)
    rr = round((tp1 - entry) / risk, 2) if risk > 0 else 0.0
    return entry, stop, tp1, tp2, rr


def _evaluate_long_breakout(m: PremarketMetrics) -> tuple[bool, str, ExclusionReason | None]:
    if m.premarket_high <= 0 or m.current_price <= m.premarket_high:
        return False, "Price has not broken premarket high", "NO_BREAKOUT"
    if m.last_bar_close < m.premarket_high * 0.998:
        return False, "Breakout not held on bar close (possible wick)", "NO_BREAKOUT"
    if m.volume_1m < VOL_ACCEL_MULT * m.avg_1m_volume_prior:
        return False, f"1m vol {m.volume_1m} < {VOL_ACCEL_MULT}x avg prior", "NO_VOLUME_ACCELERATION"
    if m.current_price <= m.vwap:
        return False, f"Price {m.current_price} at/below VWAP {m.vwap}", "BELOW_VWAP"
    if m.spread_percent > MAX_SPREAD_PCT:
        return False, f"Spread {m.spread_percent}% > {MAX_SPREAD_PCT}%", "HIGH_SPREAD"
    if m.premarket_volume < MIN_PM_VOLUME or m.relative_volume < WEAK_VOLUME_RVOL:
        return False, "Premarket volume too weak", "LOW_VOLUME"
    return True, "Premarket high breakout with volume acceleration above VWAP", None


def _evaluate_long_pullback(m: PremarketMetrics) -> tuple[bool, str, ExclusionReason | None]:
    if m.premarket_change_percent < MIN_PULLBACK_GAIN_PCT:
        return False, f"Gain {m.premarket_change_percent}% < {MIN_PULLBACK_GAIN_PCT}%", "NO_BREAKOUT"
    if len(m.bars) < 8:
        return False, "Insufficient bars for pullback structure", "NO_BREAKOUT"

    highs = m.bars["high"].astype(float)
    if float(highs.max()) <= m.current_price * 1.02:
        return False, "No clear prior impulse wave", "NO_BREAKOUT"

    near_vwap = abs(m.current_price - m.vwap) / m.vwap <= 0.012 if m.vwap > 0 else False
    near_support = m.current_price <= m.swing_low * 1.015 and m.current_price >= m.swing_low * 0.985
    if not (near_vwap or near_support):
        return False, "Not at VWAP or established support", "NO_BREAKOUT"

    last2 = m.bars.tail(2)
    bounce = (
        float(last2["close"].iloc[-1]) > float(last2["open"].iloc[-1])
        and float(last2["volume"].iloc[-1]) >= float(last2["volume"].iloc[-2]) * 0.9
    )
    if not bounce:
        return False, "No bounce with rising volume", "NO_VOLUME_ACCELERATION"

    if m.current_price < m.swing_low * 0.995:
        return False, "Broke main support", "NO_BREAKOUT"
    if m.spread_percent > MAX_SPREAD_PCT:
        return False, f"Spread {m.spread_percent}% too wide", "HIGH_SPREAD"
    if m.current_price <= m.vwap:
        return False, "Pullback held but price still below VWAP", "BELOW_VWAP"

    return True, "Pullback to VWAP/support with volume bounce", None


def _metrics_to_signal(m: PremarketMetrics, trigger: str, reason: str, status: str) -> PremarketOpportunitySignal:
    entry, stop, tp1, tp2, rr = _levels(m, trigger)
    return PremarketOpportunitySignal(
        symbol=m.symbol,
        current_price=m.current_price,
        premarket_change_percent=m.premarket_change_percent,
        premarket_volume=m.premarket_volume,
        trigger_type=trigger,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        entry=entry,
        stop_loss=stop,
        tp1=tp1,
        tp2=tp2,
        risk_reward=rr,
        vwap=m.vwap,
        premarket_high=m.premarket_high,
        premarket_low=m.premarket_low,
        spread_percent=m.spread_percent,
        volume_acceleration=m.volume_acceleration,
        volume_1m=m.volume_1m,
        volume_5m=m.volume_5m,
        relative_volume=m.relative_volume,
        distance_from_premarket_high_pct=m.distance_from_premarket_high_pct,
        momentum_acceleration=m.momentum_acceleration,
        bid=m.bid,
        ask=m.ask,
        reason=reason,
    )


def _evaluate_triggers(m: PremarketMetrics) -> tuple[PremarketOpportunitySignal | None, PremarketOpportunitySignal | None, ExclusionReason | None]:
    """Returns (opportunity, watch, exclusion_reason_if_watch_only)."""
    if not m.trade_fresh:
        _log_exclusion(m.symbol, "STALE_DATA")
        return None, None, "STALE_DATA"

    ok_b, reason_b, ex_b = _evaluate_long_breakout(m)
    if ok_b:
        opp = _metrics_to_signal(m, "LONG_BREAKOUT", reason_b, "OPPORTUNITY")
        logger.info(
            "PREMARKET_SCANNER symbol=%s status=OPPORTUNITY trigger=LONG_BREAKOUT "
            "entry=%.4f stop=%.4f tp1=%.4f tp2=%.4f",
            m.symbol, opp.entry, opp.stop_loss, opp.tp1, opp.tp2,
        )
        return opp, None, None

    ok_p, reason_p, ex_p = _evaluate_long_pullback(m)
    if ok_p:
        opp = _metrics_to_signal(m, "LONG_PULLBACK", reason_p, "OPPORTUNITY")
        logger.info(
            "PREMARKET_SCANNER symbol=%s status=OPPORTUNITY trigger=LONG_PULLBACK "
            "entry=%.4f stop=%.4f tp1=%.4f tp2=%.4f",
            m.symbol, opp.entry, opp.stop_loss, opp.tp1, opp.tp2,
        )
        return opp, None, None

    exclusion = ex_b or ex_p or "NO_BREAKOUT"
    detail = reason_b if ex_b else reason_p
    _log_exclusion(m.symbol, exclusion, detail)

    watch = _metrics_to_signal(m, "", detail or "Passes filter — awaiting trigger", "WATCH")
    return None, watch, exclusion


async def _fetch_bars_cached(client, symbol: str, session_date: str | None = None) -> pd.DataFrame:
    key = f"{symbol}:{session_date or 'today'}"
    cached = _bar_cache.get(key)
    if cached and time.monotonic() - cached[0] < BAR_CACHE_TTL:
        return cached[1]
    df = await client.get_premarket_minute_bars(symbol, session_date)
    _bar_cache[key] = (time.monotonic(), df)
    return df


async def _fetch_nbbo_cached(client, symbol: str) -> dict:
    cached = _nbbo_cache.get(symbol)
    if cached and time.monotonic() - cached[0] < BAR_CACHE_TTL:
        return cached[1]
    try:
        nbbo = await client.get_last_nbbo(symbol)
    except Exception as exc:
        logger.debug("NBBO fetch %s: %s", symbol, type(exc).__name__)
        nbbo = {}
    _nbbo_cache[symbol] = (time.monotonic(), nbbo)
    return nbbo


async def scan_premarket_async(
    snapshot_raw: dict[str, dict],
    *,
    session_date: str | None = None,
    focus_symbols: list[str] | None = None,
) -> PremarketScanResult:
    from services.polygon_client import PolygonClient

    if get_us_market_session() != "PRE_MARKET" and session_date is None:
        return PremarketScanResult(message="Scanner active during PRE_MARKET only")

    candidates: list[PremarketSnapshotRow] = []
    scanned = 0

    focus_set = {s.upper() for s in focus_symbols} if focus_symbols else None

    for sym, item in snapshot_raw.items():
        if focus_set and sym.upper() not in focus_set:
            continue
        if not is_eligible_extended_gap_symbol(sym, item):
            continue
        scanned += 1
        row = _parse_premarket_row(sym, item)
        if not row:
            continue
        fail = _passes_initial_filter(row, require_volume=False)
        if fail:
            _log_exclusion(row.symbol, fail, f"px={row.current_price} chg={row.premarket_change_percent}% vol={row.premarket_volume}")
            continue
        candidates.append(row)

    candidates.sort(key=lambda r: r.premarket_change_percent, reverse=True)
    deep = candidates[:DEEP_SCAN_TOP_N]

    opportunities: list[PremarketOpportunitySignal] = []
    watches: list[PremarketOpportunitySignal] = []

    client = PolygonClient()
    try:
        for row in deep:
            try:
                bars = await _fetch_bars_cached(client, row.symbol, session_date)
                nbbo = await _fetch_nbbo_cached(client, row.symbol)
            except Exception as exc:
                _log_exclusion(row.symbol, "STALE_DATA", type(exc).__name__)
                continue

            metrics = _compute_metrics(row, bars, nbbo)
            _fix_nbbo_parse(metrics, nbbo)

            if metrics.premarket_volume < MIN_PM_VOLUME:
                _log_exclusion(row.symbol, "LOW_VOLUME", f"enriched vol={metrics.premarket_volume}")
                continue

            opp, watch, _ = _evaluate_triggers(metrics)
            if opp:
                opportunities.append(opp)
            elif watch:
                watches.append(watch)
    finally:
        await client.close()

    opportunities.sort(key=lambda o: (o.trigger_type != "", o.premarket_change_percent), reverse=True)
    watches.sort(key=lambda w: w.premarket_change_percent, reverse=True)

    top_opp = opportunities[0] if opportunities else None
    top_watch = watches[0] if watches else None

    if top_opp:
        status = "OPPORTUNITY"
        message = f"{top_opp.symbol} — {top_opp.trigger_type}"
    elif top_watch:
        status = "WATCH"
        message = f"{top_watch.symbol} — مراقبة قبل الافتتاح"
    else:
        status = "NONE"
        message = "لا توجد فرصة فعلية الآن"

    result = PremarketScanResult(
        status=status,  # type: ignore[arg-type]
        message=message,
        scanned=scanned,
        filtered=len(candidates),
        opportunities=opportunities,
        watches=watches,
        top_opportunity=top_opp,
        top_watch=top_watch,
    )
    global _last_scan
    _last_scan = result
    logger.info(
        "Premarket scan: scanned=%d filtered=%d opportunities=%d watches=%d top=%s",
        scanned, len(candidates), len(opportunities), len(watches),
        top_opp.symbol if top_opp else (top_watch.symbol if top_watch else "none"),
    )
    return result


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def sync_premarket_scanner(
    snapshot_raw: dict[str, dict] | None = None,
    *,
    session_date: str | None = None,
    focus_symbols: list[str] | None = None,
) -> PremarketScanResult:
    from services.market_scanner_service import market_scanner

    raw = snapshot_raw if snapshot_raw is not None else market_scanner._snapshot_raw
    if not raw:
        return PremarketScanResult(message="لا توجد فرصة فعلية الآن")
    try:
        return _run_async(scan_premarket_async(raw, session_date=session_date, focus_symbols=focus_symbols))
    except Exception as exc:
        logger.warning("Premarket scanner failed: %s", type(exc).__name__)
        return PremarketScanResult(message="لا توجد فرصة فعلية الآن")


async def diagnose_symbol(
    symbol: str,
    snapshot_item: dict | None = None,
    session_date: str | None = None,
) -> dict:
    """Diagnostic for a single symbol — used in PMI tests."""
    from services.polygon_client import PolygonClient

    item = snapshot_item
    if not item:
        client = PolygonClient()
        try:
            item = await client.get_snapshot(symbol)
        finally:
            await client.close()

    row = _parse_premarket_row(symbol, item or {})
    out: dict = {"symbol": symbol.upper(), "parsed": None, "metrics": None, "triggers": {}, "exclusions": []}

    if not row:
        out["exclusions"].append("PARSE_FAILED")
        return out

    out["parsed"] = {
        "current_price": row.current_price,
        "premarket_change_percent": row.premarket_change_percent,
        "premarket_volume": row.premarket_volume,
        "trade_fresh": row.trade_fresh,
    }

    fail = _passes_initial_filter(row, require_volume=False, ignore_stale=bool(session_date))
    if fail:
        out["exclusions"].append(fail)
        return out

    client = PolygonClient()
    try:
        bars = await _fetch_bars_cached(client, symbol, session_date)
        nbbo = await _fetch_nbbo_cached(client, symbol)
    finally:
        await client.close()

    m = _compute_metrics(row, bars, nbbo)
    _fix_nbbo_parse(m, nbbo)
    out["metrics"] = {
        "premarket_high": m.premarket_high,
        "premarket_low": m.premarket_low,
        "vwap": m.vwap,
        "volume_1m": m.volume_1m,
        "volume_5m": m.volume_5m,
        "relative_volume": m.relative_volume,
        "spread_percent": m.spread_percent,
        "volume_acceleration": m.volume_acceleration,
        "premarket_volume_enriched": m.premarket_volume,
    }

    ok_b, reason_b, ex_b = _evaluate_long_breakout(m)
    ok_p, reason_p, ex_p = _evaluate_long_pullback(m)
    out["triggers"] = {
        "LONG_BREAKOUT": {"ok": ok_b, "reason": reason_b, "exclusion": ex_b},
        "LONG_PULLBACK": {"ok": ok_p, "reason": reason_p, "exclusion": ex_p},
    }
    if not ok_b and ex_b:
        out["exclusions"].append(ex_b)
    if not ok_p and ex_p and not ok_b:
        out["exclusions"].append(ex_p)

    return out
