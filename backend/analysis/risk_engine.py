"""Risk Engine — position sizing, ATR stops, dynamic take profit."""

from __future__ import annotations

from config import ACCOUNT_SIZE, RISK_PER_TRADE_PCT
from models.trading import MarketRegime, RiskAssessment, TrendAnalysis

# R-multiples for take-profit tiers (aligned with decision MIN R:R 2.0)
TP1_RR = 2.0
TP2_RR = 3.0


def validate_take_profits(
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    is_long: bool,
) -> tuple[float, float, float]:
    """Ensure stop/entry/TP ordering; recalculate from risk distance if invalid."""
    risk = abs(entry - stop)
    if risk <= 0:
        risk = max(entry * 0.01, 0.01)

    if is_long:
        if stop >= entry:
            stop = round(entry - risk, 2)
        if not (stop < entry < tp1 < tp2):
            tp1 = round(entry + risk * TP1_RR, 2)
            tp2 = round(entry + risk * TP2_RR, 2)
        if tp2 <= tp1:
            tp2 = round(tp1 + risk, 2)
    else:
        if stop <= entry:
            stop = round(entry + risk, 2)
        if not (tp2 < tp1 < entry < stop):
            tp1 = round(entry - risk * TP1_RR, 2)
            tp2 = round(entry - risk * TP2_RR, 2)
        if tp2 >= tp1:
            tp2 = round(tp1 - risk, 2)

    return round(stop, 2), round(tp1, 2), round(tp2, 2)


def _compute_take_profits(
    entry: float,
    stop: float,
    is_long: bool,
    support: float = 0.0,
    resistance: float = 0.0,
) -> tuple[float, float]:
    """Derive TP1/TP2 from risk distance and R-multiples; preserve ordering."""
    risk = abs(entry - stop)
    if risk <= 0:
        risk = max(entry * 0.01, 0.01)

    if is_long:
        tp1 = entry + risk * TP1_RR
        tp2 = entry + risk * TP2_RR
        if resistance > entry and resistance > tp1:
            capped = min(tp2, resistance)
            if capped > tp1:
                tp2 = capped
    else:
        tp1 = entry - risk * TP1_RR
        tp2 = entry - risk * TP2_RR
        if support > 0 and support < entry and support < tp1:
            capped = max(tp2, support)
            if capped < tp1:
                tp2 = capped

    _, tp1, tp2 = validate_take_profits(entry, stop, tp1, tp2, is_long)
    return tp1, tp2


def calculate_risk(
    signal: str,
    price: float,
    trend: TrendAnalysis,
    regime: MarketRegime,
    structure_low: float | None,
    structure_high: float | None,
    support: float,
    resistance: float,
) -> RiskAssessment:
    atr = trend.atr or price * 0.01
    entry = round(price, 2)

    if signal in ("Strong Buy", "Buy"):
        is_long = True
        atr_stop = round(min(structure_low or support, entry - atr * 1.5), 2)
        regime_mult = 1.3 if regime.regime == "Strong Bullish" else 1.15 if regime.regime == "Bullish" else 1.0
    elif signal in ("Strong Sell", "Sell"):
        is_long = False
        atr_stop = round(max(structure_high or resistance, entry + atr * 1.5), 2)
        regime_mult = 1.3 if regime.regime == "Strong Bearish" else 1.15 if regime.regime == "Bearish" else 1.0
    else:
        is_long = True
        atr_stop = round(entry - atr * 1.5, 2)
        regime_mult = 1.0

    tp1, tp2 = _compute_take_profits(entry, atr_stop, is_long, support, resistance)
    atr_stop, tp1, tp2 = validate_take_profits(entry, atr_stop, tp1, tp2, is_long)

    risk_per_share = abs(entry - atr_stop)
    if is_long:
        dynamic_tp = round(entry + risk_per_share * TP2_RR * regime_mult, 2)
        if dynamic_tp <= tp2:
            dynamic_tp = tp2
    else:
        dynamic_tp = round(entry - risk_per_share * TP2_RR * regime_mult, 2)
        if dynamic_tp >= tp2:
            dynamic_tp = tp2

    risk_pct = (risk_per_share / entry * 100) if entry else 0.0
    reward_per_share = abs(dynamic_tp - entry)
    reward_pct = (reward_per_share / entry * 100) if entry else 0.0
    rr = round(reward_per_share / risk_per_share, 2) if risk_per_share > 0 else 0.0

    max_loss = ACCOUNT_SIZE * (RISK_PER_TRADE_PCT / 100)
    shares = int(max_loss / risk_per_share) if risk_per_share > 0 else 0
    position_dollars = round(shares * entry, 2)

    return RiskAssessment(
        position_size_shares=shares,
        position_size_dollars=position_dollars,
        risk_percent=round(risk_pct, 2),
        reward_percent=round(reward_pct, 2),
        atr_stop=atr_stop,
        take_profit_1=tp1,
        take_profit_2=tp2,
        dynamic_take_profit=dynamic_tp,
        risk_reward_ratio=rr,
        max_loss_dollars=round(max_loss, 2),
        summary=f"Risk {risk_pct:.1f}% | Reward {reward_pct:.1f}% | R:R {rr} | {shares} shares",
    )
