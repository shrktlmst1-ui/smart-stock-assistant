"""AI Signal Engine — institutional-grade orchestrator with real calculations."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from analysis.confidence_engine import compute_confidence
from analysis.indicators import compute_indicators, macd
from analysis.liquidity_engine import liquidity_score
from analysis.scoring import momentum_score, news_score
from analysis.smc import smc_score
from analysis.smart_money_tracker import smart_money_score
from analysis.volume_engine import volume_score
from models.alerts import Alert, SignalAnalysis, TechnicalIndicators
from analysis.decision_engine import build_trade_decision
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


def _rate_of_change(close: pd.Series, period: int = 10) -> float:
    if len(close) < period + 1:
        return 0.0
    return float((close.iloc[-1] - close.iloc[-period - 1]) / close.iloc[-period - 1] * 100)


def _bearish_volume_confirms(vol: VolumeEngine, vol_s: float, change_pct: float) -> bool:
    if vol.relative_volume < 1.1:
        return False
    if change_pct < 0:
        return True
    if vol.volume_divergence and vol.divergence_direction == "bearish":
        return True
    return (100.0 - vol_s) >= 55


def _bullish_conditions(
    trend: TrendAnalysis,
    vol: VolumeEngine,
    liq: LiquidityEngine,
    smc: SMCAnalysis,
    smc_s: float,
    mom_s: float,
    news_s: float,
    vol_s: float,
    liq_s: float,
    smart_money: SmartMoneyTracker,
    traps: LiquidityTrapAnalysis,
) -> dict[str, bool]:
    return {
        "trend": trend.direction == "bullish" and trend.trend_strength >= 60,
        "volume": vol_s >= 55 and vol.relative_volume >= 1.1,
        "liquidity": liq_s >= 50 and not traps.bull_trap and liq.buy_side_liquidity >= liq.sell_side_liquidity,
        "smc": smc_s >= 58 and (
            (smc.bos and smc.bos_direction == "bullish")
            or (smc.choch and smc.choch_direction == "bullish")
            or (smc.liquidity_sweep and smc.sweep_direction == "bullish")
        ),
        "momentum": mom_s >= 55,
        "news": news_s >= 45,
        "smart_money": smart_money.flow_direction == "bullish" or smart_money.hidden_accumulation,
    }


def _bearish_conditions(
    trend: TrendAnalysis,
    vol: VolumeEngine,
    liq: LiquidityEngine,
    smc: SMCAnalysis,
    smc_s: float,
    mom_s: float,
    news_s: float,
    vol_s: float,
    liq_s: float,
    change_pct: float,
    news: NewsIntelligence,
    smart_money: SmartMoneyTracker,
    traps: LiquidityTrapAnalysis,
) -> dict[str, bool]:
    return {
        "trend": trend.direction == "bearish" and trend.trend_strength <= 40,
        "volume": _bearish_volume_confirms(vol, vol_s, change_pct),
        "liquidity": liq_s <= 50 and not traps.bear_trap and liq.sell_side_liquidity >= liq.buy_side_liquidity,
        "smc": smc_s <= 42 and (
            (smc.bos and smc.bos_direction == "bearish")
            or (smc.choch and smc.choch_direction == "bearish")
            or (smc.liquidity_sweep and smc.sweep_direction == "bearish")
        ),
        "momentum": mom_s <= 45,
        "news": news_s < 45 or news.overall_sentiment == "bearish",
        "smart_money": smart_money.flow_direction == "bearish" or smart_money.hidden_distribution,
    }


def _resolve_signal(bull: dict[str, bool], bear: dict[str, bool], ai_score: float) -> tuple[str, list[str]]:
    reasons: list[str] = []
    for k, v in bull.items():
        reasons.append(f"{'✓' if v else '○'} {k}")

    if all(bull.values()):
        signal = "Strong Buy" if ai_score >= 72 else "Buy"
        return signal, reasons
    if all(bear.values()):
        signal = "Strong Sell" if ai_score <= 28 else "Sell"
        return signal, reasons

    return "Wait", reasons


def _build_alerts(
    symbol: str,
    signal: str,
    confidence: float,
    traps: LiquidityTrapAnalysis,
    smart_money: SmartMoneyTracker,
    regime: MarketRegime,
) -> list[Alert]:
    now = datetime.now(timezone.utc).isoformat()
    alerts: list[Alert] = []

    if traps.bull_trap:
        alerts.append(Alert(
            symbol=symbol, alert_type="trap_warning", severity="high",
            title="Bull Trap", message=traps.summary, timestamp=now,
        ))
    if traps.bear_trap:
        alerts.append(Alert(
            symbol=symbol, alert_type="trap_warning", severity="high",
            title="Bear Trap", message=traps.summary, timestamp=now,
        ))
    if traps.fake_breakout:
        alerts.append(Alert(
            symbol=symbol, alert_type="fake_pump_warning", severity="medium",
            title="Fake Breakout", message=traps.summary, timestamp=now,
        ))
    if traps.stop_hunt:
        alerts.append(Alert(
            symbol=symbol, alert_type="trap_warning", severity="medium",
            title="Stop Hunt", message="Stop hunt / liquidity sweep detected", timestamp=now,
        ))
    if smart_money.whale_order:
        alerts.append(Alert(
            symbol=symbol, alert_type="info", severity="medium",
            title="Whale Order", message=smart_money.summary, timestamp=now,
        ))
    if signal in ("Strong Buy", "Buy") and confidence >= 80:
        alerts.append(Alert(
            symbol=symbol, alert_type="buy_alert", severity="high",
            title=f"{signal} — {confidence:.0f}%",
            message=f"Regime: {regime.regime}", timestamp=now,
        ))
    if signal in ("Strong Sell", "Sell") and confidence >= 80:
        alerts.append(Alert(
            symbol=symbol, alert_type="sell_alert", severity="high",
            title=f"{signal} — {confidence:.0f}%",
            message=f"Regime: {regime.regime}", timestamp=now,
        ))
    return alerts


def _decision_to_legacy_signal(decision: TradeDecision) -> str:
    """Map professional decision to legacy AISignal label — always aligned with decision engine."""
    ps = (decision.professional_signal or decision.recommendation or "WAIT").upper()
    score = decision.professional_ai_score or decision.ai_confidence
    if ps == "BUY":
        return "Strong Buy" if score >= 80 else "Buy"
    if ps == "SELL":
        return "Strong Sell" if score >= 80 else "Sell"
    return "Wait"


def generate_ai_signal(
    symbol: str,
    df: pd.DataFrame,
    daily_df: pd.DataFrame | None,
    price: float,
    change_pct: float,
    news: NewsIntelligence,
    news_items: list | None = None,
) -> tuple[
    AISignal,
    DashboardMeters,
    SMCAnalysis,
    LiquidityEngine,
    VolumeEngine,
    TrendAnalysis,
    SignalAnalysis,
    list[Alert],
    float,
    TechnicalIndicators,
    SmartMoneyTracker,
    LiquidityTrapAnalysis,
    MarketRegime,
    RiskAssessment,
    ConfidenceBreakdown,
    TradeDecision,
    VolumeLiquidityAnalysis,
    NewsRiskAnalysis,
]:
    indicators: TechnicalIndicators = compute_indicators(df, daily_df)

    decision, smc, structure, vol_liq, inst, smart_money, traps, news_risk, volume, liquidity, trend, regime, risk_assessment, confidence = build_trade_decision(
        symbol, df, daily_df, price, change_pct, news_items or [], news,
    )

    roc = _rate_of_change(df["close"])
    _, _, macd_hist = macd(df["close"])
    mom_s = momentum_score(indicators.rsi, macd_hist, roc)
    vol_s = volume_score(volume, change_pct)
    liq_s = liquidity_score(liquidity, trend.direction)
    smc_s = smc_score(smc, structure)
    smt_s = smart_money_score(smart_money)
    news_s = news_score(news)

    ai_score_val = decision.professional_ai_score

    bull = _bullish_conditions(
        trend, volume, liquidity, smc, smc_s, mom_s, news_s, vol_s, liq_s, smart_money, traps,
    )
    bear = _bearish_conditions(
        trend, volume, liquidity, smc, smc_s, mom_s, news_s, vol_s, liq_s,
        change_pct, news, smart_money, traps,
    )

    signal_type = _decision_to_legacy_signal(decision)

    volatility_pct = trend.atr / price * 100 if price else 1.0
    conf_breakdown = compute_confidence(
        signal_type, trend, vol_s, smc_s, liq_s, volatility_pct, news_s,
        smart_money, traps, bull, bear,
    )
    confidence = decision.ai_confidence
    conf_breakdown.overall = confidence

    risk: str = "low"
    if traps.severity > 50 or liquidity.liquidity_trap or volume.unusual_volume:
        risk = "high"
    elif volatility_pct > 2:
        risk = "medium"

    reason = decision.ai_explanation or decision.trigger_reason or f"Signal {decision.recommendation} | AI Score {ai_score_val:.1f}"

    market_risk = max(0.0, min(100.0, volume.volume_zscore * 12 + traps.severity * 0.4 + (30 if liquidity.liquidity_trap else 0)))

    meters = DashboardMeters(
        smart_money_meter=round(smc_s, 1),
        liquidity_meter=round(liq_s, 1),
        trend_strength=round(trend.trend_strength, 1),
        market_risk=round(market_risk, 1),
        institutional_activity=round(smt_s, 1),
        ai_confidence=round(confidence, 1),
        fear_greed=round(mom_s, 1),
    )

    ai_signal = AISignal(
        signal=signal_type,
        confidence=confidence,
        ai_score=ai_score_val,
        reason=reason,
        risk_level=risk,
        entry=decision.entry_zone_high if decision.direction == "long" else decision.entry_zone_low,
        stop_loss=decision.stop_loss,
        target_1=decision.take_profit_1,
        target_2=decision.take_profit_2,
        risk_reward_ratio=decision.risk_reward_ratio,
        confidence_breakdown=conf_breakdown,
    )

    legacy = SignalAnalysis(
        liquidity_inflow=vol_liq.liquidity_inflow >= 55,
        liquidity_outflow=vol_liq.liquidity_outflow >= 55,
        buy_pressure=vol_liq.buyer_pressure,
        sell_pressure=vol_liq.seller_pressure,
        large_buy_volume=smart_money.whale_order and change_pct > 0,
        abnormal_volume=volume.unusual_volume,
        volume_spike=volume.volume_spike,
        true_breakout=smc.bos and smc.bos_direction == "bullish" and not traps.fake_breakout,
        false_breakout=traps.fake_breakout or traps.bull_trap,
        market_trap=traps.bull_trap or traps.bear_trap,
        fake_pump=traps.fake_breakout and traps.trap_direction == "bearish",
        liquidity_trap=liquidity.liquidity_trap or traps.bull_trap or traps.bear_trap,
        smart_money_inflow=smart_money.hidden_accumulation or smart_money.flow_direction == "bullish",
        smart_money_outflow=smart_money.hidden_distribution or smart_money.flow_direction == "bearish",
        order_flow_bullish=trend.direction == "bullish",
        order_flow_bearish=trend.direction == "bearish",
        liquidity_strength=liq_s,
        summary=f"{regime.regime} | {smart_money.summary}",
    )

    alerts = _build_alerts(symbol, signal_type, confidence, traps, smart_money, regime)

    return (
        ai_signal, meters, smc, liquidity, volume, trend, legacy, alerts,
        ai_score_val, indicators, smart_money, traps, regime, risk_assessment, conf_breakdown,
        decision, vol_liq, news_risk,
    )
