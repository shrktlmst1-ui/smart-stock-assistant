"""Pydantic models for Trade Replay & Post-Trade Analytics."""

from pydantic import BaseModel


class TradeTimelineEvent(BaseModel):
    event_time: str
    event_label: str
    price: float | None = None


class PostTradeAnalysis(BaseModel):
    final_result: str = ""
    max_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    highest_price_after_entry: float | None = None
    lowest_price_after_entry: float | None = None
    time_to_target_1_seconds: int | None = None
    time_to_target_2_seconds: int | None = None
    time_to_target_3_seconds: int | None = None
    time_to_stop_loss_seconds: int | None = None
    trade_duration_seconds: int = 0
    post_trade_quality: str = ""
    entry_quality_score: float = 0.0
    risk_reward_ratio: float = 0.0


class TradeReplayDetail(BaseModel):
    signal_id: int
    symbol: str
    signal: str
    signal_date: str
    signal_time: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    ai_score: float
    confidence_score: float
    timeframe: str = "live"
    track_status: str = ""
    timeline: list[TradeTimelineEvent] = []
    post_trade: PostTradeAnalysis | None = None
    live_max_profit_pct: float = 0.0
    live_max_drawdown_pct: float = 0.0
    entry_quality_score: float = 0.0
    is_closed: bool = False


class PerformanceInsights(BaseModel):
    average_time_to_target_seconds: float = 0.0
    average_drawdown_pct: float = 0.0
    average_profit_pct: float = 0.0
    best_holding_time_seconds: int = 0
    best_timeframe: str = ""
    best_entry_quality_symbol: str = ""
    worst_entry_quality_symbol: str = ""
    closed_trades: int = 0


class TradeReplayListResponse(BaseModel):
    replays: list[TradeReplayDetail] = []
    insights: PerformanceInsights
