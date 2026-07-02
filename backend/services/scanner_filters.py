"""Coarse filters and ranking for US market snapshot tickers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from config import (
    SCANNER_MAX_PRICE,
    SCANNER_MAX_SPREAD_PCT,
    SCANNER_MIN_AVG_VOLUME,
    SCANNER_MIN_DAY_VOLUME,
    SCANNER_MIN_MARKET_CAP,
    SCANNER_MIN_PRICE,
    SCANNER_MIN_RVOL,
)
from services.market_session import MarketSession, is_regular_session
from services.volume_cache import get_cached_adv30


@dataclass
class TickerMetrics:
    symbol: str
    name: str
    price: float
    change_percent: float
    volume: int
    prev_volume: int
    relative_volume: float
    volume_spike: bool
    spread_pct: float
    day_open: float
    day_high: float
    day_low: float
    premarket_change_pct: float
    afterhours_change_pct: float
    market_cap: float
    float_shares: float
    opening_range_breakout: bool
    momentum_score: float
    composite_score: float
    prev_session_volume: int = 0
    adv30: float = 0.0
    prev_spread_pct: float = 0.0
    session_relative_volume: float = 0.0


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def parse_snapshot_item(
    item: dict,
    metadata: dict | None = None,
) -> TickerMetrics | None:
    sym = (item.get("ticker") or "").upper()
    if not sym or len(sym) > 5:
        return None
    # Skip warrants/units/rights
    if sym.endswith(("W", "U", "R", "P")) and len(sym) > 4:
        return None

    day = item.get("day") or {}
    prev = item.get("prevDay") or {}
    min_bar = item.get("min") or {}
    last_trade = item.get("lastTrade") or {}
    pre = item.get("preMarket") or {}
    after = item.get("afterHours") or {}
    meta = metadata or {}

    price = _safe_float(last_trade.get("p") or min_bar.get("c") or day.get("c") or prev.get("c"))
    if price <= 0:
        return None

    volume = int(day.get("v") or min_bar.get("v") or 0)
    prev_vol = int(prev.get("v") or 1) or 1
    prev_close = _safe_float(prev.get("c"), price)

    change_pct = _safe_float(item.get("todaysChangePerc"))
    if change_pct == 0 and prev_close:
        change_pct = (price - prev_close) / prev_close * 100

    rvol = volume / prev_vol if prev_vol else 1.0
    day_high = _safe_float(day.get("h"), price)
    day_low = _safe_float(day.get("l"), price)
    day_open = _safe_float(day.get("o"), price)
    spread_pct = ((day_high - day_low) / price * 100) if price else 99.0

    pre_vol = int(pre.get("v") or 0)
    pre_chg = 0.0
    if pre_vol > 0 and prev_close:
        pre_price = _safe_float(pre.get("c") or pre.get("h"), price)
        pre_chg = (pre_price - prev_close) / prev_close * 100

    after_vol = int(after.get("v") or 0)
    after_chg = 0.0
    if after_vol > 0:
        after_price = _safe_float(after.get("c"), price)
        after_chg = (after_price - price) / price * 100 if price else 0.0

    mcap = _safe_float(meta.get("market_cap"))
    float_shares = _safe_float(meta.get("float_shares"))
    name = str(meta.get("name") or sym)

    orb = False
    if day_open > 0:
        if change_pct > 0 and price > day_high * 0.998 and price > day_open * 1.005:
            orb = True
        elif change_pct < 0 and price < day_low * 1.002 and price < day_open * 0.995:
            orb = True

    vol_spike = rvol >= 2.0
    momentum = abs(change_pct) * math.log10(max(volume, 1))

    prev_high = _safe_float(prev.get("h"), price)
    prev_low = _safe_float(prev.get("l"), price)
    prev_spread_pct = ((prev_high - prev_low) / price * 100) if price and prev_high > prev_low else spread_pct

    adv30 = get_cached_adv30(sym)
    prev_session_volume = prev_vol
    session_rvol = (prev_session_volume / adv30) if adv30 > 0 else rvol

    composite = (
        min(rvol, 5) * 12
        + min(abs(change_pct), 15) * 3
        + math.log10(max(volume, 1)) * 4
        + (10 if vol_spike else 0)
        + (8 if orb else 0)
        + min(abs(pre_chg), 5) * 2
    )

    return TickerMetrics(
        symbol=sym,
        name=name,
        price=round(price, 2),
        change_percent=round(change_pct, 2),
        volume=volume,
        prev_volume=prev_vol,
        relative_volume=round(rvol, 2),
        volume_spike=vol_spike,
        spread_pct=round(spread_pct, 2),
        day_open=day_open,
        day_high=day_high,
        day_low=day_low,
        premarket_change_pct=round(pre_chg, 2),
        afterhours_change_pct=round(after_chg, 2),
        market_cap=mcap,
        float_shares=float_shares,
        opening_range_breakout=orb,
        momentum_score=round(momentum, 2),
        composite_score=round(composite, 2),
        prev_session_volume=prev_session_volume,
        adv30=adv30,
        prev_spread_pct=round(prev_spread_pct, 2),
        session_relative_volume=round(session_rvol, 2),
    )


def _passes_price_and_cap(m: TickerMetrics) -> bool:
    if m.price < SCANNER_MIN_PRICE or m.price > SCANNER_MAX_PRICE:
        return False
    if m.market_cap > 0 and m.market_cap < SCANNER_MIN_MARKET_CAP:
        return False
    return True


def passes_liquidity_filter(
    m: TickerMetrics,
    session: MarketSession | None = None,
) -> bool:
    """Session-aware coarse liquidity gate (strategy logic unchanged downstream)."""
    if not _passes_price_and_cap(m):
        return False

    if is_regular_session(session):
        if m.volume < SCANNER_MIN_DAY_VOLUME:
            return False
        if m.relative_volume < SCANNER_MIN_RVOL:
            return False
        if m.spread_pct > SCANNER_MAX_SPREAD_PCT and m.volume < SCANNER_MIN_DAY_VOLUME * 3:
            return False
        return True

    # Pre-market / after-hours / closed — use completed session data, not live day volume.
    prev_vol = m.prev_session_volume or m.prev_volume
    if prev_vol < SCANNER_MIN_DAY_VOLUME:
        return False

    adv = m.adv30 if m.adv30 > 0 else get_cached_adv30(m.symbol)
    if adv <= 0 or adv < SCANNER_MIN_AVG_VOLUME:
        return False

    session_rvol = prev_vol / adv if adv else 0.0
    if session_rvol < SCANNER_MIN_RVOL:
        return False

    spread = m.prev_spread_pct if m.prev_spread_pct > 0 else m.spread_pct
    if spread > SCANNER_MAX_SPREAD_PCT and prev_vol < SCANNER_MIN_DAY_VOLUME * 3:
        return False
    return True


def metrics_to_scan_row(m: TickerMetrics, reason: str = "") -> dict:
    return {
        "symbol": m.symbol,
        "name": m.name,
        "price": m.price,
        "change_percent": m.change_percent,
        "volume": m.volume,
        "relative_volume": m.relative_volume,
        "volume_spike": m.volume_spike,
        "market_cap": m.market_cap,
        "float_shares": m.float_shares,
        "spread_pct": m.spread_pct,
        "premarket_change_pct": m.premarket_change_pct,
        "afterhours_change_pct": m.afterhours_change_pct,
        "ai_score": 0.0,
        "scanner_reason": reason,
    }
