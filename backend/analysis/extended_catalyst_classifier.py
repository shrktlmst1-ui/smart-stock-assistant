"""Extended-hours news & SEC filing catalyst classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CatalystType = Literal[
    "EARNINGS",
    "CONTRACT",
    "FDA",
    "MERGER",
    "NASDAQ_COMPLIANCE",
    "DELISTING",
    "OFFERING_DILUTION",
    "REVERSE_SPLIT",
    "OTHER",
    "NO_CONFIRMED_NEWS",
]

CATALYST_TITLE_AR: dict[str, str] = {
    "EARNINGS": "أرباح / تقارير مالية",
    "CONTRACT": "عقد أو شراكة",
    "FDA": "قرار FDA",
    "MERGER": "اندماج أو استحواذ",
    "NASDAQ_COMPLIANCE": "استعادة شروط ناسداك",
    "DELISTING": "خطر شطب",
    "OFFERING_DILUTION": "طرح / ت dillution",
    "REVERSE_SPLIT": "انقسام عكسي",
    "OTHER": "محفز آخر",
    "NO_CONFIRMED_NEWS": "لا يوجد خبر مؤكد",
}

_COMPLIANCE = re.compile(
    r"(regained|regains|restored|restore).{0,40}(nasdaq|listing).{0,40}(compliance|minimum bid|bid price|"
    r"listing requirement|listing standards)|"
    r"(nasdaq|listing).{0,40}(minimum bid|bid price|compliance|listing requirement)",
    re.I,
)
_EARNINGS = re.compile(
    r"\b(earnings|eps|revenue|q[1-4]\s+\d{4}|quarterly results|beats estimates|misses estimates)\b",
    re.I,
)
_CONTRACT = re.compile(r"\b(contract award|wins contract|partnership|agreement with)\b", re.I)
_FDA = re.compile(r"\b(fda approval|fda approves|fda clearance|pdufa|complete response letter)\b", re.I)
_MERGER = re.compile(r"\b(merger|acquisition|buyout|takeover|to acquire)\b", re.I)
_DELISTING = re.compile(r"\b(delisting|delist|nasdaq notice.{0,30}deficiency)\b", re.I)
_OFFERING = re.compile(r"\b(public offering|registered direct|shelf offering|dilution|dilutive)\b", re.I)
_REVERSE_SPLIT = re.compile(r"\b(reverse split|stock split reverse|1-for-\d+)\b", re.I)
_SEC_FILING = re.compile(r"\b(8-k|6-k|form 8-k|form 6-k)\b", re.I)


@dataclass
class ExtendedCatalystResult:
    catalyst_type: CatalystType
    catalyst_title_ar: str
    catalyst_source: str
    catalyst_published_at: str
    has_confirmed_news: bool
    headline: str = ""


def classify_extended_catalyst(
    *,
    headline: str = "",
    body: str = "",
    filing_type: str = "",
    source: str = "",
    published_at: str = "",
) -> ExtendedCatalystResult:
    """Classify catalyst — Nasdaq compliance checked before earnings."""
    text = f"{headline} {body} {filing_type}".strip()
    lower = text.lower()
    src = source or ("SEC" if _SEC_FILING.search(lower) else "news")

    if not text.strip():
        return ExtendedCatalystResult(
            catalyst_type="NO_CONFIRMED_NEWS",
            catalyst_title_ar=CATALYST_TITLE_AR["NO_CONFIRMED_NEWS"],
            catalyst_source="",
            catalyst_published_at=published_at,
            has_confirmed_news=False,
        )

    if _REVERSE_SPLIT.search(lower):
        return _result("REVERSE_SPLIT", src, published_at, text, True)
    if _DELISTING.search(lower):
        return _result("DELISTING", src, published_at, text, True)
    if _OFFERING.search(lower):
        return _result("OFFERING_DILUTION", src, published_at, text, True)
    if _COMPLIANCE.search(lower):
        return _result("NASDAQ_COMPLIANCE", src, published_at, text, True)
    if _FDA.search(lower):
        return _result("FDA", src, published_at, text, True)
    if _MERGER.search(lower):
        return _result("MERGER", src, published_at, text, True)
    if _CONTRACT.search(lower):
        return _result("CONTRACT", src, published_at, text, True)
    if _EARNINGS.search(lower) and not _COMPLIANCE.search(lower):
        return _result("EARNINGS", src, published_at, text, True)
    if _SEC_FILING.search(lower):
        return _result("OTHER", src, published_at, text, True)

    return _result("OTHER", src, published_at, text, bool(headline.strip()))


def _result(
    ctype: CatalystType,
    source: str,
    published_at: str,
    headline: str,
    confirmed: bool,
) -> ExtendedCatalystResult:
    return ExtendedCatalystResult(
        catalyst_type=ctype,
        catalyst_title_ar=CATALYST_TITLE_AR[ctype],
        catalyst_source=source,
        catalyst_published_at=published_at,
        has_confirmed_news=confirmed,
        headline=headline[:200],
    )
