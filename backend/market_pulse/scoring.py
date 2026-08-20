"""Pulse score (0-100) and decision engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from config import (
    MARKET_PULSE_ALERT_TTL_SECONDS,
    MARKET_PULSE_DATA_MAX_AGE_SECONDS,
    MARKET_PULSE_ENTER_MIN_SCORE,
    MARKET_PULSE_MAX_SPREAD_BPS,
    MARKET_PULSE_WAIT_MIN_SCORE,
)
from market_pulse.catalyst_classifier import has_strong_risk
from market_pulse.metrics import PulseMetrics
from market_pulse.models import PulseDecision
from market_pulse.state import LinkedNews, SymbolPulseState


@dataclass
class ScoreBreakdown:
    catalyst_score: float = 0.0
    liquidity_score: float = 0.0
    price_confirmation_score: float = 0.0
    risk_penalty: float = 0.0
    total: float = 0.0
    decision: PulseDecision = "AVOID"
    reasons_ar: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reasons_ar is None:
            self.reasons_ar = []


def _freshness_multiplier(age_seconds: float, max_age: float) -> float:
    if age_seconds <= max_age * 0.25:
        return 1.0
    if age_seconds <= max_age * 0.5:
        return 0.85
    if age_seconds <= max_age:
        return 0.6
    return 0.0


def compute_catalyst_score(linked: LinkedNews | None, news_age: float) -> float:
    if not linked:
        return 0.0
    base = min(30.0, linked.catalyst_score)
    if linked.classification_sentiment == "positive":
        base = min(30.0, base * 1.1)
    elif linked.classification_sentiment == "negative":
        base = min(30.0, base * 0.5)
    freshness = _freshness_multiplier(news_age, MARKET_PULSE_ALERT_TTL_SECONDS)
    return min(30.0, base * freshness)


def compute_liquidity_score(metrics: PulseMetrics) -> float:
    rvol_part = min(12.0, metrics.rvol * 4.0)
    accel_part = min(10.0, max(0.0, metrics.dollar_volume_acceleration) * 5.0)
    pressure_part = min(8.0, metrics.estimated_buy_pressure * 0.08)
    return min(30.0, rvol_part + accel_part + pressure_part)


def compute_price_confirmation_score(metrics: PulseMetrics) -> float:
    score = 0.0
    if metrics.price_vs_vwap_pct >= 0.3:
        score += 10.0
    elif metrics.price_vs_vwap_pct >= 0:
        score += 5.0
    if metrics.breakout:
        score += 8.0
    if metrics.aggressive_buy_ratio >= 0.6:
        score += 7.0
    elif metrics.aggressive_buy_ratio >= 0.5:
        score += 3.0
    return min(25.0, score)


def compute_risk_penalty(linked: LinkedNews | None, metrics: PulseMetrics) -> float:
    penalty = 0.0
    flags = linked.risk_flags if linked else []
    if has_strong_risk(flags):
        penalty += 20.0
    elif flags:
        penalty += min(10.0, len(flags) * 3.0)
    if metrics.is_halted:
        penalty += 15.0
    if metrics.spread_bps > MARKET_PULSE_MAX_SPREAD_BPS:
        penalty += min(10.0, (metrics.spread_bps - MARKET_PULSE_MAX_SPREAD_BPS) / 10.0)
    return round(min(25.0, penalty), 2)


def decide_pulse(
    state: SymbolPulseState,
    metrics: PulseMetrics,
    *,
    enter_min: float = MARKET_PULSE_ENTER_MIN_SCORE,
    wait_min: float = MARKET_PULSE_WAIT_MIN_SCORE,
    max_spread_bps: float = MARKET_PULSE_MAX_SPREAD_BPS,
    data_max_age: int = MARKET_PULSE_DATA_MAX_AGE_SECONDS,
    alert_ttl: int = MARKET_PULSE_ALERT_TTL_SECONDS,
    now: datetime | None = None,
) -> ScoreBreakdown:
    now = now or datetime.now(timezone.utc)
    linked = state.linked_news
    reasons: list[str] = []

    # EXPIRED checks
    if state.alert_created_at:
        age_alert = (now - state.alert_created_at).total_seconds()
        if age_alert > alert_ttl:
            return ScoreBreakdown(
                decision="EXPIRED",
                reasons_ar=["انتهت مدة التنبيه"],
            )
    if metrics.data_age_seconds > data_max_age:
        return ScoreBreakdown(
            decision="EXPIRED",
            reasons_ar=["البيانات اللحظية قديمة"],
        )
    if metrics.news_age_seconds > alert_ttl:
        return ScoreBreakdown(
            decision="EXPIRED",
            reasons_ar=["الخبر لم يعد حديثًا"],
        )

    catalyst = compute_catalyst_score(linked, metrics.news_age_seconds)
    liquidity = compute_liquidity_score(metrics)
    price_conf = compute_price_confirmation_score(metrics)
    risk = compute_risk_penalty(linked, metrics)
    total = max(0.0, min(100.0, round(catalyst + liquidity + price_conf - risk, 2)))

    flags = linked.risk_flags if linked else []
    strong_risk = has_strong_risk(flags)

    if strong_risk:
        reasons.append("محفز سلبي قوي (تخفيف/عرض/إفلاس)")
        return ScoreBreakdown(
            catalyst_score=catalyst,
            liquidity_score=liquidity,
            price_confirmation_score=price_conf,
            risk_penalty=risk,
            total=total,
            decision="AVOID",
            reasons_ar=reasons,
        )

    if metrics.is_halted:
        reasons.append("السهم متوقف (Halt/LULD)")
        return ScoreBreakdown(
            catalyst_score=catalyst,
            liquidity_score=liquidity,
            price_confirmation_score=price_conf,
            risk_penalty=risk,
            total=total,
            decision="AVOID",
            reasons_ar=reasons,
        )

    if metrics.spread_bps > max_spread_bps:
        reasons.append("السبريد واسع — مخاطرة تنفيذ")
        return ScoreBreakdown(
            catalyst_score=catalyst,
            liquidity_score=liquidity,
            price_confirmation_score=price_conf,
            risk_penalty=risk,
            total=total,
            decision="AVOID",
            reasons_ar=reasons,
        )

    if total < wait_min:
        reasons.append("النتيجة الإجمالية ضعيفة")
        return ScoreBreakdown(
            catalyst_score=catalyst,
            liquidity_score=liquidity,
            price_confirmation_score=price_conf,
            risk_penalty=risk,
            total=total,
            decision="AVOID",
            reasons_ar=reasons,
        )

    price_confirmed = price_conf >= 12.0 and metrics.price_vs_vwap_pct >= 0
    data_fresh = metrics.data_age_seconds <= data_max_age * 0.5

    if total >= enter_min and price_confirmed and data_fresh and not strong_risk:
        reasons.append("محفز قوي مع تأكيد سعر وسيولة")
        if metrics.breakout:
            reasons.append("كسر قمة مع حجم")
        return ScoreBreakdown(
            catalyst_score=catalyst,
            liquidity_score=liquidity,
            price_confirmation_score=price_conf,
            risk_penalty=risk,
            total=total,
            decision="ENTER_NOW",
            reasons_ar=reasons,
        )

    if total >= wait_min:
        if not price_confirmed:
            reasons.append("ينقص تأكيد السعر — انتظر")
        else:
            reasons.append("إشارة جيدة لكنها تحتاج متابعة")
        return ScoreBreakdown(
            catalyst_score=catalyst,
            liquidity_score=liquidity,
            price_confirmation_score=price_conf,
            risk_penalty=risk,
            total=total,
            decision="WAIT",
            reasons_ar=reasons,
        )

    reasons.append("النتيجة الإجمالية ضعيفة")
    return ScoreBreakdown(
        catalyst_score=catalyst,
        liquidity_score=liquidity,
        price_confirmation_score=price_conf,
        risk_penalty=risk,
        total=total,
        decision="AVOID",
        reasons_ar=reasons,
    )


def compute_trade_levels(price: float, direction: str = "long") -> tuple[float, float, list[float]]:
    if price <= 0:
        return 0.0, 0.0, []
    if direction == "long":
        entry = round(price * 1.002, 4)
        stop = round(price * 0.97, 4)
        targets = [round(price * 1.03, 4), round(price * 1.06, 4)]
    else:
        entry = round(price * 0.998, 4)
        stop = round(price * 1.03, 4)
        targets = [round(price * 0.97, 4), round(price * 0.94, 4)]
    return entry, stop, targets


def alert_expires_at(created: datetime, ttl: int = MARKET_PULSE_ALERT_TTL_SECONDS) -> str:
    return (created + timedelta(seconds=ttl)).replace(tzinfo=timezone.utc).isoformat()
