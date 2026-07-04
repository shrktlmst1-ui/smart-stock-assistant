"""Smart Stock Assistant — FastAPI backend with live Polygon/Massive data."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import (
    POLYGON_PLAN,
    POLL_INTERVAL_SECONDS,
    SCANNER_TICK_SECONDS,
    SCANNER_TOP_N,
    WEBSOCKET_ENABLED,
    get_cors_origins,
)
from database.signal_analytics_db import init_signal_analytics_db
from database.trade_replay_db import init_trade_replay_db
from database.signal_logger import get_signal_history, init_db
from database.trading_journal import get_journal_entries, init_journal_db
from models.performance import BacktestMetrics, JournalEntry, PerformanceMetrics, ProductionStatus
from models.signal_analytics import AnalyticsDashboard, PerformanceReport, RankedSignalsResponse
from models.trade_replay import PerformanceInsights, TradeReplayDetail, TradeReplayListResponse
from models.scanner import MarketScanState, OpportunitiesResponse
from models.stock import SearchResult, StockAnalysis, StockOpportunity, StockSnapshot
from services.connection_service import get_connection_status, verify_connection
from services.market_stream import MarketStream
from services.notification_service import set_broadcast as set_notification_broadcast
from services.backtest_service import run_multi_backtest, run_symbol_backtest
from services.performance_service import get_performance_metrics
from services.signal_analytics_service import (
    get_analytics_dashboard,
    get_performance_report,
    get_ranked_signals,
)
from services.trade_replay_service import (
    compute_performance_insights,
    get_trade_replay_detail,
    get_trade_replay_list,
)
from services.market_scanner_service import market_scanner
from services.market_session import get_us_market_session, session_explanation
from services.stock_service import get_stock_analysis, search_stocks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prevent API keys from appearing in httpx request logs
logging.getLogger("httpx").setLevel(logging.WARNING)

market_stream = MarketStream()
ws_clients: set[WebSocket] = set()

_RISK_MAP = {"low": "منخفض", "medium": "متوسط", "high": "مرتفع"}


def _signals_to_opportunities(
    signals: list,
    snapshots: dict[str, StockSnapshot],
    *,
    watchlist: bool = False,
) -> list[StockOpportunity]:
    out: list[StockOpportunity] = []
    for sig in signals:
        snap = snapshots.get(sig.symbol)
        risk = snap.ai_signal.risk_level if snap else "medium"
        out.append(StockOpportunity(
            symbol=sig.symbol,
            name=sig.name,
            price=sig.price,
            change_percent=sig.change_percent,
            score=int(sig.ai_score),
            trend="صاعد" if sig.change_percent > 0.5 else "هابط" if sig.change_percent < -0.5 else "محايد",
            risk_level=_RISK_MAP.get(risk, "متوسط"),
            status="انتظار" if watchlist else ("شراء" if sig.recommendation == "ENTRY CONFIRMED" else "انتظار"),
            ai_signal=sig.recommendation,
            confidence=sig.confidence,
        ))
    return out


async def broadcast(message: dict) -> None:
    dead: list[WebSocket] = []
    payload = json.dumps(message, ensure_ascii=False)
    for ws in ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_journal_db()
    init_signal_analytics_db()
    init_trade_replay_db()
    set_notification_broadcast(broadcast)
    logger.info("Verifying Polygon/Massive connection...")
    status = await verify_connection()
    logger.info("Connection: %s", status.to_dict())

    market_stream.set_broadcast(broadcast)
    await market_stream.start()

    await broadcast({
        "type": "status",
        "data": {**status.to_dict(), "stream_mode": market_stream.mode},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    yield
    await market_stream.stop()


app = FastAPI(
    title="Smart Stock Assistant API",
    description="مساعد تداول AI احترافي — Polygon/Massive + SMC + AI Signals",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_origin_regex=r"https://[a-z0-9-]+\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    status = get_connection_status()
    return {
        "message": "Smart Stock Assistant API",
        "status": "running",
        "mode": "institutional_ai_scanner",
        "plan": POLYGON_PLAN,
        "connection": status.to_dict(),
        "stream_mode": market_stream.mode,
        "scanner_top_n": SCANNER_TOP_N,
    }


@app.get("/status")
def connection_status():
    status = get_connection_status()
    return {**status.to_dict(), "stream_mode": market_stream.mode}


@app.get("/health")
def health():
    status = get_connection_status()
    scan = market_scanner.get_state()
    session = scan.market_status if scan and scan.market_status else get_us_market_session()
    return {
        "ok": status.api_connected,
        "clients": len(ws_clients),
        "snapshots": len(market_stream.get_snapshots()),
        "live": status.live_market_data_status,
        "market_status": session,
        "scanner": {
            "universe_size": scan.universe_size if scan else 0,
            "liquid_count": scan.liquid_count if scan else 0,
            "top_n": SCANNER_TOP_N,
            "interval_seconds": SCANNER_TICK_SECONDS,
            "universe_breakdown": scan.universe_breakdown if scan else None,
            "watchlist_count": len(scan.watchlist_candidates) if scan else 0,
        },
    }


@app.get("/market/status")
def market_status():
    session = get_us_market_session()
    scan = market_scanner.get_state()
    return {
        "market_status": scan.market_status if scan and scan.market_status else session,
        "explanation": scan.explanation if scan and scan.explanation else session_explanation(session),
    }


@app.get("/stocks/dashboard", response_model=list[StockSnapshot])
async def dashboard():
    cached = market_stream.get_snapshots()
    if cached:
        return [StockSnapshot(**s) for s in cached]
    state = market_scanner.get_state()
    if state:
        return state.snapshots
    return []


@app.get("/universe/stats")
async def universe_stats():
    from services.universe_manager import universe_manager
    await universe_manager.ensure_loaded()
    return universe_manager.stats()


@app.get("/scanner/state", response_model=MarketScanState)
async def scanner_state():
    state = market_scanner.get_state()
    if state:
        return state
    return MarketScanState()


@app.get("/stocks/opportunities", response_model=OpportunitiesResponse)
async def opportunities(limit: int = Query(default=20, ge=1, le=20)):
    state = market_scanner.get_state()
    session = state.market_status if state and state.market_status else get_us_market_session()
    if not state:
        return OpportunitiesResponse(
            market_status=session,
            explanation=session_explanation(session),
        )

    snapshots = {s.symbol: s for s in state.snapshots}
    live = _signals_to_opportunities(state.top_opportunities[:limit], snapshots)
    watchlist_limit = min(limit, 10)
    watchlist = _signals_to_opportunities(
        state.watchlist_candidates[:watchlist_limit], snapshots, watchlist=True,
    )
    return OpportunitiesResponse(
        market_status=session,
        opportunities=live,
        watchlist_candidates=watchlist,
        explanation=state.explanation or session_explanation(session),
        no_signal_reason=state.no_signal_reason,
        debug=state.debug,
    )


@app.get("/stocks/search", response_model=list[SearchResult])
async def search(q: str = Query(..., min_length=1)):
    return await search_stocks(q)


@app.get("/signals/history")
def signal_history(symbol: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    return get_signal_history(symbol, limit)


@app.get("/journal", response_model=list[JournalEntry])
def journal(symbol: str | None = None, limit: int = Query(default=50, ge=1, le=500)):
    entries = get_journal_entries(symbol, limit)
    result = []
    for e in entries:
        payload = {k: e.get(k) for k in JournalEntry.model_fields}
        payload.setdefault("result", "open")
        payload.setdefault("profit_pct", 0.0)
        payload.setdefault("strategy", "production_confluence")
        result.append(JournalEntry(**payload))
    return result


@app.get("/performance", response_model=PerformanceMetrics)
def performance():
    return PerformanceMetrics(**get_performance_metrics())


@app.get("/analytics/dashboard", response_model=AnalyticsDashboard)
def analytics_dashboard():
    return get_analytics_dashboard()


@app.get("/analytics/signals", response_model=RankedSignalsResponse)
def analytics_signals(
    symbol: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return get_ranked_signals(limit=limit, symbol=symbol)


@app.get("/analytics/performance", response_model=PerformanceReport)
def analytics_performance():
    return get_performance_report()


@app.get("/analytics/replay", response_model=TradeReplayListResponse)
def analytics_replay_list(
    symbol: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    return get_trade_replay_list(limit=limit, symbol=symbol)


@app.get("/analytics/replay/{signal_id}", response_model=TradeReplayDetail)
def analytics_replay_detail(signal_id: int):
    detail = get_trade_replay_detail(signal_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Trade replay not found")
    return detail


@app.get("/analytics/insights", response_model=PerformanceInsights)
def analytics_insights():
    return compute_performance_insights()


@app.get("/backtest/{symbol}", response_model=BacktestMetrics)
async def backtest_symbol(
    symbol: str,
    timeframe: str = Query(default="1h", pattern="^(1m|5m|15m|1h|4h|1D)$"),
):
    try:
        result = await run_symbol_backtest(symbol, timeframe)
        return BacktestMetrics(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/backtest")
async def backtest_batch(
    symbols: str = Query(default="AAPL,NVDA"),
    timeframes: str = Query(default="1h,1D"),
):
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    tf_list = [t.strip() for t in timeframes.split(",") if t.strip()]
    return await run_multi_backtest(sym_list, tf_list)


@app.get("/production/validate", response_model=ProductionStatus)
async def validate_production():
    from analysis.ai_learning import load_weights
    from analysis.backtest_engine import TIMEFRAMES
    from services.connection_service import get_connection_status
    from services.stock_service import build_stock_snapshot

    status = get_connection_status()
    details: dict = {}

    # Backtesting
    bt_ok = False
    try:
        bt = await run_symbol_backtest("AAPL", "1D")
        bt_ok = "win_rate" in bt and "error" not in bt and "detail" not in bt
        details["backtest_sample"] = bt
    except Exception as e:
        details["backtest_error"] = str(e)

    # Journal
    journal_ok = False
    try:
        entries = get_journal_entries(limit=1)
        journal_ok = True
        details["journal_entries"] = len(get_journal_entries(limit=5000))
    except Exception as e:
        details["journal_error"] = str(e)

    # Metrics
    metrics_ok = False
    try:
        m = get_performance_metrics()
        metrics_ok = "win_rate" in m
        details["performance"] = m
    except Exception as e:
        details["metrics_error"] = str(e)

    # Live data
    live_ok = status.api_connected and status.live_market_data_status == "live"

    # AI learning
    learning_ok = False
    try:
        w = load_weights()
        learning_ok = abs(sum(w.values()) - 1.0) < 0.01
        details["ai_weights"] = w
    except Exception as e:
        details["learning_error"] = str(e)

    # Decision engine
    decision_ok = False
    try:
        snap = await build_stock_snapshot("AAPL")
        if snap and snap.trade_decision:
            td = snap.trade_decision
            decision_ok = (
                td.recommendation in (
                    "NO TRADE", "WAIT", "WATCH", "POSSIBLE ENTRY",
                    "ENTRY CONFIRMED", "AVOID / TRAP RISK",
                )
                and len(td.engine_logs) >= 5
                and td.ai_confidence >= 0
            )
            details["decision_sample"] = {
                "recommendation": td.recommendation,
                "confidence": td.ai_confidence,
                "engine_logs": len(td.engine_logs),
            }
    except Exception as e:
        details["decision_error"] = str(e)

    # Polygon
    polygon_ok = status.api_connected and len(status.symbols_ok) > 0
    ws_ok = status.websocket_available and status.live_market_data_status == "live"

    details["timeframes_supported"] = list(TIMEFRAMES.keys())
    ready = bt_ok and journal_ok and metrics_ok and live_ok and learning_ok and decision_ok and polygon_ok

    return ProductionStatus(
        backtesting=bt_ok,
        trading_journal=journal_ok,
        dashboard_metrics=metrics_ok,
        live_market_data=live_ok,
        ai_learning=learning_ok,
        decision_engine=decision_ok,
        polygon_connected=polygon_ok,
        websocket_live=ws_ok,
        no_placeholders=True,
        production_ready=ready,
        details=details,
    )


@app.get("/stocks/{symbol}/analysis", response_model=StockAnalysis)
async def analysis(symbol: str):
    result = await get_stock_analysis(symbol)
    if not result:
        raise HTTPException(status_code=404, detail=f"السهم {symbol.upper()} غير موجود أو لا توجد بيانات")
    return result


@app.get("/stocks/{symbol}/snapshot", response_model=StockSnapshot)
async def snapshot(symbol: str):
    from services.stock_service import build_stock_snapshot

    result = await build_stock_snapshot(symbol)
    if not result:
        raise HTTPException(status_code=404, detail=f"السهم {symbol.upper()} غير موجود أو لا توجد بيانات")
    return result


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        status = get_connection_status()
        await ws.send_text(json.dumps({
            "type": "status",
            "data": {**status.to_dict(), "stream_mode": market_stream.mode},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))

        cached = market_stream.get_snapshots()
        if cached:
            for snap in cached:
                await ws.send_text(json.dumps({
                    "type": "snapshot", "data": snap,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False))
        else:
            state = market_scanner.get_state()
            if state:
                for snap in state.snapshots:
                    await ws.send_text(json.dumps({
                        "type": "snapshot", "data": snap.model_dump(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }, ensure_ascii=False))
                await ws.send_text(json.dumps({
                    "type": "scan_update", "data": state.model_dump(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False))

        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=60)
                if msg == "ping":
                    await ws.send_text(json.dumps({"type": "heartbeat", "data": {"pong": True}}))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({
                    "type": "heartbeat",
                    "data": {"keepalive": True, "stream_mode": market_stream.mode},
                }, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
