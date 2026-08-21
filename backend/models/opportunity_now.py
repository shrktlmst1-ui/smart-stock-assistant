"""فرصة الآن — live confirmation engine response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OpportunityStatusCode = Literal["NONE", "WATCH", "READY", "NOW", "CANCELLED"]
OpportunityNowStatusAr = Literal["فرصة الآن", "استعد", "مراقبة", "تجنب", "أُلغيت"]
RiskLevelAr = Literal["منخفض", "متوسط", "مرتفع"]


class OpportunityNowSignal(BaseModel):
    symbol: str = ""
    name: str = ""
    price: float = 0.0
    change_percent: float = 0.0
    score: float = Field(default=0.0, ge=0, le=100)
    status: OpportunityStatusCode = "NONE"
    status_ar: str = ""
    opportunity_type: str = ""
    appeared_at: str = ""
    expires_at: str = ""
    entry_zone: float = 0.0
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    risk_level: RiskLevelAr = "مرتفع"
    risk_reward_ratio: float = 0.0
    confirmed_factors: int = 0
    total_factors: int = 17
    consecutive_confirmations: int = 0
    reasons_ar: list[str] = Field(default_factory=list)
    cancellation_reasons_ar: list[str] = Field(default_factory=list)
    late_entry_warning: bool = False
    has_news_catalyst: bool = False
    movement_without_news: bool = False
    data_timestamp: str = ""
    data_age_seconds: float = 0.0


class OpportunityNowResponse(BaseModel):
    status: OpportunityStatusCode = "NONE"
    status_ar: str = "لا توجد فرصة مكتملة الآن"
    market_status: str = "CLOSED"
    market_open: bool = True
    scan_interval_seconds: int = 15
    message: str = "لا توجد فرصة مكتملة الآن"
    live_source: str = "rest"
    ws_connected: bool = False
    monitor_pool_size: int = 0
    signals: list[OpportunityNowSignal] = Field(default_factory=list)
    top_signal: OpportunityNowSignal | None = None
