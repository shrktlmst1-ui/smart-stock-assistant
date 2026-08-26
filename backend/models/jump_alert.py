"""Persistent Jump Alert models — independent of scan snapshot."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JumpAlertStatus = Literal["ACTIVE", "EXPIRED"]


class JumpAlert(BaseModel):
    alert_id: str
    symbol: str
    name: str = ""
    created_at: str
    expires_at: str
    price: float = 0.0
    change_percent: float = 0.0
    stage: str = ""
    score: int = Field(ge=0, le=100, default=0)
    ai_signal: str = ""
    status: JumpAlertStatus = "ACTIVE"
    status_reason_ar: str = ""
    removal_reason: str = ""


class JumpAlertStatusLog(BaseModel):
    symbol: str
    alert_id: str
    still_stored: bool = False
    still_returned_by_api: bool = False
    displayed_by_ui: bool = False
    removal_reason: str = ""
