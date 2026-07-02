"""Decision Engine — professional scalping recommendation with safety rules."""

from __future__ import annotations

import logging

import pandas as pd

from analysis.engine_log import EngineLogger
from analysis.indicators import compute_indicators, macd
from analysis.institutional_flow_engine import analyze_institutional_flow
from analysis.liquidity_engine import analyze_liquidity, liquidity_score
from analysis.liquidity_trap_detector import detect_liquidity_traps
from analysis.market_regime import classify_regime
from analysis.news_risk_filter import analyze_news_risk
from analysis.risk_engine import calculate_risk, validate_take_profits
from analysis.scoring import momentum_score, news_score
from analysis.smc import analyze_smc, smc_score
from analysis.structure import MarketStructure
from analysis.trend_engine import analyze_trend
from analysis.volume_engine import analyze_volume, volume_score
from analysis.volume_liquidity_engine import analyze_volume_liquidity
from models.stock import NewsItem
from models.trading import (
    EngineLogRecord,
    InstitutionalFlowAnalysis,
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

from analysis.professional_decision import (
    REQUIRED_INSTITUTIONAL_FACTORS,
    apply_professional_decision,
    enrich_trade_decision,
)

logger = logging.getLogger(__name__)

DECISION_MIN_CONFIDENCE = 85.0
DECISION_MIN_RR = 2.0
TRAP_RISK_LOW = 30.0
NEWS_RISK_LOW = 30.0
INFLOW_STRONG = 60.0


def _rate_of_change(close: pd.Series, period: int = 10) -> float:
    if len(close) < period + 1:
        return 0.0
    return float((close.iloc[-1] - close.iloc[-period - 1]) / close.iloc[-period - 1] * 100)


def _market_structure_label(smc: SMCAnalysis, structure: MarketStructure) -> str:
    parts: list[str] = []
    if structure.mss:
        parts.append(f"MSS {structure.mss_direction}")
    elif structure.bos:
        parts.append(f"BOS {structure.bos_direction}")
    elif structure.choch:
        parts.append(f"CHOCH {structure.choch_direction}")
    else:
        parts.append(f"Trend {structure.trend}")
    if smc.liquidity_sweep:
        parts.append(f"Sweep {smc.sweep_direction}")
    return " | ".join(parts)


def _compute_decision_confidence(
    smc_s: float,
    vol_liq: VolumeLiquidityAnalysis,
    inst: InstitutionalFlowAnalysis,
    trend: TrendAnalysis,
    mom_s: float,
    news_risk: NewsRiskAnalysis,
    structure: MarketStructure,
    traps: LiquidityTrapAnalysis,
    risk: RiskAssessment,
) -> float:
    """9-factor confidence 0-100."""
    structure_s = 50.0
    if structure.mss:
        structure_s = 80 if structure.mss_direction == "bullish" else 20
    elif structure.bos:
        structure_s = 72 if structure.bos_direction == "bullish" else 28
    elif structure.choch:
        structure_s = 65 if structure.choch_direction == "bullish" else 35

    news_s = max(0.0, 100.0 - news_risk.risk_score)
    risk_s = min(100.0, risk.risk_reward_ratio / 3.0 * 100) if risk.risk_reward_ratio else 40.0
    trap_penalty = traps.severity * 0.35

    weights = {
        "smart_money": 0.14,
        "volume": 0.12,
        "liquidity": 0.12,
        "momentum": 0.10,
        "trend": 0.12,
        "news": 0.10,
        "structure": 0.14,
        "risk": 0.08,
        "institutional": 0.08,
    }
    scores = {
        "smart_money": smc_s,
        "volume": min(100.0, vol_liq.relative_volume * 35 + 30),
        "liquidity": vol_liq.liquidity_inflow,
        "momentum": mom_s,
        "trend": trend.trend_strength,
        "news": news_s,
        "structure": structure_s,
        "risk": risk_s,
        "institutional": inst.flow_score,
    }
    raw = sum(scores[k] * weights[k] for k in weights)
    return max(0.0, min(100.0, raw - trap_penalty))


def _entry_zone(price: float, trend: TrendAnalysis, direction: str) -> tuple[float, float]:
    atr = trend.atr or price * 0.005
    if direction == "long":
        return round(price - atr * 0.3, 2), round(price + atr * 0.1, 2)
    if direction == "short":
        return round(price - atr * 0.1, 2), round(price + atr * 0.3, 2)
    return round(price - atr * 0.15, 2), round(price + atr * 0.15, 2)


def _devils_advocate(
    traps: LiquidityTrapAnalysis,
    news_risk: NewsRiskAnalysis,
    vol_liq: VolumeLiquidityAnalysis,
    trend: TrendAnalysis,
    direction: str,
) -> str:
    concerns: list[str] = []
    if traps.severity > 20:
        concerns.append(traps.summary)
    if news_risk.risk_score > 15:
        concerns.append(news_risk.summary)
    if vol_liq.liquidity_outflow > vol_liq.liquidity_inflow + 10:
        concerns.append("تدفق سيولة صادر أقوى من الوارد")
    if direction == "long" and trend.direction == "bearish":
        concerns.append("الاتجاه العام هابط")
    if direction == "short" and trend.direction == "bullish":
        concerns.append("الاتجاه العام صاعد")
    return " | ".join(concerns) if concerns else "لا مخاوف رئيسية — راقب إدارة المخاطر"


def _resolve_recommendation(
    direction: str,
    confidence: float,
    traps: LiquidityTrapAnalysis,
    news_risk: NewsRiskAnalysis,
    vol_liq: VolumeLiquidityAnalysis,
    price: float,
    entry_low: float,
    entry_high: float,
    rr: float,
    bullish_bias: bool,
) -> tuple[str, str]:
    if news_risk.block_trade:
        return "NO TRADE", "خطر أخبار عالي — لا تداول"

    if traps.severity >= 50 or traps.pump_and_dump:
        return "AVOID / TRAP RISK", traps.summary

    if traps.severity >= 35:
        return "AVOID / TRAP RISK", f"فخ سيولة: {traps.summary}"

    price_confirmed_long = price >= entry_low and bullish_bias
    price_confirmed_short = price <= entry_high and not bullish_bias

    safety_ok = (
        confidence >= DECISION_MIN_CONFIDENCE
        and traps.severity < TRAP_RISK_LOW
        and news_risk.risk_score < NEWS_RISK_LOW
        and vol_liq.liquidity_inflow >= INFLOW_STRONG
        and rr >= DECISION_MIN_RR
    )

    if direction == "long" and safety_ok and price_confirmed_long:
        return "ENTRY CONFIRMED", "جميع شروط الأمان متحققة للشراء"
    if direction == "short" and safety_ok and price_confirmed_short:
        return "ENTRY CONFIRMED", "جميع شروط الأمان متحققة للبيع"

    if confidence >= 70 and direction != "neutral":
        if (direction == "long" and price_confirmed_long) or (direction == "short" and price_confirmed_short):
            return "POSSIBLE ENTRY", "إعداد جيد — بانتظار تأكيد كامل"
        return "WATCH", "إعداد يتشكل — راقب منطقة الدخول"

    if confidence >= 55:
        return "WATCH", "إشارات مختلطة — مراقبة فقط"

    if news_risk.risk_level == "medium":
        return "NO TRADE", "مخاطر أخبار متوسطة"

    return "WAIT", "لا إعداد واضح للمضاربة السريعة"


def _infer_direction(
    smc_s: float,
    trend: TrendAnalysis,
    inst: InstitutionalFlowAnalysis,
    vol_liq: VolumeLiquidityAnalysis,
) -> str:
    bull_votes = 0
    bear_votes = 0
    if smc_s >= 58:
        bull_votes += 1
    elif smc_s <= 42:
        bear_votes += 1
    if trend.direction == "bullish":
        bull_votes += 1
    elif trend.direction == "bearish":
        bear_votes += 1
    if inst.flow_direction == "bullish":
        bull_votes += 1
    elif inst.flow_direction == "bearish":
        bear_votes += 1
    if vol_liq.buyer_pressure > vol_liq.seller_pressure + 5:
        bull_votes += 1
    elif vol_liq.seller_pressure > vol_liq.buyer_pressure + 5:
        bear_votes += 1
    if bull_votes > bear_votes:
        return "long"
    if bear_votes > bull_votes:
        return "short"
    return "neutral"


def build_trade_decision(
    symbol: str,
    df: pd.DataFrame,
    daily_df: pd.DataFrame | None,
    price: float,
    change_pct: float,
    news_items: list[NewsItem],
    news_intel: NewsIntelligence,
) -> tuple[
    TradeDecision,
    SMCAnalysis,
    MarketStructure,
    VolumeLiquidityAnalysis,
    InstitutionalFlowAnalysis,
    SmartMoneyTracker,
    LiquidityTrapAnalysis,
    NewsRiskAnalysis,
    VolumeEngine,
    LiquidityEngine,
    TrendAnalysis,
    MarketRegime,
    RiskAssessment,
    float,
]:
    elog = EngineLogger()

    trend = analyze_trend(df, daily_df, price)
    smc, structure = analyze_smc(df, price)
    elog.log(
        "SMCEngine",
        {"bars": len(df), "price": price},
        f"BOS={smc.bos}, CHOCH={smc.choch}, MSS={smc.mss}, OB={len(smc.order_blocks)}",
        smc.summary,
        "Structure from swing points + OB/FVG/Breaker/Mitigation",
    )

    vol_liq = analyze_volume_liquidity(df, daily_df, price, elog)
    inst, smart_money = analyze_institutional_flow(df, price, elog)
    volume = analyze_volume(df)
    liquidity = analyze_liquidity(df, price, structure)
    traps = detect_liquidity_traps(df, price, structure, smc, liquidity)
    elog.log(
        "TrapDetection",
        {"severity": traps.severity, "price": price},
        f"flags={[traps.bull_trap, traps.bear_trap, traps.fake_breakout, traps.pump_and_dump]}",
        traps.summary,
        "Trap patterns from sweep, breakout failure, pump/dump",
    )

    news_risk = analyze_news_risk(news_items, news_intel, symbol, elog)

    indicators = compute_indicators(df, daily_df)
    roc = _rate_of_change(df["close"])
    _, _, macd_hist = macd(df["close"])
    mom_s = momentum_score(indicators.rsi, macd_hist, roc)
    smc_s = smc_score(smc, structure)
    vol_s = volume_score(volume, change_pct)
    liq_s = liquidity_score(liquidity, trend.direction)
    news_s = news_score(news_intel)

    direction = _infer_direction(smc_s, trend, inst, vol_liq)
    bullish_bias = direction == "long"

    signal_type = "Buy" if direction == "long" else "Sell" if direction == "short" else "Wait"
    regime = classify_regime(df, trend, smc_s, mom_s)
    risk = calculate_risk(
        signal_type, price, trend, regime,
        structure.last_swing_low, structure.last_swing_high,
        indicators.support, indicators.resistance,
    )

    confidence = _compute_decision_confidence(
        smc_s, vol_liq, inst, trend, mom_s, news_risk, structure, traps, risk,
    )
    elog.log(
        "AIConfidence",
        {"smc": smc_s, "vol": vol_s, "liq": liq_s, "mom": mom_s, "news": news_s},
        f"9-factor blend → {confidence:.1f}",
        f"confidence={confidence:.1f}",
        "Weighted Smart Money, Volume, Liquidity, Momentum, Trend, News, Structure, Risk, Institutional",
    )

    entry_low, entry_high = _entry_zone(price, trend, direction)
    recommendation, trigger = _resolve_recommendation(
        direction, confidence, traps, news_risk, vol_liq,
        price, entry_low, entry_high, risk.risk_reward_ratio, bullish_bias,
    )
    elog.log(
        "RecommendationEngine",
        {
            "confidence": confidence,
            "trap": traps.severity,
            "news": news_risk.risk_score,
            "inflow": vol_liq.liquidity_inflow,
            "rr": risk.risk_reward_ratio,
        },
        f"direction={direction}, rec={recommendation}",
        recommendation,
        trigger,
    )

    market_structure = _market_structure_label(smc, structure)
    devil = _devils_advocate(traps, news_risk, vol_liq, trend, direction)

    engine_logs = [
        EngineLogRecord(
            engine=e.engine,
            inputs=e.inputs,
            calculation=e.calculation,
            result=e.result,
            reason=e.reason,
        )
        for e in elog.entries
    ]

    decision = TradeDecision(
        recommendation=recommendation,
        professional_signal="WAIT",
        direction=direction,
        symbol=symbol,
        current_price=round(price, 2),
        entry_zone_low=entry_low,
        entry_zone_high=entry_high,
        stop_loss=risk.atr_stop,
        take_profit_1=risk.take_profit_1,
        take_profit_2=risk.take_profit_2,
        risk_reward_ratio=risk.risk_reward_ratio,
        ai_confidence=round(confidence, 1),
        professional_ai_score=0.0,
        liquidity_inflow=vol_liq.liquidity_inflow,
        liquidity_outflow=vol_liq.liquidity_outflow,
        trap_risk=round(traps.severity, 1),
        news_risk=news_risk.risk_score,
        market_structure=market_structure,
        trigger_reason=trigger,
        devils_advocate=devil,
        engine_logs=engine_logs,
    )

    prof = apply_professional_decision(
        decision, price, smc, structure, trend, volume, vol_liq,
        inst, smart_money, traps, news_intel, news_risk, risk,
        indicators, mom_s, smc_s,
    )
    decision = enrich_trade_decision(decision, prof, risk)
    confidence = decision.ai_confidence

    elog.log(
        "ProfessionalDecision",
        {"factors": len(prof.factor_scores), "passed": prof.all_filters_passed},
        f"score={prof.ai_score}, signal={prof.signal}",
        prof.signal,
        prof.ai_explanation,
    )
    engine_logs.append(EngineLogRecord(
        engine="ProfessionalDecision",
        inputs={"symbol": symbol, "bias": prof.bias},
        calculation=f"{len(prof.factor_scores)}-factor weighted score={prof.ai_score}, passed={len(prof.filters_passed)}/{len(REQUIRED_INSTITUTIONAL_FACTORS)}",
        result=prof.signal,
        reason=prof.final_blocker or prof.ai_explanation[:500],
    ))
    decision.engine_logs = engine_logs

    is_long = decision.direction == "long"
    stop, tp1, tp2 = validate_take_profits(
        decision.current_price,
        decision.stop_loss,
        decision.take_profit_1,
        decision.take_profit_2,
        is_long,
    )
    decision.stop_loss = stop
    decision.take_profit_1 = tp1
    decision.take_profit_2 = tp2

    logger.info(
        "[%s] Professional %s score=%.0f filters=%s rr=%.1f",
        symbol, prof.signal, prof.ai_score, prof.all_filters_passed, risk.risk_reward_ratio,
    )

    return (
        decision, smc, structure, vol_liq, inst, smart_money, traps, news_risk,
        volume, liquidity, trend, regime, risk, confidence,
    )
