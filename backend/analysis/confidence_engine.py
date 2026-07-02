"""AI Confidence Engine — dynamic confidence from multi-factor agreement."""

from __future__ import annotations

from models.trading import (
    ConfidenceBreakdown,
    LiquidityTrapAnalysis,
    NewsIntelligence,
    SmartMoneyTracker,
    TrendAnalysis,
    VolumeEngine,
)


def compute_confidence(
    signal: str,
    trend: TrendAnalysis,
    vol_s: float,
    smc_s: float,
    liq_s: float,
    volatility_pct: float,
    news_s: float,
    smart_money: SmartMoneyTracker,
    traps: LiquidityTrapAnalysis,
    bull_conditions: dict[str, bool],
    bear_conditions: dict[str, bool],
) -> ConfidenceBreakdown:
    """Adaptive confidence 0-100 from weighted factor alignment."""

    # Volatility factor: moderate vol = higher confidence, extreme = lower
    if volatility_pct < 0.5:
        vol_conf = 55.0
    elif volatility_pct < 1.5:
        vol_conf = 75.0
    elif volatility_pct < 2.5:
        vol_conf = 60.0
    else:
        vol_conf = 40.0

    trend_conf = trend.trend_strength if trend.direction != "neutral" else 45.0
    smc_conf = smc_s
    liq_conf = liq_s if not traps.bull_trap and not traps.bear_trap else max(20.0, liq_s - traps.severity * 0.3)
    news_conf = news_s
    volume_conf = vol_s

    # Smart money alignment boost
    if signal in ("Strong Buy", "Buy") and smart_money.flow_direction == "bullish":
        volume_conf = min(100.0, volume_conf + 8)
    elif signal in ("Strong Sell", "Sell") and smart_money.flow_direction == "bearish":
        volume_conf = min(100.0, volume_conf + 8)

    weights = {
        "trend": 0.22,
        "volume": 0.18,
        "smc": 0.20,
        "liquidity": 0.15,
        "volatility": 0.10,
        "news": 0.15,
    }

    overall = (
        trend_conf * weights["trend"]
        + volume_conf * weights["volume"]
        + smc_conf * weights["smc"]
        + liq_conf * weights["liquidity"]
        + vol_conf * weights["volatility"]
        + news_conf * weights["news"]
    )

    # Agreement multiplier when signal is directional
    if signal in ("Strong Buy", "Buy"):
        agree = sum(bull_conditions.values()) / max(len(bull_conditions), 1)
        overall = overall * (0.6 + 0.4 * agree)
    elif signal in ("Strong Sell", "Sell"):
        agree = sum(bear_conditions.values()) / max(len(bear_conditions), 1)
        overall = overall * (0.6 + 0.4 * agree)
    else:
        overall *= 0.45  # Wait signals get low confidence

    if traps.severity > 50:
        overall *= 0.85

    overall = max(0.0, min(100.0, overall))

    return ConfidenceBreakdown(
        trend=round(trend_conf, 1),
        volume=round(volume_conf, 1),
        smc=round(smc_conf, 1),
        liquidity=round(liq_conf, 1),
        volatility=round(vol_conf, 1),
        news=round(news_conf, 1),
        overall=round(overall, 1),
    )
