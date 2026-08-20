"""Market Pulse engine — links news catalysts with live metrics."""

from __future__ import annotations

from datetime import datetime, timezone

from config import (
    DEFAULT_SYMBOLS,
    MARKET_PULSE_ALERT_TTL_SECONDS,
    MARKET_PULSE_DATA_MAX_AGE_SECONDS,
    MARKET_PULSE_ENABLED,
    MARKET_PULSE_MAX_SYMBOLS,
    MARKET_PULSE_SYMBOL_TTL_SECONDS,
    get_polygon_api_key,
)
from market_pulse.catalyst_classifier import classify_catalyst
from market_pulse.metrics import compute_metrics
from market_pulse.models import CatalystInfo, MarketPulseAlert, MarketPulseHealth
from market_pulse.providers.base import (
    AggregateMinute,
    LuldEvent,
    QuoteTick,
    RawNewsItem,
    TradeTick,
)
from market_pulse.providers.benzinga_news import BenzingaNewsProvider
from market_pulse.providers.massive_stream import MassiveMarketStreamProvider
from market_pulse.scoring import alert_expires_at, compute_trade_levels, decide_pulse
from market_pulse.state import LinkedNews, SymbolPulseState
from market_pulse.subscription_manager import SubscriptionManager


class MarketPulseEngine:
    def __init__(
        self,
        *,
        enabled: bool = MARKET_PULSE_ENABLED,
        news_provider: BenzingaNewsProvider | None = None,
        stream_provider: MassiveMarketStreamProvider | None = None,
        watchlist: list[str] | None = None,
    ):
        self.enabled = enabled
        self._api_key = get_polygon_api_key()
        self._subs = SubscriptionManager(
            max_symbols=MARKET_PULSE_MAX_SYMBOLS,
            ttl_seconds=MARKET_PULSE_SYMBOL_TTL_SECONDS,
        )
        self.news = news_provider or BenzingaNewsProvider(api_key=self._api_key)
        self.stream = stream_provider or MassiveMarketStreamProvider(
            api_key=self._api_key,
            subscription_manager=self._subs,
        )
        self._states: dict[str, SymbolPulseState] = {}
        self._watchlist = [s.upper() for s in (watchlist or DEFAULT_SYMBOLS)]
        self._wire_stream_handlers()

    def _wire_stream_handlers(self) -> None:
        async def on_trade(tick: TradeTick) -> None:
            self.ingest_trade(tick)

        async def on_quote(tick: QuoteTick) -> None:
            self.ingest_quote(tick)

        async def on_agg(bar: AggregateMinute) -> None:
            self.ingest_aggregate(bar)

        async def on_luld(ev: LuldEvent) -> None:
            self.ingest_luld(ev)

        self.stream.on("T", on_trade)
        self.stream.on("Q", on_quote)
        self.stream.on("AM", on_agg)
        self.stream.on("A", on_agg)
        self.stream.on("LULD", on_luld)

    def has_credentials(self) -> bool:
        return bool(self._api_key)

    def _get_state(self, symbol: str) -> SymbolPulseState:
        sym = symbol.upper()
        if sym not in self._states:
            self._states[sym] = SymbolPulseState(symbol=sym)
        return self._states[sym]

    def link_news_to_symbol(self, item: RawNewsItem, symbol: str) -> None:
        sym = symbol.upper()
        self._subs.add(sym, source="news")
        classification = classify_catalyst(item.headline, item.body)
        pub = item.published_at
        news_age = 0.0
        if pub:
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            news_age = max(0.0, (datetime.now(timezone.utc) - pub).total_seconds())
        state = self._get_state(sym)
        state.linked_news = LinkedNews(
            item=item,
            news_age_seconds=news_age,
            classification_sentiment=classification.sentiment,
            trigger_type=classification.trigger_type,
            risk_flags=classification.risk_flags,
            catalyst_score=classification.score_component,
        )
        if state.alert_created_at is None:
            state.alert_created_at = datetime.now(timezone.utc)

    def ingest_news_batch(self, items: list[RawNewsItem]) -> None:
        for item in items:
            symbols = item.symbols or []
            for sym in symbols:
                self.link_news_to_symbol(item, sym)

    def ingest_trade(self, tick: TradeTick) -> None:
        state = self._get_state(tick.symbol)
        state.add_trade(tick)

    def ingest_quote(self, tick: QuoteTick) -> None:
        state = self._get_state(tick.symbol)
        state.last_quote = tick

    def ingest_aggregate(self, bar: AggregateMinute) -> None:
        state = self._get_state(bar.symbol)
        state.add_minute_bar(bar)

    def ingest_luld(self, ev: LuldEvent) -> None:
        state = self._get_state(ev.symbol)
        state.luld = ev

    async def refresh_news(self) -> list[RawNewsItem]:
        if not self.enabled or not self.has_credentials():
            return []
        items = await self.news.fetch_news()
        self.ingest_news_batch(items)
        return items

    async def start(self) -> None:
        if not self.enabled or not self.has_credentials():
            return
        for sym in self._watchlist:
            self._subs.add(sym, source="watchlist")
        await self.stream.start()

    async def stop(self) -> None:
        await self.stream.stop()
        await self.news.close()

    def build_alert(self, symbol: str, now: datetime | None = None) -> MarketPulseAlert | None:
        sym = symbol.upper()
        state = self._states.get(sym)
        if not state or not state.linked_news:
            return None
        now = now or datetime.now(timezone.utc)
        metrics = compute_metrics(state, now=now)
        breakdown = decide_pulse(state, metrics, now=now)
        linked = state.linked_news
        entry, stop, targets = compute_trade_levels(metrics.price or state.last_price)
        created = state.alert_created_at or now
        is_live = (
            self.enabled
            and self.has_credentials()
            and metrics.data_age_seconds <= MARKET_PULSE_DATA_MAX_AGE_SECONDS
            and self.stream.connected
        )
        catalyst = CatalystInfo(
            headline=linked.item.headline,
            sentiment=linked.classification_sentiment,  # type: ignore[arg-type]
            trigger_type=linked.trigger_type,
            news_age_seconds=metrics.news_age_seconds,
            symbols=linked.item.symbols,
            provider_id=linked.item.provider_id,
        )
        data_ts = now.isoformat()
        if state.latest_timestamp_ms():
            data_ts = datetime.fromtimestamp(
                state.latest_timestamp_ms() / 1000.0, tz=timezone.utc
            ).isoformat()

        return MarketPulseAlert(
            symbol=sym,
            score=round(breakdown.total, 2),
            decision=breakdown.decision,
            catalyst=catalyst,
            headline=linked.item.headline,
            news_age_seconds=round(metrics.news_age_seconds, 1),
            estimated_buy_pressure=metrics.estimated_buy_pressure,
            rvol=round(metrics.rvol, 2),
            dollar_volume_acceleration=round(metrics.dollar_volume_acceleration, 4),
            spread_bps=round(metrics.spread_bps, 2),
            price=round(metrics.price, 4),
            vwap=round(metrics.vwap, 4),
            entry=entry,
            stop_loss=stop,
            targets=targets,
            risk_flags=list(linked.risk_flags),
            data_timestamp=data_ts,
            is_live=is_live,
            expires_at=alert_expires_at(created, MARKET_PULSE_ALERT_TTL_SECONDS),
            reasons_ar=breakdown.reasons_ar,
            catalyst_score=breakdown.catalyst_score,
            liquidity_score=breakdown.liquidity_score,
            price_confirmation_score=breakdown.price_confirmation_score,
            risk_penalty=breakdown.risk_penalty,
            is_halted=metrics.is_halted,
        )

    def list_alerts(self) -> list[MarketPulseAlert]:
        alerts: list[MarketPulseAlert] = []
        for sym in sorted(self._states.keys()):
            alert = self.build_alert(sym)
            if alert:
                alerts.append(alert)
        alerts.sort(key=lambda a: a.score, reverse=True)
        return alerts

    def health(self) -> MarketPulseHealth:
        if not self.enabled:
            return MarketPulseHealth(
                enabled=False,
                status="disabled",
                has_api_key=bool(self._api_key),
                message="ميزة نبض السوق معطّلة (MARKET_PULSE_ENABLED=false)",
            )
        if not self.has_credentials():
            return MarketPulseHealth(
                enabled=True,
                status="missing_credentials",
                has_api_key=False,
                message="MASSIVE_API_KEY غير متوفر — لا تتوفر بيانات لحظية",
            )
        return MarketPulseHealth(
            enabled=True,
            status="ok" if self.stream.connected else "idle",
            has_api_key=True,
            subscribed_symbols=self._subs.count(),
            max_symbols=MARKET_PULSE_MAX_SYMBOLS,
            stream_connected=self.stream.connected,
            last_news_fetch=(
                self.news.last_fetch_at.isoformat() if self.news.last_fetch_at else None
            ),
            message="جاهز" if self.stream.connected else "بانتظار الاتصال بالبث",
        )
