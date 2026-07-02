"""Phase 4 — Professional Decision Engine with full factor gate and dynamic AI score."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from analysis.smc import smc_score
from analysis.structure import MarketStructure
from models.alerts import TechnicalIndicators
from models.trading import (
    InstitutionalFlowAnalysis,
    LiquidityEngine,
    LiquidityTrapAnalysis,
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

logger = logging.getLogger(__name__)

ProfessionalSignal = str  # BUY | SELL | WAIT | AVOID

MIN_FACTOR_SCORE = 45.0
MIN_PROFESSIONAL_SCORE = 72.0
MIN_RR_BUY_SELL = 2.0

# Institutional gate — every item must score >= MIN_FACTOR_SCORE for BUY/SELL.
REQUIRED_INSTITUTIONAL_FACTORS: tuple[str, ...] = (
    "smc",
    "bos",
    "choch",
    "order_blocks",
    "fair_value_gaps",
    "liquidity_sweep",
    "ema20",
    "ema50",
    "ema200",
    "vwap",
    "atr",
    "relative_volume",
    "volume_spike",
    "momentum",
    "news_impact",
    "risk_reward",
    "trend",
)

# Supplementary factors — affect AI score and explanation, not the BUY gate.
SUPPLEMENTARY_FACTORS: tuple[str, ...] = (
    "rsi",
    "macd",
    "delta_volume",
    "institutional_flow",
)

FACTOR_LABELS: dict[str, str] = {
    "smc": "SMC",
    "bos": "BOS",
    "choch": "CHOCH",
    "order_blocks": "Order Block",
    "fair_value_gaps": "Fair Value Gap",
    "liquidity_sweep": "Liquidity Sweep",
    "ema20": "EMA20",
    "ema50": "EMA50",
    "ema200": "EMA200",
    "vwap": "VWAP",
    "atr": "ATR",
    "relative_volume": "Relative Volume",
    "volume_spike": "Volume Spike",
    "momentum": "Momentum",
    "news_impact": "News",
    "risk_reward": "Risk/Reward",
    "trend": "Trend",
    "rsi": "RSI",
    "macd": "MACD",
    "delta_volume": "Delta Volume",
    "institutional_flow": "Institutional Flow",
}

FACTOR_WEIGHTS: dict[str, float] = {
    "smc": 0.05,
    "bos": 0.06,
    "choch": 0.05,
    "order_blocks": 0.04,
    "fair_value_gaps": 0.04,
    "liquidity_sweep": 0.04,
    "volume_spike": 0.04,
    "relative_volume": 0.04,
    "vwap": 0.04,
    "ema20": 0.035,
    "ema50": 0.035,
    "ema200": 0.035,
    "atr": 0.025,
    "trend": 0.04,
    "rsi": 0.04,
    "macd": 0.04,
    "momentum": 0.05,
    "delta_volume": 0.04,
    "news_impact": 0.05,
    "institutional_flow": 0.05,
    "risk_reward": 0.04,
}


@dataclass
class DecisionAudit:
    signal: str
    ai_score: float
    factor_scores: dict[str, float]
    all_filters_passed: bool
    filters_passed: list[str] = field(default_factory=list)
    filters_failed: list[str] = field(default_factory=list)
    supplementary_passed: list[str] = field(default_factory=list)
    supplementary_failed: list[str] = field(default_factory=list)
    buy_blockers: list[str] = field(default_factory=list)
    final_blocker: str = ""
    expected_holding_time: str = ""
    ai_explanation: str = ""
    bias: str = "neutral"


@dataclass
class ProfessionalResult:
    signal: str
    ai_score: float
    factor_scores: dict[str, float]
    all_filters_passed: bool
    expected_holding_time: str
    ai_explanation: str
    bias: str
    filters_passed: list[str] = field(default_factory=list)
    filters_failed: list[str] = field(default_factory=list)
    supplementary_passed: list[str] = field(default_factory=list)
    supplementary_failed: list[str] = field(default_factory=list)
    buy_blockers: list[str] = field(default_factory=list)
    final_blocker: str = ""


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _factor_label(name: str) -> str:
    return FACTOR_LABELS.get(name, name)


def _infer_bias(
    smc: SMCAnalysis,
    trend: TrendAnalysis,
    inst: InstitutionalFlowAnalysis,
    vol_liq: VolumeLiquidityAnalysis,
    indicators: TechnicalIndicators,
) -> str:
    bull = 0
    bear = 0
    if smc.bos_direction == "bullish" or smc.choch_direction == "bullish":
        bull += 2
    if smc.bos_direction == "bearish" or smc.choch_direction == "bearish":
        bear += 2
    if trend.direction == "bullish":
        bull += 1
    elif trend.direction == "bearish":
        bear += 1
    if inst.flow_direction == "bullish":
        bull += 1
    elif inst.flow_direction == "bearish":
        bear += 1
    if vol_liq.buyer_pressure > vol_liq.seller_pressure + 5:
        bull += 1
    elif vol_liq.seller_pressure > vol_liq.buyer_pressure + 5:
        bear += 1
    if indicators.macd > indicators.macd_signal:
        bull += 1
    else:
        bear += 1
    if bull > bear:
        return "long"
    if bear > bull:
        return "short"
    return "neutral"


def _resolve_effective_bias(
    bias: str,
    smc: SMCAnalysis,
    trend: TrendAnalysis,
    factor_scores: dict[str, float],
) -> str:
    """Resolve neutral bias from structure when institutional factors align."""
    if bias != "neutral":
        return bias

    bull = 0
    bear = 0
    if factor_scores.get("bos", 0) >= MIN_FACTOR_SCORE and smc.bos_direction == "bullish":
        bull += 1
    if factor_scores.get("bos", 0) >= MIN_FACTOR_SCORE and smc.bos_direction == "bearish":
        bear += 1
    if factor_scores.get("choch", 0) >= MIN_FACTOR_SCORE and smc.choch_direction == "bullish":
        bull += 1
    if factor_scores.get("choch", 0) >= MIN_FACTOR_SCORE and smc.choch_direction == "bearish":
        bear += 1
    if factor_scores.get("liquidity_sweep", 0) >= MIN_FACTOR_SCORE and smc.sweep_direction == "bullish":
        bull += 1
    if factor_scores.get("liquidity_sweep", 0) >= MIN_FACTOR_SCORE and smc.sweep_direction == "bearish":
        bear += 1
    if factor_scores.get("trend", 0) >= MIN_FACTOR_SCORE and trend.direction == "bullish":
        bull += 1
    if factor_scores.get("trend", 0) >= MIN_FACTOR_SCORE and trend.direction == "bearish":
        bear += 1

    if bull > bear:
        return "long"
    if bear > bull:
        return "short"
    return "neutral"


def _score_bos(smc: SMCAnalysis, bias: str) -> float:
    if bias == "long" and smc.bos and smc.bos_direction == "bullish":
        return 90.0
    if bias == "short" and smc.bos and smc.bos_direction == "bearish":
        return 90.0
    if smc.bos:
        return 55.0
    return 25.0


def _score_choch(smc: SMCAnalysis, bias: str) -> float:
    if bias == "long" and smc.choch and smc.choch_direction == "bullish":
        return 88.0
    if bias == "short" and smc.choch and smc.choch_direction == "bearish":
        return 88.0
    if smc.choch:
        return 52.0
    return 28.0


def _score_order_blocks(smc: SMCAnalysis, bias: str) -> float:
    if not smc.order_blocks:
        return 30.0
    bull = sum(1 for ob in smc.order_blocks if ob.type == "bullish")
    bear = sum(1 for ob in smc.order_blocks if ob.type == "bearish")
    if bias == "long" and bull > bear:
        return _clamp(60 + bull * 10)
    if bias == "short" and bear > bull:
        return _clamp(60 + bear * 10)
    return 45.0


def _score_fvg(smc: SMCAnalysis, bias: str) -> float:
    active = [g for g in smc.fair_value_gaps if not g.filled]
    if not active:
        return 35.0
    bull = sum(1 for g in active if g.type == "bullish")
    bear = sum(1 for g in active if g.type == "bearish")
    if bias == "long" and bull:
        return _clamp(55 + bull * 12)
    if bias == "short" and bear:
        return _clamp(55 + bear * 12)
    return 48.0


def _score_sweep(smc: SMCAnalysis, bias: str) -> float:
    if not smc.liquidity_sweep:
        return 40.0
    if bias == "long" and smc.sweep_direction == "bullish":
        return 85.0
    if bias == "short" and smc.sweep_direction == "bearish":
        return 85.0
    return 50.0


def _score_trend(trend: TrendAnalysis, bias: str) -> float:
    if bias == "long" and trend.direction == "bullish" and trend.trend_strength >= 55:
        return _clamp(trend.trend_strength)
    if bias == "short" and trend.direction == "bearish" and trend.trend_strength <= 45:
        return _clamp(100 - trend.trend_strength)
    if bias == "long" and trend.direction == "bullish":
        return _clamp(max(45.0, trend.trend_strength * 0.85))
    if bias == "short" and trend.direction == "bearish":
        return _clamp(max(45.0, (100 - trend.trend_strength) * 0.85))
    return 38.0


def _score_risk_reward(risk: RiskAssessment) -> float:
    if risk.risk_reward_ratio < MIN_RR_BUY_SELL:
        return max(15.0, risk.risk_reward_ratio / MIN_RR_BUY_SELL * 44)
    return _clamp(risk.risk_reward_ratio / 3.0 * 100)


def compute_factor_scores(
    price: float,
    bias: str,
    smc: SMCAnalysis,
    structure: MarketStructure,
    trend: TrendAnalysis,
    volume: VolumeEngine,
    vol_liq: VolumeLiquidityAnalysis,
    inst: InstitutionalFlowAnalysis,
    smart_money: SmartMoneyTracker,
    traps: LiquidityTrapAnalysis,
    news_intel: NewsIntelligence,
    news_risk: NewsRiskAnalysis,
    risk: RiskAssessment,
    indicators: TechnicalIndicators,
    mom_s: float,
    smc_s: float,
) -> dict[str, float]:
    atr_pct = (trend.atr / price * 100) if price else 0.0

    vol_spike = volume.volume_spike or vol_liq.volume_spike
    rvol = max(volume.relative_volume, vol_liq.relative_volume)

    scores: dict[str, float] = {
        "smc": _clamp(smc_s),
        "bos": _score_bos(smc, bias),
        "choch": _score_choch(smc, bias),
        "order_blocks": _score_order_blocks(smc, bias),
        "fair_value_gaps": _score_fvg(smc, bias),
        "liquidity_sweep": _score_sweep(smc, bias),
        "volume_spike": 85.0 if vol_spike else 35.0,
        "relative_volume": _clamp(min(rvol, 4) / 4 * 100),
        "vwap": 75.0 if (bias == "long" and trend.price_above_vwap) or (bias == "short" and not trend.price_above_vwap) else 40.0,
        "ema20": 80.0 if (bias == "long" and price > trend.ema_20) or (bias == "short" and price < trend.ema_20) else 42.0,
        "ema50": 78.0 if (bias == "long" and price > trend.ema_50) or (bias == "short" and price < trend.ema_50) else 40.0,
        "ema200": 76.0 if (bias == "long" and price > trend.ema_200) or (bias == "short" and price < trend.ema_200) else 38.0,
        "atr": 70.0 if 0.15 <= atr_pct <= 4.0 else (45.0 if atr_pct > 0 else 20.0),
        "trend": _score_trend(trend, bias),
        "risk_reward": _score_risk_reward(risk),
        "rsi": _clamp(50 + (indicators.rsi - 50) * (0.8 if bias == "long" else -0.8)),
        "macd": 80.0 if (bias == "long" and indicators.macd > indicators.macd_signal) or (bias == "short" and indicators.macd < indicators.macd_signal) else 38.0,
        "momentum": mom_s,
        "delta_volume": 75.0 if (
            (bias == "long" and vol_liq.delta_direction == "bullish")
            or (bias == "short" and vol_liq.delta_direction == "bearish")
        ) else 42.0,
        "news_impact": _clamp(100.0 - news_risk.risk_score),
        "institutional_flow": _clamp(inst.flow_score + (10 if (
            (bias == "long" and inst.flow_direction == "bullish")
            or (bias == "short" and inst.flow_direction == "bearish")
        ) else 0)),
    }

    # SMC composite nudge from live structure engine
    smc_blend = smc_s / 100.0
    for k in ("bos", "choch", "order_blocks", "fair_value_gaps", "liquidity_sweep"):
        scores[k] = _clamp(scores[k] * 0.85 + smc_blend * 15)

    # Penalize traps in structure-related scores
    if traps.severity > 30:
        for k in scores:
            scores[k] = _clamp(scores[k] - traps.severity * 0.15)

    if smart_money.whale_order or smart_money.absorption:
        scores["institutional_flow"] = _clamp(scores["institutional_flow"] + 8)

    return {k: round(v, 1) for k, v in scores.items()}


def compute_professional_ai_score(factor_scores: dict[str, float]) -> float:
    total = sum(factor_scores.get(k, 0) * w for k, w in FACTOR_WEIGHTS.items())
    weight_sum = sum(FACTOR_WEIGHTS.values())
    return round(_clamp(total / weight_sum), 1)


def partition_factor_results(factor_scores: dict[str, float]) -> tuple[list[str], list[str], list[str], list[str]]:
    passed: list[str] = []
    failed: list[str] = []
    supp_passed: list[str] = []
    supp_failed: list[str] = []

    for name in REQUIRED_INSTITUTIONAL_FACTORS:
        score = factor_scores.get(name, 0)
        label = f"{_factor_label(name)} ({score:.0f})"
        if score >= MIN_FACTOR_SCORE:
            passed.append(label)
        else:
            failed.append(label)

    for name in SUPPLEMENTARY_FACTORS:
        score = factor_scores.get(name, 0)
        label = f"{_factor_label(name)} ({score:.0f})"
        if score >= MIN_FACTOR_SCORE:
            supp_passed.append(label)
        else:
            supp_failed.append(label)

    return passed, failed, supp_passed, supp_failed


def required_institutional_passed(factor_scores: dict[str, float], risk: RiskAssessment) -> bool:
    if risk.risk_reward_ratio < MIN_RR_BUY_SELL:
        return False
    return all(factor_scores.get(k, 0) >= MIN_FACTOR_SCORE for k in REQUIRED_INSTITUTIONAL_FACTORS)


def all_filters_passed(factor_scores: dict[str, float], risk: RiskAssessment) -> bool:
    """True when every required institutional condition passes (including R:R >= 2.0)."""
    return required_institutional_passed(factor_scores, risk)


def expected_holding_time(atr_pct: float, signal: str, bias: str) -> str:
    if signal not in ("BUY", "SELL"):
        return "—"
    if atr_pct >= 2.5:
        return "1-3 trading days"
    if atr_pct >= 1.2:
        return "2-8 hours"
    if atr_pct >= 0.5:
        return "30-90 minutes"
    return "15-45 minutes (scalp)"


def _avoid_blockers(traps: LiquidityTrapAnalysis, news_risk: NewsRiskAnalysis) -> list[str]:
    blockers: list[str] = []
    if news_risk.block_trade:
        blockers.append(f"News risk blocks trading (score {news_risk.risk_score:.0f})")
    if traps.severity >= 55 or traps.pump_and_dump or traps.spoofing:
        blockers.append(f"Trap severity critical ({traps.severity:.0f}%)")
        if traps.pump_and_dump:
            blockers.append("Pump & dump pattern detected")
        if traps.spoofing:
            blockers.append("Spoofing pattern detected")
    elif traps.severity >= 40 or news_risk.risk_score >= 60:
        if traps.severity >= 40:
            blockers.append(f"Trap severity elevated ({traps.severity:.0f}%)")
        if news_risk.risk_score >= 60:
            blockers.append(f"News risk elevated ({news_risk.risk_score:.0f})")
    return blockers


def _wait_blockers(
    ai_score: float,
    bias: str,
    risk: RiskAssessment,
    failed_required: list[str],
) -> list[str]:
    blockers: list[str] = []

    for label in failed_required:
        blockers.append(f"{label} below minimum {MIN_FACTOR_SCORE:.0f}")

    if risk.risk_reward_ratio < MIN_RR_BUY_SELL:
        blockers.append(
            f"Risk/Reward {risk.risk_reward_ratio:.2f} below minimum {MIN_RR_BUY_SELL:.1f}"
        )

    if ai_score < MIN_PROFESSIONAL_SCORE:
        blockers.append(
            f"AI Score {ai_score:.1f} below minimum {MIN_PROFESSIONAL_SCORE:.0f}"
        )

    if bias == "neutral":
        blockers.append("Direction neutral — no confirmed long/short bias")

    return blockers


def trace_decision(
    factor_scores: dict[str, float],
    ai_score: float,
    bias: str,
    traps: LiquidityTrapAnalysis,
    news_risk: NewsRiskAnalysis,
    risk: RiskAssessment,
) -> DecisionAudit:
    passed, failed, supp_passed, supp_failed = partition_factor_results(factor_scores)
    required_ok = required_institutional_passed(factor_scores, risk)
    effective_bias = bias

    avoid_blockers = _avoid_blockers(traps, news_risk)
    if avoid_blockers:
        explanation = build_decision_explanation(
            "AVOID", ai_score, effective_bias, passed, failed,
            supp_passed, supp_failed, avoid_blockers, avoid_blockers[0],
        )
        return DecisionAudit(
            signal="AVOID",
            ai_score=ai_score,
            factor_scores=factor_scores,
            all_filters_passed=False,
            filters_passed=passed,
            filters_failed=failed,
            supplementary_passed=supp_passed,
            supplementary_failed=supp_failed,
            buy_blockers=avoid_blockers,
            final_blocker=avoid_blockers[0],
            ai_explanation=explanation,
            bias=effective_bias,
        )

    if required_ok and effective_bias == "long" and risk.risk_reward_ratio >= MIN_RR_BUY_SELL:
        explanation = build_decision_explanation(
            "BUY", ai_score, effective_bias, passed, failed,
            supp_passed, supp_failed, [], "",
        )
        return DecisionAudit(
            signal="BUY",
            ai_score=ai_score,
            factor_scores=factor_scores,
            all_filters_passed=True,
            filters_passed=passed,
            filters_failed=failed,
            supplementary_passed=supp_passed,
            supplementary_failed=supp_failed,
            buy_blockers=[],
            final_blocker="",
            ai_explanation=explanation,
            bias=effective_bias,
        )

    if required_ok and effective_bias == "short" and risk.risk_reward_ratio >= MIN_RR_BUY_SELL:
        explanation = build_decision_explanation(
            "SELL", ai_score, effective_bias, passed, failed,
            supp_passed, supp_failed, [], "",
        )
        return DecisionAudit(
            signal="SELL",
            ai_score=ai_score,
            factor_scores=factor_scores,
            all_filters_passed=True,
            filters_passed=passed,
            filters_failed=failed,
            supplementary_passed=supp_passed,
            supplementary_failed=supp_failed,
            buy_blockers=[],
            final_blocker="",
            ai_explanation=explanation,
            bias=effective_bias,
        )

    buy_blockers = _wait_blockers(ai_score, effective_bias, risk, failed)
    final_blocker = buy_blockers[0] if buy_blockers else "Institutional confluence incomplete"
    explanation = build_decision_explanation(
        "WAIT", ai_score, effective_bias, passed, failed,
        supp_passed, supp_failed, buy_blockers, final_blocker,
    )
    return DecisionAudit(
        signal="WAIT",
        ai_score=ai_score,
        factor_scores=factor_scores,
        all_filters_passed=False,
        filters_passed=passed,
        filters_failed=failed,
        supplementary_passed=supp_passed,
        supplementary_failed=supp_failed,
        buy_blockers=buy_blockers,
        final_blocker=final_blocker,
        ai_explanation=explanation,
        bias=effective_bias,
    )


def build_decision_explanation(
    signal: str,
    ai_score: float,
    bias: str,
    passed: list[str],
    failed: list[str],
    supp_passed: list[str],
    supp_failed: list[str],
    buy_blockers: list[str],
    final_blocker: str,
) -> str:
    lines = [
        f"Signal {signal} | AI Score {ai_score:.1f} | Bias {bias}",
        f"Institutional passed ({len(passed)}/{len(REQUIRED_INSTITUTIONAL_FACTORS)}): {', '.join(passed) if passed else 'none'}",
        f"Institutional failed ({len(failed)}): {', '.join(failed) if failed else 'none'}",
    ]

    if supp_passed or supp_failed:
        lines.append(
            f"Supplementary passed: {', '.join(supp_passed) if supp_passed else 'none'}"
        )
        lines.append(
            f"Supplementary failed: {', '.join(supp_failed) if supp_failed else 'none'}"
        )

    if signal == "WAIT":
        lines.append("BUY blocked because:")
        if buy_blockers:
            lines.extend(f"  • {b}" for b in buy_blockers)
        else:
            lines.append("  • Institutional confluence incomplete")
        if final_blocker:
            lines.append(f"Final blocker: {final_blocker}")
    elif signal == "AVOID":
        lines.append("AVOID because:")
        if buy_blockers:
            lines.extend(f"  • {b}" for b in buy_blockers)
        if final_blocker:
            lines.append(f"Final blocker: {final_blocker}")
    elif signal in ("BUY", "SELL"):
        lines.append(f"All {len(REQUIRED_INSTITUTIONAL_FACTORS)} institutional conditions passed.")
        if final_blocker:
            lines.append(f"Final blocker: none")

    return "\n".join(lines)


def apply_professional_decision(
    decision: TradeDecision,
    price: float,
    smc: SMCAnalysis,
    structure: MarketStructure,
    trend: TrendAnalysis,
    volume: VolumeEngine,
    vol_liq: VolumeLiquidityAnalysis,
    inst: InstitutionalFlowAnalysis,
    smart_money: SmartMoneyTracker,
    traps: LiquidityTrapAnalysis,
    news_intel: NewsIntelligence,
    news_risk: NewsRiskAnalysis,
    risk: RiskAssessment,
    indicators: TechnicalIndicators,
    mom_s: float,
    smc_s: float,
) -> ProfessionalResult:
    bias = _infer_bias(smc, trend, inst, vol_liq, indicators)
    factor_scores = compute_factor_scores(
        price, bias, smc, structure, trend, volume, vol_liq,
        inst, smart_money, traps, news_intel, news_risk, risk, indicators, mom_s, smc_s,
    )
    effective_bias = _resolve_effective_bias(bias, smc, trend, factor_scores)
    if effective_bias != bias:
        factor_scores = compute_factor_scores(
            price, effective_bias, smc, structure, trend, volume, vol_liq,
            inst, smart_money, traps, news_intel, news_risk, risk, indicators, mom_s, smc_s,
        )
    ai_score = compute_professional_ai_score(factor_scores)
    audit = trace_decision(factor_scores, ai_score, effective_bias, traps, news_risk, risk)
    atr_pct = (trend.atr / price * 100) if price else 0.0
    hold = expected_holding_time(atr_pct, audit.signal, effective_bias)

    return ProfessionalResult(
        signal=audit.signal,
        ai_score=audit.ai_score,
        factor_scores=audit.factor_scores,
        all_filters_passed=audit.all_filters_passed,
        expected_holding_time=hold,
        ai_explanation=audit.ai_explanation,
        bias=audit.bias,
        filters_passed=audit.filters_passed,
        filters_failed=audit.filters_failed,
        supplementary_passed=audit.supplementary_passed,
        supplementary_failed=audit.supplementary_failed,
        buy_blockers=audit.buy_blockers,
        final_blocker=audit.final_blocker,
    )


def enrich_trade_decision(
    decision: TradeDecision,
    prof: ProfessionalResult,
    risk: RiskAssessment,
) -> TradeDecision:
    """Merge professional layer into trade decision."""
    decision.professional_signal = prof.signal
    decision.professional_ai_score = prof.ai_score
    decision.factor_scores = prof.factor_scores
    decision.all_filters_passed = prof.all_filters_passed
    decision.expected_holding_time = prof.expected_holding_time
    decision.ai_explanation = prof.ai_explanation
    decision.recommendation = prof.signal
    decision.direction = prof.bias if prof.bias != "neutral" else decision.direction
    decision.ai_confidence = prof.ai_score
    decision.filters_passed = prof.filters_passed
    decision.filters_failed = prof.filters_failed
    decision.buy_blockers = prof.buy_blockers
    decision.final_blocker = prof.final_blocker

    if prof.signal in ("BUY", "SELL"):
        decision.trigger_reason = prof.ai_explanation
    elif prof.signal == "WAIT":
        decision.trigger_reason = prof.ai_explanation
    elif prof.signal == "AVOID":
        decision.trigger_reason = prof.ai_explanation

    return decision
