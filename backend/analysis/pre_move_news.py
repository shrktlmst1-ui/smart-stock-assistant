"""Pre-Move news catalyst scoring from real news data."""

from __future__ import annotations

from datetime import datetime, timezone

from models.pre_move import PreMoveNewsMetrics
from models.stock import NewsItem

_STRONG_KEYWORDS = (
    "fda", "approval", "contract", "acquisition", "merger", "earnings", "beat",
    "guidance", "partnership", "investment", "agreement", "compliance", "nasdaq",
    "offering", "buyback", "license", "patent", "trial", "phase",
)


def compute_news_metrics(
    news: list[NewsItem],
    change_percent: float,
    *,
    now: datetime | None = None,
) -> PreMoveNewsMetrics:
    m = PreMoveNewsMetrics()
    if not news:
        return m

    now = now or datetime.now(timezone.utc)
    best: NewsItem | None = None
    best_strength = 0.0

    for item in news[:10]:
        title = (item.title or "").lower()
        strength = 0.0
        for kw in _STRONG_KEYWORDS:
            if kw in title:
                strength += 15.0
        if strength == 0 and len(title) > 20:
            strength = 10.0

        recency_min: float | None = None
        if item.published_at:
            try:
                pub = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
                recency_min = (now - pub).total_seconds() / 60.0
                if recency_min <= 30:
                    strength += 20.0
                elif recency_min <= 120:
                    strength += 12.0
                elif recency_min <= 360:
                    strength += 6.0
            except Exception:
                recency_min = None

        if strength > best_strength:
            best_strength = strength
            best = item
            m.news_recency_minutes = recency_min

    if not best:
        return m

    m.catalyst_title = best.title
    m.news_strength = min(100.0, best_strength)
    m.news_relevance = min(100.0, best_strength * 0.9)
    m.news_catalyst_score = round(m.news_strength * 0.6 + m.news_relevance * 0.4, 1)

    if change_percent >= 25 and m.news_recency_minutes and m.news_recency_minutes > 180:
        m.news_already_priced_in = True
    elif change_percent >= 35:
        m.news_already_priced_in = True

    title_lower = best.title.lower()
    if "fda" in title_lower:
        m.catalyst_type = "FDA"
    elif "earnings" in title_lower or "revenue" in title_lower:
        m.catalyst_type = "EARNINGS"
    elif "contract" in title_lower or "partnership" in title_lower:
        m.catalyst_type = "CONTRACT"
    elif "compliance" in title_lower or "nasdaq" in title_lower:
        m.catalyst_type = "REGULATORY"
    else:
        m.catalyst_type = "GENERAL"

    return m


def score_news_component(n: PreMoveNewsMetrics, *, max_pts: float = 15.0) -> float:
    if n.news_catalyst_score <= 0:
        return 0.0
    if n.news_already_priced_in:
        return max(0.0, min(max_pts * 0.3, n.news_catalyst_score / 100.0 * max_pts * 0.3))
    return min(max_pts, round(n.news_catalyst_score / 100.0 * max_pts, 1))
