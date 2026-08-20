"""Market Pulse service — FastAPI integration layer."""

from __future__ import annotations

import logging

from config import MARKET_PULSE_ENABLED, is_market_pulse_fixture_allowed
from market_pulse.engine import MarketPulseEngine
from market_pulse.models import MarketPulseAlert, MarketPulseHealth, MarketPulseListResponse
from market_pulse.runtime import MarketPulseRuntime

logger = logging.getLogger(__name__)

_engine: MarketPulseEngine | None = None
_runtime: MarketPulseRuntime | None = None


def get_market_pulse_engine() -> MarketPulseEngine:
    global _engine
    if _engine is None:
        _engine = MarketPulseEngine()
    return _engine


def get_market_pulse_runtime() -> MarketPulseRuntime:
    global _runtime
    if _runtime is None:
        _runtime = MarketPulseRuntime(engine=get_market_pulse_engine())
    return _runtime


def reset_market_pulse_engine(engine: MarketPulseEngine | None = None) -> None:
    """Test hook."""
    global _engine, _runtime
    _engine = engine
    _runtime = None


def reset_market_pulse_runtime(runtime: MarketPulseRuntime | None = None) -> None:
    """Test hook."""
    global _runtime
    _runtime = runtime


def set_market_pulse_broadcast(fn) -> None:
    get_market_pulse_runtime().set_broadcast(fn)


async def start_market_pulse() -> None:
    await get_market_pulse_runtime().start()


async def stop_market_pulse() -> None:
    runtime = get_market_pulse_runtime()
    await runtime.stop()


def get_market_pulse_health() -> MarketPulseHealth:
    runtime = get_market_pulse_runtime()
    if not MARKET_PULSE_ENABLED:
        return get_market_pulse_engine().health()
    if is_market_pulse_fixture_allowed():
        return runtime.health()
    return runtime.health()


def list_market_pulse_alerts() -> MarketPulseListResponse:
    engine = get_market_pulse_engine()
    if not MARKET_PULSE_ENABLED and not is_market_pulse_fixture_allowed():
        return MarketPulseListResponse(enabled=False, alerts=[], count=0)
    health = get_market_pulse_health()
    if health.status == "missing_credentials" and not is_market_pulse_fixture_allowed():
        return MarketPulseListResponse(enabled=True, alerts=[], count=0)
    alerts = engine.list_alerts()
    return MarketPulseListResponse(enabled=True, alerts=alerts, count=len(alerts))


def get_market_pulse_alert(symbol: str) -> MarketPulseAlert | None:
    engine = get_market_pulse_engine()
    if not MARKET_PULSE_ENABLED and not is_market_pulse_fixture_allowed():
        return None
    health = get_market_pulse_health()
    if health.status == "missing_credentials" and not is_market_pulse_fixture_allowed():
        return None
    return engine.build_alert(symbol)


def get_pulse_for_symbol(symbol: str) -> dict | None:
    """Optional enrichment for smart-opportunities — returns None if unavailable."""
    alert = get_market_pulse_alert(symbol)
    if not alert:
        return None
    return {
        "pulse_score": alert.score,
        "pulse_decision": alert.decision,
        "pulse_headline": alert.headline,
        "pulse_is_live": alert.is_live,
        "pulse_catalyst": alert.catalyst.trigger_type if alert.catalyst else None,
    }
