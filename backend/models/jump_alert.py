"""Persistent Jump Alert models — independent of scan snapshot."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JumpAlertStatus = Literal["ACTIVE", "EXPIRED"]

QUALIFIED_JUMP_SIGNALS = frozenset({"EARLY_ENTRY", "HIGH_CONVICTION_EARLY"})


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
    jump_qualified: bool = False
    jump_alert_created: bool = False
    jump_type: str = ""
    entry_low: float = 0.0
    entry_high: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    rvol: float = 0.0
    volume_acceleration: float = 0.0
    trigger_price: float = 0.0
    timing: str = "NORMAL"
    persistence_minutes: int = 0
    risk_reward: float = 0.0
    is_too_late: bool = False


class JumpAlertStatusLog(BaseModel):
    symbol: str
    alert_id: str
    still_stored: bool = False
    still_returned_by_api: bool = False
    displayed_by_ui: bool = False
    removal_reason: str = ""
