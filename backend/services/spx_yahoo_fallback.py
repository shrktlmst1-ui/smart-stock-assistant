"""Fallback SPX market-data reader used when the configured index feed is unavailable."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX"


async def get_spx_fallback_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetch recent SPX (^SPX) bars from Yahoo and build 1h/15m/5m frames.

    This is deliberately an underlying-only fallback. It does not substitute SPX
    options data; if the options feed is unavailable the signal remains NO TRADE.
    """
    end = int(time.time())
    start = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    params = {
        "period1": start,
        "period2": end,
        "interval": "5m",
        "includePrePost": "true",
        "events": "div,splits",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(YAHOO_CHART_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("Yahoo SPX fallback returned no chart data")

    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [None])[0] or {}
    rows = []
    for i, ts in enumerate(timestamps):
        close = (quote.get("close") or [None])[i] if i < len(quote.get("close") or []) else None
        if close is None:
            continue
        rows.append(
            {
                "timestamp": pd.to_datetime(ts, unit="s", utc=True),
                "open": (quote.get("open") or [None])[i],
                "high": (quote.get("high") or [None])[i],
                "low": (quote.get("low") or [None])[i],
                "close": close,
                "volume": (quote.get("volume") or [0])[i] or 0,
            }
        )

    base = pd.DataFrame(rows)
    if base.empty:
        raise RuntimeError("Yahoo SPX fallback returned empty bars")
    base = base.dropna(subset=["open", "high", "low", "close"]).set_index("timestamp").sort_index()

    def resample(rule: str, limit: int) -> pd.DataFrame:
        frame = base.resample(rule).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna(subset=["open", "high", "low", "close"])
        return frame.tail(limit).reset_index(drop=True)

    return resample("1h", 120), resample("15min", 160), resample("5min", 220)
