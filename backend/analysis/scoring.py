"""AI Score — weighted composite from real component scores."""

from __future__ import annotations

from models.trading import NewsIntelligence

DEFAULT_WEIGHTS = {
    "trend": 0.25,
    "volume": 0.20,
    "liquidity": 0.15,
    "smc": 0.20,
    "momentum": 0.10,
    "news": 0.10,
}

WEIGHTS = dict(DEFAULT_WEIGHTS)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.get(k, 0) for k in DEFAULT_WEIGHTS)
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: round(weights.get(k, DEFAULT_WEIGHTS[k]) / total, 4) for k in DEFAULT_WEIGHTS}


def get_active_weights() -> dict[str, float]:
    try:
        from analysis.ai_learning import load_weights
        return load_weights()
    except Exception:
        return dict(DEFAULT_WEIGHTS)


def momentum_score(rsi: float, macd_hist: float, roc: float) -> float:
    score = 50.0
    score += (rsi - 50) * 0.4
    score += 10 if macd_hist > 0 else -10
    score += min(15, max(-15, roc * 5))
    return max(0.0, min(100.0, score))


def news_score(news: NewsIntelligence) -> float:
    base = 50.0 + news.confidence_adjustment * 2.5
    if news.overall_sentiment == "bullish":
        base += 10
    elif news.overall_sentiment == "bearish":
        base -= 10
    return max(0.0, min(100.0, base))


def compute_ai_score(
    trend: float,
    volume: float,
    liquidity: float,
    smc: float,
    momentum: float,
    news: float,
) -> float:
    w = get_active_weights()
    return round(
        trend * w["trend"]
        + volume * w["volume"]
        + liquidity * w["liquidity"]
        + smc * w["smc"]
        + momentum * w["momentum"]
        + news * w["news"],
        1,
    )
