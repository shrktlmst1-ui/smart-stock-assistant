"""Production WebSocket truth audit — taps running hub only (no second connection)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from analysis.early_upward_surge import DISPLAY_REAL_JUMP_ALERT
from models.opportunity_now import OpportunityNowSignal
from models.pre_move import (
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from services.aggregate_wave_tracker import aggregate_wave_tracker
from services.executed_buy_pressure import executed_buy_pressure_registry
from services.live_feed_pipeline import live_feed_pipeline
from services.live_price_registry import live_price_registry
from services.market_session import get_us_market_session
from services.real_jump_alert_layer import apply_real_jump_display, evaluate_premove_real_jump
from services.stocks_ws_hub import stocks_ws_hub


@dataclass
class ProductionTruthReport:
    mode: str = "production_hub"
    session: str = ""
    auth_success: bool = False
    a_subscribe_success: bool = False
    t_subscribe_success: bool = False
    q_subscribe_success: bool = False
    subscribe_success: bool = False
    provider_status_messages: list[str] = field(default_factory=list)
    subscribed_channels: dict = field(default_factory=dict)
    aggregates_delta: int = 0
    trades_delta: int = 0
    quotes_delta: int = 0
    last_trade: dict = field(default_factory=dict)
    last_quote: dict = field(default_factory=dict)
    dynamic_symbols: list[str] = field(default_factory=list)
    pipeline_results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    passed: bool = False

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "session": self.session,
            "auth_success": self.auth_success,
            "a_subscribe_success": self.a_subscribe_success,
            "t_subscribe_success": self.t_subscribe_success,
            "q_subscribe_success": self.q_subscribe_success,
            "subscribe_success": self.subscribe_success,
            "provider_status_messages": self.provider_status_messages,
            "subscribed_channels": self.subscribed_channels,
            "aggregates_delta": self.aggregates_delta,
            "trades_delta": self.trades_delta,
            "quotes_delta": self.quotes_delta,
            "last_trade": self.last_trade,
            "last_quote": self.last_quote,
            "dynamic_symbols": self.dynamic_symbols,
            "pipeline_results": self.pipeline_results,
            "errors": self.errors,
            "passed": self.passed,
        }


def dynamic_symbols_from_aggregates(limit: int = 8) -> list[str]:
    """Rank symbols by live aggregate activity — no REST snapshot, no fixed names."""
    ranked: list[tuple[str, float, int]] = []
    for sym, rec in aggregate_wave_tracker.iter_live_waves():
        ranked.append((sym, rec.current_move_pct, len(rec.bars)))
    if not ranked:
        for sym, rec in aggregate_wave_tracker._waves.items():
            if len(rec.bars) >= 2:
                ranked.append((sym, rec.current_move_pct, len(rec.bars)))
    ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [s for s, _, _ in ranked[:limit]]


def _premove_from_live(symbol: str, price: float, change_pct: float) -> PreMoveSignal:
    bp = executed_buy_pressure_registry.get(symbol)
    spread = 2.0
    if bp and bp.quotes.bid > 0 and bp.quotes.ask > 0:
        spread = (bp.quotes.ask - bp.quotes.bid) / ((bp.quotes.ask + bp.quotes.bid) / 2) * 100
    wave = aggregate_wave_tracker.get(symbol)
    vol_acc = wave.volume_acceleration() if wave else 0.0
    if wave:
        change_pct = wave.current_move_pct
    return PreMoveSignal(
        signal_id=f"LIVE:{symbol}:{int(time.time())}",
        symbol=symbol,
        current_price=price,
        change_percent=change_pct,
        pre_move_score=50,
        status="EARLY_ENTRY",
        lifecycle="EARLY_ENTRY",
        validated=True,
        first_detected_price=price,
        trigger_price=price,
        display_confirmed=True,
        volume=PreMoveVolumeMetrics(volume_acceleration_1m=max(vol_acc, 0.0), rvol=1.5),
        early_activity=PreMoveEarlyActivityMetrics(
            trade_velocity=float(bp.pressure_windows((60.0,))[60.0].trade_count if bp else 0),
            price_volume_response=0.4,
            micro_higher_lows=True,
            breakout_pressure_score=40.0,
        ),
        vwap=PreMoveVwapMetrics(vwap_hold=True),
        liquidity=PreMoveLiquidityMetrics(liquidity_score=60.0, spread_percent=spread),
        late_move=PreMoveLateMoveMetrics(is_too_late=False),
        stage_progression=PreMoveStageProgressionMetrics(
            stage_lifecycle="EARLY_ENTRY",
            persistence_minutes=2,
            move_from_base_pct=change_pct,
        ),
    )


def evaluate_pipeline(symbol: str, price: float, change_pct: float) -> dict:
    sym = symbol.upper()
    wave = aggregate_wave_tracker.get(sym)
    result = {
        "symbol": sym,
        "live_price": price,
        "wave_phase": wave.phase.value if wave else "NONE",
        "wave_move_pct": wave.current_move_pct if wave else 0.0,
        "real_jump_alert": False,
        "display_type": "",
        "reject_reason": "",
        "confirmed": False,
    }
    if price <= 0:
        result["reject_reason"] = "no_live_price"
        return result
    verdict = evaluate_premove_real_jump(_premove_from_live(sym, price, change_pct))
    result["reject_reason"] = verdict.reject_reason or ""
    result["confirmed"] = verdict.confirmed
    if verdict.confirmed or (verdict.wave and verdict.wave.current_move_pct >= 50):
        sig = apply_real_jump_display(
            OpportunityNowSignal(symbol=sym, name=sym, price=price, change_percent=change_pct),
            verdict,
        )
        result["display_type"] = sig.display_type
        result["real_jump_alert"] = sig.display_type == DISPLAY_REAL_JUMP_ALERT
    return result


async def ensure_dynamic_tq_subscriptions(max_symbols: int = 8) -> list[str]:
    """Merge dynamic aggregate leaders into jump consumer T/Q — same production hub."""
    dynamic = dynamic_symbols_from_aggregates(max_symbols)
    existing = stocks_ws_hub.get_consumer_symbols("jump")
    merged = list(dict.fromkeys(existing + dynamic))[:120]
    if merged != existing:
        stocks_ws_hub.set_consumer("jump", merged, ("T", "Q"))
        await stocks_ws_hub.apply_pending_sync()
    return dynamic


async def run_production_truth_audit(listen_seconds: int = 45) -> ProductionTruthReport:
    report = ProductionTruthReport(session=get_us_market_session())

    if not stocks_ws_hub.is_running:
        report.errors.append(
            "stocks_ws_hub_not_running — audit must run inside uvicorn process or via /internal/ws-truth"
        )
        return report

    hub_snap = stocks_ws_hub.audit_snapshot()
    report.auth_success = hub_snap["shards_connected"] > 0 and hub_snap["authenticated"]
    report.provider_status_messages = hub_snap.get("provider_status_messages", [])[-30:]
    report.subscribed_channels = hub_snap.get("channels_by_type", {})

    ch = report.subscribed_channels
    report.a_subscribe_success = ch.get("A_count", 0) > 0 or ch.get("A_wildcard", False)
    report.t_subscribe_success = ch.get("T_count", 0) > 0
    report.q_subscribe_success = ch.get("Q_count", 0) > 0
    report.subscribe_success = report.t_subscribe_success and report.q_subscribe_success

    report.dynamic_symbols = await ensure_dynamic_tq_subscriptions()
    await asyncio.sleep(2.0)
    hub_snap = stocks_ws_hub.audit_snapshot()
    report.subscribed_channels = hub_snap.get("channels_by_type", {})
    report.t_subscribe_success = report.subscribed_channels.get("T_count", 0) > 0
    report.q_subscribe_success = report.subscribed_channels.get("Q_count", 0) > 0
    report.subscribe_success = report.t_subscribe_success and report.q_subscribe_success
    report.provider_status_messages = hub_snap.get("provider_status_messages", [])[-40:]

    agg0 = live_feed_pipeline.stats.aggregates
    t0 = live_price_registry.status.trades_received
    q0 = live_price_registry.status.quotes_received

    deadline = time.monotonic() + listen_seconds
    while time.monotonic() < deadline:
        await asyncio.sleep(1.0)

    report.aggregates_delta = live_feed_pipeline.stats.aggregates - agg0
    report.trades_delta = live_price_registry.status.trades_received - t0
    report.quotes_delta = live_price_registry.status.quotes_received - q0

    best_trade_sym = ""
    best_trade_ts = ""
    for sym in report.dynamic_symbols + list(live_price_registry.status.subscribed_symbols):
        tick = live_price_registry.get_tick(sym)
        if not tick or tick.price <= 0:
            continue
        ex = tick.exchange_timestamp.isoformat() if tick.exchange_timestamp else ""
        if ex >= best_trade_ts:
            best_trade_ts = ex
            best_trade_sym = sym
            report.last_trade = {
                "symbol": sym,
                "price": tick.price,
                "exchange_time": ex,
                "received_at": tick.received_at.isoformat(),
            }

    best_quote_sym = ""
    best_quote_ts = ""
    for sym in report.dynamic_symbols + list(live_price_registry.status.subscribed_symbols):
        quote = live_price_registry.get_quote(sym)
        if not quote or quote.bid <= 0:
            continue
        ex = quote.exchange_timestamp.isoformat() if quote.exchange_timestamp else ""
        if ex >= best_quote_ts:
            best_quote_ts = ex
            best_quote_sym = sym
            report.last_quote = {
                "symbol": sym,
                "price": round((quote.bid + quote.ask) / 2, 4),
                "bid": quote.bid,
                "ask": quote.ask,
                "exchange_time": ex,
                "received_at": quote.received_at.isoformat(),
            }

    pipeline_syms = list(dict.fromkeys([best_trade_sym, best_quote_sym] + report.dynamic_symbols[:3]))
    for sym in pipeline_syms:
        if not sym:
            continue
        tick = live_price_registry.get_tick(sym)
        if not tick:
            continue
        wave = aggregate_wave_tracker.get(sym)
        chg = wave.current_move_pct if wave else 0.0
        report.pipeline_results.append(evaluate_pipeline(sym, tick.price, chg))

    if report.trades_delta == 0 and live_price_registry.status.trades_received > 0 and report.last_trade:
        report.errors.append("no_new_trades_in_window_using_last_known_tick")

    report.passed = (
        report.auth_success
        and report.t_subscribe_success
        and report.q_subscribe_success
        and report.trades_delta > 0
        and report.quotes_delta > 0
        and bool(report.last_trade.get("symbol"))
        and bool(report.last_quote.get("symbol"))
        and len(report.pipeline_results) > 0
    )
    return report
