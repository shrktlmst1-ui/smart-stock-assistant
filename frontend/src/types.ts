export type DecisionState =
  | "NO TRADE"
  | "WAIT"
  | "WATCH"
  | "POSSIBLE ENTRY"
  | "ENTRY CONFIRMED"
  | "AVOID / TRAP RISK"
  | "BUY"
  | "SELL"
  | "AVOID";

export type ProfessionalSignalType = "BUY" | "SELL" | "WAIT" | "AVOID";

export interface EngineLogRecord {
  engine: string;
  inputs: Record<string, unknown>;
  calculation: string;
  result: string;
  reason: string;
}

export interface TradeDecision {
  recommendation: DecisionState;
  professional_signal?: ProfessionalSignalType;
  direction: "long" | "short" | "neutral";
  symbol: string;
  current_price: number;
  entry_zone_low: number;
  entry_zone_high: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  risk_reward_ratio: number;
  ai_confidence: number;
  professional_ai_score?: number;
  factor_scores?: Record<string, number>;
  all_filters_passed?: boolean;
  expected_holding_time?: string;
  ai_explanation?: string;
  liquidity_inflow: number;
  liquidity_outflow: number;
  trap_risk: number;
  news_risk: number;
  market_structure: string;
  trigger_reason: string;
  devils_advocate: string;
  engine_logs: EngineLogRecord[];
}

export interface VolumeLiquidityAnalysis {
  relative_volume: number;
  volume_spike: boolean;
  cumulative_delta: number;
  delta_direction: string;
  vwap: number;
  price_vs_vwap: string;
  premarket_volume: number;
  premarket_rvol: number;
  gap_percent: number;
  gap_type: string;
  liquidity_inflow: number;
  liquidity_outflow: number;
  buyer_pressure: number;
  seller_pressure: number;
  summary: string;
}

export interface NewsRiskAnalysis {
  risk_level: "low" | "medium" | "high";
  risk_score: number;
  block_trade: boolean;
  matched_events: string[];
  summary: string;
}

export type StockStatus = "شراء" | "انتظار" | "خطر" | "خروج";
export type AISignalType = "Strong Buy" | "Buy" | "Wait" | "Sell" | "Strong Sell";
export type RiskLevel = "low" | "medium" | "high";

export type AlertType =
  | "entry_opportunity"
  | "exit_opportunity"
  | "trap_warning"
  | "fake_pump_warning"
  | "high_liquidity_no_confirm"
  | "buy_alert"
  | "sell_alert"
  | "info";

export interface Alert {
  symbol: string;
  alert_type: AlertType;
  title: string;
  message: string;
  severity: "low" | "medium" | "high";
  timestamp: string;
}

export interface TechnicalIndicators {
  rsi: number;
  macd: number;
  macd_signal: number;
  macd_histogram: number;
  ema_9: number;
  ema_20: number;
  ema_50: number;
  ema_200: number;
  sma_20: number;
  vwap: number;
  support: number;
  resistance: number;
}

export interface SignalAnalysis {
  liquidity_inflow: boolean;
  liquidity_outflow: boolean;
  buy_pressure: number;
  sell_pressure: number;
  large_buy_volume: boolean;
  abnormal_volume: boolean;
  volume_spike: boolean;
  true_breakout: boolean;
  false_breakout: boolean;
  market_trap: boolean;
  fake_pump: boolean;
  liquidity_trap: boolean;
  smart_money_inflow: boolean;
  smart_money_outflow: boolean;
  order_flow_bullish: boolean;
  order_flow_bearish: boolean;
  liquidity_strength: number;
  summary: string;
}

export interface AISignal {
  signal: AISignalType;
  confidence: number;
  ai_score: number;
  reason: string;
  risk_level: RiskLevel;
  entry: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  risk_reward_ratio: number;
  confidence_breakdown?: ConfidenceBreakdown;
}

export interface ConfidenceBreakdown {
  trend: number;
  volume: number;
  smc: number;
  liquidity: number;
  volatility: number;
  news: number;
  overall: number;
}

export interface SmartMoneyTracker {
  whale_order: boolean;
  hidden_accumulation: boolean;
  hidden_distribution: boolean;
  absorption: boolean;
  iceberg_activity: boolean;
  activity_score: number;
  flow_direction: string;
  summary: string;
}

export interface LiquidityTrapAnalysis {
  bull_trap: boolean;
  bear_trap: boolean;
  fake_breakout: boolean;
  fake_breakdown?: boolean;
  stop_hunt: boolean;
  liquidity_grab: boolean;
  pump_and_dump?: boolean;
  fake_momentum?: boolean;
  trap_direction: string;
  severity: number;
  summary: string;
}

export type MarketRegimeType = "Strong Bullish" | "Bullish" | "Neutral" | "Bearish" | "Strong Bearish";

export interface MarketRegime {
  regime: MarketRegimeType;
  score: number;
  volatility_regime: string;
  trend_quality: number;
  summary: string;
}

export interface RiskAssessment {
  position_size_shares: number;
  position_size_dollars: number;
  risk_percent: number;
  reward_percent: number;
  atr_stop: number;
  take_profit_1: number;
  take_profit_2: number;
  dynamic_take_profit: number;
  risk_reward_ratio: number;
  max_loss_dollars: number;
  summary: string;
}

export interface TrendAnalysis {
  ema_20: number;
  ema_50: number;
  ema_200: number;
  vwap: number;
  atr: number;
  direction: "bullish" | "bearish" | "neutral";
  trend_strength: number;
  price_above_vwap: boolean;
  ema_stack_bullish: boolean;
  ema_stack_bearish: boolean;
  summary: string;
}

export interface OrderBlock {
  type: "bullish" | "bearish";
  high: number;
  low: number;
  strength: number;
}

