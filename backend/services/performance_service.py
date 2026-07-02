"""Performance analytics from trading journal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database.trading_journal import get_journal_entries


def get_performance_metrics() -> dict:
    all_closed = get_journal_entries(limit=5000, result=None)
    closed = [t for t in all_closed if t.get("result") in ("Win", "Loss")]
    open_trades = [t for t in all_closed if t.get("result") == "open"]
    actionable = [t for t in all_closed if t.get("signal") in ("Buy", "Sell")]

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()
    month_start = (now - timedelta(days=30)).isoformat()

    wins = [t for t in closed if t["result"] == "Win"]
    losses = [t for t in closed if t["result"] == "Loss"]

    win_rate = round(len(wins) / len(closed) * 100, 2) if closed else 0.0
    total_profit = round(sum(t["profit_pct"] for t in wins if t["profit_pct"] > 0), 2)
    total_loss = round(abs(sum(t["profit_pct"] for t in losses if t["profit_pct"] < 0)), 2)
    avg_confidence = round(
        sum(t["confidence"] for t in actionable) / len(actionable), 1
    ) if actionable else 0.0

    today_trades = sum(1 for t in all_closed if t["created_at"] >= today_start)
    weekly_trades = sum(1 for t in all_closed if t["created_at"] >= week_start)
    monthly_trades = sum(1 for t in all_closed if t["created_at"] >= month_start)

    best_strategy = _best_strategy(closed)

    return {
        "win_rate": win_rate,
        "total_trades": len(closed),
        "open_trades": len(open_trades),
        "today_trades": today_trades,
        "weekly_trades": weekly_trades,
        "monthly_trades": monthly_trades,
        "total_profit_pct": total_profit,
        "total_loss_pct": total_loss,
        "net_profit_pct": round(total_profit - total_loss, 2),
        "average_confidence": avg_confidence,
        "best_performing_strategy": best_strategy,
        "wins": len(wins),
        "losses": len(losses),
    }


def _best_strategy(closed: list[dict]) -> str:
    if not closed:
        return "production_confluence"
    by_regime: dict[str, list[dict]] = {}
    for t in closed:
        regime = t.get("market_regime", "Neutral")
        by_regime.setdefault(regime, []).append(t)
    best_regime = "Neutral"
    best_wr = -1.0
    for regime, trades in by_regime.items():
        wins = sum(1 for t in trades if t["result"] == "Win")
        wr = wins / len(trades) if trades else 0
        if wr > best_wr:
            best_wr = wr
            best_regime = regime
    return f"{best_regime} ({best_wr * 100:.0f}% WR)"
