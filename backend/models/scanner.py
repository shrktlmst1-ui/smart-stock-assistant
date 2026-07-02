"""US Market Scanner models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from models.stock import StockOpportunity, StockSnapshot

MarketStatus = Literal["PRE_MARKET", "REGULAR", "AFTER_HOURS", "CLOSED"]

ScannerBoardType = Literal[
    "most_active",
    "top_gainers",
    "top_losers",
    "highest_rvol",
    "unusual_volume",
    "opening_range_breakout",
    "momentum",
    "institutional",
]


class ScanRow(BaseModel):
    symbol: str
    name: str = ""
    price: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    relative_volume: float = 1.0
    volume_spike: bool = False
    market_cap: float = 0.0
    float_shares: float = 0.0
    spread_pct: float = 0.0
    premarket_change_pct: float = 0.0
    afterhours_change_pct: float = 0.0
    ai_score: float = Field(ge=0, le=100, default=0)
    scanner_reason: str = ""


class ScanSignalSummary(BaseModel):
    """Required fields for every ranked opportunity."""
    symbol: str
    name: str
    price: float
    change_percent: float
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_ratio: float
    confidence: float
    ai_score: float
    ai_explanation: str
    trap_risk: float
    smart_money_score: float
    liquidity_score: float
    news_risk: float
    recommendation: str
    expected_holding_time: str = ""
    all_filters_passed: bool = False
    failed_factors: list[str] = []
    rejection_reason: str = ""
    # Pattern detection flags
    bos: bool = False
    choch: bool = False
    order_block: bool = False
    fair_value_gap: bool = False
    liquidity_sweep: bool = False
    whale_order: bool = False
    fake_breakout: bool = False
    bull_trap: bool = False
    bear_trap: bool = False
    spoofing: bool = False
    absorption: bool = False
    iceberg_order: bool = False
    delta_imbalance: bool = False


class ScannerBoard(BaseModel):
    board_type: ScannerBoardType
    title: str
    rows: list[ScanRow] = []
    updated_at: str = ""


class ScannerStageCounts(BaseModel):
    """Pipeline funnel — counts only, no strategy changes."""
    market_status: MarketStatus = "CLOSED"
    symbols_scanned: int = 0
    universe_symbols: int = 0
    passed_liquidity: int = 0
    deep_analysis_completed: int = 0
    passed_all_filters: int = 0
    signal_avoid: int = 0
    signal_wait: int = 0
    signal_buy: int = 0
    signal_sell: int = 0
    filter_failures: dict[str, int] = Field(default_factory=dict)


class MarketScanState(BaseModel):
    universe_size: int = 0
    liquid_count: int = 0
    candidate_pool: int = 0
    market_status: MarketStatus = "CLOSED"
    top_opportunities: list[ScanSignalSummary] = []
    watchlist_candidates: list[ScanSignalSummary] = []
    explanation: str = ""
    no_signal_reason: str = ""
    debug: ScannerStageCounts | None = None
    snapshots: list[StockSnapshot] = []
    boards: list[ScannerBoard] = []
    last_universe_refresh: str = ""
    last_tick_ms: float = 0.0
    scan_interval_seconds: int = 15
    universe_breakdown: dict[str, int] | None = None


class OpportunitiesResponse(BaseModel):
    market_status: MarketStatus
    opportunities: list[StockOpportunity] = []
    watchlist_candidates: list[StockOpportunity] = []
    explanation: str = ""
    no_signal_reason: str = ""
    debug: ScannerStageCounts | None = None
