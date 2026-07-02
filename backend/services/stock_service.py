"""Stock data service — optimized live analysis from cached Massive candles."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from analysis.ai_signal_engine import generate_ai_signal
from config import (
    DAILY_BARS_REFRESH_SECONDS,
    MINUTE_BARS_REFRESH_SECONDS,
    NEWS_REFRESH_SECONDS,
    SCANNER_WORKER_THREADS,
)
from database.signal_logger import log_signal
from models.alerts import StockStatus
from models.stock import NewsItem, SearchResult, StockAnalysis, StockOpportunity, StockSnapshot
from models.trading import NewsIntelligence
from services.journal_service import evaluate_open_trades, record_signal
from services.news_intelligence import analyze_news
from services.notification_service import notify_signal
from services.polygon_client import PolygonClient

logger = logging.getLogger(__name__)

_client: PolygonClient | None = None
_name_cache: dict[str, str] = {}
_last_logged_signal: dict[str, str] = {}
_last_journal_key: dict[str, str] = {}


@dataclass
class SymbolCache:
    minute_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    daily_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    news: list[NewsItem] = field(default_factory=list)
    news_intel: NewsIntelligence = field(default_factory=NewsIntelligence)
    minute_updated: float = 0.0
    daily_updated: float = 0.0
    news_updated: float = 0.0
    live_price: float = 0.0
    live_volume: int = 0


_symbol_cache: dict[str, SymbolCache] = {}


def get_client() -> PolygonClient:
    global _client
    if _client is None:
        _client = PolygonClient()
    return _client


def _ai_to_status(signal: str, decision_rec: str = "") -> StockStatus:
    rec = (decision_rec or "").upper()
    if rec == "BUY" or rec == "ENTRY CONFIRMED":
        return "شراء"
    if rec == "SELL":
        return "خروج"
    if rec in ("AVOID", "AVOID / TRAP RISK"):
        return "خطر"
    if rec == "NO TRADE":
        return "انتظار"
    return {
        "Strong Buy": "شراء", "Buy": "شراء", "Wait": "انتظار",
        "Sell": "خروج", "Strong Sell": "خطر",
    }.get(signal, "انتظار")


def _parse_snapshot_price(snap: dict) -> tuple[float, int, float, float]:
    day = snap.get("day", {})
    prev = snap.get("prevDay", {})
    last_trade = snap.get("lastTrade", {})
    min_bar = snap.get("min", {})
    price = float(last_trade.get("p") or min_bar.get("c") or day.get("c") or prev.get("c") or 0)
    volume = int(day.get("v") or min_bar.get("v") or 0)
    prev_close = float(prev.get("c") or price)
    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    return price, volume, change, change_pct


def _patch_df_with_live(cache: SymbolCache, price: float, volume: int) -> pd.DataFrame:
    """Update last candle with live price in-place — no copy."""
    df = cache.minute_df
    if df.empty or price <= 0:
        return df
    idx = df.index[-1]
    df.at[idx, "close"] = price
    df.at[idx, "high"] = max(float(df.at[idx, "high"]), price)
    df.at[idx, "low"] = min(float(df.at[idx, "low"]), price)
    if volume > 0:
        df.at[idx, "volume"] = volume
    return df


def _analyze_sync(
    symbol: str,
    cache: SymbolCache,
    price: float,
    volume: int,
    change: float,
    change_pct: float,
    name: str,
) -> StockSnapshot | None:
    df = _patch_df_with_live(cache, price, volume)
    if df.empty:
        return None

    ai_signal, meters, smc, liq, vol, trend, legacy_signals, alerts, _, indicators, smart_money, traps, regime, risk, conf, decision, vol_liq, news_risk = generate_ai_signal(
        symbol, df, cache.daily_df if not cache.daily_df.empty else None,
        price, change_pct, cache.news_intel, cache.news,
    )

    if _last_logged_signal.get(symbol) != ai_signal.signal:
        log_signal(symbol, ai_signal, price, change_pct, meters.model_dump())
        _last_logged_signal[symbol] = ai_signal.signal

    journal_key = f"{ai_signal.signal}:{round(ai_signal.confidence, 0)}"
    if _last_journal_key.get(symbol) != journal_key:
        record_signal(symbol, ai_signal, regime, conf)
        _last_journal_key[symbol] = journal_key

    evaluate_open_trades(symbol, price)

    return StockSnapshot(
        symbol=symbol,
        name=name,
        price=round(price, 2),
        change=round(change, 2),
        change_percent=round(change_pct, 2),
        volume=volume or int(df["volume"].iloc[-1]),
        liquidity_strength=meters.liquidity_meter,
        status=_ai_to_status(ai_signal.signal, decision.recommendation),
        indicators=indicators,
        signals=legacy_signals,
        alerts=alerts,
        news=cache.news,
        last_updated=datetime.now(timezone.utc).isoformat(),
        ai_signal=ai_signal,
        meters=meters,
        smc=smc,
        liquidity_engine=liq,
        volume_engine=vol,
        trend_analysis=trend,
        news_intelligence=cache.news_intel,
        smart_money=smart_money,
        liquidity_traps=traps,
        market_regime=regime,
        risk_assessment=risk,
        confidence_breakdown=conf,
        trade_decision=decision,
        volume_liquidity=vol_liq,
        news_risk=news_risk,
    )


async def _ensure_bars(symbol: str, client: PolygonClient, cache: SymbolCache) -> None:
    now = time.monotonic()
    if now - cache.minute_updated > MINUTE_BARS_REFRESH_SECONDS or cache.minute_df.empty:
        cache.minute_df = await client.get_aggregates(symbol, multiplier=1, timespan="minute", limit=300)
        cache.minute_updated = now
    if now - cache.daily_updated > DAILY_BARS_REFRESH_SECONDS or cache.daily_df.empty:
        cache.daily_df = await client.get_daily_bars(symbol, limit=250)
        cache.daily_updated = now


async def _ensure_news(symbol: str, client: PolygonClient, cache: SymbolCache, change_pct: float) -> None:
    now = time.monotonic()
    if now - cache.news_updated > NEWS_REFRESH_SECONDS or not cache.news:
        cache.news, cache.news_intel = await analyze_news(symbol, client, change_pct)
        cache.news_updated = now


async def _get_name(symbol: str, client: PolygonClient) -> str:
    if symbol in _name_cache:
        return _name_cache[symbol]
    try:
        details = await client.get_ticker_details(symbol)
        name = details.get("name", symbol)
    except Exception:
        name = symbol
    _name_cache[symbol] = name
    return name


def _analyze_batch_sync(jobs: list[tuple[str, SymbolCache, float, int, float, float, str]]) -> list[StockSnapshot | None]:
    if not jobs:
        return []
    workers = min(SCANNER_WORKER_THREADS, len(jobs))

    def _run(job: tuple[str, SymbolCache, float, int, float, float, str]) -> StockSnapshot | None:
        symbol, cache, price, volume, change, change_pct, name = job
        return _analyze_sync(symbol, cache, price, volume, change, change_pct, name)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run, jobs))


async def _prep_snapshot_job(
    sym: str,
    client: PolygonClient,
    batch: dict[str, dict],
) -> tuple[str, SymbolCache, float, int, float, float, str] | None:
    symbol = sym.upper().strip()
    if symbol not in _symbol_cache:
        _symbol_cache[symbol] = SymbolCache()
    cache = _symbol_cache[symbol]
    snap_data = batch.get(symbol)
    if not snap_data:
        return None
    price, volume, change, change_pct = _parse_snapshot_price(snap_data)
    if price <= 0:
        return None
    await _ensure_bars(symbol, client, cache)
    await _ensure_news(symbol, client, cache, change_pct)
    name = await _get_name(symbol, client)
    return symbol, cache, price, volume, change, change_pct, name


async def build_stock_snapshot(
    symbol: str,
    client: PolygonClient | None = None,
    snap_data: dict | None = None,
) -> StockSnapshot | None:
    symbol = symbol.upper().strip()
    client = client or get_client()
    if symbol not in _symbol_cache:
        _symbol_cache[symbol] = SymbolCache()
    cache = _symbol_cache[symbol]

    try:
        if snap_data is None:
            snap_data = await client.get_snapshot(symbol)
        price, volume, change, change_pct = _parse_snapshot_price(snap_data)
        if price <= 0:
            return None

        await _ensure_bars(symbol, client, cache)
        await _ensure_news(symbol, client, cache, change_pct)
        name = await _get_name(symbol, client)

        snap = await asyncio.to_thread(
            _analyze_sync, symbol, cache, price, volume, change, change_pct, name
        )
        return snap
    except Exception as e:
        logger.error("Failed snapshot %s: %s", symbol, e)
        return None


async def build_snapshots_batch(symbols: list[str], client: PolygonClient | None = None) -> list[StockSnapshot]:
    t0 = time.monotonic()
    client = client or get_client()
    batch = await client.get_snapshots_batch(symbols)

    prep_tasks = [
        _prep_snapshot_job(sym, client, batch)
        for sym in symbols
    ]
    prepared = await asyncio.gather(*prep_tasks)
    jobs = [job for job in prepared if job is not None]

    snapshots = await asyncio.to_thread(_analyze_batch_sync, jobs)

    results: list[StockSnapshot] = []
    for snap in snapshots:
        if snap is None:
            continue
        results.append(snap)
        await notify_signal(snap.symbol, snap.ai_signal, snap.price, snap.trade_decision)

    elapsed_ms = (time.monotonic() - t0) * 1000
    if elapsed_ms > 300:
        logger.warning("Batch %d symbols slow: %.0fms", len(symbols), elapsed_ms)
    else:
        logger.debug("Batch %d symbols in %.0fms", len(symbols), elapsed_ms)
    return results


async def get_all_snapshots() -> list[StockSnapshot]:
    from services.market_scanner_service import market_scanner
    state = market_scanner.get_state()
    return list(state.snapshots) if state else []


async def get_top_opportunities(limit: int = 20) -> list[StockOpportunity]:
    from services.market_scanner_service import market_scanner
    state = market_scanner.get_state()
    if not state:
        return []
    snapshots = {s.symbol: s for s in state.snapshots}
    risk_map = {"low": "منخفض", "medium": "متوسط", "high": "مرتفع"}
    out: list[StockOpportunity] = []
    for sig in state.top_opportunities[:limit]:
        snap = snapshots.get(sig.symbol)
        risk = snap.ai_signal.risk_level if snap else "medium"
        out.append(StockOpportunity(
            symbol=sig.symbol, name=sig.name, price=sig.price, change_percent=sig.change_percent,
            score=int(sig.ai_score),
            trend="صاعد" if sig.change_percent > 0.5 else "هابط" if sig.change_percent < -0.5 else "محايد",
            risk_level=risk_map.get(risk, "متوسط"),
            status="شراء" if sig.recommendation == "ENTRY CONFIRMED" else "انتظار",
            ai_signal=sig.recommendation, confidence=sig.confidence,
        ))
    return out


async def search_stocks(query: str) -> list[SearchResult]:
    query = query.upper().strip()
    if not query:
        return []
    client = get_client()
    tickers = await client.search_tickers(query)
    results = []
    for t in tickers[:8]:
        sym = t.get("ticker", "")
        if sym:
            snap = await build_stock_snapshot(sym)
            if snap:
                results.append(SearchResult(symbol=snap.symbol, name=snap.name, price=snap.price, change_percent=snap.change_percent))
    return results


async def get_stock_analysis(symbol: str) -> StockAnalysis | None:
    snap = await build_stock_snapshot(symbol)
    if not snap:
        return None
    ind = snap.indicators
    risk_map = {"low": "منخفض", "medium": "متوسط", "high": "مرتفع"}
    return StockAnalysis(
        symbol=snap.symbol, name=snap.name, price=snap.price, change_percent=snap.change_percent,
        trend="صاعد" if snap.change_percent > 0.5 else "هابط" if snap.change_percent < -0.5 else "محايد",
        rsi=ind.rsi, macd=ind.macd, macd_signal=ind.macd_signal,
        ema_20=ind.ema_20, ema_50=ind.ema_50, ema_200=ind.ema_200,
        volume=snap.volume, support=ind.support, resistance=ind.resistance,
        score=int(snap.ai_signal.ai_score),
        entry_price=snap.ai_signal.entry, stop_loss=snap.ai_signal.stop_loss,
        target_1=snap.ai_signal.target_1, target_2=snap.ai_signal.target_2,
        risk_level=risk_map.get(snap.ai_signal.risk_level, "متوسط"),
        recommendation_reason=snap.ai_signal.reason, status=snap.status,
        signals=snap.signals, alerts=snap.alerts, news=snap.news,
        ai_signal=snap.ai_signal, meters=snap.meters, smc=snap.smc,
        liquidity_engine=snap.liquidity_engine, volume_engine=snap.volume_engine,
        trend_analysis=snap.trend_analysis, news_intelligence=snap.news_intelligence,
        smart_money=snap.smart_money, liquidity_traps=snap.liquidity_traps,
        market_regime=snap.market_regime, risk_assessment=snap.risk_assessment,
        confidence_breakdown=snap.confidence_breakdown,
        trade_decision=snap.trade_decision,
        volume_liquidity=snap.volume_liquidity,
        news_risk=snap.news_risk,
    )
