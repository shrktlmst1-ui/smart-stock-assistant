"""Deterministic news catalyst classification — no external LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass

STRONG_RISK_PATTERNS: list[tuple[str, str]] = [
    (r"\b(offering|public offering|registered direct)\b", "offering"),
    (r"\b(dilution|dilutive)\b", "dilution"),
    (r"\b(shelf registration|shelf offering)\b", "shelf_registration"),
    (r"\b(reverse split|stock split reverse)\b", "reverse_split"),
    (r"\b(bankruptcy|chapter 11)\b", "bankruptcy"),
    (r"\b(delisting|delist)\b", "delisting"),
    (r"\b(sec investigation|sec probe|doj investigation)\b", "sec_investigation"),
    (r"\b(fda rejection|fda complete response letter|crl)\b", "fda_rejection"),
]

POSITIVE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(beat(s)? estimates|earnings beat|tops estimates)\b", "earnings_beat"),
    (r"\b(fda approval|fda approves)\b", "fda_approval"),
    (r"\b(contract award|wins contract|partnership)\b", "contract_partnership"),
    (r"\b(upgrade(d)? to buy|price target raised|analyst upgrade)\b", "upgrade"),
    (r"\b(acquisition|merger agreement|buyout)\b", "m_and_a"),
]

NEGATIVE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(miss(es)? estimates|earnings miss|below estimates)\b", "earnings_miss"),
    (r"\b(downgrade(d)?|price target cut|analyst downgrade)\b", "downgrade"),
    (r"\b(layoff|workforce reduction|guidance cut)\b", "negative_guidance"),
]


@dataclass
class CatalystClassification:
    sentiment: str  # positive | negative | neutral
    trigger_type: str
    risk_flags: list[str]
    score_component: float  # 0-30 raw catalyst strength


def _match_patterns(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for pattern, label in patterns:
        if re.search(pattern, lower, re.IGNORECASE):
            found.append(label)
    return found


def classify_catalyst(headline: str, body: str = "") -> CatalystClassification:
    text = f"{headline} {body}".strip()
    risk_flags = _match_patterns(text, STRONG_RISK_PATTERNS)
    if risk_flags:
        return CatalystClassification(
            sentiment="negative",
            trigger_type=risk_flags[0],
            risk_flags=risk_flags,
            score_component=max(0.0, 10.0 - len(risk_flags) * 3),
        )

    positives = _match_patterns(text, POSITIVE_PATTERNS)
    negatives = _match_patterns(text, NEGATIVE_PATTERNS)

    if positives and not negatives:
        strength = min(30.0, 18.0 + len(positives) * 4.0)
        return CatalystClassification(
            sentiment="positive",
            trigger_type=positives[0],
            risk_flags=[],
            score_component=strength,
        )
    if negatives and not positives:
        return CatalystClassification(
            sentiment="negative",
            trigger_type=negatives[0],
            risk_flags=negatives,
            score_component=max(5.0, 12.0 - len(negatives) * 2),
        )
    if positives and negatives:
        return CatalystClassification(
            sentiment="neutral",
            trigger_type="mixed",
            risk_flags=negatives,
            score_component=10.0,
        )
    return CatalystClassification(
        sentiment="neutral",
        trigger_type="general",
        risk_flags=[],
        score_component=8.0,
    )


def has_strong_risk(risk_flags: list[str]) -> bool:
    strong = {
        "offering", "dilution", "shelf_registration", "reverse_split",
        "bankruptcy", "delisting", "sec_investigation", "fda_rejection",
    }
    return bool(strong.intersection(risk_flags))
