from datetime import datetime, timedelta, timezone

import pandas as pd

from analysis.spx_options_engine import evaluate_spx


def _bars(n: int = 80, step: float = 1.0) -> pd.DataFrame:
    start = datetime.now(timezone.utc) - timedelta(minutes=n * 5)
    rows = []
    price = 5000.0
    for i in range(n):
        price += step
        rows.append({
            "open": price - 0.5,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1000 + (500 if i == n - 1 else 0),
            "timestamp": start + timedelta(minutes=i * 5),
        })
    return pd.DataFrame(rows)


def test_spx_never_trades_without_options_gate():
    df = _bars()
    signal = evaluate_spx(df, df, df, options_ready=False)
    assert signal.symbol == "I:SPX"
    assert signal.decision == "NO TRADE"


def test_spx_can_be_actionable_only_after_options_gate():
    df = _bars(step=2.0)
    signal = evaluate_spx(df, df, df, options_ready=True)
    assert signal.symbol == "I:SPX"
    assert signal.decision in {"CALL", "NO TRADE"}
