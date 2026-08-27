"""Explosion Confluence Score for REAL_JUMP_ALERT — weighted baseline, hard gates, bonus only."""

from __future__ import annotations

from dataclasses import dataclass, field

from config import (
    PREMOVE_MIN_LIQUIDITY_SCORE,
    STAGE_EE_MAX_SPREAD_PCT,
    STAGE_EE_MIN_RVOL,
    STAGE_VOL_ACCEL_STRONG,
)

# Baseline weights — sum = 100%
EXPLOSION_WEIGHTS: dict[str, float] = {
    "price_acceleration": 0.25,
    "breakout_higher_high": 0.15,
    "volume_acceleration": 0.15,
    "trade_velocity": 0.12,
    "buy_pressure": 0.12,
    "rvol_same_time": 0.08,
    "liquidity": 0.06,
    "spread": 0.04,
    "compression_coil": 0.03,
}

# Baseline pass threshold — do not tune without replay evidence
CONFLUENCE_PASS_THRESHOLD = 0.58

BONUS_SMALL_FLOAT = 0.03
BONUS_NEWS = 0.03
BONUS_PREMARKET_GAP = 0.02
BONUS_PSYCH_LEVEL = 0.02
BONUS_CATALYST = 0.02
MAX_BONUS = 0.10

SMALL_FLOAT_SHARES = 10_000_000
PSYCH_LEVEL_TOLERANCE_PCT = 0.8


@dataclass
class RealJumpBonusContext:
    float_shares: float = 0.0
    news_catalyst_score: float = 0.0
    premarket_gap_pct: float = 0.0
    near_psychological_level: bool = False
    catalyst_strength: float = 0.0


@dataclass
class ExplosionConfluenceResult:
    total_score: float = 0.0
    base_score: float = 0.0
    bonus_score: float = 0.0
    component_scores: dict[str, float] = field(default_factory=dict)
    bonus_factors: list[str] = field(default_factory=list)
    hard_gates: dict[str, bool] = field(default_factory=dict)
    hard_gate_pass: bool = False


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _score_price_acceleration(acc_1m: float, acc_3m: float, acc_5m: float) -> float:
    a1 = _clamp01(acc_1m / 0.50)
    a3 = _clamp01(acc_3m / 0.80)
    a5 = _clamp01(acc_5m / 1.00)
    return _clamp01(a1 * 0.45 + a3 * 0.35 + a5 * 0.20)


def _score_volume_acceleration(vol_accel_1m: float, vol_slope: float) -> float:
    base = _clamp01(vol_accel_1m / max(STAGE_VOL_ACCEL_STRONG, 0.01))
    if vol_slope >= 1.12:
        base = max(base, 0.85)
    return base


def _score_trade_velocity(growth: float | None, velocity: float | None) -> float:
    g = _clamp01((growth or 0.0) / 0.25)
    if (velocity or 0) > 0 and (growth or 0) >= 0.10:
        g = max(g, 0.7)
    return g


def _score_buy_pressure(pvr: float, dollar_vol_growth: float) -> float:
    return _clamp01(max(pvr / 0.55, dollar_vol_growth / 0.35))


def _score_rvol(rvol_same_time: float | None, rvol: float) -> float:
    eff = rvol_same_time if rvol_same_time is not None and rvol_same_time > 0 else rvol
    return _clamp01(eff / max(STAGE_EE_MIN_RVOL, 0.01))


def _score_liquidity(liquidity_score: float) -> float:
    return _clamp01(liquidity_score / 80.0)


def _score_spread(spread_pct: float) -> float:
    if spread_pct <= STAGE_EE_MAX_SPREAD_PCT:
        return 1.0
    if spread_pct >= STAGE_EE_MAX_SPREAD_PCT * 2:
        return 0.0
    return _clamp01(1.0 - (spread_pct - STAGE_EE_MAX_SPREAD_PCT) / STAGE_EE_MAX_SPREAD_PCT)


def _score_compression(range_compression_3m: float) -> float:
    return _clamp01(range_compression_3m / 0.70)