export interface FairValueGap {
  type: "bullish" | "bearish";
  top: number;
  bottom: number;
  filled: boolean;
}

export interface DashboardMeters {
  smart_money_meter: number;
  liquidity_meter: number;
  trend_strength: number;
  market_risk: number;
  institutional_activity: number;
  ai_confidence: number;
  fear_greed?: number;
}

export interface SMCAnalysis {
  bos: boolean;
  bos_direction: string;
  choch: boolean;
  choch_direction: string;
  mss?: boolean;
  mss_direction?: string;
  order_blocks: OrderBlock[];
  fair_value_gaps: FairValueGap[];
  breaker_blocks?: OrderBlock[];
  mitigation_blocks?: OrderBlock[];
  liquidity_sweep: boolean;
  sweep_direction: string;
  summary: string;
}

export interface LiquidityEngine {
  buy_side_liquidity: number;
  sell_side_liquidity: number;
  liquidity_grab: boolean;
  liquidity_trap: boolean;
  grab_direction: string;
  summary: string;
}

export interface VolumeEngine {
  volume_spike: boolean;
  relative_volume: number;
  unusual_volume: boolean;
  volume_divergence: boolean;
  divergence_direction: string;
  session_rvol: number;
  volume_zscore: number;
  dark_pool_estimate: number;
  summary: string;
}

export interface InstitutionalDetection {
  large_order_detected: boolean;
  whale_activity: boolean;
  smart_money_score: number;
  summary: string;
}

export interface NewsSentiment {
  headline: string;
  sentiment: string;
  score: number;
  price_correlation: string;
  confidence_impact: number;
}

export interface NewsIntelligence {
  items: NewsSentiment[];
  overall_sentiment: string;
  confidence_adjustment: number;
  source: string;
}

export interface NewsItem {
  id: string;
  title: string;
  source: string;
  published_at: string;
  url: string;
  symbols: string[];
}

export interface StockSnapshot {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  liquidity_strength: number;
  status: StockStatus;
  indicators: TechnicalIndicators;
  signals: SignalAnalysis;
  alerts: Alert[];
  news: NewsItem[];
  last_updated: string;
  ai_signal: AISignal;
  meters: DashboardMeters;
  smc: SMCAnalysis;
  liquidity_engine: LiquidityEngine;
  volume_engine: VolumeEngine;
  trend_analysis: TrendAnalysis;
  news_intelligence: NewsIntelligence;
  smart_money: SmartMoneyTracker;
  liquidity_traps: LiquidityTrapAnalysis;
  market_regime: MarketRegime;
  risk_assessment: RiskAssessment;
  confidence_breakdown: ConfidenceBreakdown;
  trade_decision: TradeDecision;
  volume_liquidity: VolumeLiquidityAnalysis;
  news_risk: NewsRiskAnalysis;
}

export interface ConnectionStatus {
  api_connected: boolean;
  authentication_status: string;
  subscription_status: string;
  live_market_data_status: string;
  data_mode: string;
  stream_mode?: string;
  plan: string;
  websocket_enabled: boolean;
  websocket_available: boolean;
  symbols_tested: string[];
  symbols_ok: string[];
  symbols_failed: string[];
  errors: string[];
  last_check: string;
}

export interface NotificationPayload {
  symbol: string;
  signal: AISignalType;
  confidence: number;
  reason: string;
  risk_level: RiskLevel;
  entry: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  price: number;
  sound: boolean;
  desktop: boolean;
}

export interface PerformanceMetrics {
  win_rate: number;
  total_trades: number;
  open_trades: number;
  today_trades: number;
  weekly_trades: number;
  monthly_trades: number;
  total_profit_pct: number;
  total_loss_pct: number;
  net_profit_pct: number;
  average_confidence: number;
  best_performing_strategy: string;
  wins: number;
  losses: number;
}

export interface ProductionStatus {
  backtesting: boolean;
  trading_journal: boolean;
  dashboard_metrics: boolean;
  live_market_data: boolean;
  ai_learning: boolean;
  decision_engine?: boolean;
  polygon_connected?: boolean;
  websocket_live?: boolean;
  no_placeholders: boolean;
  production_ready: boolean;
  details: Record<string, unknown>;
}

export interface WsMessage {
  type: "snapshot" | "alert" | "news" | "heartbeat" | "status" | "notification" | "scan_update";
  data: StockSnapshot | ConnectionStatus | NotificationPayload | MarketScanState | Record<string, unknown>;
  timestamp: string;
}

export interface ScanRow {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  volume: number;
  relative_volume: number;
  volume_spike: boolean;
  ai_score: number;
  scanner_reason: string;
}

export interface ScanSignalSummary {
  symbol: string;
  name: string;
  price: number;
  change_percent: number;
  entry: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  risk_reward_ratio: number;
  confidence: number;
  ai_score: number;
  ai_explanation: string;
  trap_risk: number;
  smart_money_score: number;
  liquidity_score: number;
  news_risk: number;
  recommendation: string;
  expected_holding_time?: string;
  all_filters_passed?: boolean;
  bos?: boolean;
  choch?: boolean;
  whale_order?: boolean;
  spoofing?: boolean;
  delta_imbalance?: boolean;
}

export interface ScannerBoard {
  board_type: string;
  title: string;
  rows: ScanRow[];
  updated_at: string;
}

export interface MarketScanState {
  universe_size: number;
  liquid_count: number;
  candidate_pool: number;
  top_opportunities: ScanSignalSummary[];
  snapshots?: StockSnapshot[];
  boards: ScannerBoard[];
  last_universe_refresh: string;
  last_tick_ms: number;
  scan_interval_seconds?: number;
  universe_breakdown?: Record<string, number>;
}
