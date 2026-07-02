"""Polygon.io / Massive REST client with rate limiting."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pandas as pd

from config import POLYGON_API_KEY, POLYGON_BASE_URL, POLYGON_PLAN, RATE_LIMIT_PER_MINUTE

logger = logging.getLogger(__name__)


class PolygonAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class RateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self.timestamps = [t for t in self.timestamps if now - t < 60]
            if len(self.timestamps) >= self.max_per_minute:
                wait = 60 - (now - self.timestamps[0]) + 0.05
                await asyncio.sleep(wait)
                now = time.monotonic()
                self.timestamps = [t for t in self.timestamps if now - t < 60]
            self.timestamps.append(time.monotonic())


class PolygonClient:
    def __init__(self, api_key: str = POLYGON_API_KEY, plan: str = POLYGON_PLAN):
        if not api_key:
            raise ValueError("API key missing — set MASSIVE_API_KEY or POLYGON_API_KEY in backend/.env")
        self.api_key = api_key
        self.plan = plan
        self.rate_limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, path: str, params: dict | None = None) -> dict[str, Any]:
        await self.rate_limiter.acquire()
        params = dict(params or {})
        params["apiKey"] = self.api_key

        client = await self._get_client()
        url = f"{POLYGON_BASE_URL}{path}"
        resp = await client.get(url, params=params)

        if resp.status_code == 401:
            raise PolygonAPIError(401, "Authentication failed — invalid API key")
        if resp.status_code == 403:
            raise PolygonAPIError(403, "Forbidden — check subscription plan")
        if resp.status_code == 429:
            raise PolygonAPIError(429, "Rate limit exceeded")
        resp.raise_for_status()
        return resp.json()

    async def verify_authentication(self) -> dict[str, Any]:
        """Verify API key with a lightweight request."""
        data = await self._request("/v3/reference/tickers/AAPL", params={"limit": 1})
        return {
            "authenticated": data.get("status") == "OK",
            "status": data.get("status"),
        }

    async def get_ticker_details(self, symbol: str) -> dict[str, Any]:
        data = await self._request(f"/v3/reference/tickers/{symbol.upper()}")
        return data.get("results", {})

    async def get_snapshot(self, symbol: str) -> dict[str, Any]:
        data = await self._request(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.upper()}"
        )
        return data.get("ticker", {})

    async def get_snapshots_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch multiple tickers in one REST call (chunked)."""
        if not symbols:
            return {}
        result: dict[str, dict[str, Any]] = {}
        chunk_size = 50
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i : i + chunk_size]
            tickers_param = ",".join(s.upper() for s in chunk)
            data = await self._request(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": tickers_param},
            )
            for item in data.get("tickers", []):
                sym = item.get("ticker", "")
                if sym:
                    result[sym] = item
        return result

    async def get_full_market_snapshot(self) -> list[dict[str, Any]]:
        """Full US equities snapshot — all tickers in one call."""
        data = await self._request("/v2/snapshot/locale/us/markets/stocks/tickers")
        return data.get("tickers", [])

    async def list_reference_tickers(
        self,
        exchange: str | None = None,
        ticker_type: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Paginated reference tickers for universe construction."""
        params: dict[str, Any] = {
            "market": "stocks",
            "active": "true",
            "limit": limit,
            "sort": "ticker",
            "order": "asc",
        }
        if exchange:
            params["exchange"] = exchange
        if ticker_type:
            params["type"] = ticker_type

        results: list[dict[str, Any]] = []
        path = "/v3/reference/tickers"
        next_url: str | None = None
        pages = 0
        max_pages = 50

        while pages < max_pages:
            if next_url:
                await self.rate_limiter.acquire()
                client = await self._get_client()
                resp = await client.get(next_url, params={"apiKey": self.api_key})
                resp.raise_for_status()
                data = resp.json()
            else:
                data = await self._request(path, params)

            batch = data.get("results", [])
            results.extend(batch)
            next_url = data.get("next_url")
            pages += 1
            if not next_url:
                break

        return results

    async def get_ticker_metadata_batch(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch float / market cap for symbols (cached by caller)."""
        out: dict[str, dict[str, Any]] = {}
        for sym in symbols[:30]:
            try:
                details = await self.get_ticker_details(sym)
                if details:
                    out[sym.upper()] = {
                        "market_cap": float(details.get("market_cap") or 0),
                        "float_shares": float(
                            details.get("share_class_shares_outstanding")
                            or details.get("weighted_shares_outstanding")
                            or 0
                        ),
                        "name": details.get("name", sym),
                    }
            except Exception as e:
                logger.debug("metadata %s: %s", sym, e)
        return out

    async def get_bars_for_timeframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        from analysis.backtest_engine import TIMEFRAMES
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        mult, span, days_back, limit = TIMEFRAMES[timeframe]
        return await self.get_aggregates(symbol, mult, span, limit, days_back)

    async def get_aggregates(
        self,
        symbol: str,
        multiplier: int = 1,
        timespan: str = "minute",
        limit: int = 300,
        days_back: int = 5,
    ) -> pd.DataFrame:
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days_back)

        data = await self._request(
            f"/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{timespan}"
            f"/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}",
            params={"adjusted": "true", "sort": "asc", "limit": limit},
        )
        return self._results_to_df(data.get("results", []))

    async def get_daily_bars(self, symbol: str, limit: int = 250) -> pd.DataFrame:
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=400)
        data = await self._request(
            f"/v2/aggs/ticker/{symbol.upper()}/range/1/day"
            f"/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}",
            params={"adjusted": "true", "sort": "asc", "limit": limit},
        )
        return self._results_to_df(data.get("results", []))

    @staticmethod
    def _results_to_df(results: list) -> pd.DataFrame:
        if not results:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "timestamp"])
        df = pd.DataFrame(results)
        df = df.rename(
            columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "t": "timestamp"}
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df[["open", "high", "low", "close", "volume", "timestamp"]]

    async def get_news(self, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
        data = await self._request(
            "/v2/reference/news",
            params={"ticker": symbol.upper(), "limit": limit, "order": "desc"},
        )
        return data.get("results", [])

    async def search_tickers(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._request(
            "/v3/reference/tickers",
            params={"search": query.upper(), "active": "true", "market": "stocks", "limit": limit},
        )
        return data.get("results", [])

    def is_realtime_capable(self) -> bool:
        return self.plan in ("starter", "developer", "advanced")
