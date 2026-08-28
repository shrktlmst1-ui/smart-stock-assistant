"""Unified signal snapshot — single source for UI fields and Reason Now."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from models.opportunity_now import OpportunityNowSignal

RejectReason = Literal[
    "STALE_DATA",
    "SCORE_STATUS_MISMATCH",
    "PRICE_BELOW_STOP",
    "TARGET_HIT_MOVEMENT_ENDED",
    "ENTRY_ON_OLD_PEAK",
    "REASON_FIELD_MISMATCH",
    "LIVE_DATA_UNAVAILABLE",
]


@dataclass
class SignalSnapshot:
    symbol: str
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    price: float = 0.0
    change_percent: float = 0.0
    rvol: float = 0.0
    volume_acceleration: float = 0.0
    buy_pressure_ratio_60s: float = 0.0
    buy_pressure_source: str = "INSUFFICIENT_DATA"
    score: float = 0.0
    status: str = "NONE"
    entry_zone: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    data_age_ms: float = 0.0
    wave_move_pct: float = 0.0
    wave_phase: str = "IDLE"
    move_start_price: float = 0.0
    spread_pct: float = 0.0
    trade_count_60s: int = 0
    live_feed_valid: bool = False
    rejection: RejectReason | None = None
    reason_now_ar: str = ""

    MAX_DATA_AGE_MS = 15_000.0

    def validate(self) -> RejectReason | None:
        if not self.live_feed_valid:
            return "LIVE_DATA_UNAVAILABLE"
        if self.data_age_ms > self.MAX_DATA_AGE_MS:
            return "STALE_DATA"
        if self.status in ("NOW", "READY") and self.score < 55:
            return "SCORE_STATUS_MISMATCH"
        if self.status == "WATCH" and self.score < 40:
            return "SCORE_STATUS_MISMATCH"
        if self.stop_loss > 0 and self.price < self.stop_loss:
            return "PRICE_BELOW_STOP"
        if self.target_1 > 0 and self.price >= self.target_1 and self.wave_phase == "ENDED":
            return "TARGET_HIT_MOVEMENT_ENDED"
        if self.entry_zone > 0 and self.move_start_price > 0:
            if self.entry_zone >= self.price * 0.98 and self.wave_phase == "ENDED":
                return "ENTRY_ON_OLD_PEAK"
        reason = self.build_reason_now_ar()
        if self.reason_now_ar and self.reason_now_ar != reason:
            return "REASON_FIELD_MISMATCH"
        return None

    def build_reason_now_ar(self) -> str:
        parts: list[str] = []
        if self.price > 0:
            parts.append(f"السعر {self.price:.2f}$")
        if self.wave_move_pct > 0:
            parts.append(f"موجة {self.wave_move_pct:.1f}%")
        if self.buy_pressure_source == "EXECUTED_TRADES" and self.buy_pressure_ratio_60s > 0:
            parts.append(f"ضغط شراء منفذ {self.buy_pressure_ratio_60s * 100:.0f}%")
        if self.rvol > 0:
            parts.append(f"RVOL {self.rvol:.1f}x")
        if self.volume_acceleration > 0:
            parts.append(f"تسارع حجم {self.volume_acceleration:.0%}")
        if self.spread_pct > 0:
            parts.append(f"سبريد {self.spread_pct:.2f}%")
        if self.score > 0:
            parts.append(f"Score {self.score:.0f}")
        return " · ".join(parts) if parts else "لا توجد بيانات حية كافية"

    def apply_validation(self) -> SignalSnapshot:
        self.reason_now_ar = self.build_reason_now_ar()
        self.rejection = self.validate()
        return self

    def to_opportunity_signal(self) -> OpportunityNowSignal | None:
        self.apply_validation()
        if self.rejection:
            return None
        return OpportunityNowSignal(
            symbol=self.symbol,
            name=self.symbol,
            price=self.price,
            change_percent=self.change_percent,
            score=self.score,
            status=self.status if self.status in ("NONE", "WATCH", "READY", "NOW", "CANCELLED") else "NONE",
            status_ar=self.reason_now_ar,
            entry_zone=self.entry_zone,
            stop_loss=self.stop_loss,
            target_1=self.target_1,
            target_2=self.target_2,
            data_age_seconds=self.data_age_ms / 1000.0,
            rvol=self.rvol,
            volume_acceleration=self.volume_acceleration,
            buy_pressure_score=self.buy_pressure_ratio_60s * 100.0,
            real_jump_move_start_price=self.move_start_price,
            real_jump_current_move_pct=self.wave_move_pct,
            real_jump_wave_state=self.wave_phase,
            reasons_ar=[self.reason_now_ar],
        )


def build_snapshot_from_wave_and_pressure(
    symbol: str,
    *,
    wave,
    pressure,
    baseline_rvol: float,
    live_feed_valid: bool,
    data_age_ms: float,
    bid: float = 0.0,
    ask: float = 0.0,
) -> SignalSnapshot:
    """Build snapshot from production wave + executed pressure — no hardcoded symbols."""
    w60 = pressure.pressure_windows((60.0,))[60.0] if pressure else None
    ratio = w60.ratio if w60 else 0.0
    spread_pct = ((ask - bid) / ((ask + bid) / 2) * 100.0) if bid > 0 and ask > 0 else 99.0
    vol_acc = wave.volume_acceleration() if wave else 0.0
    rising = wave.price_acceleration_1m() > 0 if wave else False
    rvol_valid = baseline_rvol > 0 and baseline_rvol >= 1.0

    status = "NONE"
    score = 0.0
    if live_feed_valid and wave and wave.is_live:
        score = min(100.0, 40.0 + wave.current_move_pct * 0.5 + ratio * 30.0)
        if wave.current_move_pct >= 50:
            status = "NOW"
        elif wave.current_move_pct >= 20:
            status = "WATCH"

    snap = SignalSnapshot(
        symbol=symbol.upper(),
        price=wave.current_price if wave else 0.0,
        change_percent=wave.current_move_pct if wave else 0.0,
        rvol=baseline_rvol,
        volume_acceleration=vol_acc,
        buy_pressure_ratio_60s=ratio,
        buy_pressure_source=pressure.source if pressure else "INSUFFICIENT_DATA",
        score=score,
        status=status,
        entry_zone=wave.move_start_price if wave else 0.0,
        stop_loss=(wave.move_start_price * 0.95) if wave and wave.move_start_price > 0 else 0.0,
        target_1=wave.wave_peak_price if wave else 0.0,
        target_2=(wave.wave_peak_price * 1.05) if wave and wave.wave_peak_price > 0 else 0.0,
        data_age_ms=data_age_ms,
        wave_move_pct=wave.current_move_pct if wave else 0.0,
        wave_phase=wave.phase.value if wave else "IDLE",
        move_start_price=wave.move_start_price if wave else 0.0,
        spread_pct=spread_pct,
        trade_count_60s=w60.trade_count if w60 else 0,
        live_feed_valid=live_feed_valid,
    )
    return snap.apply_validation()
