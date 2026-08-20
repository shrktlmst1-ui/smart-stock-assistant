"""Tests for Market Pulse — Phase 1 (mock transports only)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from market_pulse.catalyst_classifier import classify_catalyst, has_strong_risk
from market_pulse.engine import MarketPulseEngine
from market_pulse.metrics import compute_metrics
from market_pulse.news_dedup import dedupe_key, dedupe_news
from market_pulse.providers.base import (
    AggregateMinute,
    QuoteTick,
    RawNewsItem,
    TradeTick,
)
from market_pulse.providers.reference_news import ReferenceNewsProvider
from market_pulse.providers.massive_stream import MassiveMarketStreamProvider
from market_pulse.scoring import decide_pulse
from market_pulse.service import reset_market_pulse_engine, reset_market_pulse_runtime
from market_pulse.runtime import MarketPulseRuntime
from market_pulse.state import LinkedNews, SymbolPulseState
from market_pulse.subscription_manager import SubscriptionManager


def _now_ms(offset_sec: int = 0) -> int:
    return int((datetime.now(timezone.utc) + timedelta(seconds=offset_sec)).timestamp() * 1000)


def _positive_news(symbol: str = "NVDA") -> RawNewsItem:
    return RawNewsItem(
        provider_id="news-1",
        headline="NVDA beats estimates, raises guidance",
        url="https://example.com/nvda-beat",
        published_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        symbols=[symbol],
        body="Strong earnings beat",
    )


def _offering_news(symbol: str = "ABCD") -> RawNewsItem:
    return RawNewsItem(
        provider_id="news-2",
        headline="ABCD announces public offering and dilution",
        url="https://example.com/offering",
        published_at=datetime.now(timezone.utc) - timedelta(seconds=20),
        symbols=[symbol],
        body="Registered direct offering",
    )


def _build_hot_state(symbol: str = "NVDA") -> SymbolPulseState:
    now_ms = _now_ms()
    state = SymbolPulseState(symbol=symbol, baseline_minute_volume=1000)
    item = _positive_news(symbol)
    cls = classify_catalyst(item.headline, item.body)
    state.linked_news = LinkedNews(
        item=item,
        news_age_seconds=30.0,
        classification_sentiment=cls.sentiment,
        trigger_type=cls.trigger_type,
        risk_flags=cls.risk_flags,
        catalyst_score=cls.score_component,
    )
    state.alert_created_at = datetime.now(timezone.utc)
    state.last_quote = QuoteTick(symbol=symbol, bid=99.9, ask=100.1, bid_size=100, ask_size=100, timestamp_ms=now_ms)
    for i in range(40):
        state.add_trade(
            TradeTick(
                symbol=symbol,
                price=100.0 + i * 0.05,
                size=500,
                timestamp_ms=now_ms - (40 - i) * 1000,
            )
        )
    state.add_minute_bar(
        AggregateMinute(
            symbol=symbol,
            open=99.0,
            high=102.0,
            low=98.5,
            close=101.5,
            volume=5000,
            vwap=100.5,
            timestamp_ms=now_ms - 60_000,
        )
    )
    state.add_minute_bar(
        AggregateMinute(
            symbol=symbol,
            open=101.0,
            high=103.0,
            low=100.5,
            close=102.5,
            volume=15000,
            vwap=101.8,
            timestamp_ms=now_ms,
        )
    )
    state.day_high = 102.0
    return state


# --- Classifier ---


def test_classify_positive_earnings_beat():
    r = classify_catalyst("Company beats estimates on revenue")
    assert r.sentiment == "positive"
    assert r.trigger_type == "earnings_beat"
    assert not has_strong_risk(r.risk_flags)


def test_classify_negative_offering_dilution():
    r = classify_catalyst("Company announces public offering and dilution")
    assert r.sentiment == "negative"
    assert "offering" in r.risk_flags
    assert has_strong_risk(r.risk_flags)


def test_classify_fda_rejection_strong_risk():
    r = classify_catalyst("FDA rejection for lead drug candidate")
    assert has_strong_risk(r.risk_flags)
    assert "fda_rejection" in r.risk_flags


# --- Dedup ---


def test_dedupe_by_provider_id():
    a = RawNewsItem(provider_id="x1", headline="Same", url="u1", symbols=["A"])
    b = RawNewsItem(provider_id="x1", headline="Same copy", url="u2", symbols=["A"])
    out = dedupe_news([a, b])
    assert len(out) == 1


def test_dedupe_by_url_when_no_id():
    a = RawNewsItem(provider_id="", headline="H1", url="https://x.com/a", symbols=["A"])
    b = RawNewsItem(provider_id="", headline="H2", url="https://x.com/a", symbols=["A"])
    assert dedupe_key(a) == dedupe_key(b)
    assert len(dedupe_news([a, b])) == 1


def test_dedupe_by_title_hash():
    a = RawNewsItem(provider_id="", headline="Breaking News", url="", symbols=["A"])
    b = RawNewsItem(provider_id="", headline="Breaking   News", url="", symbols=["A"])
    assert len(dedupe_news([a, b])) == 1


# --- Metrics / buy pressure ---


def test_estimated_buy_pressure_increases_with_volume_and_trades():
    state = _build_hot_state("NVDA")
    metrics = compute_metrics(state)
    assert metrics.rvol > 1.0
    assert metrics.estimated_buy_pressure > 50.0
    assert metrics.dollar_volume_acceleration > 0


# --- Scoring / decisions ---


def test_enter_now_requires_high_score_and_fresh_data():
    state = _build_hot_state("NVDA")
    metrics = compute_metrics(state)
    result = decide_pulse(state, metrics)
    assert result.total >= 65
    assert result.decision in ("ENTER_NOW", "WAIT")


def test_stale_data_blocks_enter_now():
    state = _build_hot_state("NVDA")
    metrics = compute_metrics(state)
    metrics.data_age_seconds = 500
    result = decide_pulse(state, metrics, data_max_age=120)
    assert result.decision == "EXPIRED"


def test_offering_forces_avoid():
    state = _build_hot_state("ABCD")
    item = _offering_news("ABCD")
    cls = classify_catalyst(item.headline, item.body)
    state.linked_news = LinkedNews(
        item=item,
        classification_sentiment=cls.sentiment,
        trigger_type=cls.trigger_type,
        risk_flags=cls.risk_flags,
        catalyst_score=cls.score_component,
    )
    metrics = compute_metrics(state)
    result = decide_pulse(state, metrics)
    assert result.decision == "AVOID"
    assert any("محفز" in r or "تخفيف" in r for r in result.reasons_ar)


def test_alert_expiry():
    state = _build_hot_state("NVDA")
    state.alert_created_at = datetime.now(timezone.utc) - timedelta(seconds=2000)
    metrics = compute_metrics(state)
    result = decide_pulse(state, metrics, alert_ttl=900)
    assert result.decision == "EXPIRED"


def test_score_bounded_0_100():
    state = _build_hot_state("NVDA")
    metrics = compute_metrics(state)
    result = decide_pulse(state, metrics)
    assert 0 <= result.total <= 100


# --- Subscription manager — no wildcards ---


def test_no_market_wide_wildcard_subscriptions():
    mgr = SubscriptionManager(max_symbols=50)
    assert mgr.add("T.*") is False
    assert mgr.add("Q.*") is False
    mgr.add("AAPL")
    subs = mgr.build_ws_subscriptions()
    assert all("*" not in s for s in subs)
    assert mgr.contains_wildcard(subs) is False
    assert all(s.endswith("AAPL") or "AAPL" in s for s in subs)


def test_subscription_max_and_ttl():
    mgr = SubscriptionManager(max_symbols=2, ttl_seconds=1)
    mgr.add("AAA")
    mgr.add("BBB")
    mgr.add("CCC")
    assert mgr.count() == 2
    assert "BBB" in mgr._symbols
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    mgr._symbols["BBB"].subscribed_at = past
    evicted = mgr.evict_stale()
    assert "BBB" in evicted


# --- Reference news provider mock ---


@pytest.mark.asyncio
async def test_reference_news_fetch_dedupes_and_links_symbols():
    payload = {
        "results": [
            {
                "id": "n1",
                "title": "Beat estimates",
                "published_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "article_url": "https://example.com/n1",
                "description": "Strong quarter",
                "tickers": ["NVDA"],
            },
            {"id": "n1", "title": "Duplicate", "tickers": ["NVDA"]},
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v2/reference/news")
        assert request.url.params["sort"] == "published_utc"
        assert request.url.params["order"] == "desc"
        assert "apiKey" in request.url.params
        assert request.url.params["apiKey"] == "test-key-hidden"
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = ReferenceNewsProvider(api_key="test-key-hidden", client=client)
    items = await provider.fetch_news()
    await provider.close()
    assert len(items) == 1
    assert items[0].symbols == ["NVDA"]
    assert items[0].url == "https://example.com/n1"
    assert items[0].body == "Strong quarter"


@pytest.mark.asyncio
async def test_reference_news_http_errors_return_empty():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": "ERROR"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = ReferenceNewsProvider(api_key="test-key-hidden", client=client)
    items = await provider.fetch_news()
    await provider.close()
    assert items == []


@pytest.mark.asyncio
async def test_reference_news_timeout_returns_empty():
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = ReferenceNewsProvider(api_key="test-key-hidden", client=client)
    items = await provider.fetch_news()
    await provider.close()
    assert items == []


# --- Engine integration ---


@pytest.mark.asyncio
async def test_engine_builds_alert_without_live_ws():
    engine = MarketPulseEngine(enabled=True, watchlist=[])
    engine._api_key = "test-key"
    item = _positive_news("NVDA")
    engine.link_news_to_symbol(item, "NVDA")
    state = engine._get_state("NVDA")
    now_ms = _now_ms()
    state.last_quote = QuoteTick("NVDA", 100.0, 100.2, 100, 100, now_ms)
    for i in range(30):
        engine.ingest_trade(
            TradeTick("NVDA", 100.0 + i * 0.02, 400, now_ms - (30 - i) * 800)
        )
    engine.ingest_aggregate(
        AggregateMinute("NVDA", 99, 101, 98, 100, 4000, 99.5, now_ms - 60_000)
    )
    engine.ingest_aggregate(
        AggregateMinute("NVDA", 100, 103, 99, 102, 12000, 101.0, now_ms)
    )
    alert = engine.build_alert("NVDA")
    assert alert is not None
    assert alert.symbol == "NVDA"
    assert alert.decision in ("ENTER_NOW", "WAIT", "AVOID")
    assert "test-key" not in alert.model_dump_json()


# --- API contract ---


@pytest.fixture
def client():
    from main import app

    return TestClient(app)


def test_health_disabled_by_default(client, auth_headers):
    reset_market_pulse_engine(MarketPulseEngine(enabled=False))
    resp = client.get("/market-pulse/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["status"] == "disabled"
    assert "apiKey" not in resp.text
    assert "MASSIVE_API_KEY" not in resp.text


def test_health_missing_credentials(client, auth_headers):
    engine = MarketPulseEngine(enabled=True)
    engine._api_key = ""
    reset_market_pulse_engine(engine)
    resp = client.get("/market-pulse/health", headers=auth_headers)
    data = resp.json()
    assert data["status"] == "missing_credentials"
    assert data["has_api_key"] is False


def test_market_pulse_list_empty_when_disabled(client, auth_headers):
    reset_market_pulse_engine(MarketPulseEngine(enabled=False))
    resp = client.get("/market-pulse", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_market_pulse_list_enabled_when_feature_on(client, auth_headers, monkeypatch):
    monkeypatch.setattr("market_pulse.service.MARKET_PULSE_ENABLED", True)
    engine = MarketPulseEngine(enabled=True)
    engine._api_key = "test-key"
    reset_market_pulse_engine(engine)

    resp = client.get("/market-pulse", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert isinstance(data["alerts"], list)


def test_market_pulse_symbol_404(client, auth_headers):
    reset_market_pulse_engine(MarketPulseEngine(enabled=True))
    engine = MarketPulseEngine(enabled=True)
    engine._api_key = "k"
    reset_market_pulse_engine(engine)
    resp = client.get("/market-pulse/UNKNOWN", headers=auth_headers)
    assert resp.status_code == 404


def test_api_response_contract_fields(client, auth_headers):
    engine = MarketPulseEngine(enabled=True)
    engine._api_key = "secret-key-not-in-response"
    engine.link_news_to_symbol(_positive_news("TSLA"), "TSLA")
    st = engine._get_state("TSLA")
    now_ms = _now_ms()
    st.last_quote = QuoteTick("TSLA", 250.0, 250.3, 50, 50, now_ms)
    engine.ingest_trade(TradeTick("TSLA", 250.1, 100, now_ms))
    reset_market_pulse_engine(engine)
    reset_market_pulse_runtime(MarketPulseRuntime(engine=engine))

    with patch("market_pulse.service.MARKET_PULSE_ENABLED", True):
        resp = client.get("/market-pulse/TSLA", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "symbol", "score", "decision", "catalyst", "headline", "news_age_seconds",
        "estimated_buy_pressure", "rvol", "dollar_volume_acceleration", "spread_bps",
        "price", "vwap", "entry", "stop_loss", "targets", "risk_flags",
        "data_timestamp", "is_live", "expires_at", "reasons_ar",
    ):
        assert key in body
    assert "secret-key" not in resp.text


def test_no_api_key_in_logs(client, auth_headers, caplog):
    caplog.set_level(logging.DEBUG)
    engine = MarketPulseEngine(enabled=True)
    engine._api_key = "super-secret-key-12345"
    reset_market_pulse_engine(engine)
    client.get("/market-pulse/health", headers=auth_headers)
    joined = " ".join(r.message for r in caplog.records)
    assert "super-secret-key-12345" not in joined


@pytest.mark.asyncio
async def test_stream_rejects_wildcard_subscription():
    mgr = SubscriptionManager()
    stream = MassiveMarketStreamProvider(api_key="k", subscription_manager=mgr)
    fake_ws = AsyncMock()
    fake_ws.send = AsyncMock()
    stream._subs.build_ws_subscriptions = lambda: ["T.*", "Q.*"]  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="Wildcard"):
        await stream._subscribe(fake_ws)


@pytest.mark.asyncio
async def test_stream_parses_trade_message():
    mgr = SubscriptionManager()
    mgr.add("AAPL")
    stream = MassiveMarketStreamProvider(api_key="k", subscription_manager=mgr)
    received: list[TradeTick] = []

    async def on_trade(t: TradeTick) -> None:
        received.append(t)

    stream.on("T", on_trade)
    msg = json.dumps([{"ev": "T", "sym": "AAPL", "p": 150.5, "s": 100, "t": _now_ms()}])
    await stream.push_message(msg)
    assert len(received) == 1
    assert received[0].symbol == "AAPL"
