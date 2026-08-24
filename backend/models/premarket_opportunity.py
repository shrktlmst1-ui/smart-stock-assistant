"""Real-time premarket opportunity scanner models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PremarketTriggerType = Literal["LONG_BREAKOUT", "LONG_PULLBACK", "EARLY_MOMENTUM", ""]
PremarketStatus = Literal["CONFIRMED_ENTRY", "EARLY_MOMENTUM", "WATCH", "NONE"]
ExclusionReason = Literal[
    "LOW_VOLUME",
    "NO_BREAKOUT",
    "BELOW_VWAP",
    "HIGH_SPREAD",
    "NO_VOLUME_ACCELERATION",
    "PRICE_OUT_OF_RANGE",
    "STALE_DATA",
]


class PremarketOpportunitySignal(BaseModel):
    symbol: str
    current_price: float = 0.0
    premarket_change_percent: float = 0.0
    premarket_volume: int = 0
    trigger_type: PremarketTriggerType = ""
    status: PremarketStatus = "NONE"
    entry: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    risk_reward: float = 0.0
    vwap: float = 0.0
    premarket_high: float = 0.0
    premarket_low: float = 0.0
    spread_percent: float = 0.0
    volume_acceleration: float = 0.0
    volume_1m: int = 0
    volume_5m: int = 0
    relative_volume: float = 0.0
    distance_from_premarket_high_pct: float = 0.0
    distance_to_premarket_high: float = 0.0
    momentum_acceleration: float = 0.0
    early_entry_zone: float = 0.0
    invalidation_level: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    reason: str = ""


class PremarketScanResult(BaseModel):
    status: PremarketStatus = "NONE"
    message: str = "لا توجد فرصة فعلية الآن"
    scanned: int = 0
    filtered: int = 0
    opportunities: list[PremarketOpportunitySignal] = Field(default_factory=list)
    watches: list[PremarketOpportunitySignal] = Field(default_factory=list)
    top_opportunity: PremarketOpportunitySignal | None = None
    top_early: PremarketOpportunitySignal | None = None
    top_watch: PremarketOpportunitySignal | None = None
