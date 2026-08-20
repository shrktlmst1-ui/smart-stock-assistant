"""Synthetic news and market ticks for dev/test — never used in production."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from market_pulse.providers.base import AggregateMinute, QuoteTick, RawNewsItem, TradeTick


FIXTURE_SYMBOLS = ("NVDA", "TSLA", "AMD")


def fixture_news_items() -> list[RawNewsItem]:
    now = datetime.now(timezone.utc)
    return [
        RawNewsItem(
            provider_id="fixture-nvda-1",
            headline="NVDA beats estimates and raises guidance",
            url="https://example.com/fixture/nvda",
            published_at=now - timedelta(seconds=45),
            symbols=["NVDA"],
            body="Earnings beat with strong data-center demand",
        ),
        RawNewsItem(
            provider_id="fixture-tsla-1",
            headline="TSLA wins contract partnership upgrade",
            url="https://example.com/fixture/tsla",
            published_at=now - timedelta(seconds=90),
            symbols=["TSLA"],
            body="Analyst upgrade and contract award",
        ),
        RawNewsItem(
            provider_id="fixture-amd-1",
            headline="AMD announces public offering dilution",
            url="https://example.com/fixture/amd",
            published_at=now - timedelta(seconds=30),
            symbols=["AMD"],
            body="Registered direct offering",
        ),
    ]


def push_fixture_ticks(engine, now_ms: int | None = None) -> None:
    """Inject synthetic ticks into the pulse engine."""
    now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    profiles = {
        "NVDA": {"price": 106.0, "bid": 105.95, "ask": 106.05, "vol": 12000},
        "TSLA": {"price": 248.5, "bid": 248.3, "ask": 248.7, "vol": 8000},
        "AMD": {"price": 162.0, "bid": 161.5, "ask": 162.8, "vol": 5000},
    }
    for sym, p in profiles.items():
        engine.ingest_quote(
            QuoteTick(sym, p["bid"], p["ask"], 500, 500, now_ms)
        )
        for i in range(12):
            engine.ingest_trade(
                TradeTick(sym, p["price"] + i * 0.02, 400, now_ms - (12 - i) * 2000)
            )
        engine.ingest_aggregate(
            AggregateMinute(
                sym,
                p["price"] - 2,
                p["price"] + 1,
                p["price"] - 3,
                p["price"],
                p["vol"] // 2,
                p["price"] - 0.5,
                now_ms - 60_000,
            )
        )
        engine.ingest_aggregate(
            AggregateMinute(
                sym,
                p["price"],
                p["price"] + 2,
                p["price"] - 0.5,
                p["price"] + 1,
                p["vol"],
                p["price"] + 0.5,
                now_ms,
            )
        )
        state = engine._get_state(sym)
        state.baseline_minute_volume = 1000
        state.day_high = p["price"] + 1
