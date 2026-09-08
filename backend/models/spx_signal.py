"""SPX-only options decision models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SPXDecision = Literal["CALL", "PUT", "NO TRADE"]


class SPXLevels(BaseModel):
    previous_day_high: float | None = None
    previous_day_low: float | None = None
    previous_week_high: float | None = None
    previous_week_low: float | None = None
    overnight_high: float | None = None
    overnight_low: float | None = None
    opening_range_high: float | None = None
    opening_range_low: float | None = None
    swing_high: float | None = None
    swing_low: float | None = None
    vwap: float | None = None
    support_zone: tuple[float, float] | None = None
    resistance_zone: tuple[float, float] | None = None


class SPXOptionCandidate(BaseModel):
    ticker: str | None = None
    contract_type: Literal["call", "put"] | None = None
    expiration_date: str | None = None
    strike: float | None = None
    bid: float | None = None
    ask: float | None = None
    midpoint: float | None = None
    spread_pct: float | None = None
    delta: float | None = None
    iv: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    liquid: bool = False


class SPXSignal(BaseModel):
    symbol: str = "I:SPX"
    decision: SPXDecision = "NO TRADE"
    score: int = Field(default=0, ge=0, le=100)
    regime: Literal["TREND_UP", "TREND_DOWN", "RANGE", "UNKNOWN"] = "UNKNOWN"
    confidence: str = "LOW"
    reason: str
    entry: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    levels: SPXLevels = Field(default_factory=SPXLevels)
    option: SPXOptionCandidate | None = None
    factors: list[str] = Field(default_factory=list)
    rejected_factors: list[str] = Field(default_factory=list)
    data_fresh: bool = False
    options_ready: bool = False
    kill_switch: bool = False
    cycle_id: str
    timestamp: datetime


class SPXHealth(BaseModel):
    symbol: str = "I:SPX"
    running: bool
    last_cycle: datetime | None = None
    last_decision: SPXDecision = "NO TRADE"
    last_score: int = 0
    stale: bool = True
    kill_switch: bool = False
    cycles: int = 0
