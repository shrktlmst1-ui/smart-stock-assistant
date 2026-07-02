"""Unit tests for professional decision engine audit and consistency."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.professional_decision import (
    MIN_FACTOR_SCORE,
    MIN_PROFESSIONAL_SCORE,
    REQUIRED_INSTITUTIONAL_FACTORS,
    compute_professional_ai_score,
    required_institutional_passed,
    trace_decision,
)
from models.trading import LiquidityTrapAnalysis, NewsRiskAnalysis, RiskAssessment


def _all_pass_scores() -> dict[str, float]:
    return {k: 75.0 for k in (
        "smc", "bos", "choch", "order_blocks", "fair_value_gaps", "liquidity_sweep",
        "ema20", "ema50", "ema200", "vwap", "atr", "relative_volume", "volume_spike",
        "momentum", "news_impact", "risk_reward", "trend",
        "rsi", "macd", "delta_volume", "institutional_flow",
    )}


def test_all_required_pass_produces_buy():
    scores = _all_pass_scores()
    risk = RiskAssessment(risk_reward_ratio=2.5)
    audit = trace_decision(
        scores,
        compute_professional_ai_score(scores),
        "long",
        LiquidityTrapAnalysis(),
        NewsRiskAnalysis(),
        risk,
    )
    assert audit.signal == "BUY", audit.ai_explanation
    assert audit.all_filters_passed is True
    assert len(audit.filters_failed) == 0
    assert "BUY blocked because" not in audit.ai_explanation


def test_wait_lists_all_failed_filters_and_blocker():
    scores = _all_pass_scores()
    scores["bos"] = 30.0
    scores["choch"] = 28.0
    scores["trend"] = 38.0
    risk = RiskAssessment(risk_reward_ratio=2.5)
    ai_score = compute_professional_ai_score(scores)
    audit = trace_decision(
        scores, ai_score, "long",
        LiquidityTrapAnalysis(), NewsRiskAnalysis(), risk,
    )
    assert audit.signal == "WAIT"
    assert "BUY blocked because:" in audit.ai_explanation
    assert audit.final_blocker
    assert any("BOS" in f for f in audit.filters_failed)
    assert any("CHOCH" in f for f in audit.filters_failed)
    assert not required_institutional_passed(scores, risk)


def test_avoid_explains_trap_blocker():
    scores = _all_pass_scores()
    traps = LiquidityTrapAnalysis(severity=60, pump_and_dump=True)
    audit = trace_decision(
        scores,
        compute_professional_ai_score(scores),
        "long",
        traps,
        NewsRiskAnalysis(),
        RiskAssessment(risk_reward_ratio=2.5),
    )
    assert audit.signal == "AVOID"
    assert "AVOID because:" in audit.ai_explanation
    assert audit.final_blocker


def test_low_rr_blocks_buy():
    scores = _all_pass_scores()
    scores["risk_reward"] = 30.0
    risk = RiskAssessment(risk_reward_ratio=1.5)
    audit = trace_decision(
        scores,
        compute_professional_ai_score(scores),
        "long",
        LiquidityTrapAnalysis(),
        NewsRiskAnalysis(),
        risk,
    )
    assert audit.signal == "WAIT"
    assert not required_institutional_passed(scores, risk)
    assert any("Risk/Reward" in b for b in audit.buy_blockers)


def test_ai_score_matches_factor_weights():
    scores = _all_pass_scores()
    ai_score = compute_professional_ai_score(scores)
    assert ai_score >= MIN_PROFESSIONAL_SCORE


def test_required_factor_count():
    assert len(REQUIRED_INSTITUTIONAL_FACTORS) == 17


if __name__ == "__main__":
    tests = [
        test_all_required_pass_produces_buy,
        test_wait_lists_all_failed_filters_and_blocker,
        test_avoid_explains_trap_blocker,
        test_low_rr_blocks_buy,
        test_ai_score_matches_factor_weights,
        test_required_factor_count,
    ]
    for fn in tests:
        fn()
        print(f"OK {fn.__name__}")
    print(f"All {len(tests)} tests passed")
