"""Extended-hours news-gap detection models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ExtendedSession = Literal["PRE_MARKET", "AFTER_HOURS"]
DetectionStage = Literal["WATCH", "ACTIVE", "EXPLOSIVE"]
CatalystType = Literal[
    "EARNINGS",
    "CONTRACT",
    "FDA",
    "MERGER",
    "NASDAQ_COMPLIANCE",
    "DELISTING",
    "OFFERING_DILUTION",
    "REVERSE_SPLIT",
    "OTHER",
    "NO_CONFIRMED_NEWS",
]


class ExtendedGapFields(BaseModel):
    """Optional extended-hours fields merged into opportunity-now signals."""

    session: str = ""
    previous_close: float = 0.0
    extended_price: float = 0.0
    extended_gap_pct: float = 0.0
    extended_volume: int = 0
    relative_volume: float = 0.0
    catalyst_type: str = ""
    catalyst_title_ar: str = ""
    catalyst_source: str = ""
    catalyst_published_at: str = ""
    detection_stage: str = ""
    risk_flags_ar: list[str] = Field(default_factory=list)
    detected_at: str = ""
    has_confirmed_news: bool = False
