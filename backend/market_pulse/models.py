"""Pydantic models for Market Pulse API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PulseDecision = Literal["ENTER_NOW", "WAIT", "AVOID", "EXPIRED"]


class CatalystInfo(BaseModel):
    headline: str = ""
    sentiment: Literal["positive", "negative", "neutral"] = "neutral"
    trigger_type: str = ""
    news_age_seconds: float = 0.0
    symbols: list[str] = Field(default_factory=list)
    provider_id: str = ""


class MarketPulseAlert(BaseModel):
    symbol: str
    score: float = Field(ge=0, le=100)
    decision: PulseDecision
    catalyst: CatalystInfo
    headline: str = ""
    news_age_seconds: float = 0.0
    estimated_buy_pressure: float = Field(ge=0, le=100, default=0.0)
    rvol: float = 0.0
    dollar_volume_acceleration: float = 0.0
    spread_bps: float = 0.0
    price: float = 0.0
    vwap: float = 0.0
    entry: float = 0.0
    stop_loss: float = 0.0
    targets: list[float] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    data_timestamp: str = ""
    is_live: bool = False
    expires_at: str = ""
    reasons_ar: list[str] = Field(default_factory=list)
    catalyst_score: float = 0.0
    liquidity_score: float = 0.0
    price_confirmation_score: float = 0.0
    risk_penalty: float = 0.0
    is_halted: bool = False


class MarketPulseListResponse(BaseModel):
    enabled: bool = False
    alerts: list[MarketPulseAlert] = Field(default_factory=list)
    count: int = 0


class MarketPulseHealth(BaseModel):
    enabled: bool = False
    status: Literal["ok", "disabled", "missing_credentials", "degraded", "idle"] = "disabled"
    has_api_key: bool = False
    subscribed_symbols: int = 0
    max_symbols: int = 50
    stream_connected: bool = False
    last_news_fetch: str | None = None
    message: str = ""
