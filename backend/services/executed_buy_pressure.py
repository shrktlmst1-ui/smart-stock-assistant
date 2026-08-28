"""Executed buy pressure from WebSocket trades vs live quotes — no proxy, no bid/ask size alone."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

BuyPressureSource = Literal["EXECUTED_TRADES", "INSUFFICIENT_DATA"]


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


@dataclass
class QuoteState:
    bid: float = 0.0
    ask: float = 0.0
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutedTrade:
    ts_mono: float
    price: float
    size: int
    side: TradeSide
    dollar_volume: float


@dataclass
class WindowPressure:
    window_sec: float
    buy_dollar: float = 0.0
    sell_dollar: float = 0.0
    trade_count: int = 0

    @property
    def ratio(self) -> float:
        total = self.buy_dollar + self.sell_dollar
        if total <= 0:
            return 0.0
        return self.buy_dollar / total

    @property
    def total_dollar(self) -> float:
        return self.buy_dollar + self.sell_dollar


@dataclass
class SymbolBuyPressure:
    symbol: str
    quotes: QuoteState = field(default_factory=QuoteState)
    trades: deque[ExecutedTrade] = field(default_factory=lambda: deque(maxlen=5000))
    last_tick_side: TradeSide = TradeSide.NEUTRAL

    def update_quote(self, bid: float, ask: float) -> None:
        if bid > 0 and ask > 0:
            self.quotes.bid = bid
            self.quotes.ask = ask
            self.quotes.updated_at = datetime.now(timezone.utc)

    def _classify_trade(self, price: float) -> TradeSide:
        bid, ask = self.quotes.bid, self.quotes.ask
        if bid > 0 and ask > 0 and ask >= bid:
            if price >= ask:
                return TradeSide.BUY
            if price <= bid:
                return TradeSide.SELL
            mid = (bid + ask) / 2.0
            if price > mid:
                return TradeSide.BUY
            if price < mid:
                return TradeSide.SELL
            return TradeSide.NEUTRAL
        if self.trades:
            prev = self.trades[-1].price
            if price > prev:
                return TradeSide.BUY
            if price < prev:
                return TradeSide.SELL
        return TradeSide.NEUTRAL

    def ingest_trade(self, price: float, size: int, *, ts_mono: float | None = None) -> TradeSide:
        if price <= 0 or size <= 0:
            return TradeSide.NEUTRAL
        now = ts_mono if ts_mono is not None else time.monotonic()
        side = self._classify_trade(price)
        if side == TradeSide.NEUTRAL and self.trades:
            prev = self.trades[-1].price
            if price > prev:
                side = TradeSide.BUY
            elif price < prev:
                side = TradeSide.SELL
        self.last_tick_side = side
        dv = price * size
        self.trades.append(
            ExecutedTrade(ts_mono=now, price=price, size=size, side=side, dollar_volume=dv)
        )
        return side

    def pressure_windows(self, windows: tuple[float, ...] = (10.0, 30.0, 60.0)) -> dict[float, WindowPressure]:
        now = time.monotonic()
        out: dict[float, WindowPressure] = {}
        for w in windows:
            wp = WindowPressure(window_sec=w)
            cutoff = now - w
            for t in self.trades:
                if t.ts_mono < cutoff:
                    continue
                wp.trade_count += 1
                if t.side == TradeSide.BUY:
                    wp.buy_dollar += t.dollar_volume
                elif t.side == TradeSide.SELL:
                    wp.sell_dollar += t.dollar_volume
            out[w] = wp
        return out

    @property
    def source(self) -> BuyPressureSource:
        w60 = self.pressure_windows((60.0,))[60.0]
        if w60.trade_count >= 3 and (self.quotes.bid > 0 or w60.total_dollar > 0):
            return "EXECUTED_TRADES"
        return "INSUFFICIENT_DATA"

    def executed_ratio_60s(self) -> float:
        return self.pressure_windows((60.0,))[60.0].ratio


class ExecutedBuyPressureRegistry:
    """Per-symbol executed buy pressure from T/Q — thread-safe for asyncio single-thread."""

    STRONG_BUY_MIN_RATIO_60S = 0.62
    STRONG_BUY_MIN_TRADES_60S = 8
    STRONG_BUY_MIN_DOLLAR_60S = 2500.0

    def __init__(self) -> None:
        self._symbols: dict[str, SymbolBuyPressure] = {}

    def reset(self) -> None:
        self._symbols.clear()

    def _get(self, symbol: str) -> SymbolBuyPressure:
        sym = symbol.upper()
        if sym not in self._symbols:
            self._symbols[sym] = SymbolBuyPressure(symbol=sym)
        return self._symbols[sym]

    def ingest_quote(self, symbol: str, bid: float, ask: float) -> None:
        self._get(symbol).update_quote(bid, ask)

    def ingest_trade(self, symbol: str, price: float, size: int) -> TradeSide:
        return self._get(symbol).ingest_trade(price, size)

    def get(self, symbol: str) -> SymbolBuyPressure | None:
        return self._symbols.get(symbol.upper())

    def qualifies_strong_buy_watch(
        self,
        symbol: str,
        *,
        price_rising: bool,
        volume_accel_above_baseline: bool,
        rvol_valid: bool,
        spread_tradable: bool,
    ) -> tuple[bool, str]:
        """STRONG_BUY_WATCH — executed pressure + price + volume + RVOL + spread + liquidity."""
        bp = self._symbols.get(symbol.upper())
        if not bp or bp.source != "EXECUTED_TRADES":
            return False, "insufficient_executed_trades"
        w60 = bp.pressure_windows((60.0,))[60.0]
        if w60.trade_count < self.STRONG_BUY_MIN_TRADES_60S:
            return False, f"trades_60s={w60.trade_count}<{self.STRONG_BUY_MIN_TRADES_60S}"
        if w60.total_dollar < self.STRONG_BUY_MIN_DOLLAR_60S:
            return False, f"dollar_60s={w60.total_dollar:.0f}<{self.STRONG_BUY_MIN_DOLLAR_60S}"
        if w60.ratio < self.STRONG_BUY_MIN_RATIO_60S:
            return False, f"buy_ratio_60s={w60.ratio:.2f}<{self.STRONG_BUY_MIN_RATIO_60S}"
        if not price_rising:
            return False, "price_not_rising"
        if not volume_accel_above_baseline:
            return False, "volume_accel_below_baseline"
        if not rvol_valid:
            return False, "rvol_invalid"
        if not spread_tradable:
            return False, "spread_not_tradable"
        w30 = bp.pressure_windows((30.0,))[30.0]
        if w30.ratio < 0.55:
            return False, "buy_ratio_30s_not_sustained"
        return True, "executed_buy_pressure_sustained"


executed_buy_pressure_registry = ExecutedBuyPressureRegistry()
