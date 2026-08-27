"""Independent REAL_JUMP_ALERT layer — sits above existing display signals unchanged."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from analysis.early_upward_surge import (
    DISPLAY_REAL_JUMP_ALERT,
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
WAVE_SAMPLE_MAX = 8


@dataclass
class _SymbolWaveHistory:
    prior_wave: RealJumpWaveSnapshot | None = None
    samples: deque[tuple[datetime, float]] = field(default_factory=lambda: deque(maxlen=WAVE_SAMPLE_MAX))
    stagnant_ticks: int = 0


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

    def update(
        self,
        symbol: str,
        *,
        current_price: float,
        bars: pd.DataFrame | None = None,
        timestamp: datetime | None = None,
    ) -> RealJumpWaveSnapshot:
        hist = self._get(symbol)
        ts = timestamp or datetime.now(timezone.utc)
        if not hist.samples or hist.samples[-1][1] != current_price:
            hist.samples.append((ts, current_price))

        prior = hist.prior_wave
        if bars is not None and len(bars) >= 2:
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

        if wave.wave_active:
            hist.stagnant_ticks = 0
        elif prior and prior.wave_active:
            hist.stagnant_ticks += 1
            if hist.stagnant_ticks >= 2:
                wave.wave_ended = True
                wave.wave_active = False

        hist.prior_wave = wave
        return wave


real_jump_wave_tracker = RealJumpWaveTracker()


def _movement_start(sig: PreMoveSignal) -> float:
    if sig.first_detected_price > 0:
        return sig.first_detected_price
    if sig.entry_low > 0:
        return sig.entry_low
    if sig.trigger_price > 0:
        return sig.trigger_price * 0.985
    return 0.0


def evaluate_premove_real_jump(
    sig: PreMoveSignal,
    *,
    bars: pd.DataFrame | None = None,
) -> RealPriceJumpVerdict:
    ctx = context_from_premove(sig)
    ea = sig.early_activity
    wave = real_jump_wave_tracker.update(
        sig.symbol,
        current_price=sig.current_price,
        bars=bars,
    )
    return evaluate_real_jump_alert(
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
    )


def evaluate_opportunity_real_jump(
    sig: OpportunityNowSignal,
    *,
    bars: pd.DataFrame | None = None,
) -> RealPriceJumpVerdict:
    ctx = context_from_opportunity_signal(sig)
    entry_high = sig.entry_zone_high or sig.entry_zone
    wave = real_jump_wave_tracker.update(
        sig.symbol,
        current_price=sig.price,
        bars=bars,
    )
    return evaluate_real_jump_alert(
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


def apply_real_jump_display(sig: OpportunityNowSignal, verdict: RealPriceJumpVerdict) -> OpportunityNowSignal:
    data = sig.model_dump()
    data["display_type"] = DISPLAY_REAL_JUMP_ALERT
    data["status"] = "NOW"
    data["status_ar"] = "قفزة سعرية حقيقية"
    data["opportunity_type"] = DISPLAY_REAL_JUMP_ALERT
    data["confluence_factors"] = list(verdict.evidence_factors)
    data["confluence_count"] = len(verdict.evidence_factors)
    if verdict.wave is not None:
        data["confluence_factors"] = list(dict.fromkeys(
            data["confluence_factors"]
            + [
                f"move_start_price:{verdict.wave.move_start_price:.4f}",
                f"current_move_pct:{verdict.wave.current_move_pct:.2f}",
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
