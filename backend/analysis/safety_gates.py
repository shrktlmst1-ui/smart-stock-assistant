"""Mandatory safety gates — separate from weighted factor scoring."""

from __future__ import annotations

from config import (
    SCANNER_MAX_PRICE,
    SCANNER_MAX_SPREAD_PCT,
    SCANNER_MIN_DAY_VOLUME,
    SCANNER_MIN_RVOL,
)
from analysis.professional_decision import (
    MIN_FACTOR_SCORE,
    REQUIRED_INSTITUTIONAL_FACTORS,
)
from models.stock import StockSnapshot
from services.scanner_filters import TickerMetrics, passes_liquidity_filter

TOTAL_INSTITUTIONAL_FACTORS = len(REQUIRED_INSTITUTIONAL_FACTORS)


def passes_automatic_price(price: float) -> bool:
    """Automatic lists: price > 0 and <= $10."""
    return price > 0 and price <= SCANNER_MAX_PRICE


def count_confirmed_factors(factor_scores: dict[str, float] | None) -> int:
    if not factor_scores:
        return 0
    return sum(
        1 for k in REQUIRED_INSTITUTIONAL_FACTORS if factor_scores.get(k, 0) >= MIN_FACTOR_SCORE
    )


def safety_passed_metrics(m: TickerMetrics, *, session) -> tuple[bool, list[str]]:
    """Phase-1/2 safety on coarse metrics."""
    reasons: list[str] = []
    if not passes_automatic_price(m.price):
        reasons.append("السعر خارج نطاق 0–10$")
        return False, reasons
    if not passes_liquidity_filter(m, session):
        reasons.append("السيولة أو الحجم غير كافٍ")
        return False, reasons
    if m.spread_pct > SCANNER_MAX_SPREAD_PCT * 1.5:
        reasons.append("السبريد مرتفع")
        return False, reasons
    return True, reasons


def safety_passed_snapshot(snap: StockSnapshot) -> tuple[bool, list[str]]:
    """Phase-3 safety on deep snapshot."""
    reasons: list[str] = []
    td = snap.trade_decision
    price = snap.price or td.current_price

    if not passes_automatic_price(price):
        reasons.append("السعر خارج نطاق 0–10$")
        return False, reasons

    vol = snap.volume or 0
    rvol = 1.0
    if snap.volume_engine:
        rvol = snap.volume_engine.relative_volume or snap.volume_engine.session_rvol or 1.0
    if vol > 0 and vol < SCANNER_MIN_DAY_VOLUME // 2 and rvol < SCANNER_MIN_RVOL:
        reasons.append("السيولة ضعيفة")
        return False, reasons

    spread_est = 0.0
    if snap.indicators and snap.indicators.resistance > snap.indicators.support > 0:
        spread_est = (snap.indicators.resistance - snap.indicators.support) / max(price, 0.01) * 100
    if spread_est > SCANNER_MAX_SPREAD_PCT * 2:
        reasons.append("السبريد مرتفع")
        return False, reasons

    if td.trap_risk >= 55 or snap.liquidity_traps.fake_breakout:
        reasons.append("مخاطرة فخ أو مطاردة")
        return False, reasons

    if td.news_risk >= 70:
        reasons.append("مخاطرة إخبارية")
        return False, reasons

    signal = (td.professional_signal or td.recommendation or "WAIT").upper()
    if signal == "AVOID" and td.trap_risk >= 45:
        reasons.append("إشارة تجنب")
        return False, reasons

    return True, reasons


def status_reason_ar(
    *,
    safety_ok: bool,
    safety_reasons: list[str],
    score: float,
    confirmed: int,
    total: int = TOTAL_INSTITUTIONAL_FACTORS,
) -> str:
    if not safety_ok:
        return "، ".join(safety_reasons[:3]) if safety_reasons else "فشل شروط الأمان"
    if score >= 80:
        return f"فرصة قوية — {confirmed}/{total} عوامل مؤكدة"
    if score >= 70:
        return f"استعد — {confirmed}/{total} عوامل مؤكدة"
    if score >= 60:
        return f"مراقبة — {confirmed}/{total} عوامل مؤكدة"
    return f"درجة منخفضة — {confirmed}/{total} عوامل مؤكدة"
