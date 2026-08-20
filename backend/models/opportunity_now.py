"""فرصة الآن — sub-$10 momentum opportunities from scanner cache."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OpportunityNowStatus = Literal["فرصة الآن", "استعد", "مراقبة", "تجنب"]
RiskLevelAr = Literal["منخفض", "متوسط", "مرتفع"]


class OpportunityNowSignal(BaseModel):
    symbol: str
    name: str
    price: float
    change_percent: float
    score: float = Field(ge=0, le=100)
    status: OpportunityNowStatus
    appeared_at: str
    expires_at: str
    entry_zone: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_level: RiskLevelAr
    reasons_ar: list[str] = Field(default_factory=list)
    late_entry_warning: bool = False
    has_news_catalyst: bool = False
    movement_without_news: bool = False
    data_timestamp: str = ""


class OpportunityNowResponse(BaseModel):
    market_status: str
    market_open: bool = True
    scan_interval_seconds: int = 15
    message: str = ""
    signals: list[OpportunityNowSignal] = Field(default_factory=list)
    top_signal: OpportunityNowSignal | None = None
