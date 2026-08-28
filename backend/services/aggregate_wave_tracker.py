"""Wave tracker from second aggregates (A.*) — move from move_start only, not daily change."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

WavePhase = Literal["IDLE", "BUILDING", "ACTIVE", "ENDED"]

MIN_BUILDING_MOVE_PCT = 8.0
ACTIVE_MOVE_PCT = 15.0
DISTINGUISHED_MOVE_PCT = 50.0
COLLAPSE_RETRACE_PCT = 35.0
IDLE_RESET_RETRACE_PCT = 45.0


class WaveState(str, Enum):
    IDLE = "IDLE"
    BUILDING = "BUILDING"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


@dataclass
class AggregateBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class WaveRecord:
    symbol: str
    phase: WaveState = WaveState.IDLE
    move_start_time: datetime | None = None
    move_start_price: float = 0.0
    current_price: float = 0.0
    wave_peak_price: float = 0.0
    current_move_pct: float = 0.0
    retracement_from_peak_pct: float = 0.0
    first_detected_time: datetime | None = None
    first_detected_price: float = 0.0
    bars: deque[AggregateBar] = field(default_factory=lambda: deque(maxlen=360))
    last_bar_ts: datetime | None = None
    ended_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        return self.phase in (WaveState.BUILDING, WaveState.ACTIVE)

    def price_acceleration_1m(self) -> float:
        return self._accel_window(60)

    def price_acceleration_3m(self) -> float:
        return self._accel_window(180)

    def price_acceleration_5m(self) -> float:
        return self._accel_window(300)

    def volume_acceleration(self) -> float:
        if len(self.bars) < 10:
            return 0.0
        recent = list(self.bars)[-5:]
        prior = list(self.bars)[-10:-5]
        rv = sum(b.volume for b in recent) / max(len(recent), 1)
        pv = sum(b.volume for b in prior) / max(len(prior), 1)
        if pv <= 0:
            return 0.0
        return (rv - pv) / pv

    def _accel_window(self, seconds: int) -> float:
        if len(self.bars) < 2 or self.move_start_price <= 0:
            return 0.0
        cutoff = datetime.now(timezone.utc).timestamp() - seconds
        window = [b for b in self.bars if b.ts.timestamp() >= cutoff]
        if len(window) < 2:
            return 0.0
        start_p = window[0].close
        end_p = window[-1].close
        if start_p <= 0:
            return 0.0
        return (end_p - start_p) / start_p * 100.0


def _move_pct(start: float, current: float) -> float:
    if start <= 0:
        return 0.0
    return (current - start) / start * 100.0


def _retrace_pct(peak: float, current: float) -> float:
    if peak <= 0 or current >= peak:
        return 0.0
    return (peak - current) / peak * 100.0


class AggregateWaveTracker:
    """Second-by-second wave model from A.* aggregates."""

    def __init__(self) -> None:
        self._waves: dict[str, WaveRecord] = {}

    def reset(self) -> None:
        self._waves.clear()

    def get(self, symbol: str) -> WaveRecord | None:
        return self._waves.get(symbol.upper())

    def ingest_aggregate(
        self,
        symbol: str,
        *,
        close: float,
        open_: float = 0.0,
        high: float = 0.0,
        low: float = 0.0,
        volume: int = 0,
        exchange_ts: datetime | None = None,
    ) -> WaveRecord:
        sym = symbol.upper()
        if close <= 0:
            rec = self._waves.get(sym)
            if rec:
                return rec
            return WaveRecord(symbol=sym)

        now = exchange_ts or datetime.now(timezone.utc)
        rec = self._waves.get(sym)
        if rec is None:
            rec = WaveRecord(symbol=sym)
            self._waves[sym] = rec

        bar = AggregateBar(
            ts=now,
            open=open_ or close,
            high=high or close,
            low=low or close,
            close=close,
            volume=volume,
        )
        rec.bars.append(bar)
        rec.last_bar_ts = now
        rec.current_price = close

        if rec.phase == WaveState.ENDED:
            if _retrace_pct(rec.wave_peak_price, close) <= IDLE_RESET_RETRACE_PCT:
                rec.phase = WaveState.IDLE
                rec.move_start_price = 0.0
                rec.move_start_time = None
                rec.ended_at = None
            else:
                rec.current_move_pct = _move_pct(rec.move_start_price, close)
                rec.retracement_from_peak_pct = _retrace_pct(rec.wave_peak_price, close)
                return rec

        if rec.phase == WaveState.IDLE:
            if len(rec.bars) >= 3:
                local_low = min(b.low for b in list(rec.bars)[-5:])
                if close > local_low * 1.001:
                    rec.phase = WaveState.BUILDING
                    rec.move_start_price = local_low
                    rec.move_start_time = now
                    rec.wave_peak_price = close
                    rec.first_detected_time = now
                    rec.first_detected_price = close

        if rec.phase in (WaveState.BUILDING, WaveState.ACTIVE):
            if rec.move_start_price <= 0:
                rec.move_start_price = close
                rec.move_start_time = now
            rec.current_move_pct = _move_pct(rec.move_start_price, close)
            rec.wave_peak_price = max(rec.wave_peak_price, close, high or close)
            rec.retracement_from_peak_pct = _retrace_pct(rec.wave_peak_price, close)

            rising = (
                rec.price_acceleration_1m() > 0
                or rec.price_acceleration_3m() > 0.05
                or (len(rec.bars) >= 2 and close >= rec.bars[-2].close)
            )
            collapsed = rec.retracement_from_peak_pct >= COLLAPSE_RETRACE_PCT and not rising

            if collapsed or (rec.current_move_pct < 0 and rec.phase == WaveState.ACTIVE):
                rec.phase = WaveState.ENDED
                rec.ended_at = now
            elif rec.current_move_pct >= ACTIVE_MOVE_PCT and rising:
                rec.phase = WaveState.ACTIVE
            elif rec.current_move_pct >= MIN_BUILDING_MOVE_PCT:
                rec.phase = WaveState.BUILDING
            elif rec.current_move_pct < MIN_BUILDING_MOVE_PCT / 2:
                rec.phase = WaveState.IDLE
                rec.move_start_price = 0.0
                rec.move_start_time = None

        return rec

    def iter_live_waves(self):
        for sym, rec in self._waves.items():
            if rec.is_live:
                yield sym, rec

    def eligible_distinguished_symbols(self) -> list[str]:
        return [s for s in self._waves if self.eligible_distinguished(s)]

    def eligible_distinguished(self, symbol: str) -> bool:
        rec = self._waves.get(symbol.upper())
        if not rec or not rec.is_live:
            return False
        return rec.current_move_pct >= DISTINGUISHED_MOVE_PCT and rec.retracement_from_peak_pct < COLLAPSE_RETRACE_PCT

    def symbols_building(self) -> list[str]:
        return [s for s, w in self._waves.items() if w.phase == WaveState.BUILDING]

    def symbols_active(self) -> list[str]:
        return [s for s, w in self._waves.items() if w.phase in (WaveState.BUILDING, WaveState.ACTIVE)]


aggregate_wave_tracker = AggregateWaveTracker()
