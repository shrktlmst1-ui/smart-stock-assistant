"""Live confirmation engine — 3-read confirmation, chase prevention, NOW/WATCH/READY states."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from analysis.professional_decision import REQUIRED_INSTITUTIONAL_FACTORS
from analysis.safety_gates import count_confirmed_factors, passes_automatic_price
from config import SCANNER_MAX_PRICE, SCANNER_MIN_PRICE
from models.stock import StockSnapshot
from services.price_universe import passes_universe_price

logger = logging.getLogger(__name__)

OpportunityStatusCode = Literal["NONE", "WATCH", "READY", "NOW", "CANCELLED"]

# Safe defaults — no required env vars.
LIVE_MONITOR_POOL = 100
MAX_SPREAD_PCT = 0.5
MIN_RVOL = 1.2
MIN_DAY_VOLUME = 250_000
DATA_MAX_AGE_SECONDS = 90
VWAP_EXTENSION_PCT = 3.0
NOW_TTL_SECONDS = 90
REQUIRED_CONFIRMATIONS = 3
READING_MIN_GAP_SECONDS = 8
MIN_SCORE_NOW = 80.0
MIN_SCORE_READY = 70.0
MIN_SCORE_WATCH = 60.0
MIN_CONFIRMED_FACTORS = 12
MIN_RRR = 2.0
MIN_MICRO_CONDITIONS = 3

STATUS_AR: dict[str, str] = {
    "NONE": "لا توجد فرصة مكتملة الآن",
    "WATCH": "مراقبة",
    "READY": "استعد",
    "NOW": "فرصة الآن",
    "CANCELLED": "أُلغيت",
}

MICRO_LABELS: dict[str, str] = {
    "trade_accel": "تسارع الصفقات",
    "volume_accel": "تسارع الحجم",
    "ask_buying": "شراء عند Ask",
    "vwap_reclaim": "استرجاع VWAP",
    "day_high_break": "اختراق قمة اليوم",
    "up_momentum": "زخم صاعد",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


@dataclass
class ConfirmationReading:
    timestamp: datetime
    price: float
    micro_count: int
    micro_hits: list[str] = field(default_factory=list)
    passed: bool = False


@dataclass
class CandidateState:
    symbol: str
    name: str = ""
    status: OpportunityStatusCode = "WATCH"
    readings: deque[ConfirmationReading] = field(default_factory=lambda: deque(maxlen=10))
    consecutive_confirmations: int = 0
    now_started_at: datetime | None = None
    expires_at: datetime | None = None
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    score: float = 0.0
    confirmed_factors: int = 0
    total_factors: int = len(REQUIRED_INSTITUTIONAL_FACTORS)
    risk_reward_ratio: float = 0.0
    nomination_reasons: list[str] = field(default_factory=list)
    cancellation_reasons: list[str] = field(default_factory=list)
    data_age_seconds: float = 0.0
    last_price: float = 0.0
    last_volume: int = 0
    baseline_spread: float = 0.25
    baseline_volume: int = 0
    day_high: float = 0.0
    vwap: float = 0.0
    spread_pct: float = 0.0
    change_percent: float = 0.0
    last_updated: str = ""
    prev_prices: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    prev_volumes: deque[int] = field(default_factory=lambda: deque(maxlen=5))
    breakout_active: bool = False
    ws_source: bool = False


class LiveConfirmationEngine:
    """Tracks top-N candidates with time-separated confirmation reads."""

    def __init__(self) -> None:
        self._candidates: dict[str, CandidateState] = {}
        self._monitor_symbols: list[str] = []
        self.ws_connected: bool = False
        self.ws_fallback: bool = False
        self.last_error: str = ""

    def reset(self) -> None:
        self._candidates.clear()
        self._monitor_symbols.clear()
        self.ws_connected = False
        self.ws_fallback = False
        self.last_error = ""

    def set_monitor_symbols(self, symbols: list[str]) -> None:
        self._monitor_symbols = [s.upper() for s in symbols[:LIVE_MONITOR_POOL]]
        for sym in self._monitor_symbols:
            if sym not in self._candidates:
                self._candidates[sym] = CandidateState(symbol=sym)

    def set_ws_status(self, *, connected: bool, fallback: bool = False, error: str = "") -> None:
        self.ws_connected = connected
        self.ws_fallback = fallback
        self.last_error = error

    @staticmethod
    def _spread_pct(snap: StockSnapshot) -> float:
        price = snap.price or 1.0
        high = snap.indicators.resistance if snap.indicators else price
        low = snap.indicators.support if snap.indicators else price
        if high > low > 0:
            return (high - low) / price * 100.0
        return 0.25

    @staticmethod
    def _vwap(snap: StockSnapshot) -> float:
        if snap.trend_analysis and snap.trend_analysis.vwap:
            return snap.trend_analysis.vwap
        if snap.volume_liquidity and snap.volume_liquidity.vwap:
            return snap.volume_liquidity.vwap
        return snap.price

    @staticmethod
    def _rvol(snap: StockSnapshot) -> float:
        if snap.volume_engine:
            return snap.volume_engine.relative_volume or snap.volume_engine.session_rvol or 0.0
        if snap.volume_liquidity:
            return snap.volume_liquidity.relative_volume or 0.0
        return 0.0

    @staticmethod
    def _data_age_seconds(snap: StockSnapshot) -> float:
        updated = _parse_ts(snap.last_updated)
        if not updated:
            return 9999.0
        return max(0.0, (_utcnow() - updated).total_seconds())

    @staticmethod
    def _compute_score(snap: StockSnapshot, *, spread: float, rvol: float, vwap: float) -> float:
        vol_accel = min(1.0, rvol / 3.0)
        liquidity = min(25.0, vol_accel * 15 + min(10.0, (snap.volume or 0) / MIN_DAY_VOLUME * 5))
        change = abs(snap.change_percent or 0.0)
        momentum = min(20.0, change * 4 + min(8.0, rvol * 2))
        vwap_pct = ((snap.price - vwap) / vwap * 100) if vwap > 0 else 0.0
        trend = min(15.0, max(0.0, vwap_pct * 3) + (5.0 if snap.trend_analysis and snap.trend_analysis.direction == "bullish" else 0))
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
        news_score = 4.0 if rvol >= 2.0 and momentum >= 12.0 else 0.0
        if snap.news:
            news_score = min(10.0, news_score + 6.0)
        return min(100.0, liquidity + momentum + trend + spread_score + smc_score + news_score)

    @staticmethod
    def _compute_rrr(price: float, stop: float, target: float) -> float:
        risk = abs(price - stop)
        reward = abs(target - price)
        if risk <= 0:
            return 0.0
        return round(reward / risk, 2)

    def _evaluate_micro(
        self,
        state: CandidateState,
        snap: StockSnapshot,
        *,
        price: float,
        ws_tick: bool = False,
    ) -> tuple[int, list[str]]:
        hits: list[str] = []
        vwap = state.vwap or self._vwap(snap)
        day_high = state.day_high or (snap.indicators.resistance if snap.indicators else price)

        if len(state.prev_prices) >= 2:
            accel = state.prev_prices[-1] - state.prev_prices[-2]
            if price > state.prev_prices[-1] and accel >= 0:
                hits.append("trade_accel")

        if len(state.prev_volumes) >= 2 and state.last_volume > state.prev_volumes[-1]:
            hits.append("volume_accel")

        if ws_tick and snap.change_percent and snap.change_percent > 0 and price >= vwap:
            hits.append("ask_buying")

        if vwap > 0 and price >= vwap * 1.001 and (not state.prev_prices or state.prev_prices[-1] < vwap):
            hits.append("vwap_reclaim")

        if day_high > 0 and price >= day_high * 0.998:
            hits.append("day_high_break")

        if snap.change_percent and snap.change_percent > 1.0 and snap.trend_analysis and snap.trend_analysis.direction == "bullish":
            hits.append("up_momentum")

        labels = [MICRO_LABELS.get(h, h) for h in hits]
        return len(hits), labels

    def _base_safety_failed(
        self,
        snap: StockSnapshot,
        *,
        data_age: float,
        spread: float,
        rvol: float,
        vwap: float,
        price: float,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not passes_universe_price(price):
            reasons.append(f"السعر خارج نطاق {SCANNER_MIN_PRICE}–{SCANNER_MAX_PRICE}$")
            return True, reasons
        if data_age > DATA_MAX_AGE_SECONDS:
            reasons.append("البيانات قديمة")
            return True, reasons
        if spread > MAX_SPREAD_PCT:
            reasons.append("السبريد مرتفع")
            return True, reasons
        if rvol < MIN_RVOL or (snap.volume or 0) < MIN_DAY_VOLUME:
            reasons.append("السيولة ضعيفة")
            return True, reasons
        if vwap > 0 and price > vwap * (1 + VWAP_EXTENSION_PCT / 100):
            reasons.append("السعر ممتد عن VWAP — مطاردة")
            return True, reasons
        return False, reasons

    def _count_confirmations(self, state: CandidateState) -> int:
        if not state.readings:
            return 0
        passed = [r for r in state.readings if r.passed]
        if not passed:
            return 0
        count = 1
        for i in range(len(passed) - 1, 0, -1):
            gap = (passed[i].timestamp - passed[i - 1].timestamp).total_seconds()
            if gap >= READING_MIN_GAP_SECONDS:
                count += 1
            else:
                break
        return count

    def _check_chase_cancel(self, state: CandidateState, price: float) -> list[str]:
        reasons: list[str] = []
        if state.vwap > 0 and price > state.vwap * (1 + VWAP_EXTENSION_PCT / 100):
            reasons.append("مطاردة — ابتعاد عن VWAP")
        if state.baseline_spread > 0 and state.spread_pct > max(MAX_SPREAD_PCT, state.baseline_spread * 2):
            reasons.append("اتساع مفاجئ في السبريد")
        if state.baseline_volume > 0 and state.last_volume < int(state.baseline_volume * 0.6):
            reasons.append("انخفاض الحجم")
        if state.breakout_active and state.day_high > 0 and price < state.day_high * 0.995:
            reasons.append("فشل الاختراق")
        if state.entry_zone_high > 0 and price > state.entry_zone_high * 1.008:
            reasons.append("تجاوز منطقة الدخول")
        if state.now_started_at:
            age = (_utcnow() - state.now_started_at).total_seconds()
            if age > NOW_TTL_SECONDS:
                reasons.append("انتهت صلاحية 90 ثانية")
        return reasons

    def ingest_snapshot(self, snap: StockSnapshot, *, ws_tick: bool = False) -> None:
        sym = snap.symbol.upper()
        if sym not in self._candidates and sym not in self._monitor_symbols:
            return
        if not passes_automatic_price(snap.price):
            return

        state = self._candidates.setdefault(sym, CandidateState(symbol=sym, name=snap.name or sym))
        price = snap.price
        spread = self._spread_pct(snap)
        rvol = self._rvol(snap)
        vwap = self._vwap(snap)
        data_age = self._data_age_seconds(snap)
        score = self._compute_score(snap, spread=spread, rvol=rvol, vwap=vwap)
        factors = count_confirmed_factors(snap.trade_decision.factor_scores if snap.trade_decision else None)

        state.name = snap.name or sym
        state.last_price = price
        state.last_volume = snap.volume or state.last_volume
        state.vwap = vwap
        state.spread_pct = spread
        state.change_percent = snap.change_percent or 0.0
        state.data_age_seconds = data_age
        state.last_updated = snap.last_updated or _utcnow().isoformat()
        state.score = round(score, 1)
        state.confirmed_factors = factors
        state.day_high = max(state.day_high, snap.indicators.resistance if snap.indicators else price)
        if state.baseline_spread <= 0:
            state.baseline_spread = spread
        if state.baseline_volume <= 0:
            state.baseline_volume = snap.volume or 0

        stop = round(price * 0.975, 4)
        t1 = round(price * 1.05, 4)
        t2 = round(price * 1.08, 4)
        state.stop_loss = stop
        state.target_1 = t1
        state.target_2 = t2
        state.entry_zone_low = round(price * 0.998, 4)
        state.entry_zone_high = round(price * 1.004, 4)
        state.risk_reward_ratio = self._compute_rrr(price, stop, t1)

        if ws_tick:
            state.ws_source = True
            state.prev_prices.append(price)
            state.prev_volumes.append(state.last_volume)

        safety_failed, safety_reasons = self._base_safety_failed(
            snap, data_age=data_age, spread=spread, rvol=rvol, vwap=vwap, price=price,
        )

        if state.status == "NOW":
            cancel = self._check_chase_cancel(state, price)
            if cancel:
                state.status = "CANCELLED"
                state.cancellation_reasons = cancel
                state.now_started_at = None
                state.expires_at = None
                return

        micro_count, micro_labels = self._evaluate_micro(state, snap, price=price, ws_tick=ws_tick)
        reading_ok = (
            not safety_failed
            and score >= MIN_SCORE_WATCH
            and micro_count >= MIN_MICRO_CONDITIONS
        )
        now = _utcnow()
        if reading_ok:
            last = state.readings[-1].timestamp if state.readings else None
            if last is None or (now - last).total_seconds() >= READING_MIN_GAP_SECONDS:
                state.readings.append(
                    ConfirmationReading(
                        timestamp=now,
                        price=price,
                        micro_count=micro_count,
                        micro_hits=micro_labels,
                        passed=True,
                    )
                )

        state.consecutive_confirmations = self._count_confirmations(state)
        state.nomination_reasons = micro_labels[:3]
        if safety_reasons:
            state.nomination_reasons = safety_reasons + state.nomination_reasons

        if safety_failed:
            state.status = "WATCH"
            return

        can_now = (
            state.consecutive_confirmations >= REQUIRED_CONFIRMATIONS
            and score >= MIN_SCORE_NOW
            and factors >= MIN_CONFIRMED_FACTORS
            and state.risk_reward_ratio >= MIN_RRR
            and micro_count >= MIN_MICRO_CONDITIONS
        )

        if can_now and state.status != "CANCELLED":
            if state.status != "NOW":
                state.now_started_at = now
                state.expires_at = now + timedelta(seconds=NOW_TTL_SECONDS)
            state.status = "NOW"
            if "day_high_break" in [k for k, v in MICRO_LABELS.items() if v in micro_labels]:
                state.breakout_active = True
        elif score >= MIN_SCORE_READY and state.consecutive_confirmations >= 1:
            if state.status not in ("NOW", "CANCELLED"):
                state.status = "READY"
        elif state.status not in ("NOW", "CANCELLED"):
            state.status = "WATCH"

    def ingest_ws_trade(self, symbol: str, price: float, size: int = 0) -> None:
        sym = symbol.upper()
        if sym not in self._monitor_symbols:
            return
        state = self._candidates.setdefault(sym, CandidateState(symbol=sym))
        state.last_price = price
        state.prev_prices.append(price)
        if size > 0:
            state.last_volume += size
            state.prev_volumes.append(state.last_volume)
        state.ws_source = True

    def best_candidate(self, *, market_open: bool) -> CandidateState | None:
        now_candidates = [c for c in self._candidates.values() if c.status == "NOW" and c.last_price > 0]
        if market_open and now_candidates:
            return max(now_candidates, key=lambda c: (c.score, c.consecutive_confirmations))
        ready = [c for c in self._candidates.values() if c.status == "READY"]
        if ready:
            return max(ready, key=lambda c: c.score)
        watch = [c for c in self._candidates.values() if c.status == "WATCH" and c.score >= MIN_SCORE_WATCH]
        if watch:
            return max(watch, key=lambda c: c.score)
        cancelled = [c for c in self._candidates.values() if c.status == "CANCELLED"]
        if cancelled:
            return max(cancelled, key=lambda c: c.last_updated or "")
        return None


live_confirmation_engine = LiveConfirmationEngine()
