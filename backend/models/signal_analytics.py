"""Pydantic models for Professional Signal Analytics."""

from pydantic import BaseModel, Field


class SignalExplanationItem(BaseModel):
    label: str
    passed: bool


class SignalAnalyticsRecord(BaseModel):
    id: int
    symbol: str
    signal: str
    signal_date: str
    signal_time: str
    timeframe: str = "live"
    ai_score: float
    confidence_score: float
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    trend_direction: str
    market_status: str
    sector: str = ""
    industry: str = ""
    track_status: str = "Waiting"
    trade_quality_stars: int = Field(ge=1, le=5, default=1)
    trade_quality_label: str = "Weak"
    explanation: list[SignalExplanationItem] = []
    trend_strength: float = 0.0
    relative_volume: float = 0.0
    failure_reason: str | None = None
    profit_pct: float = 0.0
    exit_price: float | None = None
    created_at: str
    closed_at: str | None = None
    holding_seconds: int = 0
    rank_score: float = 0.0


class AnalyticsDashboard(BaseModel):
    total_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    win_rate_pct: float = 0.0
    average_profit_pct: float = 0.0
    average_loss_pct: float = 0.0
    average_holding_time_hours: float = 0.0
    best_performing_sector: str = ""
    best_performing_timeframe: str = ""
    highest_ai_score_today: float = 0.0
    highest_confidence_today: float = 0.0
    open_tracks: int = 0
    active_tracks: int = 0


class PerformanceReport(BaseModel):
    today_signals: int = 0
    week_signals: int = 0
    month_signals: int = 0
    overall_total: int = 0
    win_rate: float = 0.0
    average_return_pct: float = 0.0
    average_drawdown_pct: float = 0.0
    best_symbol: str = ""
    worst_symbol: str = ""
    wins: int = 0
    losses: int = 0
    dashboard: AnalyticsDashboard


class RankedSignalsResponse(BaseModel):
    signals: list[SignalAnalyticsRecord] = []
    dashboard: AnalyticsDashboard
