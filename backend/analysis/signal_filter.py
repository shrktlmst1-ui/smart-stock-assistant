"""Production Signal Quality Filter — strict confluence gate."""

from __future__ import annotations

from config import MIN_CONFIDENCE_PRODUCTION, MIN_RISK_REWARD
from models.trading import NewsIntelligence

PRODUCTION_SIGNALS = ("Buy", "Sell")


def apply_production_filter(
    raw_signal: str,
    confidence: float,
    risk_reward_ratio: float,
    bull: dict[str, bool],
    bear: dict[str, bool],
    news: NewsIntelligence,
) -> tuple[str, list[str]]:
    """Return Buy/Sell only when ALL production requirements pass; else Wait."""
    notes: list[str] = []

    for k, v in bull.items():
        notes.append(f"{'✓' if v else '○'} {k}")

    if raw_signal in ("Strong Buy", "Buy"):
        checks = {
            "all_bullish": all(bull.values()),
            "confidence": confidence >= MIN_CONFIDENCE_PRODUCTION,
            "risk_reward": risk_reward_ratio >= MIN_RISK_REWARD,
            "news_not_bearish": news.overall_sentiment != "bearish",
        }
        for name, ok in checks.items():
            notes.append(f"{'✓' if ok else '✗'} {name}")
        if all(checks.values()):
            return "Buy", notes
        return "Wait", notes

    if raw_signal in ("Strong Sell", "Sell"):
        checks = {
            "all_bearish": all(bear.values()),
            "confidence": confidence >= MIN_CONFIDENCE_PRODUCTION,
            "risk_reward": risk_reward_ratio >= MIN_RISK_REWARD,
            "news_not_bullish": news.overall_sentiment != "bullish",
        }
        for name, ok in checks.items():
            notes.append(f"{'✓' if ok else '✗'} {name}")
        if all(checks.values()):
            return "Sell", notes
        return "Wait", notes

    return "Wait", notes
