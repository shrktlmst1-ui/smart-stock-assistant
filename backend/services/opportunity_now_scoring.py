"""Legacy scoring helpers for فرصة الآن — used by unit tests."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from config import SCANNER_MAX_PRICE, SCANNER_MIN_PRICE
from models.opportunity_now import OpportunityNowSignal
from models.stock import StockSnapshot
from services.price_universe import passes_universe_price

logger = logging.getLogger(__name__)

MAX_SPREAD_PCT = 0.5
MIN_RVOL = 1.2
MIN_DAY_VOLUME = 250_000
DATA_MAX_AGE_SECONDS = 120
VWAP_EXTENSION_PCT = 4.0
SIGNAL_TTL_SECONDS = 900

_signal_created: dict[str, str] = {}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _data_age_seconds(snap: StockSnapshot) -> float:
    updated = _parse_ts(snap.last_updated)
    if not updated:
        return 9999.0
    return max(0.0, (datetime.now(timezone.utc) - updated).total_seconds())


def _spread_pct(snap: StockSnapshot) -> float:
    price = snap.price or 1.0
    high = snap.indicators.resistance if snap.indicators else price
    low = snap.indicators.support if snap.indicators else price
    if high > low > 0:
        return (high - low) / price * 100.0
    return 0.25


def _rvol(snap: StockSnapshot) -> float:
    if snap.volume_engine:
        return snap.volume_engine.relative_volume or snap.volume_engine.session_rvol or 0.0
    if snap.volume_liquidity:
        return snap.volume_liquidity.relative_volume or 0.0
    return 0.0


def _vwap(snap: StockSnapshot) -> float:
    if snap.trend_analysis and snap.trend_analysis.vwap:
        return snap.trend_analysis.vwap
    if snap.volume_liquidity and snap.volume_liquidity.vwap:
        return snap.volume_liquidity.vwap
    return snap.price


def _has_news(snap: StockSnapshot) -> bool:
    return bool(snap.news) or (
        snap.news_intelligence.overall_sentiment in ("bullish", "bearish")
        and snap.news_intelligence.confidence_adjustment != 0
    )


def _news_headline(snap: StockSnapshot) -> str:
    if snap.news:
        return snap.news[0].title
    return snap.news_intelligence.summary or ""


def _safety_failed(
    snap: StockSnapshot,
    *,
    data_age: float,
    spread: float,
    rvol: float,
    vwap: float,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    failed = False
    if data_age > DATA_MAX_AGE_SECONDS:
        reasons.append("البيانات قديمة")
        failed = True
    if spread > MAX_SPREAD_PCT:
        reasons.append("السبريد مرتفع")
        failed = True
    if rvol < MIN_RVOL or (snap.volume or 0) < MIN_DAY_VOLUME:
        reasons.append("السيولة ضعيفة")
        failed = True
    if vwap > 0 and snap.price > vwap * (1 + VWAP_EXTENSION_PCT / 100):
        reasons.append("السعر ممتد عن VWAP")
        failed = True
    return failed, reasons


def _score_components(snap: StockSnapshot, *, spread: float, rvol: float, vwap: float) -> dict[str, float]:
    vol_accel = min(1.0, rvol / 3.0)
    liquidity = min(25.0, vol_accel * 15 + min(10.0, (snap.volume or 0) / MIN_DAY_VOLUME * 5))
    change = abs(snap.change_percent or 0.0)
    momentum = min(20.0, change * 4 + min(8.0, rvol * 2))
    vwap_pct = ((snap.price - vwap) / vwap * 100) if vwap > 0 else 0.0
    trend = 0.0
    if vwap_pct >= 0:
        trend += min(10.0, vwap_pct * 3)
    if snap.trend_analysis and snap.trend_analysis.direction == "bullish":
        trend += 5.0
    trend = min(15.0, trend)
    spread_score = max(0.0, 15.0 - spread * 20)
    smc = snap.smc
    smc_score = 0.0
    if smc:
        if smc.bos:
            smc_score += 6.0
        if smc.liquidity_sweep:
            smc_score += 4.0
        if smc.fair_value_gaps:
            smc_score += 3.0
        if smc.order_blocks:
            smc_score += 2.0
    smc_score = min(15.0, smc_score)
    news_score = 0.0
    if _has_news(snap):
        news_score = 10.0
        if snap.news_intelligence.overall_sentiment == "bullish":
            news_score = min(10.0, news_score + 2.0)
    elif rvol >= 2.0 and momentum >= 12.0:
        news_score = 4.0
    return {
        "liquidity": round(liquidity, 2),
        "momentum": round(momentum, 2),
        "trend": round(trend, 2),
        "spread": round(spread_score, 2),
        "smc": round(smc_score, 2),
        "news": round(news_score, 2),
    }


def _status_from_score(score: float, *, safety_failed: bool, market_open: bool) -> str:
    if safety_failed or score < 60:
        return "تجنب"
    if score >= 80 and market_open:
        return "فرصة الآن"
    if score >= 70:
        return "استعد"
    return "مراقبة"


def _risk_level(score: float, spread: float) -> str:
    if score >= 80 and spread <= 0.3:
        return "منخفض"
    if score >= 70:
        return "متوسط"
    return "مرتفع"


def _build_reasons(components: dict[str, float], snap: StockSnapshot, *, movement_no_news: bool) -> list[str]:
    reasons: list[str] = []
    if components["liquidity"] >= 15:
        reasons.append("حجم متسارع")
    if components["trend"] >= 8:
        reasons.append("فوق VWAP")
    if components["smc"] >= 8:
        reasons.append("اختراق مؤكد")
    if components["spread"] >= 10:
        reasons.append("سبريد مناسب")
    if components["news"] >= 8:
        headline = _news_headline(snap)
        if headline:
            reasons.append(f"محفز: {headline[:60]}")
        else:
            reasons.append("محفز إخباري")
    elif movement_no_news:
        reasons.append("حركة بلا خبر — زخم وسيولة")
    if not reasons:
        reasons.append("إشارة ضعيفة")
    return reasons


def _snapshot_to_signal(snap: StockSnapshot, *, market_open: bool) -> OpportunityNowSignal | None:
    if not passes_universe_price(snap.price):
        return None

    spread = _spread_pct(snap)
    rvol = _rvol(snap)
    vwap = _vwap(snap)
    data_age = _data_age_seconds(snap)
    safety_failed, safety_reasons = _safety_failed(
        snap, data_age=data_age, spread=spread, rvol=rvol, vwap=vwap,
    )

    components = _score_components(snap, spread=spread, rvol=rvol, vwap=vwap)
    score = min(100.0, sum(components.values()))
    if safety_failed:
        score = min(score, 59.0)

    has_news = _has_news(snap)
    movement_no_news = not has_news and components["liquidity"] >= 15 and components["momentum"] >= 12
    status_ar = _status_from_score(score, safety_failed=safety_failed, market_open=market_open)
    if not market_open and status_ar == "فرصة الآن":
        status_ar = "مراقبة"

    status_code = "NOW" if status_ar == "فرصة الآن" else "READY" if status_ar == "استعد" else "WATCH" if status_ar == "مراقبة" else "CANCELLED"

    sym = snap.symbol.upper()
    now = datetime.now(timezone.utc)
    if sym not in _signal_created:
        _signal_created[sym] = snap.last_updated or now.isoformat()

    appeared = _parse_ts(_signal_created[sym]) or now
    age = (now - appeared).total_seconds()
    if age > SIGNAL_TTL_SECONDS:
        _signal_created[sym] = now.isoformat()
        appeared = now

    expires = appeared + timedelta(seconds=SIGNAL_TTL_SECONDS)
    if (now - appeared).total_seconds() > SIGNAL_TTL_SECONDS:
        return None

    vwap_pct = ((snap.price - vwap) / vwap * 100) if vwap > 0 else 0.0
    late_entry = vwap_pct > VWAP_EXTENSION_PCT
    reasons = _build_reasons(components, snap, movement_no_news=movement_no_news)
    reasons = safety_reasons + reasons
    entry = round(snap.price * 1.001, 4)
    stop = round(snap.price * 0.97, 4)
    t1 = round(snap.price * 1.03, 4)
    t2 = round(snap.price * 1.06, 4)

    return OpportunityNowSignal(
        symbol=sym,
        name=snap.name or sym,
        price=round(snap.price, 4),
        change_percent=round(snap.change_percent or 0.0, 2),
        score=round(score, 1),
        status=status_code,  # type: ignore[arg-type]
        status_ar=status_ar,
        appeared_at=appeared.isoformat(),
        expires_at=expires.isoformat(),
        entry_zone=entry,
        stop_loss=stop,
        target_1=t1,
        target_2=t2,
        risk_level=_risk_level(score, spread),  # type: ignore[arg-type]
        reasons_ar=reasons[:6],
        late_entry_warning=late_entry,
        has_news_catalyst=has_news,
        movement_without_news=movement_no_news,
        data_timestamp=snap.last_updated or now.isoformat(),
    )


def reset_signal_cache() -> None:
    _signal_created.clear()
