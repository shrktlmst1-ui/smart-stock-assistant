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
REAL_JUMP_MAX = 3
WAVE_SAMPLE_MAX = 12

WAVE_END_NO_HH_MINUTES = 3
WAVE_END_LOW_VELOCITY_MINUTES = 2
WAVE_END_LOW_VOL_ACCEL_MINUTES = 2
WAVE_END_VELOCITY_FRACTION = 0.45
WAVE_END_VOL_ACCEL_MIN = 1.2
WAVE_END_RETRACE_FRACTION = 0.35


def _wave_id(symbol: str, wave: RealJumpWaveSnapshot) -> str:
    ts = wave.move_start_time.isoformat() if wave.move_start_time else "na"
    return f"{symbol.upper()}:{wave.move_start_price:.4f}:{ts}"


@dataclass
class _SymbolWaveHistory:
    prior_wave: RealJumpWaveSnapshot | None = None
    samples: deque[tuple[datetime, float]] = field(default_factory=lambda: deque(maxlen=WAVE_SAMPLE_MAX))
    wave_peak_price: float = 0.0
    peak_trade_velocity: float = 0.0
    last_higher_high_time: datetime | None = None
    no_hh_minutes: float = 0.0
    low_velocity_minutes: float = 0.0
    low_vol_accel_minutes: float = 0.0
    active_wave_id: str = ""
    active_alert_id: str = ""
    first_kpi: RealJumpEarlyDetectionKPI | None = None
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

    def _check_wave_end(
        self,
        hist: _SymbolWaveHistory,
        wave: RealJumpWaveSnapshot,
        *,
        current_price: float,
        timestamp: datetime,
        trade_velocity: float,
        volume_acceleration_1m: float,
        made_higher_high: bool,
    ) -> bool:
        if wave.move_start_price <= 0:
            return False
        peak = max(hist.wave_peak_price, wave.wave_peak_price, current_price)
        hist.wave_peak_price = peak
        wave.wave_peak_price = peak

        if made_higher_high:
            hist.last_higher_high_time = timestamp
            hist.no_hh_minutes = 0.0
        elif hist.last_higher_high_time:
            hist.no_hh_minutes = self._minutes_since(hist.last_higher_high_time, timestamp)

        if trade_velocity > hist.peak_trade_velocity:
            hist.peak_trade_velocity = trade_velocity
        peak_vel = max(hist.peak_trade_velocity, 0.01)
        if trade_velocity < peak_vel * WAVE_END_VELOCITY_FRACTION:
            hist.low_velocity_minutes += 1.0
        else:
            hist.low_velocity_minutes = 0.0

        if volume_acceleration_1m < WAVE_END_VOL_ACCEL_MIN:
            hist.low_vol_accel_minutes += 1.0
        else:
            hist.low_vol_accel_minutes = 0.0

        move_span = peak - wave.move_start_price
        retrace = 0.0
        if move_span > 0:
            retrace = (peak - current_price) / move_span

        end_signals = [
            hist.no_hh_minutes >= WAVE_END_NO_HH_MINUTES,
            hist.low_velocity_minutes >= WAVE_END_LOW_VELOCITY_MINUTES,
            hist.low_vol_accel_minutes >= WAVE_END_LOW_VOL_ACCEL_MINUTES,
            retrace >= WAVE_END_RETRACE_FRACTION,
        ]
        return sum(end_signals) >= 2

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

        prior = hist.prior_wave
        made_hh = False
        if bars is not None and len(bars) >= 2:
            highs = bars["high"].astype(float)
            made_hh = highs.iloc[-1] > highs.iloc[-2]
            wave = derive_real_jump_wave(
                bars=bars,
                current_price=current_price,
                prior=prior,
                move_start_time=ts,
            )
        else:
            acc_1m, acc_3m, acc_5m = self._accel_from_samples(hist.samples)
            wave = derive_real_jump_wave(
                bars=None,
                current_price=current_price,
                prior=prior,
                move_start_time=ts,
                price_acceleration_1m=acc_1m,
                price_acceleration_3m=acc_3m,
                price_acceleration_5m=acc_5m,
            )
            if wave.move_start_price <= 0 and len(hist.samples) >= 2:
                wave.move_start_price = hist.samples[0][1]
                wave.move_start_time = hist.samples[0][0]
            if wave.move_start_price > 0:
                wave.current_move_pct = (
                    (current_price - wave.move_start_price) / wave.move_start_price * 100.0
                )
            from analysis.early_upward_surge import _wave_has_upward_momentum

            if _wave_has_upward_momentum(acc_1m, acc_3m, acc_5m) and wave.current_move_pct >= 2.0:
                wave.wave_active = True
            made_hh = len(hist.samples) >= 2 and current_price > hist.samples[-2][1]

        wave.wave_peak_price = max(hist.wave_peak_price, current_price, wave.wave_peak_price)
        wave.wave_id = _wave_id(symbol, wave)

        if wave.is_new_wave:
            hist.wave_peak_price = current_price
            hist.peak_trade_velocity = trade_velocity
            hist.last_higher_high_time = ts
            hist.no_hh_minutes = 0.0
            hist.low_velocity_minutes = 0.0
            hist.low_vol_accel_minutes = 0.0
            hist.active_wave_id = wave.wave_id
            hist.first_kpi = None

        if wave.wave_active and self._check_wave_end(
            hist,
            wave,
            current_price=current_price,
            timestamp=ts,
            trade_velocity=trade_velocity,
            volume_acceleration_1m=volume_acceleration_1m,
            made_higher_high=made_hh,
        ):
            wave.wave_active = False
            wave.wave_ended = True

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
    ) -> RealJumpEarlyDetectionKPI:
        peak = max(wave.wave_peak_price, wave.move_start_price)
        first_price = wave.first_detected_price or wave.move_start_price
        first_time = wave.first_detected_time or wave.move_start_time or timestamp
        base = session_prev_close if session_prev_close > 0 else wave.move_start_price
        first_pct = (
            (first_price - base) / base * 100.0 if base > 0 else wave.current_move_pct
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
            existing.kpi = self._build_kpi(wave, verdict, timestamp=ts, session_prev_close=session_prev_close)
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
        alert_id = f"{wid}:{int(ts.timestamp())}"
        kpi = self._build_kpi(wave, verdict, timestamp=ts, session_prev_close=session_prev_close)
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


def apply_real_jump_display(sig: OpportunityNowSignal, verdict: RealPriceJumpVerdict) -> OpportunityNowSignal:
    data = sig.model_dump()
    data["display_type"] = DISPLAY_REAL_JUMP_ALERT
    data["status"] = "NOW"
    data["status_ar"] = "قفزة سعرية حقيقية"
    data["opportunity_type"] = DISPLAY_REAL_JUMP_ALERT
    data["confluence_factors"] = list(verdict.evidence_factors)
    data["confluence_count"] = len(verdict.evidence_factors)
    kpi = verdict.kpi
    if kpi is not None:
        data["confluence_factors"] = list(dict.fromkeys(
            data["confluence_factors"]
            + [
                f"move_start_price:{kpi.move_start_price:.4f}",
                f"current_move_pct:{verdict.wave.current_move_pct:.2f}" if verdict.wave else "",
                f"explosion_score:{kpi.explosion_confluence_score:.2f}",
                f"first_detected_pct:{kpi.first_detected_pct:.2f}",
                f"lead_time_min:{kpi.lead_time_minutes:.1f}",
            ]
        ))
    elif verdict.wave is not None:
        data["confluence_factors"] = list(dict.fromkeys(
            data["confluence_factors"]
            + [
                f"move_start_price:{verdict.wave.move_start_price:.4f}",
                f"current_move_pct:{verdict.wave.current_move_pct:.2f}",
                f"explosion_score:{verdict.explosion_confluence_score:.2f}",
            ]
        ))
    if not data.get("buy_pressure_score"):
        rvol = sig.rvol or sig.relative_volume or 0.5
        move_pct = verdict.wave.current_move_pct if verdict.wave else sig.change_percent
        data["buy_pressure_score"] = round(fast_filter_surge_rank(move_pct, rvol), 2)
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
