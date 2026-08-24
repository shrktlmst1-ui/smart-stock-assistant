"""Pre-Move signal validation — reject contradictory outputs."""

from __future__ import annotations

from models.pre_move import PreMoveSignal


def validate_signal(sig: PreMoveSignal) -> tuple[bool, str]:
    """Final validation before user-facing display."""
    if sig.status == "INSUFFICIENT_DATA":
        return False, "INSUFFICIENT_DATA"

    if sig.pre_move_score <= 0 and sig.status not in ("NO_SETUP", "TOO_LATE_TO_CHASE"):
        return False, "SCORE_ZERO_WITH_STATUS"

    if sig.status in ("EARLY_ENTRY", "HIGH_CONVICTION_EARLY", "CONFIRMED_ENTRY"):
        if sig.liquidity.liquidity_score < 40:
            return False, "LOW_LIQUIDITY"
        if sig.risk_level == "مرتفع" and sig.pre_move_score < 75:
            return False, "HIGH_RISK_LOW_SCORE"
        if sig.risk_reward > 0 and sig.risk_reward < 1.0:
            return False, "BAD_RISK_REWARD"
        if sig.late_move.is_too_late:
            return False, "TOO_LATE_TO_CHASE"

    if sig.status == "CONFIRMED_ENTRY" and sig.pre_move_score < 60:
        return False, "CONFIRMED_WITHOUT_SCORE"

    if sig.data_age_seconds > 180:
        return False, "STALE_DATA"

    return True, ""
