"""News Risk Filter — macro/earnings event detection before any trade recommendation."""

from __future__ import annotations

import re

from analysis.engine_log import EngineLogger
from models.stock import NewsItem
from models.trading import NewsIntelligence, NewsRiskAnalysis

_HIGH_RISK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("earnings", re.compile(r"\b(earnings|EPS|quarterly results|Q[1-4] results|guidance)\b", re.I)),
    ("fed", re.compile(r"\b(Fed|Federal Reserve|Powell|FOMC|rate decision|interest rate)\b", re.I)),
    ("cpi", re.compile(r"\b(CPI|consumer price index|inflation data)\b", re.I)),
    ("ppi", re.compile(r"\b(PPI|producer price index)\b", re.I)),
    ("unemployment", re.compile(r"\b(unemployment|jobless claims|nonfarm|NFP|labor market)\b", re.I)),
    ("fomc", re.compile(r"\b(FOMC|fed meeting|dot plot)\b", re.I)),
    ("macro", re.compile(r"\b(GDP|retail sales|PMI|ISM|trade balance|treasury yield)\b", re.I)),
    ("company_news", re.compile(r"\b(merger|acquisition|FDA|lawsuit|SEC investigation|bankruptcy|recall)\b", re.I)),
]


def analyze_news_risk(
    news_items: list[NewsItem],
    news_intel: NewsIntelligence,
    symbol: str,
    logger: EngineLogger | None = None,
) -> NewsRiskAnalysis:
    matched: list[str] = []
    risk_score = 0.0

    texts: list[str] = []
    for item in news_items[:20]:
        if symbol in item.symbols or not item.symbols:
            texts.append(item.title)

    for item in news_intel.items[:10]:
        texts.append(item.headline)

    combined = " ".join(texts)

    for event_name, pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(combined):
            matched.append(event_name)
            risk_score += 18

    if news_intel.overall_sentiment == "bearish" and news_intel.confidence_adjustment < -10:
        matched.append("negative_sentiment")
        risk_score += 12

    # Recent news density — many headlines in short window
    if len(news_items) >= 5:
        matched.append("high_news_volume")
        risk_score += 10

    risk_score = min(100.0, risk_score)
    if risk_score >= 55:
        level = "high"
        block = True
    elif risk_score >= 30:
        level = "medium"
        block = False
    else:
        level = "low"
        block = False

    summary = "لا مخاطر أخبار عالية"
    if matched:
        summary = f"أحداث: {', '.join(matched)} — مستوى {level}"

    result = NewsRiskAnalysis(
        risk_level=level,
        risk_score=round(risk_score, 1),
        block_trade=block,
        matched_events=matched,
        summary=summary,
    )

    if logger:
        logger.log(
            "NewsRiskFilter",
            {"symbol": symbol, "headlines": len(texts), "sentiment": news_intel.overall_sentiment},
            f"score={risk_score:.0f}, events={matched}",
            f"block={block}, level={level}",
            "High-risk macro/earnings keywords trigger NO TRADE",
        )
    return result
