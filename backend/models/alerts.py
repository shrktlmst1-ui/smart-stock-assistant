from typing import Literal

from pydantic import BaseModel, Field


AlertType = Literal[
    "entry_opportunity",
    "exit_opportunity",
    "trap_warning",
    "fake_pump_warning",
    "high_liquidity_no_confirm",
    "buy_alert",
    "sell_alert",
    "info",
]

StockStatus = Literal["شراء", "انتظار", "خطر", "خروج"]


class Alert(BaseModel):
    symbol: str
    alert_type: AlertType
    title: str
    message: str
    severity: Literal["low", "medium", "high"] = "medium"
    timestamp: str


class TechnicalIndicators(BaseModel):
    rsi: float
    macd: float
    macd_signal: float
    macd_histogram: float
    ema_9: float
    ema_20: float
    ema_50: float
    ema_200: float
    sma_20: float
    vwap: float
    support: float
    resistance: float


class SignalAnalysis(BaseModel):
    liquidity_inflow: bool = False
    liquidity_outflow: bool = False
    buy_pressure: float = Field(ge=0, le=100, default=50)
    sell_pressure: float = Field(ge=0, le=100, default=50)
    large_buy_volume: bool = False
    abnormal_volume: bool = False
    volume_spike: bool = False
    true_breakout: bool = False
    false_breakout: bool = False
    market_trap: bool = False
    fake_pump: bool = False
    liquidity_trap: bool = False
    smart_money_inflow: bool = False
    smart_money_outflow: bool = False
    order_flow_bullish: bool = False
    order_flow_bearish: bool = False
    liquidity_strength: float = Field(ge=0, le=100, default=0)
    summary: str = ""
