"""Central live price registry — single WS feed, shared across scanner/analysis."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from services.market_session import MarketSession, get_us_market_session
from services.session_price import (
    REGULAR_DAY_BAR_MAX_AGE_SECONDS,
    REGULAR_LAST_TRADE_MAX_AGE_SECONDS,
    REGULAR_QUOTE_MAX_AGE_SECONDS,
    STALE_PRICE_REASON_AR,
    STALE_PRICE_STATUS,
    SessionPrice,
    _age_seconds,
    _build_result,
    _ns_to_datetime,
    _stale,
)

from services.ws_feed_state import message_age_seconds, resolve_feed_state

logger = logging.getLogger(__name__)

LiveSource = Literal["live_trade", "live_quote"]

FEED_LOG_INTERVAL_SEC = 30.0

# Jump Engine 24/7 — ingest WS ticks in all active trading sessions.
_ACTIVE_LIVE_SESSIONS = frozenset({"PRE_MARKET", "REGULAR", "AFTER_HOURS"})


@dataclass
class LivePriceTick:
    symbol: str
    price: float
    exchange_timestamp: datetime | None
    received_at: datetime
    source: LiveSource
    session: MarketSession
    bid: float = 0.0
    ask: float = 0.0

    @property
    def age_seconds(self) -> float:
        ref = self.exchange_timestamp or self.received_at
        return _age_seconds(ref)


@dataclass
class FeedStatus:
    connected: bool = False
    authenticated: bool = False
    hub_running: bool = False
    aggregates_subscribed: bool = False
    subscribed_symbols: set[str] = field(default_factory=set)
    t_channel_count: int = 0
    q_channel_count: int = 0
    subscribed_at_mono: float | None = None
    last_trade_at: datetime | None = None
    last_quote_at: datetime | None = None
    last_disconnect_at: datetime | None = None
    last_message_at: datetime | None = None
    first_message_at: datetime | None = None
    reconnect_count: int = 0
    trades_received: int = 0
    quotes_received: int = 0
    aggregates_received: int = 0
    provider_subscription_ack: bool = False
    provider_subscription_ack_message: str = ""
    bootstrap_snapshot_count: int = 0
    bootstrap_symbols_count: int = 0
    requested_channels_count: int = 0
    stale_failure_count: int = 0
    last_error: str = ""
    ws_url: str = ""


class LivePriceRegistry:
    """Thread-safe enough for asyncio single-thread — one central WS writer."""

    def __init__(self) -> None:
        self._ticks: dict[str, LivePriceTick] = {}
        self._quotes: dict[str, LivePriceTick] = {}
        self._status = FeedStatus()
        self._last_trade_log_mono: float = 0.0
        self._session: MarketSession | None = None

    @property
    def status(self) -> FeedStatus:
        return self._status

    def set_connected(self, connected: bool, *, authenticated: bool = False) -> None:
        self._status.connected = connected
        self._status.authenticated = authenticated
        if connected:
            logger.info("[LIVE_PRICE] websocket connected authenticated=%s", authenticated)
        else:
            self._status.last_disconnect_at = datetime.now(timezone.utc)
            logger.warning("[LIVE_PRICE] feed disconnected error=%s", self._status.last_error or "n/a")

    def set_subscribed(self, symbols: list[str]) -> None:
        self._status.subscribed_symbols = {s.upper() for s in symbols if s}
        logger.info("[LIVE_PRICE] subscribed count=%d", len(self._status.subscribed_symbols))

    def set_hub_health(
        self,
        *,
        shards_connected: int,
        shards_total: int,
        subscribed: set[str],
        hub_running: bool = True,
        aggregates_subscribed: bool = False,
        t_channel_count: int = 0,
        q_channel_count: int = 0,
        ws_url: str = "",
        subscribed_at_mono: float | None = None,
    ) -> None:
        """Update feed status from shared stocks WS hub (partial shard OK)."""
        was_connected = self._status.connected
        self._status.connected = shards_connected > 0
        self._status.authenticated = shards_connected > 0
        self._status.hub_running = hub_running
        self._status.aggregates_subscribed = aggregates_subscribed
        self._status.t_channel_count = t_channel_count
        self._status.q_channel_count = q_channel_count
        if ws_url:
            self._status.ws_url = ws_url
        if subscribed_at_mono is not None:
            self._status.subscribed_at_mono = subscribed_at_mono
        if subscribed:
            self._status.subscribed_symbols = subscribed
        if shards_connected > 0 and not was_connected:
            logger.info(
                "[LIVE_PRICE] hub shards connected %d/%d symbols=%d t=%d q=%d",
                shards_connected,
                shards_total,
                len(self._status.subscribed_symbols),
                t_channel_count,
                q_channel_count,
            )
        elif shards_connected == 0 and shards_total > 0 and was_connected:
            self._status.last_disconnect_at = datetime.now(timezone.utc)
            logger.warning("[LIVE_PRICE] all hub shards disconnected — REST fallback active")

    def note_reconnect(self) -> None:
        self._status.reconnect_count += 1
        logger.info("[LIVE_PRICE] reconnect attempt=%d", self._status.reconnect_count)

    def note_stale_reconnect(self) -> None:
        self._status.stale_failure_count += 1
        logger.warning(
            "[LIVE_PRICE] stale_reconnect stale_failure_count=%d",
            self._status.stale_failure_count,
        )

    def set_bootstrap_metrics(self, *, snapshot_count: int, symbols_count: int) -> None:
        self._status.bootstrap_snapshot_count = snapshot_count
        self._status.bootstrap_symbols_count = symbols_count

    def set_provider_subscription_ack(self, ack: bool, message: str = "") -> None:
        self._status.provider_subscription_ack = ack
        if message:
            self._status.provider_subscription_ack_message = message[:200]
        if ack:
            logger.info(
                "[LIVE_PRICE] provider_subscription_ack message=%s",
                message[:120],
            )

    def set_requested_channels_count(self, count: int) -> None:
        self._status.requested_channels_count = count

    def note_aggregate_received(self) -> None:
        self._status.aggregates_received += 1

    def set_error(self, msg: str) -> None:
        self._status.last_error = msg[:200]

    def ingest_trade(
        self,
        symbol: str,
        price: float,
        *,
        exchange_ts_ns: object = None,
        size: int = 0,
    ) -> None:
        sym = symbol.upper()
        if price <= 0:
            return
        session = get_us_market_session()
        if session not in _ACTIVE_LIVE_SESSIONS:
            mono = time.monotonic()
            if mono - self._last_trade_log_mono >= FEED_LOG_INTERVAL_SEC:
                self._last_trade_log_mono = mono
                logger.info(
                    "[LIVE_PRICE] out_of_session_trade sym=%s session=%s price=%.4f (diagnostic only)",
                    sym,
                    session,
                    price,
                )
            return
        now = datetime.now(timezone.utc)
        ex_ts = _ns_to_datetime(exchange_ts_ns) if exchange_ts_ns else now
        tick = LivePriceTick(
            symbol=sym,
            price=round(price, 4),
            exchange_timestamp=ex_ts,
            received_at=now,
            source="live_trade",
            session=session,
        )
        self._ticks[sym] = tick
        self._status.trades_received += 1
        self._status.last_trade_at = now
        from services.live_symbol_ranker import note_live_trade

        note_live_trade(sym, price, size)
        mono = time.monotonic()
        if mono - self._last_trade_log_mono >= FEED_LOG_INTERVAL_SEC:
            self._last_trade_log_mono = mono
            logger.info(
                "[LIVE_PRICE] trade_received sym=%s price=%.4f age=%.1fs total=%d",
                sym,
                price,
                tick.age_seconds,
                self._status.trades_received,
            )

    def ingest_quote(
        self,
        symbol: str,
        bid: float,
        ask: float,
        *,
        exchange_ts_ns: object = None,
    ) -> None:
        sym = symbol.upper()
        if bid <= 0 or ask <= 0:
            return
        session = get_us_market_session()
        if session not in _ACTIVE_LIVE_SESSIONS:
            logger.debug(
                "[LIVE_PRICE] out_of_session_quote sym=%s session=%s (diagnostic only)",
                sym,
                session,
            )
            return
        mid = round((bid + ask) / 2, 4)
        now = datetime.now(timezone.utc)
        ex_ts = _ns_to_datetime(exchange_ts_ns) if exchange_ts_ns else now
        tick = LivePriceTick(
            symbol=sym,
            price=mid,
            exchange_timestamp=ex_ts,
            received_at=now,
            source="live_quote",
            session=session,
            bid=bid,
            ask=ask,
        )
        self._quotes[sym] = tick
        self._status.quotes_received += 1
        self._status.last_quote_at = now

    def note_message_received(self) -> None:
        """Track last inbound WS market payload for Jump Engine heartbeat."""
        now = datetime.now(timezone.utc)
        self._status.last_message_at = now
        if self._status.first_message_at is None:
            self._status.first_message_at = now
            logger.info("[LIVE_PRICE] first_ws_message_time=%s", now.isoformat())
        self._status.stale_failure_count = 0

    def feed_state(self) -> str:
        subscribed = self._status.provider_subscription_ack and (
            self._status.t_channel_count > 0 or self._status.q_channel_count > 0
        )
        return resolve_feed_state(
            session=get_us_market_session(),
            hub_running=self._status.hub_running,
            connected=self._status.connected,
            authenticated=self._status.authenticated,
            subscribed=subscribed,
            last_message_at=self._status.last_message_at,
            subscribed_at_mono=self._status.subscribed_at_mono,
            stale_failure_count=self._status.stale_failure_count,
        )

    def last_message_age_seconds(self) -> float | None:
        return message_age_seconds(self._status.last_message_at)

    def last_message_iso(self) -> str:
        ts = self._status.last_message_at
        return ts.isoformat() if ts else ""

    def get_tick(self, symbol: str) -> LivePriceTick | None:
        return self._ticks.get(symbol.upper())

    def get_quote(self, symbol: str) -> LivePriceTick | None:
        return self._quotes.get(symbol.upper())

    def resolve_live(
        self,
        symbol: str,
        *,
        prev_close: float = 0.0,
        volume: int = 0,
    ) -> SessionPrice | None:
        """Return fresh live SessionPrice during REGULAR, or None."""
        session = get_us_market_session()
        if session not in _ACTIVE_LIVE_SESSIONS:
            return None

        sym = symbol.upper()
        trade = self._ticks.get(sym)
        if trade and trade.age_seconds <= REGULAR_LAST_TRADE_MAX_AGE_SECONDS:
            return _build_result(
                price=trade.price,
                volume=volume,
                prev_close=prev_close,
                timestamp=trade.exchange_timestamp or trade.received_at,
                session=session,
                source="live_trade",
            )
        # Carry fresh extended-hours tick into REGULAR open (session transition continuity).
        if trade and trade.session in ("PRE_MARKET", "AFTER_HOURS") and trade.age_seconds <= 900:
            return _build_result(
                price=trade.price,
                volume=volume,
                prev_close=prev_close,
                timestamp=trade.exchange_timestamp or trade.received_at,
                session=session,
                source="live_trade",
            )

        quote = self._quotes.get(sym)
        if quote and quote.age_seconds <= REGULAR_QUOTE_MAX_AGE_SECONDS:
            return _build_result(
                price=quote.price,
                volume=volume,
                prev_close=prev_close,
                timestamp=quote.exchange_timestamp or quote.received_at,
                session=session,
                source="live_quote",
            )

        return None

    def inspect(self, symbol: str) -> dict:
        sym = symbol.upper()
        trade = self._ticks.get(sym)
        quote = self._quotes.get(sym)
        resolved = self.resolve_live(sym)
        return {
            "symbol": sym,
            "feed_connected": self._status.connected,
            "feed_authenticated": self._status.authenticated,
            "subscribed": sym in self._status.subscribed_symbols,
            "live_trade": None
            if not trade
            else {
                "price": trade.price,
                "exchange_timestamp": trade.exchange_timestamp.isoformat() if trade.exchange_timestamp else "",
                "received_at": trade.received_at.isoformat(),
                "age_seconds": round(trade.age_seconds, 1),
                "fresh": trade.age_seconds <= REGULAR_LAST_TRADE_MAX_AGE_SECONDS,
            },
            "live_quote": None
            if not quote
            else {
                "price": quote.price,
                "bid": quote.bid,
                "ask": quote.ask,
                "age_seconds": round(quote.age_seconds, 1),
                "fresh": quote.age_seconds <= REGULAR_QUOTE_MAX_AGE_SECONDS,
            },
            "resolved_live": None
            if not resolved
            else {
                "price": resolved.price,
                "source": resolved.source,
                "age_seconds": round(_age_seconds(resolved.timestamp), 1),
                "fresh": resolved.is_valid,
            },
        }

    def clear_execution_prices(self) -> None:
        """On session transition — drop prices used for execution, keep feed stats."""
        self._ticks.clear()
        self._quotes.clear()
        logger.info("[LIVE_PRICE] execution prices cleared on session transition")

    def mark_stale_if_feed_down(self) -> None:
        if not self._status.connected:
            logger.info("[LIVE_PRICE] stale_price feed_down — no new live ticks")

    def patch_snapshot_item(self, item: dict, symbol: str) -> dict:
        """Merge freshest WS tick into snapshot item before price resolution."""
        sym = symbol.upper()
        patched = dict(item)
        tick = self._ticks.get(sym) or self._quotes.get(sym)
        if not tick or tick.price <= 0:
            return patched
        ts_ns = int((tick.exchange_timestamp or tick.received_at).timestamp() * 1_000_000_000)
        patched["lastTrade"] = {"p": tick.price, "t": ts_ns}
        patched["updated"] = ts_ns
        return patched

    def ws_message_age_seconds(self) -> float | None:
        ts = self._status.last_message_at
        if not ts:
            return None
        return _age_seconds(ts)


live_price_registry = LivePriceRegistry()
