from typing import Literal

from pydantic import BaseModel, Field

from models.alerts import Alert, SignalAnalysis, StockStatus, TechnicalIndicators
from models.trading import (
    AISignal,
    ConfidenceBreakdown,
    DashboardMeters,
    LiquidityEngine,
    LiquidityTrapAnalysis,
    MarketRegime,
    NewsIntelligence,
    NewsRiskAnalysis,
    RiskAssessment,
    SMCAnalysis,
    SmartMoneyTracker,
    TradeDecision,
    TrendAnalysis,
    VolumeEngine,
    VolumeLiquidityAnalysis,
)


class NewsItem(BaseModel):
    id: str
    title: str
    source: str
    published_at: str
    url: str = ""
    symbols: list[str] = []


class StockSnapshot(BaseModel):
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    volume: int
    liquidity_strength: float = Field(ge=0, le=100)
    status: StockStatus
    indicators: TechnicalIndicators
    signals: SignalAnalysis
    alerts: list[Alert] = []
    news: list[NewsItem] = []
    last_updated: str
    # AI Trading Assistant modules
    ai_signal: AISignal
    meters: DashboardMeters
    smc: SMCAnalysis
    liquidity_engine: LiquidityEngine
    volume_engine: VolumeEngine
    trend_analysis: TrendAnalysis
    news_intelligence: NewsIntelligence
    smart_money: SmartMoneyTracker
    liquidity_traps: LiquidityTrapAnalysis
    market_regime: MarketRegime
    risk_assessment: RiskAssessment
    confidence_breakdown: ConfidenceBreakdown
    trade_decision: TradeDecision
    volume_liquidity: VolumeLiquidityAnalysis
    news_risk: NewsRiskAnalysis


class StockOpportunity(BaseModel):
    symbol: str
    name: str
    price: float
    change_percent: float
    score: int = Field(ge=0, le=100)
    trend: Literal["صاعد", "هابط", "محايد"]
    risk_level: Literal["منخفض", "متوسط", "مرتفع"]
    status: StockStatus = "انتظار"
    ai_signal: str = "Wait"
    confidence: float = 50.0


class StockAnalysis(BaseModel):
    symbol: str
    name: str
    price: float
    change_percent: float
    trend: Literal["صاعد", "هابط", "محايد"]
    rsi: float
    macd: float
    macd_signal: float
    ema_20: float
    ema_50: float
    ema_200: float
    volume: int
    support: float
    resistance: float
    score: int = Field(ge=0, le=100)
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_level: Literal["منخفض", "متوسط", "مرتفع"]
    recommendation_reason: str
    status: StockStatus = "انتظار"
    signals: SignalAnalysis | None = None
    alerts: list[Alert] = []
    news: list[NewsItem] = []
    ai_signal: AISignal | None = None
    meters: DashboardMeters | None = None
    smc: SMCAnalysis | None = None
    liquidity_engine: LiquidityEngine | None = None
    volume_engine: VolumeEngine | None = None
    trend_analysis: TrendAnalysis | None = None
    news_intelligence: NewsIntelligence | None = None
    smart_money: SmartMoneyTracker | None = None
    liquidity_traps: LiquidityTrapAnalysis | None = None
    market_regime: MarketRegime | None = None
    risk_assessment: RiskAssessment | None = None
    confidence_breakdown: ConfidenceBreakdown | None = None
    trade_decision: TradeDecision | None = None
    volume_liquidity: VolumeLiquidityAnalysis | None = None
    news_risk: NewsRiskAnalysis | None = None


class SearchResult(BaseModel):
    symbol: str
    name: str
    price: float
    change_percent: float


class DashboardUpdate(BaseModel):
    type: Literal["snapshot", "alert", "news", "heartbeat", "status", "notification"]
    data: dict
    timestamp: str
