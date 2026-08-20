"""Buy-pressure and liquidity metrics — estimated, not true net order flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from market_pulse.state import SymbolPulseState


@dataclass
class PulseMetrics:
    rvol: float = 0.0
    dollar_volume_acceleration: float = 0.0
    trade_count: int = 0
    trades_per_minute: float = 0.0
    aggressive_buy_ratio: float = 0.5
    spread_bps: float = 999.0
    price: float = 0.0
    vwap: float = 0.0
    price_vs_vwap_pct: float = 0.0
    breakout: bool = False
    estimated_buy_pressure: float = 0.0
    data_age_seconds: float = 9999.0
    news_age_seconds: float = 9999.0
    is_halted: bool = False
    halt_reason: str = ""


def _mid(bid: float, ask: float) -> float:
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return max(bid, ask, 0.0)


def compute_metrics(state: SymbolPulseState, now: datetime | None = None) -> PulseMetrics:
    now = now or datetime.now(timezone.utc)
    m = PulseMetrics()
    m.price = state.last_price
    m.is_halted = bool(state.luld and state.luld.halt)
    m.halt_reason = state.luld.reason if state.luld else ""

    if state.linked_news:
        pub = state.linked_news.item.published_at
        if pub:
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            m.news_age_seconds = max(0.0, (now - pub).total_seconds())
        else:
            m.news_age_seconds = state.linked_news.news_age_seconds

    ts_ms = state.latest_timestamp_ms()
    if ts_ms:
        data_ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        m.data_age_seconds = max(0.0, (now - data_ts).total_seconds())

    # VWAP from minute bars or trades
    if state.minute_bars:
        total_pv = sum(b.vwap * b.volume for b in state.minute_bars if b.volume > 0)
        total_v = sum(b.volume for b in state.minute_bars)
        m.vwap = total_pv / total_v if total_v > 0 else state.minute_bars[-1].close
    elif state.trades:
        total_pv = sum(t.price * t.size for t in state.trades)
        total_v = sum(t.size for t in state.trades)
        m.vwap = total_pv / total_v if total_v > 0 else state.trades[-1].price

    if m.vwap > 0 and m.price > 0:
        m.price_vs_vwap_pct = (m.price - m.vwap) / m.vwap * 100.0

    # Spread
    if state.last_quote:
        mid = _mid(state.last_quote.bid, state.last_quote.ask)
        if mid > 0:
            m.spread_bps = (state.last_quote.ask - state.last_quote.bid) / mid * 10000.0

    # RVOL — recent minute vs baseline
    recent_vol = 0
    if state.minute_bars:
        recent_vol = state.minute_bars[-1].volume
    elif state.trades:
        cutoff = int(now.timestamp() * 1000) - 60_000
        recent_vol = sum(t.size for t in state.trades if t.timestamp_ms >= cutoff)
    baseline = max(state.baseline_minute_volume, 1.0)
    m.rvol = recent_vol / baseline

    # Dollar volume acceleration — last minute vs prior minute
    if len(state.minute_bars) >= 2:
        last = state.minute_bars[-1]
        prev = state.minute_bars[-2]
        last_dv = last.close * last.volume
        prev_dv = max(prev.close * prev.volume, 1.0)
        m.dollar_volume_acceleration = (last_dv - prev_dv) / prev_dv
    elif state.trades:
        now_ms = int(now.timestamp() * 1000)
        last_min = [t for t in state.trades if t.timestamp_ms >= now_ms - 60_000]
        prev_min = [t for t in state.trades if now_ms - 120_000 <= t.timestamp_ms < now_ms - 60_000]
        last_dv = sum(t.price * t.size for t in last_min) or 0.0
        prev_dv = sum(t.price * t.size for t in prev_min) or 1.0
        m.dollar_volume_acceleration = (last_dv - prev_dv) / max(prev_dv, 1.0)

    # Trades
    m.trade_count = len(state.trades)
    if state.trades:
        span_ms = max(state.trades[-1].timestamp_ms - state.trades[0].timestamp_ms, 1)
        m.trades_per_minute = m.trade_count / (span_ms / 60_000.0)

    # Aggressive buy ratio — trades at/above mid vs below
    if state.trades and state.last_quote:
        mid = _mid(state.last_quote.bid, state.last_quote.ask)
        if mid > 0:
            buys = sum(1 for t in state.trades if t.price >= mid)
            m.aggressive_buy_ratio = buys / len(state.trades)
    elif state.trades:
        # Without quote, use uptick heuristic
        ups = 0
        for i, t in enumerate(state.trades):
            if i == 0:
                continue
            if t.price >= state.trades[i - 1].price:
                ups += 1
        m.aggressive_buy_ratio = ups / max(len(state.trades) - 1, 1)

    # Breakout
    if state.day_high > 0 and m.price > 0:
        prior_high = state.day_high
        if state.minute_bars and len(state.minute_bars) >= 2:
            prior_high = max(b.high for b in state.minute_bars[:-1])
        m.breakout = m.price >= prior_high * 0.999

    # Estimated buy pressure (0-100) — not true net liquidity
    rvol_score = min(1.0, m.rvol / 3.0)
    accel_score = min(1.0, max(0.0, m.dollar_volume_acceleration + 0.5))
    speed_score = min(1.0, m.trades_per_minute / 30.0)
    m.estimated_buy_pressure = round(
        (rvol_score * 0.35 + accel_score * 0.35 + m.aggressive_buy_ratio * 0.2 + speed_score * 0.1)
        * 100.0,
        2,
    )
    return m
