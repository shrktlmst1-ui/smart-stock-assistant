"""Professional AI trading models — SMC, engines, signals, meters."""

from typing import Literal

from pydantic import BaseModel, Field

AISignalType = Literal["Strong Buy", "Buy", "Wait", "Sell", "Strong Sell"]
RiskLevel = Literal["low", "medium", "high"]
TrendDirection = Literal["bullish", "bearish", "neutral"]
MarketRegimeType = Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"]
FlowDirection = Literal["bullish", "bearish", "neutral"]
TrapDirection = Literal["bullish", "bearish", "none"]
VolatilityRegime = Literal["low", "normal", "high"]


class OrderBlock(BaseModel):
    type: Literal["bullish", "bearish"]
    high: float
    low: float
    strength: float = Field(ge=0, le=100)


class FairValueGap(BaseModel):
    type: Literal["bullish", "bearish"]
    top: float
    bottom: float
    filled: bool = False


class SMCAnalysis(BaseModel):
    bos: bool = False
    bos_direction: Literal["bullish", "bearish", "none"] = "none"
    choch: bool = False
    choch_direction: Literal["bullish", "bearish", "none"] = "none"
    mss: bool = False
    mss_direction: Literal["bullish", "bearish", "none"] = "none"
    order_blocks: list[OrderBlock] = []
    fair_value_gaps: list[FairValueGap] = []
    breaker_blocks: list[OrderBlock] = []
    mitigation_blocks: list[OrderBlock] = []
    liquidity_sweep: bool = False
    sweep_direction: Literal["bullish", "bearish", "none"] = "none"
    summary: str = ""


class TrendAnalysis(BaseModel):
    ema_20: float
    ema_50: float
    ema_200: float
    vwap: float
    atr: float
    direction: TrendDirection = "neutral"
    trend_strength: float = Field(ge=0, le=100)
    price_above_vwap: bool = False
    ema_stack_bullish: bool = False
    ema_stack_bearish: bool = False
    summary: str = ""


class LiquidityEngine(BaseModel):
    buy_side_liquidity: float = Field(ge=0, le=100, default=50)
    sell_side_liquidity: float = Field(ge=0, le=100, default=50)
    liquidity_grab: bool = False
    liquidity_trap: bool = False
    grab_direction: Literal["bullish", "bearish", "none"] = "none"
    summary: str = ""


class VolumeEngine(BaseModel):
    volume_spike: bool = False
    relative_volume: float = 1.0
    unusual_volume: bool = False
    volume_divergence: bool = False
    divergence_direction: Literal["bullish", "bearish", "none"] = "none"
    session_rvol: float = 1.0
    volume_zscore: float = 0.0
    dark_pool_estimate: float = Field(ge=0, le=100, default=0)
    summary: str = ""


class SmartMoneyTracker(BaseModel):
    whale_order: bool = False
    hidden_accumulation: bool = False
    hidden_distribution: bool = False
    absorption: bool = False
    iceberg_activity: bool = False
    activity_score: float = Field(ge=0, le=100, default=50)
    flow_direction: FlowDirection = "neutral"
    summary: str = ""


class LiquidityTrapAnalysis(BaseModel):
    bull_trap: bool = False
    bear_trap: bool = False
    fake_breakout: bool = False
    fake_breakdown: bool = False
    stop_hunt: bool = False
    liquidity_grab: bool = False
    pump_and_dump: bool = False
    fake_momentum: bool = False
    spoofing: bool = False
    delta_imbalance: bool = False
    trap_direction: TrapDirection = "none"
    severity: float = Field(ge=0, le=100, default=0)
    summary: str = ""


class MarketRegime(BaseModel):
    regime: MarketRegimeType = "Neutral"
    score: float = Field(ge=0, le=100, default=50)
    volatility_regime: VolatilityRegime = "normal"
    trend_quality: float = Field(ge=0, le=100, default=50)
    summary: str = ""


class ConfidenceBreakdown(BaseModel):
    trend: float = Field(ge=0, le=100, default=50)
    volume: float = Field(ge=0, le=100, default=50)
    smc: float = Field(ge=0, le=100, default=50)
    liquidity: float = Field(ge=0, le=100, default=50)
    volatility: float = Field(ge=0, le=100, default=50)
    news: float = Field(ge=0, le=100, default=50)
    overall: float = Field(ge=0, le=100, default=50)


class RiskAssessment(BaseModel):
    position_size_shares: int = 0
    position_size_dollars: float = 0.0
    risk_percent: float = 0.0
    reward_percent: float = 0.0
    atr_stop: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    dynamic_take_profit: float = 0.0
    risk_reward_ratio: float = 0.0
    max_loss_dollars: float = 0.0
    summary: str = ""


