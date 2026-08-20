"""Smart Opportunity models — الفرص الذكية."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from models.scanner import MarketStatus

EntryStateType = Literal["ENTER_NOW", "WAIT_PRICE", "AVOID", "EXPIRED", "STALE_DATA"]


class SmartOpportunityItem(BaseModel):
    symbol: str
    name: str
    price: float
    change_percent: float
    rvol: float
    spread_pct: float
    ai_score: float
    market_status: MarketStatus
    last_updated: str
    volume: int = 0
    entry_state: EntryStateType
    entry_label_ar: str
    entry_color: str
    entry_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    risk_reward_ratio: float = 0.0
    signal_created_at: str = ""
    signal_expires_at: str = ""
    data_fresh: bool = True
    data_age_seconds: float = 0.0
    direction: str = "long"
    # Pattern flags for display
    bos: bool = False
    choch: bool = False
    order_block: bool = False
    fair_value_gap: bool = False
    liquidity_sweep: bool = False
    # Optional Market Pulse enrichment (Phase 1)
    pulse_score: float | None = None
    pulse_decision: str | None = None
    pulse_headline: str | None = None
    pulse_is_live: bool | None = None
    pulse_catalyst: str | None = None


class SmartOpportunitiesResponse(BaseModel):
    market_status: MarketStatus
    explanation: str = ""
    opportunities: list[SmartOpportunityItem] = Field(default_factory=list)
    scanned_count: int = 0
    filtered_count: int = 0
    last_scan_ms: float = 0.0
    no_signal_reason: str = ""


class RiskCalculateRequest(BaseModel):
    capital: float = Field(gt=0, description="رأس المال")
    risk_pct: float = Field(gt=0, le=100, description="نسبة المخاطرة %")
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    direction: Literal["long", "short"] = "long"


class RiskCalculateResponse(BaseModel):
    capital: float
    risk_pct: float
    risk_amount: float
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    loss_per_share: float
    shares: int
    position_value: float
    expected_profit_tp1: float
    expected_profit_tp2: float
    capped_by_capital: bool
    valid: bool
    error: str = ""
