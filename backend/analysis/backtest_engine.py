"""Backtesting Engine — replay signals on historical Massive/Polygon OHLCV."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analysis.ai_signal_engine import generate_ai_signal
from models.trading import NewsIntelligence

TIMEFRAMES = {
    "1m": (1, "minute", 5, 5000),
    "5m": (5, "minute", 14, 5000),
    "15m": (15, "minute", 30, 5000),
    "1h": (1, "hour", 90, 5000),
    "4h": (4, "hour", 180, 3000),
    "1D": (1, "day", 730, 500),
}

NEUTRAL_NEWS = NewsIntelligence()
MIN_BARS = 80
STEP = 5
MAX_HOLD_BARS = 48


@dataclass
class BacktestTrade:
    symbol: str
    signal: str
    entry: float
    stop_loss: float
    target_1: float
    target_2: float
    entry_idx: int
    exit_idx: int
    exit_price: float
    result: str
    profit_pct: float
    risk_reward: float


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    avg_risk_reward: float = 0.0
    total_return_pct: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)


def _simulate_exit(
    df: pd.DataFrame,
    entry_idx: int,
    signal: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
) -> tuple[int, float, str, float]:
    is_buy = signal == "Buy"
    for j in range(entry_idx + 1, min(entry_idx + MAX_HOLD_BARS + 1, len(df))):
        bar = df.iloc[j]
        hi, lo, cl = float(bar["high"]), float(bar["low"]), float(bar["close"])
        if is_buy:
            if lo <= stop:
                pct = (stop - entry) / entry * 100
                return j, stop, "Loss", pct
            if hi >= tp2:
                pct = (tp2 - entry) / entry * 100
                return j, tp2, "Win", pct
            if hi >= tp1:
                pct = (tp1 - entry) / entry * 100
                return j, tp1, "Win", pct
        else:
            if hi >= stop:
                pct = (entry - stop) / entry * 100
                return j, stop, "Loss", pct
            if lo <= tp2:
                pct = (entry - tp2) / entry * 100
                return j, tp2, "Win", pct
            if lo <= tp1:
                pct = (entry - tp1) / entry * 100
                return j, tp1, "Win", pct
    last = float(df.iloc[min(entry_idx + MAX_HOLD_BARS, len(df) - 1)]["close"])
    if is_buy:
        pct = (last - entry) / entry * 100
    else:
        pct = (entry - last) / entry * 100
    result = "Win" if pct > 0 else "Loss"
    return min(entry_idx + MAX_HOLD_BARS, len(df) - 1), last, result, pct


def run_backtest(symbol: str, df: pd.DataFrame, timeframe: str) -> BacktestResult:
    result = BacktestResult(symbol=symbol.upper(), timeframe=timeframe)
    if len(df) < MIN_BARS + MAX_HOLD_BARS:
        return result

    daily_df = None
    if timeframe == "1D":
        daily_df = df

    trades: list[BacktestTrade] = []
    last_entry_idx = -MAX_HOLD_BARS

    for i in range(MIN_BARS, len(df) - 5, STEP):
        if i - last_entry_idx < MAX_HOLD_BARS:
            continue
        window = df.iloc[: i + 1].copy()
        price = float(window["close"].iloc[-1])
        if len(window) < 2:
            continue
        prev = float(window["close"].iloc[-2])
        change_pct = (price - prev) / prev * 100 if prev else 0.0

        ai_signal, *_ = generate_ai_signal(symbol, window, daily_df, price, change_pct, NEUTRAL_NEWS)
        if ai_signal.signal not in ("Buy", "Sell"):
            continue

        exit_idx, exit_price, trade_result, profit_pct = _simulate_exit(
            df, i, ai_signal.signal, ai_signal.entry,
            ai_signal.stop_loss, ai_signal.target_1, ai_signal.target_2,
        )
        trades.append(BacktestTrade(
            symbol=symbol.upper(),
            signal=ai_signal.signal,
            entry=ai_signal.entry,
            stop_loss=ai_signal.stop_loss,
            target_1=ai_signal.target_1,
            target_2=ai_signal.target_2,
            entry_idx=i,
            exit_idx=exit_idx,
            exit_price=round(exit_price, 2),
            result=trade_result,
            profit_pct=round(profit_pct, 3),
            risk_reward=ai_signal.risk_reward_ratio,
        ))
        last_entry_idx = i

    return _compute_metrics(result, trades)


def _compute_metrics(result: BacktestResult, trades: list[BacktestTrade]) -> BacktestResult:
    result.trades = trades
    result.total_trades = len(trades)
    if not trades:
        return result

    wins = [t for t in trades if t.result == "Win"]
    losses = [t for t in trades if t.result == "Loss"]
    result.wins = len(wins)
    result.losses = len(losses)
    result.win_rate = round(result.wins / result.total_trades * 100, 2)
    result.loss_rate = round(result.losses / result.total_trades * 100, 2)

    gross_profit = sum(t.profit_pct for t in wins if t.profit_pct > 0)
    gross_loss = abs(sum(t.profit_pct for t in losses if t.profit_pct < 0))
    result.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else round(gross_profit, 2)

    returns = [t.profit_pct for t in trades]
    result.total_return_pct = round(sum(returns), 2)
    result.avg_risk_reward = round(float(np.mean([t.risk_reward for t in trades])), 2)

    equity = [100.0]
    for r in returns:
        equity.append(equity[-1] * (1 + r / 100))
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        peak = max(peak, e)
        dd = (peak - e) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
    result.max_drawdown = round(max_dd, 2)

    if len(returns) > 1:
        std = float(np.std(returns))
        mean = float(np.mean(returns))
        result.sharpe_ratio = round(mean / std * math.sqrt(252), 2) if std > 0 else 0.0

    return result


def backtest_result_to_dict(r: BacktestResult) -> dict:
    return {
        "symbol": r.symbol,
        "timeframe": r.timeframe,
        "total_trades": r.total_trades,
        "wins": r.wins,
        "losses": r.losses,
        "win_rate": r.win_rate,
        "loss_rate": r.loss_rate,
        "profit_factor": r.profit_factor,
        "max_drawdown": r.max_drawdown,
        "sharpe_ratio": r.sharpe_ratio,
        "avg_risk_reward": r.avg_risk_reward,
        "total_return_pct": r.total_return_pct,
        "trade_count": len(r.trades),
    }