class NewsSentiment(BaseModel):
    headline: str
    sentiment: Literal["bullish", "bearish", "neutral"]
    score: float = Field(ge=-1, le=1, default=0)
    price_correlation: Literal["aligned", "divergent", "neutral"] = "neutral"
    confidence_impact: float = Field(ge=-20, le=20, default=0)


class NewsIntelligence(BaseModel):
    items: list[NewsSentiment] = []
    overall_sentiment: Literal["bullish", "bearish", "neutral"] = "neutral"
    confidence_adjustment: float = Field(ge=-20, le=20, default=0)
    source: str = "polygon"


class AISignal(BaseModel):
    signal: AISignalType
    confidence: float = Field(ge=0, le=100)
    ai_score: float = Field(ge=0, le=100)
    reason: str
    risk_level: RiskLevel
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward_ratio: float = 0.0
    confidence_breakdown: ConfidenceBreakdown | None = None


class VolumeLiquidityAnalysis(BaseModel):
    relative_volume: float = 1.0
    volume_spike: bool = False
    cumulative_delta: float = 0.0
    delta_direction: FlowDirection = "neutral"
    vwap: float = 0.0
    price_vs_vwap: Literal["above", "below", "at"] = "at"
    premarket_volume: int = 0
    premarket_rvol: float = 1.0
    gap_percent: float = 0.0
    gap_type: Literal["gap_up", "gap_down", "none"] = "none"
    liquidity_inflow: float = Field(ge=0, le=100, default=50)
    liquidity_outflow: float = Field(ge=0, le=100, default=50)
    buyer_pressure: float = Field(ge=0, le=100, default=50)
    seller_pressure: float = Field(ge=0, le=100, default=50)
    summary: str = ""


class InstitutionalFlowAnalysis(BaseModel):
    institutional_candle: bool = False
    accumulation: bool = False
    distribution: bool = False
    sell_absorption: bool = False
    buy_absorption: bool = False
    abnormal_volume_price: bool = False
    flow_score: float = Field(ge=0, le=100, default=50)
    flow_direction: FlowDirection = "neutral"
    summary: str = ""


class NewsRiskAnalysis(BaseModel):
    risk_level: Literal["low", "medium", "high"] = "low"
    risk_score: float = Field(ge=0, le=100, default=0)
    block_trade: bool = False
    matched_events: list[str] = []
    summary: str = ""


DecisionState = Literal[
    "NO TRADE", "WAIT", "WATCH", "POSSIBLE ENTRY", "ENTRY CONFIRMED", "AVOID / TRAP RISK",
    "BUY", "SELL", "AVOID",
]

ProfessionalSignalType = Literal["BUY", "SELL", "WAIT", "AVOID"]


class EngineLogRecord(BaseModel):
    engine: str
    inputs: dict = {}
    calculation: str = ""
    result: str = ""
    reason: str = ""


class TradeDecision(BaseModel):
    recommendation: DecisionState = "WAIT"
    professional_signal: ProfessionalSignalType = "WAIT"
    direction: Literal["long", "short", "neutral"] = "neutral"
    symbol: str = ""
    current_price: float = 0.0
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    risk_reward_ratio: float = 0.0
    ai_confidence: float = Field(ge=0, le=100, default=0)
    professional_ai_score: float = Field(ge=0, le=100, default=0)
    factor_scores: dict[str, float] = {}
    all_filters_passed: bool = False
    expected_holding_time: str = ""
    ai_explanation: str = ""
    liquidity_inflow: float = Field(ge=0, le=100, default=50)
    liquidity_outflow: float = Field(ge=0, le=100, default=50)
    trap_risk: float = Field(ge=0, le=100, default=0)
    news_risk: float = Field(ge=0, le=100, default=0)
    market_structure: str = ""
    trigger_reason: str = ""
    devils_advocate: str = ""
    engine_logs: list[EngineLogRecord] = []
    filters_passed: list[str] = []
    filters_failed: list[str] = []
    buy_blockers: list[str] = []
    final_blocker: str = ""


class DashboardMeters(BaseModel):
    smart_money_meter: float = Field(ge=0, le=100, default=50)
    liquidity_meter: float = Field(ge=0, le=100, default=50)
    trend_strength: float = Field(ge=0, le=100, default=50)
    market_risk: float = Field(ge=0, le=100, default=50)
    institutional_activity: float = Field(ge=0, le=100, default=50)
    ai_confidence: float = Field(ge=0, le=100, default=50)
    fear_greed: float = Field(ge=0, le=100, default=50)
