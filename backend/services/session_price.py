"""Session-aware price resolution — single source of truth for current_price."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from services.market_session import (
    AFTER_HOURS_CLOSE,
    ET,
    PRE_MARKET_OPEN,
    REGULAR_CLOSE,
    REGULAR_OPEN,
    MarketSession,
    get_us_market_session,
)

logger = logging.getLogger(__name__)

STALE_TRADE_SECONDS = 900

PriceSource = Literal[
    "live_trade",
    "live_quote",
    "last_trade",
    "day_bar",
    "min_bar",
    "quote",
    "premarket",
    "after_hours",
    "prev_close",
    "none",
]

STALE_PRICE_STATUS = "STALE_PRICE"
STALE_PRICE_REASON_AR = "السعر اللحظي غير محدث — تم إيقاف التوصية مؤقتًا"

# REGULAR session — source-specific freshness (scalping-grade)
REGULAR_LAST_TRADE_MAX_AGE_SECONDS = int(os.getenv("REGULAR_LAST_TRADE_MAX_AGE_SECONDS", "15"))
REGULAR_QUOTE_MAX_AGE_SECONDS = int(os.getenv("REGULAR_QUOTE_MAX_AGE_SECONDS", "5"))
REGULAR_DAY_BAR_MAX_AGE_SECONDS = int(os.getenv("REGULAR_DAY_BAR_MAX_AGE_SECONDS", "60"))

# Legacy alias — no longer used for REGULAR resolution
REGULAR_PRICE_MAX_AGE_SECONDS = REGULAR_LAST_TRADE_MAX_AGE_SECONDS

_last_known_session: MarketSession | None = None


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _exchange_ts_to_epoch_seconds(raw: object) -> float | None:
    """Normalize Polygon/Massive exchange timestamps to UTC epoch seconds."""
    if raw is None:
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    # Magnitude-based unit detection (REST snapshots often ns; WebSocket T/Q use ms).
    if v >= 100_000_000_000_000_000:  # nanoseconds
        return v / 1_000_000_000.0
    if v >= 100_000_000_000_000:  # microseconds
        return v / 1_000_000.0
    if v >= 100_000_000_000:  # milliseconds
        return v / 1_000.0
    return float(v)


def _ns_to_datetime(ns: object) -> datetime | None:
    """Parse exchange timestamp (seconds, ms, µs, or ns) to UTC datetime."""
    secs = _exchange_ts_to_epoch_seconds(ns)
    if secs is None:
        return None
    try:
        return datetime.fromtimestamp(secs, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _is_trade_fresh(trade_ns: object, max_age_seconds: int = STALE_TRADE_SECONDS) -> bool:
    trade_dt = _ns_to_datetime(trade_ns)
    if trade_dt is None:
        return False
    return _age_seconds(trade_dt) <= max_age_seconds


def _age_seconds(when: datetime | None) -> float:
    if when is None:
        return float("inf")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - when).total_seconds())


def _snapshot_timestamp(item: dict) -> datetime | None:
    """Best-effort snapshot / bar update time from Polygon ticker payload."""
    raw = item.get("updated")
    if raw is not None:
        dt = _ns_to_datetime(raw)
        if dt is not None:
            return dt
    min_bar = item.get("min") or {}
    min_t = min_bar.get("t") or min_bar.get("s")
    if min_t is not None:
        try:
            val = int(min_t)
            if val > 1_000_000_000_000_000:  # ns
                return _ns_to_datetime(val)
            if val > 1_000_000_000_000:  # ms
                return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    return None


def _is_trade_in_extended_session(trade_ns: object, session: MarketSession) -> bool:
    trade_dt = _ns_to_datetime(trade_ns)
    if trade_dt is None:
        return False
    trade_et = trade_dt.astimezone(ET)
    now_et = datetime.now(ET)
    if trade_et.date() != now_et.date():
        return False
    t = trade_et.time()
    if session == "PRE_MARKET":
        return PRE_MARKET_OPEN <= t < REGULAR_OPEN
    if session == "AFTER_HOURS":
        return REGULAR_CLOSE <= t < AFTER_HOURS_CLOSE
    return False


@dataclass(frozen=True)
class SessionPrice:
    price: float
    volume: int
    change: float
    change_percent: float
    timestamp: datetime | None
    session: MarketSession
    source: PriceSource
    is_stale: bool = False
    stale_reason: str = ""

    @property
    def is_valid(self) -> bool:
        return self.price > 0 and not self.is_stale

    def to_metadata(self) -> dict:
        age = _age_seconds(self.timestamp) if self.timestamp else None
        return {
            "price": round(self.price, 4),
            "price_timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "price_session": self.session,
            "price_source": self.source,
            "price_is_stale": self.is_stale,
            "price_stale_reason": self.stale_reason,
            "price_age_seconds": round(age, 1) if age is not None and age != float("inf") else None,
        }


def _is_trade_in_regular_session(trade_ns: object) -> bool:
    trade_dt = _ns_to_datetime(trade_ns)
    if trade_dt is None:
        return False
    trade_et = trade_dt.astimezone(ET)
    now_et = datetime.now(ET)
    if trade_et.date() != now_et.date():
        return False
    t = trade_et.time()
    return REGULAR_OPEN <= t < REGULAR_CLOSE


def _is_min_bar_in_regular_session(min_bar: dict) -> bool:
    """Polygon snapshot min bar is the current minute — valid during regular hours."""
    if not min_bar:
        return False
    now_et = datetime.now(ET)
    t = now_et.time()
    return REGULAR_OPEN <= t < REGULAR_CLOSE


def _quote_mid(nbbo: dict | None) -> tuple[float, datetime | None]:
    if not nbbo:
        return 0.0, None
    bid = _safe_float(nbbo.get("p") or nbbo.get("bid"))
    ask = _safe_float(nbbo.get("P") or nbbo.get("ask"))
    if bid <= 0 or ask <= 0:
        return 0.0, None
    ts_raw = nbbo.get("t") or nbbo.get("sip_timestamp") or nbbo.get("participant_timestamp")
    ts = _ns_to_datetime(ts_raw) if ts_raw else None
    return round((bid + ask) / 2, 4), ts


def _build_result(
    *,
    price: float,
    volume: int,
    prev_close: float,
    timestamp: datetime | None,
    session: MarketSession,
    source: PriceSource,
    is_stale: bool = False,
    stale_reason: str = "",
) -> SessionPrice:
    change = price - prev_close if prev_close > 0 else 0.0
    change_pct = (change / prev_close * 100.0) if prev_close > 0 else 0.0
    return SessionPrice(
        price=round(price, 4),
        volume=max(0, volume),
        change=round(change, 4),
        change_percent=round(change_pct, 2),
        timestamp=timestamp,
        session=session,
        source=source,
        is_stale=is_stale,
        stale_reason=stale_reason,
    )


def _stale(session: MarketSession, prev_close: float, reason: str = STALE_PRICE_STATUS) -> SessionPrice:
    return _build_result(
        price=0.0,
        volume=0,
        prev_close=prev_close,
        timestamp=None,
        session=session,
        source="none",
        is_stale=True,
        stale_reason=reason,
    )


def _resolve_regular_price(
    item: dict,
    *,
    prev_close: float,
    nbbo: dict | None,
) -> SessionPrice:
    """REGULAR: live_trade → live_quote → REST fallbacks (freshness-guarded). Never premarket."""
    from services.live_price_registry import live_price_registry

    sym = (item.get("ticker") or "").upper()
    day = item.get("day") or {}
    day_vol = int(day.get("v") or 0)

    live = live_price_registry.resolve_live(sym, prev_close=prev_close, volume=day_vol)
    if live is not None and live.is_valid:
        return live

    last = item.get("lastTrade") or {}
    day = item.get("day") or {}
    min_bar = item.get("min") or {}
    last_trade_ns = last.get("t") or item.get("updated")
    last_trade_p = _safe_float(last.get("p"))
    day_vol = int(day.get("v") or 0)
    snap_ts = _snapshot_timestamp(item)

    # 1) fresh last_trade (≤15s, regular session only)
    if (
        last_trade_p > 0
        and _is_trade_in_regular_session(last_trade_ns)
        and _is_trade_fresh(last_trade_ns, REGULAR_LAST_TRADE_MAX_AGE_SECONDS)
    ):
        return _build_result(
            price=last_trade_p,
            volume=day_vol,
            prev_close=prev_close,
            timestamp=_ns_to_datetime(last_trade_ns),
            session="REGULAR",
            source="last_trade",
        )

    # 2) fresh quote (≤5s)
    quote_p, quote_ts = _quote_mid(nbbo)
    if quote_p > 0 and quote_ts is not None and _age_seconds(quote_ts) <= REGULAR_QUOTE_MAX_AGE_SECONDS:
        return _build_result(
            price=quote_p,
            volume=day_vol,
            prev_close=prev_close,
            timestamp=quote_ts,
            session="REGULAR",
            source="quote",
        )

    # 3) fresh day_bar / regular session bar (≤60s)
    day_c = _safe_float(day.get("c"))
    bar_ts = snap_ts
    if bar_ts is None and _is_min_bar_in_regular_session(min_bar):
        bar_ts = _snapshot_timestamp({"min": min_bar})

    if day_c > 0 and day_vol > 0 and bar_ts is not None and _age_seconds(bar_ts) <= REGULAR_DAY_BAR_MAX_AGE_SECONDS:
        return _build_result(
            price=day_c,
            volume=day_vol,
            prev_close=prev_close,
            timestamp=bar_ts,
            session="REGULAR",
            source="day_bar",
        )

    min_c = _safe_float(min_bar.get("c"))
    min_v = int(min_bar.get("v") or 0)
    if (
        min_c > 0
        and min_v > 0
        and _is_min_bar_in_regular_session(min_bar)
        and bar_ts is not None
        and _age_seconds(bar_ts) <= REGULAR_DAY_BAR_MAX_AGE_SECONDS
    ):
        return _build_result(
            price=min_c,
            volume=min_v,
            prev_close=prev_close,
            timestamp=bar_ts,
            session="REGULAR",
            source="min_bar",
        )

    if last_trade_p > 0 and not _is_trade_in_regular_session(last_trade_ns):
        logger.debug(
            "Rejecting premarket lastTrade %.4f during REGULAR for %s",
            last_trade_p,
            item.get("ticker"),
        )
    return _stale("REGULAR", prev_close)


def inspect_price_sources(
    item: dict,
    session: MarketSession | None = None,
    nbbo: dict | None = None,
) -> dict:
    """Diagnostic view of candidate prices and freshness for reporting."""
    market_session = session or get_us_market_session()
    last = item.get("lastTrade") or {}
    day = item.get("day") or {}
    pre = item.get("preMarket") or {}
    last_trade_ns = last.get("t") or item.get("updated")
    last_trade_p = _safe_float(last.get("p"))
    snap_ts = _snapshot_timestamp(item)
    quote_p, quote_ts = _quote_mid(nbbo)

    lt_age = _age_seconds(_ns_to_datetime(last_trade_ns)) if last_trade_ns else None
    q_age = _age_seconds(quote_ts) if quote_ts else None
    bar_age = _age_seconds(snap_ts) if snap_ts else None

    resolved = resolve_session_price(item, session=market_session, nbbo=nbbo)

    live_inspect = None
    sym = (item.get("ticker") or "").upper()
    if sym and market_session == "REGULAR":
        try:
            from services.live_price_registry import live_price_registry

            live_inspect = live_price_registry.inspect(sym)
        except Exception:
            pass

    return {
        "symbol": sym,
        "session": market_session,
        "live_registry": live_inspect,
        "last_trade": {
            "price": last_trade_p,
            "age_seconds": round(lt_age, 1) if lt_age is not None and lt_age != float("inf") else None,
            "in_regular_session": _is_trade_in_regular_session(last_trade_ns),
            "fresh": (
                last_trade_p > 0
                and _is_trade_in_regular_session(last_trade_ns)
                and lt_age is not None
                and lt_age <= REGULAR_LAST_TRADE_MAX_AGE_SECONDS
            ),
            "max_age_seconds": REGULAR_LAST_TRADE_MAX_AGE_SECONDS,
        },
        "quote": {
            "price": quote_p,
            "age_seconds": round(q_age, 1) if q_age is not None and q_age != float("inf") else None,
            "fresh": quote_p > 0 and q_age is not None and q_age <= REGULAR_QUOTE_MAX_AGE_SECONDS,
            "max_age_seconds": REGULAR_QUOTE_MAX_AGE_SECONDS,
        },
        "day_bar": {
            "price": _safe_float(day.get("c")),
            "age_seconds": round(bar_age, 1) if bar_age is not None and bar_age != float("inf") else None,
            "fresh": (
                _safe_float(day.get("c")) > 0
                and int(day.get("v") or 0) > 0
                and bar_age is not None
                and bar_age <= REGULAR_DAY_BAR_MAX_AGE_SECONDS
            ),
            "max_age_seconds": REGULAR_DAY_BAR_MAX_AGE_SECONDS,
        },
        "premarket": {
            "price": _safe_float(pre.get("c") or pre.get("h")) if pre else None,
            "eligible_during_regular": False,
        },
        "resolved": {
            "price": resolved.price,
            "source": resolved.source,
            "session": resolved.session,
            "is_stale": resolved.is_stale,
            "is_fresh": resolved.is_valid,
            "timestamp": resolved.timestamp.isoformat() if resolved.timestamp else "",
            "age_seconds": round(_age_seconds(resolved.timestamp), 1)
            if resolved.timestamp
            else None,
        },
    }


def resolve_session_price(
    item: dict,
    session: MarketSession | None = None,
    nbbo: dict | None = None,
    *,
    max_age_seconds: int | None = None,
) -> SessionPrice:
    """Resolve current price strictly for the active market session."""
    market_session = session or get_us_market_session()
    prev = item.get("prevDay") or {}
    prev_close = _safe_float(prev.get("c"))
    last = item.get("lastTrade") or {}
    day = item.get("day") or {}
    min_bar = item.get("min") or {}
    pre = item.get("preMarket") or {}
    after = item.get("afterHours") or {}
    last_trade_ns = last.get("t") or item.get("updated")
    last_trade_p = _safe_float(last.get("p"))

    if market_session == "REGULAR":
        if max_age_seconds is not None:
            # Test override: treat as last_trade max age only
            trade_ts = _ns_to_datetime(last_trade_ns)
            if (
                last_trade_p > 0
                and _is_trade_in_regular_session(last_trade_ns)
                and _is_trade_fresh(last_trade_ns, max_age_seconds)
            ):
                return _build_result(
                    price=last_trade_p,
                    volume=int(day.get("v") or 0),
                    prev_close=prev_close,
                    timestamp=trade_ts,
                    session=market_session,
                    source="last_trade",
                )
        return _resolve_regular_price(item, prev_close=prev_close, nbbo=nbbo)

    if market_session == "PRE_MARKET":
        pre_price = _safe_float(pre.get("c") or pre.get("h"))
        pre_vol = int(pre.get("v") or 0) if pre.get("v") is not None else 0
        trade_ts = _ns_to_datetime(last_trade_ns)

        if pre_price <= 0 and _is_trade_in_extended_session(last_trade_ns, "PRE_MARKET"):
            pre_price = last_trade_p
        if pre_price <= 0:
            pre_price = _safe_float(min_bar.get("c"))
        if pre_price <= 0:
            return _stale(market_session, prev_close)

        fresh = _is_trade_fresh(last_trade_ns, STALE_TRADE_SECONDS)
        if not fresh and pre_vol <= 0:
            return _stale(market_session, prev_close)

        return _build_result(
            price=pre_price,
            volume=pre_vol,
            prev_close=prev_close,
            timestamp=trade_ts,
            session=market_session,
            source="premarket" if pre.get("c") or pre.get("h") else "last_trade",
        )

    if market_session == "AFTER_HOURS":
        after_price = _safe_float(after.get("c") or after.get("h"))
        after_vol = int(after.get("v") or 0) if after.get("v") is not None else 0
        trade_ts = _ns_to_datetime(last_trade_ns)

        if after_price <= 0 and _is_trade_in_extended_session(last_trade_ns, "AFTER_HOURS"):
            after_price = last_trade_p
        if after_price <= 0:
            return _stale(market_session, prev_close)

        fresh = _is_trade_fresh(last_trade_ns, STALE_TRADE_SECONDS)
        if not fresh and after_vol <= 0:
            return _stale(market_session, prev_close)

        return _build_result(
            price=after_price,
            volume=after_vol,
            prev_close=prev_close,
            timestamp=trade_ts,
            session=market_session,
            source="after_hours",
        )

    # CLOSED — last valid regular close with session label
    day_c = _safe_float(day.get("c"))
    day_v = int(day.get("v") or 0)
    close_price = day_c or prev_close
    if close_price <= 0:
        return _stale(market_session, prev_close)
    return _build_result(
        price=close_price,
        volume=day_v or int(prev.get("v") or 0),
        prev_close=prev_close,
        timestamp=None,
        session=market_session,
        source="day_bar" if day_c > 0 else "prev_close",
    )


def parse_snapshot_price(
    snap: dict,
    session: MarketSession | None = None,
    nbbo: dict | None = None,
) -> tuple[float, int, float, float, SessionPrice]:
    """Backward-compatible tuple + full SessionPrice metadata."""
    sp = resolve_session_price(snap, session=session, nbbo=nbbo)
    if sp.is_stale:
        return 0.0, 0, 0.0, 0.0, sp
    return sp.price, sp.volume, sp.change, sp.change_percent, sp


def resolve_jump_execution_price(
    item: dict,
    *,
    symbol: str,
    session: MarketSession | None = None,
    nbbo: dict | None = None,
) -> tuple[SessionPrice, dict]:
    """
    Jump pipeline price — prefer WS live tick, then REST NBBO/trade fallbacks.
    Returns (SessionPrice, diagnostic dict).
    """
    from services.live_price_registry import live_price_registry

    sym = symbol.upper()
    market_session = session or get_us_market_session()

    merged_item = dict(item)
    try:
        from services.market_scanner_service import market_scanner

        cached = market_scanner._snapshot_raw.get(sym)
        if cached:
            merged_item = dict(cached)
    except Exception:
        pass

    merged_item = live_price_registry.patch_snapshot_item(merged_item, sym)
    sp = resolve_session_price(merged_item, session=market_session, nbbo=nbbo)

    ws_age = live_price_registry.ws_message_age_seconds()
    snap_ts = _snapshot_timestamp(merged_item)
    snap_age = _age_seconds(snap_ts) if snap_ts else None
    live_inspect = live_price_registry.inspect(sym) if market_session == "REGULAR" else {}

    diag = {
        "symbol": sym,
        "price_source": sp.source,
        "price": sp.price,
        "last_ws_message_age": round(ws_age, 1) if ws_age is not None else None,
        "snapshot_age": round(snap_age, 1) if snap_age is not None else None,
        "STALE_PRICE": sp.is_stale,
        "ws_connected": live_price_registry.status.connected,
        "ws_subscribed": sym in live_price_registry.status.subscribed_symbols,
        "live_trade_fresh": (live_inspect.get("live_trade") or {}).get("fresh"),
    }
    logger.info(
        "JUMP_PRICE_DIAGNOSTIC symbol=%s price_source=%s price=%s last_ws_message_age=%s "
        "snapshot_age=%s STALE_PRICE=%s ws_connected=%s ws_subscribed=%s",
        sym,
        diag["price_source"],
        diag["price"],
        diag["last_ws_message_age"],
        diag["snapshot_age"],
        diag["STALE_PRICE"],
        diag["ws_connected"],
        diag["ws_subscribed"],
    )
    return sp, diag


def invalidate_price_caches() -> None:
    """Drop cached symbol/bar data when market session changes."""
    try:
        from services import stock_service

        stock_service._symbol_cache.clear()
        stock_service._last_logged_signal.clear()
        stock_service._last_journal_key.clear()
    except Exception as exc:
        logger.debug("stock_service cache clear skipped: %s", exc)

    try:
        from services.premarket_opportunity_scanner import _bar_cache, _nbbo_cache

        _bar_cache.clear()
        _nbbo_cache.clear()
    except Exception as exc:
        logger.debug("premarket cache clear skipped: %s", exc)

    try:
        from services.pre_move_predictor_service import _bar_cache as pm_bar_cache

        pm_bar_cache.clear()
    except Exception as exc:
        logger.debug("pre_move bar cache clear skipped: %s", exc)

    try:
        from services.snapshot_cache_service import invalidate_opportunities_cache

        invalidate_opportunities_cache()
    except Exception as exc:
        logger.debug("opportunities cache clear skipped: %s", exc)

    try:
        from services.live_price_registry import live_price_registry

        live_price_registry.clear_execution_prices()
    except Exception as exc:
        logger.debug("live_price_registry clear skipped: %s", exc)

    logger.info("Price caches invalidated on session transition")


def ensure_session_cache_valid() -> MarketSession:
    """Invalidate stale session prices when PREMARKET→REGULAR etc."""
    global _last_known_session
    current = get_us_market_session()
    if _last_known_session is not None and _last_known_session != current:
        invalidate_price_caches()
    _last_known_session = current
    return current
