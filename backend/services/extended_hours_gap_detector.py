"""Extended Hours News-Gap Detector — pre/after market gap scanner."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from analysis.extended_catalyst_classifier import (
    CATALYST_TITLE_AR,
    ExtendedCatalystResult,
    classify_extended_catalyst,
)
from services.live_confirmation_engine import LIVE_MONITOR_POOL, live_confirmation_engine
from services.market_session import MarketSession, get_us_market_session

logger = logging.getLogger(__name__)

DetectionStage = Literal["WATCH", "ACTIVE", "EXPLOSIVE"]

MIN_PRICE_USD = 0.50
MAX_PRICE_USD = 10.0
WATCH_GAP_PCT = 4.0
WATCH_MIN_VOLUME = 50_000
ACTIVE_GAP_PCT = 7.0
EXPLOSIVE_GAP_PCT = 20.0
ACTIVE_MIN_RVOL = 2.0
NEWS_MAX_AGE_HOURS = 24
LATE_CHASE_GAP_PCT = 20.0
MICRO_CAP_THRESHOLD = 50_000_000
LOW_FLOAT_THRESHOLD = 10_000_000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_extended_gap_pct(extended_price: float, previous_regular_close: float) -> float:
    if previous_regular_close <= 0 or extended_price <= 0:
        return 0.0
    return round((extended_price - previous_regular_close) / previous_regular_close * 100.0, 2)


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _parse_news_age_hours(published_at: str) -> float:
    if not published_at:
        return 9999.0
    try:
        ts = published_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (_utcnow() - dt).total_seconds() / 3600.0)
    except ValueError:
        return 9999.0


def determine_detection_stage(
    gap_pct: float,
    extended_volume: int,
    *,
    has_recent_news: bool,
    relative_volume: float,
) -> DetectionStage | None:
    if gap_pct < WATCH_GAP_PCT or extended_volume < WATCH_MIN_VOLUME:
        return None
    if gap_pct >= EXPLOSIVE_GAP_PCT:
        return "EXPLOSIVE"
    if gap_pct >= ACTIVE_GAP_PCT and (has_recent_news or relative_volume >= ACTIVE_MIN_RVOL):
        return "ACTIVE"
    return "WATCH"


def is_late_chase(
    *,
    previous_close: float,
    extended_price: float,
    extended_gap_pct: float,
) -> bool:
    if extended_gap_pct >= LATE_CHASE_GAP_PCT:
        return True
    entry_high = previous_close * 1.04
    return extended_price > entry_high * 1.02


def _stage_score(stage: DetectionStage) -> float:
    return {"WATCH": 65.0, "ACTIVE": 75.0, "EXPLOSIVE": 88.0}[stage]


@dataclass
class ExtendedGapDetection:
    symbol: str
    name: str
    session: MarketSession
    previous_close: float
    extended_price: float
    extended_gap_pct: float
    extended_volume: int
    relative_volume: float
    detection_stage: DetectionStage
    catalyst_type: str
    catalyst_title_ar: str
    catalyst_source: str
    catalyst_published_at: str
    has_confirmed_news: bool
    risk_flags_ar: list[str] = field(default_factory=list)
    detected_at: str = ""
    is_late_chase: bool = False
    market_cap: float = 0.0
    float_shares: float = 0.0


class ExtendedGapRegistry:
    """In-memory registry — keyed by symbol, no mock data."""

    def __init__(self) -> None:
        self._detections: dict[str, ExtendedGapDetection] = {}

    def reset(self) -> None:
        self._detections.clear()

    def get(self, symbol: str) -> ExtendedGapDetection | None:
        return self._detections.get(symbol.upper())

    def all(self) -> list[ExtendedGapDetection]:
        return list(self._detections.values())

    def register(self, detection: ExtendedGapDetection) -> None:
        self._detections[detection.symbol.upper()] = detection


extended_gap_registry = ExtendedGapRegistry()


def _extract_extended_quote(
    item: dict,
    session: MarketSession,
) -> tuple[float, int, float] | None:
    prev = item.get("prevDay") or {}
    previous_close = _safe_float(prev.get("c"))
    if previous_close <= 0:
        return None

    if session == "PRE_MARKET":
        pre = item.get("preMarket") or {}
        ext_price = _safe_float(pre.get("c") or pre.get("h"))
        ext_vol = int(pre.get("v") or 0)
        if ext_price <= 0:
            last = item.get("lastTrade") or {}
            min_bar = item.get("min") or {}
            ext_price = _safe_float(last.get("p") or min_bar.get("c"))
        if ext_price <= 0:
            return None
        prev_vol = int(prev.get("v") or 1) or 1
        rvol = ext_vol / prev_vol if prev_vol else 1.0
        return ext_price, ext_vol, rvol

    if session == "AFTER_HOURS":
        after = item.get("afterHours") or {}
        ext_price = _safe_float(after.get("c") or after.get("h"))
        ext_vol = int(after.get("v") or 0)
        if ext_price <= 0:
            return None
        day = item.get("day") or {}
        day_vol = int(day.get("v") or prev.get("v") or 1) or 1
        rvol = ext_vol / day_vol if day_vol else 1.0
        return ext_price, ext_vol, rvol

    return None


def _collect_catalyst_from_news(news_items: list) -> ExtendedCatalystResult:
    best: ExtendedCatalystResult | None = None
    for item in news_items[:10]:
        if isinstance(item, dict):
            headline = str(item.get("title") or "")
            body = str(item.get("description") or item.get("summary") or "")
            pub = str(item.get("published_utc") or item.get("published_at") or "")
            source = str(item.get("publisher") or item.get("source") or "news")
            filing = str(item.get("filing_type") or "")
        else:
            headline = getattr(item, "title", "") or ""
            body = getattr(item, "summary", "") or ""
            pub = getattr(item, "published_at", "") or ""
            source = "news"
            filing = ""
        age_h = _parse_news_age_hours(pub)
        if age_h > NEWS_MAX_AGE_HOURS:
            continue
        result = classify_extended_catalyst(
            headline=headline,
            body=body,
            filing_type=filing,
            source=source,
            published_at=pub,
        )
        if result.has_confirmed_news and (best is None or pub > best.catalyst_published_at):
            best = result
    return best or classify_extended_catalyst()


def _build_risk_flags(
    *,
    market_cap: float,
    float_shares: float,
    catalyst_type: str,
) -> list[str]:
    flags: list[str] = []
    if 0 < market_cap < MICRO_CAP_THRESHOLD or 0 < float_shares < LOW_FLOAT_THRESHOLD:
        flags.append("سهم صغير — عالي المخاطر")
    if catalyst_type == "REVERSE_SPLIT":
        flags.append("انقسام عكسي — خطر")
    if catalyst_type == "DELISTING":
        flags.append("خطر الشطب")
    if catalyst_type == "OFFERING_DILUTION":
        flags.append("طرح / ت dillution — خطر")
    return flags


def evaluate_gap(
    *,
    symbol: str,
    name: str = "",
    session: MarketSession,
    previous_close: float,
    extended_price: float,
    extended_volume: int,
    relative_volume: float = 0.0,
    news_headline: str = "",
    news_body: str = "",
    news_source: str = "news",
    news_published_at: str = "",
    market_cap: float = 0.0,
    float_shares: float = 0.0,
) -> ExtendedGapDetection | None:
    """Evaluate a single symbol — used by scanner and tests."""
    if session not in ("PRE_MARKET", "AFTER_HOURS"):
        return None
    if not (MIN_PRICE_USD <= extended_price <= MAX_PRICE_USD):
        return None

    gap_pct = compute_extended_gap_pct(extended_price, previous_close)
    if gap_pct < WATCH_GAP_PCT:
        return None

    if news_headline:
        catalyst = classify_extended_catalyst(
            headline=news_headline,
            body=news_body,
            source=news_source,
            published_at=news_published_at,
        )
        has_recent = _parse_news_age_hours(news_published_at) <= NEWS_MAX_AGE_HOURS
    else:
        catalyst = classify_extended_catalyst()
        has_recent = False

    if relative_volume <= 0 and extended_volume > 0:
        relative_volume = max(relative_volume, extended_volume / max(WATCH_MIN_VOLUME, 1))

    stage = determine_detection_stage(
        gap_pct,
        extended_volume,
        has_recent_news=has_recent and catalyst.has_confirmed_news,
        relative_volume=relative_volume,
    )
    if stage is None:
        return None

    risk_flags = _build_risk_flags(
        market_cap=market_cap,
        float_shares=float_shares,
        catalyst_type=catalyst.catalyst_type,
    )
    if risk_flags and "عالي المخاطر" not in " ".join(risk_flags):
        pass
    elif 0 < market_cap < MICRO_CAP_THRESHOLD:
        risk_flags.append("Micro-cap — عالي المخاطر")

    late = is_late_chase(
        previous_close=previous_close,
        extended_price=extended_price,
        extended_gap_pct=gap_pct,
    )

    return ExtendedGapDetection(
        symbol=symbol.upper(),
        name=name or symbol.upper(),
        session=session,
        previous_close=round(previous_close, 4),
        extended_price=round(extended_price, 4),
        extended_gap_pct=gap_pct,
        extended_volume=extended_volume,
        relative_volume=round(relative_volume, 2),
        detection_stage=stage,
        catalyst_type=catalyst.catalyst_type,
        catalyst_title_ar=catalyst.catalyst_title_ar or CATALYST_TITLE_AR.get(catalyst.catalyst_type, ""),
        catalyst_source=catalyst.catalyst_source,
        catalyst_published_at=catalyst.catalyst_published_at,
        has_confirmed_news=catalyst.has_confirmed_news,
        risk_flags_ar=risk_flags,
        detected_at=_utcnow().isoformat(),
        is_late_chase=late,
        market_cap=market_cap,
        float_shares=float_shares,
    )


def scan_snapshot_raw(
    snapshot_raw: dict[str, dict],
    *,
    session: MarketSession | None = None,
    news_by_symbol: dict[str, list] | None = None,
    metadata_by_symbol: dict[str, dict] | None = None,
) -> list[ExtendedGapDetection]:
    session = session or get_us_market_session()
    if session not in ("PRE_MARKET", "AFTER_HOURS"):
        return []

    news_by_symbol = news_by_symbol or {}
    metadata_by_symbol = metadata_by_symbol or {}
    results: list[ExtendedGapDetection] = []

    for sym, item in snapshot_raw.items():
        quote = _extract_extended_quote(item, session)
        if not quote:
            continue
        ext_price, ext_vol, rvol = quote
        prev = item.get("prevDay") or {}
        previous_close = _safe_float(prev.get("c"))
        meta = metadata_by_symbol.get(sym.upper(), {})
        news_items = news_by_symbol.get(sym.upper(), [])
        catalyst = _collect_catalyst_from_news(news_items)

        det = evaluate_gap(
            symbol=sym,
            name=str(meta.get("name") or sym),
            session=session,
            previous_close=previous_close,
            extended_price=ext_price,
            extended_volume=ext_vol,
            relative_volume=rvol,
            news_headline=catalyst.headline,
            news_body="",
            news_source=catalyst.catalyst_source,
            news_published_at=catalyst.catalyst_published_at,
            market_cap=_safe_float(meta.get("market_cap")),
            float_shares=_safe_float(meta.get("float_shares")),
        )
        if det:
            results.append(det)

    results.sort(key=lambda d: d.extended_gap_pct, reverse=True)
    return results


def apply_detection_to_engine(det: ExtendedGapDetection) -> None:
    """Push detection into live_confirmation_engine monitor pool without rebuilding it."""
    from services.live_confirmation_engine import CandidateState

    sym = det.symbol.upper()
    state = live_confirmation_engine._candidates.setdefault(
        sym, CandidateState(symbol=sym, name=det.name),
    )
    state.name = det.name
    state.last_price = det.extended_price
    state.last_volume = det.extended_volume
    state.change_percent = det.extended_gap_pct
    state.score = _stage_score(det.detection_stage)
    state.last_updated = det.detected_at
    state.entry_zone_low = round(det.previous_close * 1.001, 4)
    state.entry_zone_high = round(det.previous_close * 1.04, 4)
    state.stop_loss = round(det.previous_close * 0.97, 4)
    state.target_1 = round(det.extended_price * 1.03, 4)
    state.target_2 = round(det.extended_price * 1.06, 4)
    state.nomination_reasons = [
        f"{'قبل الافتتاح' if det.session == 'PRE_MARKET' else 'بعد الإغلاق'}: +{det.extended_gap_pct:.1f}%",
        det.catalyst_title_ar,
    ]
    if det.risk_flags_ar:
        state.nomination_reasons.extend(det.risk_flags_ar[:2])

    if det.is_late_chase:
        state.status = "CANCELLED"
        state.cancellation_reasons = [
            "تم رصد القفزة، لكن الدخول الآن مطاردة",
            "لا تدخل حتى يحدث تراجع وتأكيد جديد",
            "لا تطارد السهم",
        ]
    else:
        state.status = "WATCH"


def merge_monitor_pool(gap_symbols: list[str], base_pool: list[str]) -> list[str]:
    merged: list[str] = []
    for sym in gap_symbols + base_pool:
        s = sym.upper()
        if s and s not in merged:
            merged.append(s)
    return merged[:LIVE_MONITOR_POOL]


def sync_extended_gap_detector() -> list[ExtendedGapDetection]:
    """Run detector on scanner raw cache and wire into monitor pool + engine."""
    from services.market_scanner_service import market_scanner

    session = get_us_market_session()
    if session not in ("PRE_MARKET", "AFTER_HOURS"):
        extended_gap_registry.reset()
        return []

    news_by_symbol: dict[str, list] = {}
    for sym, snap in market_scanner._snapshots.items():
        if snap.news:
            news_by_symbol[sym] = [
                {"title": n.title, "published_utc": n.published_at, "publisher": getattr(n, "source", "news")}
                for n in snap.news
            ]

    detections = scan_snapshot_raw(
        market_scanner._snapshot_raw,
        session=session,
        news_by_symbol=news_by_symbol,
    )

    extended_gap_registry.reset()
    gap_symbols = [d.symbol for d in detections]
    base = list(market_scanner._rank_pool[:LIVE_MONITOR_POOL])
    merged = merge_monitor_pool(gap_symbols, base)
    live_confirmation_engine.set_monitor_symbols(merged)

    for det in detections:
        extended_gap_registry.register(det)
        apply_detection_to_engine(det)

    if detections:
        logger.info(
            "Extended gap detector: session=%s found=%d top=%s gap=%.1f%%",
            session,
            len(detections),
            detections[0].symbol,
            detections[0].extended_gap_pct,
        )
    return detections
