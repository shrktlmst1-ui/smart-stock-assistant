"""Backtest service — run historical simulations via Polygon data."""

from __future__ import annotations

from analysis.backtest_engine import TIMEFRAMES, backtest_result_to_dict, run_backtest
from services.polygon_client import PolygonClient


async def run_symbol_backtest(symbol: str, timeframe: str, client: PolygonClient | None = None) -> dict:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Invalid timeframe. Use: {', '.join(TIMEFRAMES)}")
    client = client or PolygonClient()
    df = await client.get_bars_for_timeframe(symbol, timeframe)
    if df.empty:
        return backtest_result_to_dict(run_backtest(symbol, df, timeframe))
    result = run_backtest(symbol, df, timeframe)
    return backtest_result_to_dict(result)


async def run_multi_backtest(
    symbols: list[str],
    timeframes: list[str] | None = None,
) -> list[dict]:
    client = PolygonClient()
    tfs = timeframes or ["1h", "1D"]
    results = []
    for sym in symbols:
        for tf in tfs:
            try:
                results.append(await run_symbol_backtest(sym, tf, client))
            except Exception as e:
                results.append({"symbol": sym, "timeframe": tf, "error": str(e)})
    await client.close()
    return results
