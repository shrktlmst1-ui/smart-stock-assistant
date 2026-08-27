"""Independent REAL_JUMP_ALERT layer — sits above existing display signals unchanged."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from analysis.early_upward_surge import (
    DISPLAY_REAL_JUMP_ALERT,
    RealJumpEarlyDetectionKPI,
    RealJumpWaveSnapshot,
    RealPriceJumpVerdict,
    derive_real_jump_wave,
    evaluate_real_jump_alert,
    fast_filter_surge_rank,
)
from config import PREMOVE_DATA_MAX_AGE_SECONDS, PREMOVE_MIN_LIQUIDITY_SCORE
from models.opportunity_now import OpportunityNowSignal
from models.pre_move import PreMoveSignal
from services.display_buy_pressure_filter import context_from_premove, context_from_opportunity_signal

MAX_PRICE_USD = 10.0
REAL_JUMP_SECTION_MIN_WAVE_PCT = 100.0
REAL_JUMP_EXPLOSIVE_WAVE_PCT = 150.0
WAVE_SAMPLE_MAX = 12

WAVE_END_NO_HH_MINUTES = 8
WAVE_END_LOW_VELOCITY_MINUTES = 4
WAVE_END_LOW_VOL_ACCEL_MINUTES = 4
WAVE_END_VELOCITY_FRACTION = 0.40
WAVE_END_VOL_ACCEL_MIN = 1.15
WAVE_END_RETRACE_FRACTION = 0.55
WAVE_END_RETRACE_MIN_MOVE_PCT = 40.0  # ignore retrace until wave extended meaningfully
WAVE_COOLING_TO_END_MINUTES = 8
WAVE_STRUCTURE_BREAK_PCT = 0.85  # deep break only — not a shallow pullback
WAVE_MIN_MINUTES_BEFORE_COOLING = 6
WAVE_POST_DETECT_MIN_MINUTES_BEFORE_COOLING = 12
WAVE_POST_DETECT_COOLING_TO_END_MINUTES = 15
WAVE_POST_DETECT_NO_HH_MINUTES = 15
WAVE_POST_DETECT_LOW_VELOCITY_MINUTES = 8
WAVE_ACTIVE_TO_COOLING_SIGNALS = 2
WAVE_COOLING_TO_END_SIGNALS = 3
WAVE_POST_DETECT_ACTIVE_TO_COOLING = 4
WAVE_POST_DETECT_COOLING_TO_END = 5

WAVE_STATE_ACTIVE = "ACTIVE"
WAVE_STATE_COOLING = "COOLING"
WAVE_STATE_ENDED = "ENDED"


def _wave_id(symbol: str, wave: RealJumpWaveSnapshot) -> str:
    ts = wave.move_start_time.isoformat() if wave.move_start_time else "na"
    return f"{symbol.upper()}:{wave.move_start_price:.4f}:{ts}"


@dataclass
class _LockedWave:
    """Immutable move_start for the lifetime of one upward wave."""

    wave_id: str = ""
    move_start_price: float = 0.0
    move_start_time: datetime | None = None
    wave_state: str = WAVE_STATE_ENDED
    wave_peak_price: float = 0.0
    first_detected_time: datetime | None = None
    first_detected_price: float = 0.0
    first_detected_pct: float = 0.0
    cooling_since: datetime | None = None
    reset_reason: str = ""
    peak_trade_velocity: float = 0.0
    last_higher_high_time: datetime | None = None
    no_hh_minutes: float = 0.0
    low_velocity_minutes: float = 0.0
    low_vol_accel_minutes: float = 0.0
    extended_mode: bool = False  # locked after wave_peak_move_pct crosses +100%


@dataclass
class _SymbolWaveHistory:
    prior_wave: RealJumpWaveSnapshot | None = None
    locked: _LockedWave = field(default_factory=_LockedWave)
    samples: deque[tuple[datetime, float]] = field(default_factory=lambda: deque(maxlen=WAVE_SAMPLE_MAX))
    bar_timestamps: deque[datetime] = field(default_factory=lambda: deque(maxlen=8))


@dataclass
class ActiveRealJumpAlert:
    symbol: str
    wave_id: str
    alert_id: str
    kpi: RealJumpEarlyDetectionKPI
    last_updated: datetime
    verdict: RealPriceJumpVerdict | None = None


@dataclass
class RealJumpProcessResult:
    emit: bool = False
    update_existing: bool = False
    clear: bool = False
    verdict: RealPriceJumpVerdict | None = None
    alert: ActiveRealJumpAlert | None = None


class RealJumpWaveTracker:
    """Per-symbol instant-wave state — survives across scan cycles."""

    def __init__(self) -> None:
        self._history: dict[str, _SymbolWaveHistory] = {}

    def reset(self) -> None:
        self._history.clear()

    def _get(self, symbol: str) -> _SymbolWaveHistory:
        sym = symbol.upper()
        if sym not in self._history:
            self._history[sym] = _SymbolWaveHistory()
        return self._history[sym]

    def _accel_from_samples(self, samples: deque[tuple[datetime, float]]) -> tuple[float, float, float]:
        if len(samples) < 2:
            return 0.0, 0.0, 0.0
        prices = [p for _, p in samples]
        acc_1m = 0.0
        if len(prices) >= 2 and prices[-2] > 0:
            acc_1m = (prices[-1] - prices[-2]) / prices[-2] * 100.0
        acc_3m = acc_1m
        if len(prices) >= 4 and prices[-4] > 0:
            acc_3m = (prices[-1] - prices[-4]) / prices[-4] * 100.0
        acc_5m = acc_3m
        if len(prices) >= 6 and prices[-6] > 0:
            acc_5m = (prices[-1] - prices[-6]) / prices[-6] * 100.0
        elif len(prices) >= 3 and prices[0] > 0:
            acc_5m = (prices[-1] - prices[0]) / prices[0] * 100.0
        return round(acc_1m, 3), round(acc_3m, 3), round(acc_5m, 3)

    def _minutes_since(self, ref: datetime | None, now: datetime) -> float:
        if ref is None:
            return 0.0
        return max(0.0, (now - ref).total_seconds() / 60.0)

    def _compute_accelerations(
        self,
        bars: pd.DataFrame | None,
        samples: deque[tuple[datetime, float]],
    ) -> tuple[float, float, float]:
        if bars is not None and len(bars) >= 2:
            from analysis.early_upward_surge import compute_price_acceleration
            return compute_price_acceleration(bars)
        return self._accel_from_samples(samples)

    def _detect_new_move_start(
        self,
        bars: pd.DataFrame | None,
        samples: deque[tuple[datetime, float]],
        current_price: float,
        ts: datetime,
    ) -> tuple[float, datetime | None]:
        """Find swing low for a brand-new wave — only called when prior wave ENDED."""
        if bars is not None and len(bars) >= 2:
            lows = bars["low"].astype(float)
            lookback = min(12, len(bars))
            move_start = float(lows.iloc[-lookback:].min())
            start_time = ts
            if "timestamp" in bars.columns and len(bars) >= lookback:
                idx = lows.iloc[-lookback:].idxmin()
                bar_ts = bars.loc[idx, "timestamp"]
                if isinstance(bar_ts, pd.Timestamp):
                    start_time = bar_ts.to_pydatetime()
            return move_start, start_time
        if samples:
            move_start = min(p for _, p in samples)
            start_time = samples[0][0]
            return move_start, start_time
        return current_price, ts

    def _end_signal_count(
        self,
        locked: _LockedWave,
        *,
        current_price: float,
        timestamp: datetime,
        trade_velocity: float,
        volume_acceleration_1m: float,
        made_higher_high: bool,
        acc_1m: float,
        acc_3m: float,
        acc_5m: float,
    ) -> int:
        if locked.move_start_price <= 0:
            return 0
        peak = max(locked.wave_peak_price, current_price)
        locked.wave_peak_price = peak
        if locked.move_start_price > 0:
            peak_move_pct = (peak - locked.move_start_price) / locked.move_start_price * 100.0
            if peak_move_pct >= REAL_JUMP_SECTION_MIN_WAVE_PCT:
                locked.extended_mode = True

        current_move_pct = (
            (current_price - locked.move_start_price) / locked.move_start_price * 100.0
            if locked.move_start_price > 0 else 0.0
        )

        if made_higher_high:
            locked.last_higher_high_time = timestamp
            locked.no_hh_minutes = 0.0
        elif locked.last_higher_high_time:
            locked.no_hh_minutes = self._minutes_since(locked.last_higher_high_time, timestamp)

        if trade_velocity > locked.peak_trade_velocity:
            locked.peak_trade_velocity = trade_velocity
        peak_vel = max(locked.peak_trade_velocity, 0.01)
        if trade_velocity < peak_vel * WAVE_END_VELOCITY_FRACTION:
            locked.low_velocity_minutes += 1.0
        else:
            locked.low_velocity_minutes = 0.0

        if volume_acceleration_1m < WAVE_END_VOL_ACCEL_MIN:
            locked.low_vol_accel_minutes += 1.0
        else:
            locked.low_vol_accel_minutes = 0.0

        move_span = peak - locked.move_start_price
        peak_move_pct = move_span / locked.move_start_price * 100.0 if locked.move_start_price > 0 else 0.0
        retrace = (peak - current_price) / move_span if move_span > 0 else 0.0
        from analysis.early_upward_surge import _wave_has_upward_momentum, _wave_is_stagnant

        post_detect = locked.first_detected_time is not None
        no_hh_thresh = WAVE_POST_DETECT_NO_HH_MINUTES if post_detect else WAVE_END_NO_HH_MINUTES
        low_vel_thresh = WAVE_POST_DETECT_LOW_VELOCITY_MINUTES if post_detect else WAVE_END_LOW_VELOCITY_MINUTES

        # Consolidation after a large move — do not treat as wave end while gain mostly intact
        faded_from_peak = current_move_pct < peak_move_pct * 0.35 if peak_move_pct > 0 else False

        signals = [
            locked.no_hh_minutes >= no_hh_thresh and faded_from_peak,
            locked.low_velocity_minutes >= low_vel_thresh and faded_from_peak,
            locked.low_vol_accel_minutes >= WAVE_END_LOW_VOL_ACCEL_MINUTES and faded_from_peak,
            retrace >= WAVE_END_RETRACE_FRACTION and peak_move_pct >= WAVE_END_RETRACE_MIN_MOVE_PCT and current_move_pct < 15.0,
            _wave_is_stagnant(acc_1m, acc_3m) and peak_move_pct >= 25.0 and current_move_pct < 10.0,
            not _wave_has_upward_momentum(acc_1m, acc_3m, acc_5m) and acc_1m < -0.15 and current_move_pct < 5.0,
            current_price < locked.move_start_price * WAVE_STRUCTURE_BREAK_PCT,
        ]
        return sum(signals)

    def _apply_lifecycle(
        self,
        locked: _LockedWave,
        *,
        current_price: float,
        timestamp: datetime,
        trade_velocity: float,
        volume_acceleration_1m: float,
        made_higher_high: bool,
        acc_1m: float,
        acc_3m: float,
        acc_5m: float,
    ) -> None:
        from analysis.early_upward_surge import _wave_has_upward_momentum

        end_count = self._end_signal_count(
            locked,
            current_price=current_price,
            timestamp=timestamp,
            trade_velocity=trade_velocity,
            volume_acceleration_1m=volume_acceleration_1m,
            made_higher_high=made_higher_high,
            acc_1m=acc_1m,
            acc_3m=acc_3m,
            acc_5m=acc_5m,
        )
        momentum = _wave_has_upward_momentum(acc_1m, acc_3m, acc_5m)
        post_detect = locked.first_detected_time is not None
        wave_age_min = self._minutes_since(locked.move_start_time, timestamp)
        min_before_cooling = (
            WAVE_POST_DETECT_MIN_MINUTES_BEFORE_COOLING if post_detect else WAVE_MIN_MINUTES_BEFORE_COOLING
        )
        active_to_cooling = WAVE_POST_DETECT_ACTIVE_TO_COOLING if post_detect else WAVE_ACTIVE_TO_COOLING_SIGNALS
        cooling_to_end = WAVE_POST_DETECT_COOLING_TO_END if post_detect else WAVE_COOLING_TO_END_SIGNALS
        cooling_min_limit = WAVE_POST_DETECT_COOLING_TO_END_MINUTES if post_detect else WAVE_COOLING_TO_END_MINUTES
        hard_break = current_price < locked.move_start_price * WAVE_STRUCTURE_BREAK_PCT
        current_move_pct = (
            (current_price - locked.move_start_price) / locked.move_start_price * 100.0
            if locked.move_start_price > 0 else 0.0
        )

        # After +100% peak: hold same wave through consolidation until meaningful give-back
        if locked.extended_mode and current_move_pct >= 20.0 and not hard_break:
            if locked.wave_state != WAVE_STATE_ACTIVE:
                locked.wave_state = WAVE_STATE_ACTIVE
                locked.cooling_since = None
            return

        if locked.wave_state == WAVE_STATE_ACTIVE:
            if hard_break and end_count >= 2:
                locked.wave_state = WAVE_STATE_COOLING
                locked.cooling_since = timestamp
            elif wave_age_min >= min_before_cooling and end_count >= active_to_cooling:
                locked.wave_state = WAVE_STATE_COOLING
                locked.cooling_since = timestamp
            return

        if locked.wave_state == WAVE_STATE_COOLING:
            if momentum and made_higher_high and end_count < active_to_cooling:
                locked.wave_state = WAVE_STATE_ACTIVE
                locked.cooling_since = None
                return
            cooling_min = self._minutes_since(locked.cooling_since, timestamp)
            if end_count >= cooling_to_end or (cooling_min >= cooling_min_limit and end_count >= active_to_cooling):
                locked.wave_state = WAVE_STATE_ENDED
                locked.reset_reason = "lifecycle_ended"

    def _snapshot_from_locked(
        self,
        symbol: str,
        locked: _LockedWave,
        *,
        current_price: float,
        acc_1m: float,
        acc_3m: float,
        acc_5m: float,
        is_new: bool = False,
    ) -> RealJumpWaveSnapshot:
        ms = locked.move_start_price
        current_move_pct = (current_price - ms) / ms * 100.0 if ms > 0 else 0.0
        active = locked.wave_state in (WAVE_STATE_ACTIVE, WAVE_STATE_COOLING)
        wave = RealJumpWaveSnapshot(
            move_start_time=locked.move_start_time,
            move_start_price=ms,
            current_move_pct=round(current_move_pct, 3),
            price_acceleration_1m=acc_1m,
            price_acceleration_3m=acc_3m,
            price_acceleration_5m=acc_5m,
            wave_peak_price=max(locked.wave_peak_price, current_price),
            first_detected_time=locked.first_detected_time,
            first_detected_price=locked.first_detected_price,
            first_detected_pct=locked.first_detected_pct,
            current_price=current_price,
            wave_id=locked.wave_id,
            wave_active=active,
            wave_ended=locked.wave_state == WAVE_STATE_ENDED,
            is_new_wave=is_new,
            wave_state=locked.wave_state,
            reset_reason=locked.reset_reason,
        )
        return wave

    def lock_first_detected(
        self,
        symbol: str,
        *,
        detected_time: datetime,
        detected_price: float,
    ) -> None:
        """Immutable first detection for the active locked wave."""
        hist = self._get(symbol)
        locked = hist.locked
        if locked.move_start_price <= 0:
            return
        if locked.first_detected_time is None:
            locked.first_detected_time = detected_time
            locked.first_detected_price = detected_price
            locked.first_detected_pct = round(
                (detected_price - locked.move_start_price) / locked.move_start_price * 100.0, 3,
            )

    def update(
        self,
        symbol: str,
        *,
        current_price: float,
        bars: pd.DataFrame | None = None,
        timestamp: datetime | None = None,
        trade_velocity: float = 0.0,
        volume_acceleration_1m: float = 0.0,
    ) -> RealJumpWaveSnapshot:
        hist = self._get(symbol)
        ts = timestamp or datetime.now(timezone.utc)
        if not hist.samples or hist.samples[-1][1] != current_price:
            hist.samples.append((ts, current_price))
        hist.bar_timestamps.append(ts)

        acc_1m, acc_3m, acc_5m = self._compute_accelerations(bars, hist.samples)
        from analysis.early_upward_surge import _wave_has_upward_momentum

        made_hh = False
        if bars is not None and len(bars) >= 2:
            highs = bars["high"].astype(float)
            made_hh = highs.iloc[-1] > highs.iloc[-2]
        elif len(hist.samples) >= 2:
            made_hh = current_price > hist.samples[-2][1]

        locked = hist.locked
        current_move_pct = (
            (current_price - locked.move_start_price) / locked.move_start_price * 100.0
            if locked.move_start_price > 0 else 0.0
        )
        momentum = _wave_has_upward_momentum(acc_1m, acc_3m, acc_5m)
        is_new = False

        if locked.wave_state in (WAVE_STATE_ACTIVE, WAVE_STATE_COOLING):
            locked.wave_peak_price = max(locked.wave_peak_price, current_price)
            self._apply_lifecycle(
                locked,
                current_price=current_price,
                timestamp=ts,
                trade_velocity=trade_velocity,
                volume_acceleration_1m=volume_acceleration_1m,
                made_higher_high=made_hh,
                acc_1m=acc_1m,
                acc_3m=acc_3m,
                acc_5m=acc_5m,
            )
            wave = self._snapshot_from_locked(
                symbol, locked, current_price=current_price,
                acc_1m=acc_1m, acc_3m=acc_3m, acc_5m=acc_5m, is_new=False,
            )
            hist.prior_wave = wave
            return wave

        # ENDED or no wave — start new only on clear upward momentum
        if locked.wave_state == WAVE_STATE_ENDED or locked.move_start_price <= 0:
            ms_candidate, ms_time = self._detect_new_move_start(
                bars, hist.samples, current_price, ts,
            )
            if ms_candidate <= 0:
                ms_candidate = current_price
                ms_time = ts
            tentative_pct = (
                (current_price - ms_candidate) / ms_candidate * 100.0 if ms_candidate > 0 else 0.0
            )
            min_pct_for_new = 5.0 if hist.prior_wave and hist.prior_wave.first_detected_time else 2.0
            if momentum and tentative_pct >= min_pct_for_new:
                locked.wave_id = _wave_id(symbol, RealJumpWaveSnapshot(
                    move_start_price=ms_candidate, move_start_time=ms_time,
                ))
                locked.move_start_price = ms_candidate
                locked.move_start_time = ms_time
                locked.wave_state = WAVE_STATE_ACTIVE
                locked.wave_peak_price = current_price
                locked.peak_trade_velocity = trade_velocity
                locked.last_higher_high_time = ts
                locked.no_hh_minutes = 0.0
                locked.low_velocity_minutes = 0.0
                locked.low_vol_accel_minutes = 0.0
                locked.cooling_since = None
                locked.reset_reason = ""
                locked.first_detected_time = None
                locked.first_detected_price = 0.0
                locked.first_detected_pct = 0.0
                locked.extended_mode = False
                is_new = True

        if locked.wave_state == WAVE_STATE_ACTIVE:
            locked.wave_peak_price = max(locked.wave_peak_price, current_price)

        wave = self._snapshot_from_locked(
            symbol, locked, current_price=current_price,
            acc_1m=acc_1m, acc_3m=acc_3m, acc_5m=acc_5m, is_new=is_new,
        )
        hist.prior_wave = wave
        return wave


class RealJumpAlertRegistry:
    """REAL_JUMP_COOLDOWN — one alert per wave; update in place; new wave only after re-acceleration."""

    def __init__(self) -> None:
        self._alerts: dict[str, ActiveRealJumpAlert] = {}

    def reset(self) -> None:
        self._alerts.clear()

    def get(self, symbol: str) -> ActiveRealJumpAlert | None:
        return self._alerts.get(symbol.upper())

    def _build_kpi(
        self,
        wave: RealJumpWaveSnapshot,
        verdict: RealPriceJumpVerdict,
        *,
        timestamp: datetime,
        session_prev_close: float = 0.0,
        current_price: float = 0.0,
    ) -> RealJumpEarlyDetectionKPI:
        peak = max(wave.wave_peak_price, wave.move_start_price, current_price)
        move_start = wave.move_start_price
        # Immutable first detection — prefer locked wave values set at first alert
        first_price = wave.first_detected_price if wave.first_detected_price > 0 else current_price
        first_time = wave.first_detected_time or timestamp
        first_pct = wave.first_detected_pct if wave.first_detected_pct > 0 else (
            (first_price - move_start) / move_start * 100.0 if move_start > 0 else wave.current_move_pct
        )
        wave_peak_move = (
            (peak - move_start) / move_start * 100.0 if move_start > 0 else 0.0
        )
        peak_after = (
            (peak - first_price) / first_price * 100.0 if first_price > 0 else 0.0
        )
        lead = 0.0
        if first_time and wave.move_start_time and peak > first_price:
            lead = self._minutes_to_peak_estimate(wave, peak, first_time)
        return RealJumpEarlyDetectionKPI(
            first_detected_time=first_time,
            first_detected_price=first_price,
            move_start_price=wave.move_start_price,
            wave_peak_price=peak,
            first_detected_pct=round(first_pct, 3),
            wave_peak_move_pct=round(wave_peak_move, 3),
            peak_after_detection_pct=round(peak_after, 3),
            lead_time_minutes=round(lead, 2),
            explosion_confluence_score=verdict.explosion_confluence_score,
        )

    @staticmethod
    def _minutes_to_peak_estimate(wave: RealJumpWaveSnapshot, peak: float, first_time: datetime) -> float:
        if wave.move_start_price <= 0 or peak <= wave.move_start_price:
            return 0.0
        span = peak - wave.move_start_price
        detected = (wave.first_detected_price or wave.move_start_price) - wave.move_start_price
        if span <= 0:
            return 0.0
        fraction_before_peak = max(0.0, 1.0 - detected / span)
        return round(max(1.0, fraction_before_peak * 8.0), 2)

    def process(
        self,
        symbol: str,
        verdict: RealPriceJumpVerdict,
        *,
        wave: RealJumpWaveSnapshot,
        current_price: float = 0.0,
        timestamp: datetime | None = None,
        session_prev_close: float = 0.0,
    ) -> RealJumpProcessResult:
        sym = symbol.upper()
        ts = timestamp or datetime.now(timezone.utc)
        out = RealJumpProcessResult(verdict=verdict)
        existing = self._alerts.get(sym)

        if not verdict.confirmed or wave.wave_ended or not wave.wave_active:
            if existing and (wave.wave_ended or not wave.wave_active):
                out.clear = True
                self._alerts.pop(sym, None)
            return out

        wid = wave.wave_id or _wave_id(sym, wave)
        if existing and existing.wave_id == wid:
            existing.last_updated = ts
            existing.verdict = verdict
            # Preserve immutable first detection from first alert
            if existing.kpi:
                wave.first_detected_time = existing.kpi.first_detected_time
                wave.first_detected_price = existing.kpi.first_detected_price
                wave.first_detected_pct = existing.kpi.first_detected_pct
            existing.kpi = self._build_kpi(
                wave, verdict, timestamp=ts, session_prev_close=session_prev_close, current_price=current_price,
            )
            verdict.is_alert_update = True
            verdict.kpi = existing.kpi
            out.emit = True
            out.update_existing = True
            out.alert = existing
            return out

        if existing and existing.wave_id != wid and not wave.is_new_wave:
            out.clear = False
            return out

        if wave.first_detected_time is None:
            wave.first_detected_time = ts
        if wave.first_detected_price <= 0 and current_price > 0:
            wave.first_detected_price = current_price
        if wave.first_detected_pct <= 0 and wave.move_start_price > 0:
            wave.first_detected_pct = round(
                (wave.first_detected_price - wave.move_start_price) / wave.move_start_price * 100.0, 3,
            )
        real_jump_wave_tracker.lock_first_detected(
            sym,
            detected_time=wave.first_detected_time or ts,
            detected_price=wave.first_detected_price or current_price,
        )
        # Sync locked values back onto wave after registry lock
        hist_locked = real_jump_wave_tracker._get(sym).locked
        wave.first_detected_time = hist_locked.first_detected_time
        wave.first_detected_price = hist_locked.first_detected_price
        wave.first_detected_pct = hist_locked.first_detected_pct
        alert_id = f"{wid}:{int(ts.timestamp())}"
        kpi = self._build_kpi(
            wave, verdict, timestamp=ts, session_prev_close=session_prev_close, current_price=current_price,
        )
        alert = ActiveRealJumpAlert(
            symbol=sym,
            wave_id=wid,
            alert_id=alert_id,
            kpi=kpi,
            last_updated=ts,
            verdict=verdict,
        )
        self._alerts[sym] = alert
        verdict.kpi = kpi
        out.emit = True
        out.update_existing = False
        out.alert = alert
        return out


real_jump_wave_tracker = RealJumpWaveTracker()
real_jump_alert_registry = RealJumpAlertRegistry()


def _movement_start(sig: PreMoveSignal) -> float:
    if sig.first_detected_price > 0:
        return sig.first_detected_price
    if sig.entry_low > 0:
        return sig.entry_low
    if sig.trigger_price > 0:
        return sig.trigger_price * 0.985
    return 0.0


def _premarket_gap_pct(sig: PreMoveSignal) -> float:
    levels = getattr(sig, "levels", None)
    if levels is None:
        return 0.0
    prev = getattr(levels, "prev_day_high", 0) or getattr(levels, "support", 0)
    open_px = getattr(levels, "premarket_high", 0) or sig.current_price
    if prev > 0 and open_px > 0:
        return max(0.0, (open_px - prev) / prev * 100.0)
    return 0.0


def evaluate_premove_real_jump(
    sig: PreMoveSignal,
    *,
    bars: pd.DataFrame | None = None,
    timestamp: datetime | None = None,
) -> RealPriceJumpVerdict:
    ctx = context_from_premove(sig)
    ea = sig.early_activity
    wave = real_jump_wave_tracker.update(
        sig.symbol,
        current_price=sig.current_price,
        bars=bars,
        timestamp=timestamp,
        trade_velocity=float(ea.trade_velocity or 0),
        volume_acceleration_1m=ctx.volume_acceleration_1m,
    )
    news = getattr(sig, "news", None)
    verdict = evaluate_real_jump_alert(
        current_price=sig.current_price,
        change_pct=sig.change_percent,
        price_volume_response=ctx.price_volume_response,
        micro_higher_lows=ctx.micro_higher_lows,
        vwap_hold=ctx.vwap_hold,
        vwap_reclaim=ctx.vwap_reclaim,
        breakout_pressure=ctx.breakout_pressure,
        resistance_distance_pct=ctx.resistance_distance_pct,
        trigger_price=sig.trigger_price,
        movement_start_price=wave.move_start_price or _movement_start(sig),
        volume_acceleration_1m=ctx.volume_acceleration_1m,
        volume_acceleration_slope=ctx.volume_acceleration_slope,
        rvol=ctx.rvol,
        rvol_same_time=ctx.rvol_same_time,
        trade_velocity_growth=ctx.trade_velocity_growth,
        trade_velocity=ea.trade_velocity,
        dollar_volume_growth=ctx.dollar_volume_growth,
        liquidity_score=ctx.liquidity_score,
        spread_pct=ctx.spread_pct,
        persistence_minutes=sig.stage_progression.persistence_minutes,
        move_from_base_pct=wave.current_move_pct,
        range_compression_3m=ea.range_compression_3m,
        compression_only=sig.compression.compression_score >= 0.5 and wave.current_move_pct < 2.0,
        watch_only=sig.status in ("EARLY_WATCH", "PRE_BREAKOUT") and not sig.display_confirmed,
        late_guard=False,
        bars=bars,
        wave=wave,
        news_catalyst_score=getattr(news, "news_catalyst_score", 0.0) if news else 0.0,
        premarket_gap_pct=_premarket_gap_pct(sig),
        catalyst_strength=getattr(news, "news_strength", 0.0) if news else 0.0,
    )
    real_jump_alert_registry.process(
        sig.symbol,
        verdict,
        wave=wave,
        current_price=sig.current_price,
        timestamp=timestamp,
    )
    return verdict


def evaluate_opportunity_real_jump(
    sig: OpportunityNowSignal,
    *,
    bars: pd.DataFrame | None = None,
    timestamp: datetime | None = None,
) -> RealPriceJumpVerdict:
    ctx = context_from_opportunity_signal(sig)
    entry_high = sig.entry_zone_high or sig.entry_zone
    wave = real_jump_wave_tracker.update(
        sig.symbol,
        current_price=sig.price,
        bars=bars,
        timestamp=timestamp,
        trade_velocity=0.0,
        volume_acceleration_1m=sig.volume_acceleration,
    )
    verdict = evaluate_real_jump_alert(
        current_price=sig.price,
        change_pct=sig.change_percent,
        price_volume_response=ctx.price_volume_response,
        micro_higher_lows=ctx.micro_higher_lows,
        breakout_pressure=ctx.breakout_pressure or (45.0 if sig.detection_stage == "EXPLOSIVE" else 0.0),
        resistance_distance_pct=ctx.resistance_distance_pct,
        trigger_price=entry_high,
        movement_start_price=wave.move_start_price or (sig.entry_zone_low or sig.entry_zone),
        volume_acceleration_1m=sig.volume_acceleration,
        rvol=sig.rvol or sig.relative_volume,
        trade_velocity_growth=ctx.trade_velocity_growth,
        dollar_volume_growth=ctx.dollar_volume_growth,
        liquidity_score=max(ctx.liquidity_score, PREMOVE_MIN_LIQUIDITY_SCORE),
        spread_pct=ctx.spread_pct,
        persistence_minutes=sig.consecutive_confirmations,
        move_from_base_pct=wave.current_move_pct,
        late_guard=False,
        bars=bars,
        wave=wave,
    )
    real_jump_alert_registry.process(
        sig.symbol,
        verdict,
        wave=wave,
        current_price=sig.price,
        timestamp=timestamp,
    )
    return verdict


def real_jump_wave_peak_move_pct(kpi: RealJumpEarlyDetectionKPI | None) -> float:
    if not kpi or kpi.move_start_price <= 0:
        return 0.0
    return kpi.wave_peak_move_pct


def eligible_for_price_jump_section(
    kpi: RealJumpEarlyDetectionKPI | None,
    *,
    current_move_pct: float = 0.0,
) -> bool:
    """قسم «قفزة سعرية» — current_move_pct from locked move_start (live)."""
    live = current_move_pct
    if kpi and kpi.move_start_price > 0 and kpi.first_detected_price > 0:
        pass
    return live >= REAL_JUMP_SECTION_MIN_WAVE_PCT


def is_explosive_wave(
    current_move_pct: float,
) -> bool:
    return current_move_pct >= REAL_JUMP_EXPLOSIVE_WAVE_PCT


def apply_real_jump_display(sig: OpportunityNowSignal, verdict: RealPriceJumpVerdict) -> OpportunityNowSignal:
    data = sig.model_dump()
    wave = verdict.wave
    kpi = verdict.kpi
    current_price = sig.price
    data["display_type"] = DISPLAY_REAL_JUMP_ALERT
    data["status"] = "NOW"
    data["status_ar"] = "REAL_JUMP_ALERT"
    data["opportunity_type"] = DISPLAY_REAL_JUMP_ALERT
    data["confluence_factors"] = list(verdict.evidence_factors)
    data["confluence_count"] = len(verdict.evidence_factors)

    move_start = (kpi.move_start_price if kpi else 0.0) or (wave.move_start_price if wave else 0.0)
    move_start_time = ""
    if wave and wave.move_start_time:
        move_start_time = wave.move_start_time.isoformat()
    first_detected_time = ""
    if kpi and kpi.first_detected_time:
        first_detected_time = kpi.first_detected_time.isoformat()
    elif wave and wave.first_detected_time:
        first_detected_time = wave.first_detected_time.isoformat()

    current_move_pct = wave.current_move_pct if wave else 0.0
    first_detected_price = (kpi.first_detected_price if kpi else 0.0) or (wave.first_detected_price if wave else 0.0)
    first_detected_pct = (kpi.first_detected_pct if kpi else 0.0) or (wave.first_detected_pct if wave else 0.0)
    wave_peak = (kpi.wave_peak_price if kpi else 0.0) or (wave.wave_peak_price if wave else current_price)
    wave_peak_move = kpi.wave_peak_move_pct if kpi else 0.0
    if wave_peak_move <= 0 and move_start > 0 and wave_peak > move_start:
        wave_peak_move = (wave_peak - move_start) / move_start * 100.0
    peak_after = kpi.peak_after_detection_pct if kpi else 0.0
    if peak_after <= 0 and first_detected_price > 0 and wave_peak > first_detected_price:
        peak_after = (wave_peak - first_detected_price) / first_detected_price * 100.0

    data["real_jump_move_start_price"] = round(move_start, 4)
    data["real_jump_move_start_time"] = move_start_time
    data["real_jump_current_move_pct"] = round(current_move_pct, 3)
    data["real_jump_first_detected_price"] = round(first_detected_price, 4)
    data["real_jump_first_detected_pct"] = round(first_detected_pct, 3)
    data["real_jump_first_detected_time"] = first_detected_time
    data["real_jump_wave_peak_price"] = round(wave_peak, 4)
    data["real_jump_wave_peak_move_pct"] = round(wave_peak_move, 3)
    data["real_jump_peak_after_detection_pct"] = round(peak_after, 3)
    if is_explosive_wave(current_move_pct):
        data["detection_stage"] = "EXPLOSIVE"
    elif eligible_for_price_jump_section(kpi, current_move_pct=current_move_pct):
        data["detection_stage"] = data.get("detection_stage") or "REAL_JUMP_ALERT"

    if not data.get("buy_pressure_score"):
        rvol = sig.rvol or sig.relative_volume or 0.5
        data["buy_pressure_score"] = round(fast_filter_surge_rank(current_move_pct, rvol), 2)
    return OpportunityNowSignal(**data)


def eligible_premove(sig: PreMoveSignal) -> bool:
    if sig.current_price <= 0 or sig.current_price > MAX_PRICE_USD:
        return False
    if sig.data_age_seconds > PREMOVE_DATA_MAX_AGE_SECONDS:
        return False
    return True


def reset_real_jump_state() -> None:
    real_jump_wave_tracker.reset()
    real_jump_alert_registry.reset()
