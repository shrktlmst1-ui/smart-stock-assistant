"""AI Learning — deterministic weight updates from closed trade outcomes."""

from __future__ import annotations

import json
from pathlib import Path

from analysis.scoring import WEIGHTS, normalize_weights

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "data" / "ai_weights.json"

FACTOR_MAP = {
    "trend": "trend",
    "volume": "volume",
    "liquidity": "liquidity",
    "smc": "smc",
    "momentum": "momentum",
    "news": "news",
}


def load_weights() -> dict[str, float]:
    if WEIGHTS_PATH.exists():
        try:
            data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
            merged = {**WEIGHTS, **data}
            return normalize_weights(merged)
        except (json.JSONDecodeError, OSError):
            pass
    return dict(WEIGHTS)


def save_weights(weights: dict[str, float]) -> None:
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_PATH.write_text(json.dumps(normalize_weights(weights), indent=2), encoding="utf-8")


def diagnose_failure(factor_scores: dict[str, float], signal: str) -> str:
    """Identify weakest confirmed factor on a losing trade."""
    if not factor_scores:
        return "insufficient_factor_data"
    is_buy = signal in ("Buy", "Strong Buy")
    weak: list[tuple[str, float]] = []
    for key, score in factor_scores.items():
        if key == "overall":
            continue
        mapped = FACTOR_MAP.get(key, key)
        if is_buy and score < 55:
            weak.append((mapped, score))
        elif not is_buy and score > 45:
            weak.append((mapped, score))
    if not weak:
        return "market_reversal"
    weakest = min(weak, key=lambda x: x[1] if is_buy else -x[1])
    return f"weak_{weakest[0]}"


def learn_from_closed_trade(
    result: str,
    signal: str,
    factor_scores: dict[str, float],
    failure_reason: str | None = None,
) -> dict[str, float]:
    """Adjust weights deterministically — no randomness."""
    weights = load_weights()
    adjust = 0.015

    if result == "Win":
        if factor_scores:
            best = max(
                ((k, v) for k, v in factor_scores.items() if k != "overall"),
                key=lambda x: x[1],
                default=("trend", 50),
            )
            key = FACTOR_MAP.get(best[0], best[0])
            if key in weights:
                weights[key] = min(0.45, weights[key] + adjust)
    elif result == "Loss":
        reason = failure_reason or diagnose_failure(factor_scores, signal)
        if reason.startswith("weak_"):
            key = reason.replace("weak_", "")
            if key in weights:
                weights[key] = max(0.05, weights[key] - adjust)
        else:
            weights["momentum"] = max(0.05, weights.get("momentum", 0.1) - adjust * 0.5)

    weights = normalize_weights(weights)
    save_weights(weights)
    return weights
