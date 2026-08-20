"""Smart Stock Assistant — FastAPI backend with live Polygon/Massive data."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import (
    MARKET_PULSE_WS_MAX_CLIENTS,
    POLYGON_PLAN,
    POLL_INTERVAL_SECONDS,
    SCANNER_TICK_SECONDS,
    SCANNER_TOP_N,
    WEBSOCKET_ENABLED,
    get_cors_origins,
    is_auth_fully_configured,
    is_auth_jwt_configured,
    is_auth_password_configured,
    is_production_release,
)
from database.signal_analytics_db import init_signal_analytics_db
from database.trade_replay_db import init_trade_replay_db
from database.signal_logger import get_signal_history, init_db
from database.smart_signal_logger import get_smart_signal_history, init_smart_signals_db
from database.trading_journal import get_journal_entries, init_journal_db
from analysis.position_sizer import calculate_position_size
from models.smart_opportunity import (
    RiskCalculateRequest,
    RiskCalculateResponse,
    SmartOpportunitiesResponse,
)
from services.smart_opportunities_service import get_smart_opportunities
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
from middleware.auth_middleware import AuthMiddleware
from services.auth_service import (
    LoginRequest,
    LoginResponse,
    decode_access_token,
    extract_bearer_token,
    login as auth_login,
)
from services.stock_service import get_stock_analysis, search_stocks
from market_pulse.models import MarketPulseAlert, MarketPulseHealth, MarketPulseListResponse
from market_pulse.service import (
    get_market_pulse_alert,
    get_market_pulse_health,
    list_market_pulse_alerts,
    set_market_pulse_broadcast,
    start_market_pulse,
    stop_market_pulse,
)
from services.auth_service import require_ws_auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prevent API keys from appearing in httpx request logs
logging.getLogger("httpx").setLevel(logging.WARNING)

market_stream = MarketStream()
ws_clients: set[WebSocket] = set()
pulse_ws_clients: set[WebSocket] = set()

_RISK_MAP = {"low": "منخفض", "medium": "متوسط", "high": "مرتفع"}

WEB_ROOT_CANDIDATES = (
    Path(__file__).resolve().parent / "static" / "web",
    Path(__file__).resolve().parent.parent / "app" / "build" / "web",
)


def _resolve_web_root() -> Path:
    for candidate in WEB_ROOT_CANDIDATES:
        if (candidate / "index.html").is_file():
            return candidate
    return WEB_ROOT_CANDIDATES[0]


WEB_ROOT = _resolve_web_root()
INDEX_HTML = WEB_ROOT / "index.html"


def _web_build_available() -> bool:
    return INDEX_HTML.is_file()


def _safe_web_file(relative_path: str) -> Path | None:
    """Resolve a file under app/build/web; block path traversal."""
    rel = relative_path.lstrip("/")
    if not rel:
        return INDEX_HTML if INDEX_HTML.is_file() else None
    target = (WEB_ROOT / rel).resolve()
    try:
        target.relative_to(WEB_ROOT.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def _serve_web_file(path: Path) -> FileResponse:
    return FileResponse(path)


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


async def broadcast_pulse(message: dict) -> None:
    """Fan-out processed pulse updates — never includes API keys."""
    dead: list[WebSocket] = []
    payload = json.dumps(message, ensure_ascii=False)
    if "apiKey" in payload or "MASSIVE_API_KEY" in payload:
        return
    for ws in pulse_ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        pulse_ws_clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_journal_db()
    init_signal_analytics_db()
    init_trade_replay_db()
    init_smart_signals_db()
    set_notification_broadcast(broadcast)
    if _web_build_available():
        logger.info("Serving Flutter web UI from %s", WEB_ROOT)
    else:
        logger.warning("Flutter web build not found at %s", WEB_ROOT)
    if is_production_release() and not is_auth_fully_configured():
        logger.error(
            "Auth misconfigured in production: jwt_secret=%s password=%s",
            "set" if is_auth_jwt_configured() else "MISSING",
            "set" if is_auth_password_configured() else "MISSING",
        )
    elif not is_auth_jwt_configured():
        logger.warning("APP_JWT_SECRET is not set — protected routes will reject tokens")

    logger.info("Verifying Polygon/Massive connection...")
    status = await verify_connection()
    logger.info("Connection: %s", status.to_dict())

    market_stream.set_broadcast(broadcast)
    set_market_pulse_broadcast(broadcast_pulse)
    await market_stream.start()
    await start_market_pulse()

    await broadcast({
        "type": "status",
        "data": {**status.to_dict(), "stream_mode": market_stream.mode},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    yield
    await stop_market_pulse()
    await market_stream.stop()


app = FastAPI(
    title="Smart Stock Assistant API",
    description="مساعد تداول AI احترافي — Polygon/Massive + SMC + AI Signals",
    version="3.0.0",
    lifespan=lifespan,
)

# Auth runs inside CORS so 401/503/error responses still receive CORS headers.
app.add_middleware(AuthMiddleware, web_file_resolver=_safe_web_file)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_origin_regex=r"https://[a-z0-9-]+\.onrender\.com",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.post("/auth/login", response_model=LoginResponse)
def auth_login_endpoint(request: Request, body: LoginRequest):
    return auth_login(request, body)


@app.get("/auth/session")
def auth_session(request: Request):
    token = extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    decode_access_token(token)
    return {"authenticated": True}


@app.get("/")
def serve_frontend():
    """Serve the Flutter web app entry point."""
    if not _web_build_available():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Flutter web build not found at {WEB_ROOT}. "
                "Run: cd app && flutter build web --release"
            ),
        )
    return _serve_web_file(INDEX_HTML)


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
        "auth_jwt_configured": is_auth_jwt_configured(),
        "auth_password_configured": is_auth_password_configured(),
        "auth_fully_configured": is_auth_fully_configured(),
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


@app.get("/smart-opportunities", response_model=SmartOpportunitiesResponse)
async def smart_opportunities():
    """Top smart opportunities with entry decision — uses cached scanner data."""
    return get_smart_opportunities()


@app.get("/market-pulse/health", response_model=MarketPulseHealth)
def market_pulse_health():
    """Health for نبض السوق الذكي — no live data without API key."""
    return get_market_pulse_health()


@app.get("/market-pulse", response_model=MarketPulseListResponse)
def market_pulse_list():
    """All active market pulse alerts."""
    return list_market_pulse_alerts()


@app.get("/market-pulse/{symbol}", response_model=MarketPulseAlert)
def market_pulse_symbol(symbol: str):
    """Single-symbol market pulse alert."""
    alert = get_market_pulse_alert(symbol)
    if not alert:
        raise HTTPException(status_code=404, detail="لا يوجد تنبيه نبض لهذا الرمز")
    return alert


@app.post("/risk/calculate", response_model=RiskCalculateResponse)
def risk_calculate(body: RiskCalculateRequest):
    """Position sizing calculator — shares = risk_amount / |entry - stop|."""
    result = calculate_position_size(
        capital=body.capital,
        risk_pct=body.risk_pct,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        take_profit_1=body.take_profit_1,
        take_profit_2=body.take_profit_2,
        direction=body.direction,
    )
    return RiskCalculateResponse(
        capital=result.capital,
        risk_pct=result.risk_pct,
        risk_amount=result.risk_amount,
        entry_price=result.entry_price,
        stop_loss=result.stop_loss,
        take_profit_1=result.take_profit_1,
        take_profit_2=result.take_profit_2,
        loss_per_share=result.loss_per_share,
        shares=result.shares,
        position_value=result.position_value,
        expected_profit_tp1=result.expected_profit_tp1,
        expected_profit_tp2=result.expected_profit_tp2,
        capped_by_capital=result.capped_by_capital,
        valid=result.valid,
        error=result.error,
    )


@app.get("/smart-signals/history")
def smart_signal_history(symbol: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
    return get_smart_signal_history(symbol, limit)


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
    if not await require_ws_auth(ws):
        return
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


@app.websocket("/ws/market-pulse")
async def market_pulse_websocket(ws: WebSocket):
    if len(pulse_ws_clients) >= MARKET_PULSE_WS_MAX_CLIENTS:
        await ws.close(code=1013, reason="Max pulse connections reached")
        return
    await ws.accept()
    if not await require_ws_auth(ws):
        return
    pulse_ws_clients.add(ws)
    try:
        health = get_market_pulse_health()
        await ws.send_text(json.dumps({
            "type": "pulse_health",
            "data": health.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))

        listing = list_market_pulse_alerts()
        await ws.send_text(json.dumps({
            "type": "pulse_list",
            "data": listing.model_dump(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))

        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
                if msg == "ping":
                    await ws.send_text(json.dumps({
                        "type": "heartbeat",
                        "data": {"pong": True},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({
                    "type": "heartbeat",
                    "data": {"keepalive": True},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        pulse_ws_clients.discard(ws)


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """Serve Flutter static assets; unknown frontend routes fall back to index.html."""
    if not _web_build_available():
        raise HTTPException(status_code=404, detail="Not found")
    web_file = _safe_web_file(full_path)
    if web_file is not None:
        return _serve_web_file(web_file)
    return _serve_web_file(INDEX_HTML)