def _compute_bonus(ctx: RealJumpBonusContext | None) -> tuple[float, list[str]]:
    if ctx is None:
        return 0.0, []
    bonus = 0.0
    factors: list[str] = []
    if 0 < ctx.float_shares < SMALL_FLOAT_SHARES:
        bonus += BONUS_SMALL_FLOAT
        factors.append("bonus_small_float")
    if ctx.news_catalyst_score >= 35:
        bonus += BONUS_NEWS * _clamp01(ctx.news_catalyst_score / 100.0)
        factors.append("bonus_news_catalyst")
    if ctx.premarket_gap_pct >= 3.0:
        bonus += BONUS_PREMARKET_GAP
        factors.append("bonus_premarket_gap")
    if ctx.near_psychological_level:
        bonus += BONUS_PSYCH_LEVEL
        factors.append("bonus_psych_level")
    if ctx.catalyst_strength >= 0.4:
        bonus += BONUS_CATALYST * _clamp01(ctx.catalyst_strength)
        factors.append("bonus_catalyst_strength")
    return min(bonus, MAX_BONUS), factors


def near_psychological_level(price: float) -> bool:
    if price <= 0:
        return False
    for level in (1, 2, 3, 5, 10):
        if abs(price - level) / level * 100 <= PSYCH_LEVEL_TOLERANCE_PCT:
            return True
    whole = round(price)
    if whole > 0 and abs(price - whole) / whole * 100 <= PSYCH_LEVEL_TOLERANCE_PCT:
        return True
    return False


def compute_explosion_confluence(
    *,
    price_acceleration_ok: bool,
    acc_1m: float,
    acc_3m: float,
    acc_5m: float,
    breakout_ok: bool,
    multi_tick_ok: bool,
    volume_acceleration_1m: float,
    volume_acceleration_slope: float,
    trade_velocity_growth: float | None,
    trade_velocity: float | None,
    price_volume_response: float,
    dollar_volume_growth: float,
    rvol: float,
    rvol_same_time: float | None,
    liquidity_score: float,
    spread_pct: float,
    range_compression_3m: float,
    bonus: RealJumpBonusContext | None = None,
) -> ExplosionConfluenceResult:
    """Weighted Explosion Confluence Score with non-compensable hard gates."""
    out = ExplosionConfluenceResult()
    liquidity_ok = liquidity_score >= PREMOVE_MIN_LIQUIDITY_SCORE
    spread_ok = spread_pct <= STAGE_EE_MAX_SPREAD_PCT

    out.hard_gates = {
        "price_acceleration_rising": price_acceleration_ok and acc_1m > 0,
        "multi_tick_persistence": multi_tick_ok,
        "breakout_higher_high": breakout_ok,
        "liquidity_tradable": liquidity_ok,
        "spread_acceptable": spread_ok,
    }
    out.hard_gate_pass = all(out.hard_gates.values())

    components = {
        "price_acceleration": _score_price_acceleration(acc_1m, acc_3m, acc_5m),
        "breakout_higher_high": 1.0 if breakout_ok else 0.0,
        "volume_acceleration": _score_volume_acceleration(volume_acceleration_1m, volume_acceleration_slope),
        "trade_velocity": _score_trade_velocity(trade_velocity_growth, trade_velocity),
        "buy_pressure": _score_buy_pressure(price_volume_response, dollar_volume_growth),
        "rvol_same_time": _score_rvol(rvol_same_time, rvol),
        "liquidity": _score_liquidity(liquidity_score),
        "spread": _score_spread(spread_pct),
        "compression_coil": _score_compression(range_compression_3m),
    }
    out.component_scores = components
    out.base_score = round(sum(components[k] * EXPLOSION_WEIGHTS[k] for k in EXPLOSION_WEIGHTS), 4)
    out.bonus_score, out.bonus_factors = _compute_bonus(bonus)
    out.total_score = round(min(1.0, out.base_score + out.bonus_score), 4)
    return out
