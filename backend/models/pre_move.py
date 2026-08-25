"""Pre-Move Predictor — early setup detection models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from models.pre_move_stage import PreMoveStageProgressionMetrics

PreMoveStatus = Literal[
    "NO_SETUP",
    "EARLY_WATCH",
    "PRE_BREAKOUT",
    "EARLY_ENTRY",
    "HIGH_CONVICTION_EARLY",
    "TOO_LATE_TO_CHASE",
    "CONFIRMED_ENTRY",
    "INSUFFICIENT_DATA",
    "STALE_PRICE",
    "FAILED_SETUP",
]

PreMoveLifecycle = Literal[
    "DISCOVERED",
    "EARLY_WATCH",
    "PRE_BREAKOUT",
    "EARLY_ENTRY",
    "BREAKOUT_CONFIRMED",
    "TOO_LATE_TO_CHASE",
    "FAILED_SETUP",
    "STOPPED",
    "TARGET1_HIT",
    "TARGET2_HIT",
]

PreMoveTiming = Literal["EARLY", "NORMAL", "LATE"]


class PreMoveScoreBreakdown(BaseModel):
    early_activity: float = 0.0
    early_activity_max: float = 28.0
    volume: float = 0.0
    volume_max: float = 12.0
    structure: float = 0.0
    structure_max: float = 10.0
    vwap: float = 0.0
    vwap_max: float = 10.0
    breakout_pressure: float = 0.0
    breakout_pressure_max: float = 10.0
    news: float = 0.0
    news_max: float = 10.0
    liquidity: float = 0.0
    liquidity_max: float = 10.0
    confluence_bonus: float = 0.0
    pre_expansion_bonus: float = 0.0
    signal_decay: float = 0.0
    late_move_penalty: float = 0.0
    unavailable_factors: list[str] = Field(default_factory=list)


class PreMoveVolumeMetrics(BaseModel):
    volume_1m: int = 0
    volume_3m: int = 0
    volume_5m: int = 0
    volume_10m: int = 0
    volume_acceleration: float = 0.0
    volume_acceleration_1m: float = 0.0
    volume_acceleration_3m: float = 0.0
    volume_acceleration_slope: float = 0.0
    vol_1m_prev: int = 0
    vol_3m_current: int = 0
    volume_growth_rate: float = 0.0
    rvol: float = 0.0
    rvol_same_time: float | None = None
    volume_vs_previous_1m: float = 0.0
    volume_vs_previous_5m: float = 0.0
    dollar_volume_1m: float = 0.0
    dollar_volume_3m: float = 0.0
    dollar_volume_growth: float = 0.0


class PreMoveEarlyActivityMetrics(BaseModel):
    vol_1m_current: int = 0
    vol_1m_prev: int = 0
    vol_1m_prev2: int = 0
    vol_3m_current: int = 0
    vol_3m_previous: int = 0
    volume_acceleration_1m: float = 0.0
    volume_acceleration_3m: float = 0.0
    volume_acceleration_slope: float = 0.0
    dollar_volume_1m: float = 0.0
    dollar_volume_3m: float = 0.0
    dollar_volume_growth: float = 0.0
    trades_per_minute: float | None = None
    trade_count_growth: float | None = None
    trade_velocity: float | None = None
    trade_velocity_acceleration: float | None = None
    trade_data_available: bool = False
    baseline_volume: float = 0.0
    baseline_range: float = 0.0
    baseline_spread: float = 0.0
    activity_deviation_score: float = 0.0
    micro_higher_lows: bool = False
    micro_higher_lows_score: float = 0.0
    price_volume_response: float = 0.0
    absorption_score: float = 0.0
    higher_low_persistence: float = 0.0
    range_compression_3m: float = 0.0
    range_compression_5m: float = 0.0
    atr_contraction: float = 0.0
    volume_rising_inside_compression: bool = False
    breakout_pressure_score: float = 0.0
    resistance_distance_pct: float = 0.0
    rvol_same_time: float | None = None
    early_activity_score: float = 0.0
    confluence_bonus: float = 0.0
    confluence_factors: list[str] = Field(default_factory=list)
    signal_decay: float = 0.0
    unavailable_factors: list[str] = Field(default_factory=list)


class PreMoveCompressionMetrics(BaseModel):
    compression_score: float = 0.0
    range_contraction: float = 0.0
    higher_lows_score: float = 0.0
    resistance_pressure: float = 0.0
    atr_contraction: float = 0.0


class PreMoveVwapMetrics(BaseModel):
    vwap: float = 0.0
    vwap_reclaim: bool = False
    vwap_hold: bool = False
    distance_from_vwap_pct: float = 0.0
    vwap_support_test: bool = False


class PreMoveBreakoutMetrics(BaseModel):
    resistance: float = 0.0
    support: float = 0.0
    distance_to_breakout_pct: float = 0.0
    premarket_high: float = 0.0
    day_high: float = 0.0
    prev_day_high: float = 0.0


class PreMoveNewsMetrics(BaseModel):
    news_recency_minutes: float | None = None
    news_strength: float = 0.0
    news_relevance: float = 0.0
    news_catalyst_score: float = 0.0
    news_already_priced_in: bool = False
    catalyst_title: str = ""
    catalyst_type: str = ""


class PreMoveLiquidityMetrics(BaseModel):
    liquidity_score: float = 0.0
    dollar_volume: float = 0.0
    spread_percent: float = 0.0
    trade_frequency: float = 0.0


class PreMoveLateMoveMetrics(BaseModel):
    late_move_score: float = 0.0
    is_too_late: bool = False
    rsi: float | None = None
    extension_from_base_pct: float = 0.0
    distance_from_vwap_pct: float = 0.0
    consecutive_expansion_candles: int = 0
    volume_exhaustion: bool = False
    reasons: list[str] = Field(default_factory=list)


class PreMoveLifecycleEvent(BaseModel):
    at: str
    status: str
    score: int
    price: float = 0.0


class PreMoveSignal(BaseModel):
    signal_id: str
    symbol: str
    name: str = ""
    current_price: float = 0.0
    change_percent: float = 0.0
    pre_move_score: int = Field(ge=0, le=100, default=0)
    status: PreMoveStatus = "NO_SETUP"
    lifecycle: PreMoveLifecycle = "DISCOVERED"
    timing: PreMoveTiming = "NORMAL"
    emoji: str = ""

    first_detected_at: str = ""
    first_detected_price: float = 0.0
    first_detected_score: int = 0

    trigger_price: float = 0.0
    entry_low: float = 0.0
    entry_high: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    risk_reward: float = 0.0

    volume: PreMoveVolumeMetrics = Field(default_factory=PreMoveVolumeMetrics)
    early_activity: PreMoveEarlyActivityMetrics = Field(default_factory=PreMoveEarlyActivityMetrics)
    compression: PreMoveCompressionMetrics = Field(default_factory=PreMoveCompressionMetrics)
    vwap: PreMoveVwapMetrics = Field(default_factory=PreMoveVwapMetrics)
    breakout: PreMoveBreakoutMetrics = Field(default_factory=PreMoveBreakoutMetrics)
    news: PreMoveNewsMetrics = Field(default_factory=PreMoveNewsMetrics)
    liquidity: PreMoveLiquidityMetrics = Field(default_factory=PreMoveLiquidityMetrics)
    late_move: PreMoveLateMoveMetrics = Field(default_factory=PreMoveLateMoveMetrics)
    score_breakdown: PreMoveScoreBreakdown = Field(default_factory=PreMoveScoreBreakdown)
    stage_progression: PreMoveStageProgressionMetrics = Field(default_factory=PreMoveStageProgressionMetrics)

    risk_level: Literal["منخفض", "متوسط", "مرتفع"] = "متوسط"
    reason: str = ""
    rejection_reason: str = ""
    data_timestamp: str = ""
    data_age_seconds: float = 0.0
    lifecycle_history: list[PreMoveLifecycleEvent] = Field(default_factory=list)
    validated: bool = False


class PreMoveScanStats(BaseModel):
    scanned: int = 0
    early_candidates: int = 0
    pre_breakout: int = 0
    early_entry: int = 0
    high_conviction: int = 0
    too_late: int = 0
    rejected_liquidity: int = 0
    rejected_safety: int = 0
    rejected_validation: int = 0
    insufficient_data: int = 0
    deep_analyzed: int = 0
    scan_duration_ms: float = 0.0
    deep_duration_ms: float = 0.0


class PreMoveScanResult(BaseModel):
    signals: list[PreMoveSignal] = Field(default_factory=list)
    rejected: list[PreMoveSignal] = Field(default_factory=list)
    stats: PreMoveScanStats = Field(default_factory=PreMoveScanStats)
    message: str = ""


class PreMoveKPIs(BaseModel):
    total_predictions: int = 0
    valid_breakouts: int = 0
    false_positives: int = 0
    tp1_hit_rate: float = 0.0
    tp2_hit_rate: float = 0.0
    stop_rate: float = 0.0
    avg_return_after_signal: float = 0.0
    median_return: float = 0.0
    avg_time_to_trigger_min: float = 0.0
    avg_time_to_tp1_min: float = 0.0
    avg_early_detection_lead_min: float = 0.0
    late_detection_rate: float = 0.0
    percent_move_before_detection: float | None = None
    move_captured_before_detection: float | None = None
