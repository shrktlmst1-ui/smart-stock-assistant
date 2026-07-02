"""Journal service — log signals and evaluate open trade outcomes."""

from __future__ import annotations

import logging

from analysis.ai_learning import diagnose_failure, learn_from_closed_trade
from database.trading_journal import close_trade, get_open_trades, log_journal_entry
from models.trading import AISignal, ConfidenceBreakdown, MarketRegime

logger = logging.getLogger(__name__)


def record_signal(
    symbol: str,
    ai_signal: AISignal,
    regime: MarketRegime,
    confidence_breakdown: ConfidenceBreakdown | None,
    timeframe: str = "live",
) -> int:
    """Log every actionable or Wait signal for journal tracking."""
    factors = {}
    if confidence_breakdown:
        factors = confidence_breakdown.model_dump()

    return log_journal_entry(
        symbol=symbol,
        signal=ai_signal.signal,
        entry=ai_signal.entry,
        stop_loss=ai_signal.stop_loss,
        target_1=ai_signal.target_1,
        target_2=ai_signal.target_2,
        confidence=ai_signal.confidence,
        ai_score=ai_signal.ai_score,
        market_regime=regime.regime,
        risk_reward_ratio=ai_signal.risk_reward_ratio,
        reason=ai_signal.reason,
        factor_scores=factors,
        strategy="production_confluence",
        timeframe=timeframe,
    )


def evaluate_open_trades(symbol: str, price: float) -> int:
    """Check open journal trades against live price; close and trigger learning."""
    closed = 0
    for trade in get_open_trades(symbol):
        if trade["signal"] not in ("Buy", "Sell"):
            continue
        entry = trade["entry"]
        stop = trade["stop_loss"]
        tp1 = trade["target_1"]
        tp2 = trade["target_2"]
        is_buy = trade["signal"] == "Buy"
        result = None
        exit_price = price
        profit_pct = 0.0

        if is_buy:
            if price <= stop:
                result, exit_price = "Loss", stop
                profit_pct = (stop - entry) / entry * 100
            elif price >= tp2:
                result, exit_price = "Win", tp2
                profit_pct = (tp2 - entry) / entry * 100
            elif price >= tp1:
                result, exit_price = "Win", tp1
                profit_pct = (tp1 - entry) / entry * 100
        else:
            if price >= stop:
                result, exit_price = "Loss", stop
                profit_pct = (entry - stop) / entry * 100
            elif price <= tp2:
                result, exit_price = "Win", tp2
                profit_pct = (entry - tp2) / entry * 100
            elif price <= tp1:
                result, exit_price = "Win", tp1
                profit_pct = (entry - tp1) / entry * 100

        if result:
            close_trade(trade["id"], result, round(profit_pct, 3), exit_price)
            factors = trade.get("factor_scores") or {}
            failure = diagnose_failure(factors, trade["signal"]) if result == "Loss" else None
            learn_from_closed_trade(result, trade["signal"], factors, failure)
            closed += 1
            logger.info("Closed trade %s %s: %s %.2f%%", symbol, trade["id"], result, profit_pct)
    return closed
