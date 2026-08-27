"""Stage Progression Engine — rolling per-symbol state and metrics."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

StageLifecycle = Literal[
    "DISCOVERED",
    "EARLY_WATCH",
    "PRE_BREAKOUT",
    "EARLY_ENTRY",
    "BREAKOUT_CONFIRMED",
    "TOO_LATE_TO_CHASE",
    "FAILED_SETUP",
    "REARMED",
]


class StageSnapshot(BaseModel):
    """Causal minute-level evidence snapshot — no future data."""

    timestamp: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    pre_move_score: int = 0

    volume_acceleration_1m: float = 0.0
    volume_acceleration_3m: float = 0.0
    volume_acceleration_slope: float = 0.0
    rvol: float = 0.0
    rvol_same_time: float | None = None
    dollar_volume_growth: float = 0.0
    trade_velocity: float | None = None
    trade_velocity_growth: float | None = None

    early_activity_score: float = 0.0
    compression_score: float = 0.0
    range_compression_3m: float = 0.0
    micro_higher_lows: bool = False
    higher_lows_score: float = 0.0
    resistance_distance_pct: float = 0.0
    distance_to_breakout_pct: float = 0.0
    breakout_pressure: float = 0.0

    vwap_hold: bool = False
    vwap_reclaim: bool = False
    distance_from_vwap_pct: float = 0.0

    liquidity_score: float = 0.0
    spread_pct: float = 0.0
    price_volume_response: float = 0.0
    price_holding_score: float = 0.0

    news_catalyst_score: float = 0.0
    risk_reward: float = 0.0
    trigger_price: float = 0.0

    late_guard: bool = False
    failed_setup: bool = False


class PreMoveStageProgressionMetrics(BaseModel):
    stage_lifecycle: StageLifecycle = "DISCOVERED"
    previous_lifecycle: StageLifecycle = "DISCOVERED"
    stage_progression_score: float = 0.0
    momentum_persistence_score: float = 0.0
    persistence_minutes: int = 0
    signal_decay: float = 0.0
    progression_trend: float = 0.0
    trigger_readiness_score: float = 0.0
    move_from_base_pct: float = 0.0
    pb_persistence_windows: int = 0
    resistance_approaching: bool = False
    ee_gate_passed: bool = False
    ee_timing_gate_passed: bool = False
    ee_confidence: list[str] = Field(default_factory=list)
    ee_block_reasons: list[str] = Field(default_factory=list)
    ee_confluence_quality: float = 0.0
    ee_quality_score: float = 0.0
    ee_rejection_score: float = 0.0
    ee_volume_efficiency: float = 0.0
    ee_breakout_failure_risk: float = 0.0
    ee_entry_location: float = 0.0
    ee_spread_stability: float = 0.0
    ee_liquidity_consistency: float = 0.0
    ee_stop_distance_pct: float = 0.0
    ee_price_holding: float = 0.0
    ee_catalyst_confirmed: bool = False
    ee_quality_factors: list[str] = Field(default_factory=list)
    ee_quality_blocks: list[str] = Field(default_factory=list)
    escalation_ready: bool = False
    regression_signals: list[str] = Field(default_factory=list)
    evidence_factors: list[str] = Field(default_factory=list)
    snapshot_count: int = 0


@dataclass
class RollingStageState:
    """In-memory rolling history T-N … NOW for one symbol."""

    symbol: str
    session_date: str = ""
    current_stage: StageLifecycle = "DISCOVERED"
    peak_stage: StageLifecycle = "DISCOVERED"
    stage_entered_at: str = ""
    first_detected_at: str = ""
    first_detected_price: float = 0.0
    peak_progression_score: float = 0.0
    minutes_in_stage: float = 0.0
    base_price: float = 0.0
    pb_consecutive_windows: int = 0
    snapshots: deque = field(default_factory=lambda: deque(maxlen=8))
    last_updated: float = 0.0
    fast_watch_locked: bool = False
    fast_watch_at: str = ""
    fast_watch_price: float = 0.0
    fast_watch_display_type: str = ""
    reacceleration_count: int = 0

    def append(self, snap: StageSnapshot) -> None:
        self.snapshots.append(snap)

    def history(self, n: int | None = None) -> list[StageSnapshot]:
        items = list(self.snapshots)
        if n is not None:
            return items[-n:]
        return items

    def at_offset(self, offset: int) -> StageSnapshot | None:
        """offset 0 = NOW, 1 = T-1, etc."""
        items = list(self.snapshots)
        if offset >= len(items):
            return None
        return items[-(offset + 1)]
