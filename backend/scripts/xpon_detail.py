"""One-off XPON detail dump for replay validation."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.replay_xpon_premove import (
    SESSION_DATE,
    SYMBOL,
    _filter_premarket_regular,
    analyze_causal,
)
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient

ET = ZoneInfo("America/New_York")


async def run() -> None:
    client = PolygonClient()
    try:
        bars = await client.get_minute_bars_on_date(SYMBOL, SESSION_DATE)
        prior_date = (datetime.strptime(SESSION_DATE, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        prior_bars = await client.get_minute_bars_on_date(SYMBOL, prior_date)
        snap = await client.get_snapshot(SYMBOL)
        news_raw = await fetch_stock_news(client, SYMBOL, limit=20)
    finally:
        await client.close()

    bars = _filter_premarket_regular(bars)
    prev = float((snap.get("prevDay") or {}).get("c") or 3.435)

    print("ALL RAW MINUTE BARS:")
    for _, row in bars.iterrows():
        ts = row["timestamp"].tz_convert(ET)
        print(
            f"  {ts.strftime('%H:%M:%S')} "
            f"O={row['open']:.4f} H={row['high']:.4f} L={row['low']:.4f} "
            f"C={row['close']:.4f} V={int(row['volume'])}"
        )

    print("\nCAUSAL SCORES FROM BAR 3+:")
    for bi in range(2, len(bars)):
        t = analyze_causal(bars, prior_bars, news_raw, prev, bi)
        print(
            f"  {t['time_et']} P={t['price']} Chg={t['change_pct']}% "
            f"Sc={t['score']} {t['status']} late={t['late_guard']}"
        )

    low_idx = bars["low"].astype(float).idxmin()
    low_row = bars.loc[low_idx]
    high_idx = bars["high"].astype(float).idxmax()
    high_row = bars.loc[high_idx]
    print()
    print("SESSION LOW", float(low_row["low"]), "at", low_row["timestamp"].tz_convert(ET))
    print("SESSION HIGH", float(high_row["high"]), "at", high_row["timestamp"].tz_convert(ET))
    print("PREV CLOSE", prev)


if __name__ == "__main__":
    asyncio.run(run())
