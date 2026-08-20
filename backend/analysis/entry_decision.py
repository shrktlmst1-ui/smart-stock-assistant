"""Entry decision engine — ادخل الآن / انتظر السعر / تجنب / انتهت الإشارة."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from config import (
    ENTRY_DATA_MAX_AGE_SECONDS,
    ENTRY_MAX_SPREAD_PCT,
    ENTRY_MIN_AI_SCORE,
    ENTRY_MIN_DAY_VOLUME,
    ENTRY_MIN_RRR,
    ENTRY_MIN_RVOL,
    ENTRY_SIGNAL_EXPIRY_CANDLES,
    ENTRY_TIMEFRAME_MINUTES,
)

EntryState = Literal[
    "ENTER_NOW",
    "WAIT_PRICE",
    "AVOID",
    "EXPIRED",
    "STALE_DATA",
]


@dataclass
class EntryDecisionConfig:
    min_ai_score: float = ENTRY_MIN_AI_SCORE
    min_rrr: float = ENTRY_MIN_RRR
    max_spread_pct: float = ENTRY_MAX_SPREAD_PCT
    min_rvol: float = ENTRY_MIN_RVOL
    min_day_volume: int = ENTRY_MIN_DAY_VOLUME
    signal_expiry_candles: int = ENTRY_SIGNAL_EXPIRY_CANDLES
    timeframe_minutes: int = ENTRY_TIMEFRAME_MINUTES
    data_max_age_seconds: int = ENTRY_DATA_MAX_AGE_SECONDS


@dataclass
class EntryDecisionResult:
    state: EntryState
    label_ar: str
    color: str
    entry_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    risk_reward_ratio: float = 0.0
    signal_created_at: str = ""
    signal_expires_at: str = ""
    data_fresh: bool = True
    data_age_seconds: float = 0.0


_STATE_LABELS: dict[EntryState, tuple[str, str]] = {
    "ENTER_NOW": ("ادخل الآن", "green"),
    "WAIT_PRICE": ("انتظر السعر", "yellow"),
    "AVOID": ("تجنب", "red"),
    "EXPIRED": ("انتهت الإشارة", "gray"),
    "STALE_DATA": ("البيانات متأخرة — للمراقبة فقط", "yellow"),
}


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_data_freshness(
    last_updated: str,
    *,
    max_age_seconds: int = ENTRY_DATA_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> tuple[bool, float]:
    """Return (is_fresh, age_seconds)."""
    now = now or datetime.now(timezone.utc)
    ts = _parse_ts(last_updated)
    if ts is None:
        return False, float(max_age_seconds + 1)
    age = (now - ts).total_seconds()
    return age <= max_age_seconds, max(0.0, age)


def compute_signal_expiry(
    signal_created_at: str,
    *,
    candles: int = ENTRY_SIGNAL_EXPIRY_CANDLES,
    timeframe_minutes: int = ENTRY_TIMEFRAME_MINUTES,
) -> str:
    created = _parse_ts(signal_created_at) or datetime.now(timezone.utc)
    expires = created + timedelta(minutes=candles * timeframe_minutes)
    return expires.isoformat()


def is_signal_expired(
    signal_created_at: str,
    *,
    candles: int = ENTRY_SIGNAL_EXPIRY_CANDLES,
    timeframe_minutes: int = ENTRY_TIMEFRAME_MINUTES,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(timezone.utc)
    expiry = _parse_ts(compute_signal_expiry(
        signal_created_at, candles=candles, timeframe_minutes=timeframe_minutes,
    ))
    if expiry is None:
        return False
    return now >= expiry


def is_stop_broken(
    price: float,
    stop_loss: float,
    direction: str,
) -> bool:
    if stop_loss <= 0 or price <= 0:
        return False
    if direction == "short":
        return price >= stop_loss
    return price <= stop_loss


def is_price_in_entry_zone(
    price: float,
    entry_low: float,
    entry_high: float,
) -> bool:
    if entry_low <= 0 or entry_high <= 0:
        return False
    lo, hi = min(entry_low, entry_high), max(entry_low, entry_high)
    return lo <= price <= hi


def _build_reasons(
    *,
    ai_score: float,
    in_zone: bool,
    rrr: float,
    rvol: float,
    spread_pct: float,
    volume: int,
    smc_flags: dict[str, bool],
    cfg: EntryDecisionConfig,
) -> list[str]:
    reasons: list[str] = []
    if ai_score >= cfg.min_ai_score:
        reasons.append(f"درجة AI عالية ({ai_score:.0f})")
    if in_zone:
        reasons.append("السعر داخل منطقة الدخول")
    if rrr >= cfg.min_rrr:
        reasons.append(f"نسبة المخاطرة/العائد {rrr:.1f} ≥ {cfg.min_rrr:.0f}")
    if rvol >= cfg.min_rvol:
        reasons.append(f"حجم نسبي قوي (RVOL {rvol:.1f}x)")
    if spread_pct <= cfg.max_spread_pct:
        reasons.append(f"سبريد منخفض ({spread_pct:.2f}%)")
    if volume >= cfg.min_day_volume:
        reasons.append(f"سيولة يومية كافية ({volume:,})")
    if smc_flags.get("bos"):
        reasons.append("كسر هيكل BOS")
    if smc_flags.get("order_block"):
        reasons.append("Order Block نشط")
    if smc_flags.get("fair_value_gap"):
        reasons.append("FVG غير مملوء")
    if smc_flags.get("liquidity_sweep"):
        reasons.append("Sweep سيولة")
    return reasons[:3]


def _build_warnings(
    *,
    trap_risk: float,
    news_risk: float,
    spread_pct: float,
    rvol: float,
    failed_factors: list[str],
    devils_advocate: str,
    cfg: EntryDecisionConfig,
) -> list[str]:
    warnings: list[str] = []
    if trap_risk >= 35:
        warnings.append(f"خطر فخ سيولة ({trap_risk:.0f}%)")
    if news_risk >= 40:
        warnings.append(f"مخاطر أخبار ({news_risk:.0f}%)")
    if spread_pct > cfg.max_spread_pct:
        warnings.append(f"سبريد مرتفع ({spread_pct:.2f}%)")
    if rvol < cfg.min_rvol:
        warnings.append(f"حجم نسبي ضعيف ({rvol:.1f}x)")
    if failed_factors:
        warnings.append(f"عوامل فاشلة: {', '.join(failed_factors[:3])}")
    if devils_advocate and devils_advocate != "لا مخاوف رئيسية — راقب إدارة المخاطر":
        warnings.append(devils_advocate[:120])
    return warnings


def evaluate_entry_decision(
    *,
    price: float,
    ai_score: float,
    rrr: float,
    rvol: float,
    spread_pct: float,
    volume: int,
    entry_low: float,
    entry_high: float,
    stop_loss: float,
    take_profit_1: float,
    take_profit_2: float,
    direction: str,
    trap_risk: float,
    news_risk: float,
    professional_signal: str,
    recommendation: str,
    failed_factors: list[str],
    devils_advocate: str,
    last_updated: str,
    signal_created_at: str | None = None,
    smc_flags: dict[str, bool] | None = None,
    cfg: EntryDecisionConfig | None = None,
    now: datetime | None = None,
) -> EntryDecisionResult:
    """Determine entry state using configurable multi-factor rules."""
    cfg = cfg or EntryDecisionConfig()
    now = now or datetime.now(timezone.utc)
    smc_flags = smc_flags or {}
    created = signal_created_at or last_updated or now.isoformat()
    expires_at = compute_signal_expiry(
        created,
        candles=cfg.signal_expiry_candles,
        timeframe_minutes=cfg.timeframe_minutes,
    )

    fresh, age = check_data_freshness(last_updated, max_age_seconds=cfg.data_max_age_seconds, now=now)
    in_zone = is_price_in_entry_zone(price, entry_low, entry_high)
    stop_hit = is_stop_broken(price, stop_loss, direction)
    expired = is_signal_expired(
        created,
        candles=cfg.signal_expiry_candles,
        timeframe_minutes=cfg.timeframe_minutes,
        now=now,
    )

    reasons = _build_reasons(
        ai_score=ai_score,
        in_zone=in_zone,
        rrr=rrr,
        rvol=rvol,
        spread_pct=spread_pct,
        volume=volume,
        smc_flags=smc_flags,
        cfg=cfg,
    )
    warnings = _build_warnings(
        trap_risk=trap_risk,
        news_risk=news_risk,
        spread_pct=spread_pct,
        rvol=rvol,
        failed_factors=failed_factors,
        devils_advocate=devils_advocate,
        cfg=cfg,
    )

    base = EntryDecisionResult(
        entry_reasons=reasons,
        warnings=warnings,
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_reward_ratio=rrr,
        signal_created_at=created,
        signal_expires_at=expires_at,
        data_fresh=fresh,
        data_age_seconds=age,
        state="WAIT_PRICE",
        label_ar=_STATE_LABELS["WAIT_PRICE"][0],
        color=_STATE_LABELS["WAIT_PRICE"][1],
    )

    if expired or stop_hit:
        base.state = "EXPIRED"
        base.label_ar = _STATE_LABELS["EXPIRED"][0]
        base.color = _STATE_LABELS["EXPIRED"][1]
        if stop_hit:
            base.warnings.insert(0, "تم كسر مستوى إلغاء الصفقة")
        if expired:
            base.warnings.insert(0, f"انتهت صلاحية الإشارة ({cfg.signal_expiry_candles} شمعات)")
        return base

    sig = (professional_signal or recommendation or "WAIT").upper()
    if sig == "AVOID" or trap_risk >= 50 or news_risk >= 60:
        base.state = "AVOID"
        base.label_ar = _STATE_LABELS["AVOID"][0]
        base.color = _STATE_LABELS["AVOID"][1]
        return base

    if not fresh:
        base.state = "STALE_DATA"
        base.label_ar = _STATE_LABELS["STALE_DATA"][0]
        base.color = _STATE_LABELS["STALE_DATA"][1]
        base.warnings.insert(0, f"البيانات متأخرة ({int(age)} ثانية)")
        return base

    liquidity_ok = volume >= cfg.min_day_volume and spread_pct <= cfg.max_spread_pct and rvol >= cfg.min_rvol
    enter_conditions = (
        ai_score >= cfg.min_ai_score
        and in_zone
        and rrr >= cfg.min_rrr
        and liquidity_ok
        and not stop_hit
    )

    if enter_conditions:
        base.state = "ENTER_NOW"
        base.label_ar = _STATE_LABELS["ENTER_NOW"][0]
        base.color = _STATE_LABELS["ENTER_NOW"][1]
        return base

    if ai_score >= cfg.min_ai_score * 0.8 and sig in ("BUY", "SELL", "POSSIBLE ENTRY", "ENTRY CONFIRMED"):
        base.state = "WAIT_PRICE"
        base.label_ar = _STATE_LABELS["WAIT_PRICE"][0]
        base.color = _STATE_LABELS["WAIT_PRICE"][1]
        if not in_zone:
            base.warnings.insert(0, "السعر خارج منطقة الدخول")
        if rrr < cfg.min_rrr:
            base.warnings.insert(0, f"RRR {rrr:.1f} أقل من {cfg.min_rrr:.0f}")
        return base

    base.state = "AVOID"
    base.label_ar = _STATE_LABELS["AVOID"][0]
    base.color = _STATE_LABELS["AVOID"][1]
    return base
