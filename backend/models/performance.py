"""Performance and backtest API models."""

from pydantic import BaseModel, Field


class BacktestMetrics(BaseModel):
    symbol: str
    timeframe: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    avg_risk_reward: float = 0.0
    total_return_pct: float = 0.0
    trade_count: int = 0


class PerformanceMetrics(BaseModel):
    win_rate: float = 0.0
    total_trades: int = 0
    open_trades: int = 0
    today_trades: int = 0
    weekly_trades: int = 0
    monthly_trades: int = 0
    total_profit_pct: float = 0.0
    total_loss_pct: float = 0.0
    net_profit_pct: float = 0.0
    average_confidence: float = 0.0
    best_performing_strategy: str = "production_confluence"
    wins: int = 0
    losses: int = 0


class JournalEntry(BaseModel):
    id: int
    symbol: str
    signal: str
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    confidence: float
    ai_score: float
    market_regime: str
    risk_reward_ratio: float
    reason: str | None = None
    result: str = "open"
    profit_pct: float = 0.0
    created_at: str
    closed_at: str | None = None
    strategy: str = "production_confluence"


class ProductionStatus(BaseModel):
    backtesting: bool = False
    trading_journal: bool = False
    dashboard_metrics: bool = False
    live_market_data: bool = False
    ai_learning: bool = False
    decision_engine: bool = False
    polygon_connected: bool = False
    websocket_live: bool = False
    no_placeholders: bool = True
    production_ready: bool = False
    details: dict = Field(default_factory=dict)
