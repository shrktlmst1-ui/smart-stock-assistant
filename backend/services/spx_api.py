"""FastAPI router for the SPX-only decision surface."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from models.spx_signal import SPXHealth, SPXSignal
from services.spx_signal_service import spx_signal_service

router = APIRouter(prefix="/spx", tags=["SPX Options"])


@router.get("/signal", response_model=SPXSignal)
async def spx_signal() -> SPXSignal:
    """Return the latest SPX decision, refreshing it when none exists."""
    if spx_signal_service.last_signal is None:
        return await spx_signal_service.evaluate()
    return spx_signal_service.last_signal


@router.post("/signal/refresh", response_model=SPXSignal)
async def spx_signal_refresh() -> SPXSignal:
    return await spx_signal_service.evaluate()


@router.get("/health", response_model=SPXHealth)
def spx_health() -> SPXHealth:
    return spx_signal_service.health()


@router.get("/decision")
def spx_decision() -> dict:
    signal = spx_signal_service.last_signal
    if signal is None:
        raise HTTPException(status_code=503, detail="SPX signal not initialized")
    return {
        "symbol": "I:SPX",
        "decision": signal.decision,
        "score": signal.score,
        "confidence": signal.confidence,
        "regime": signal.regime,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "take_profit_1": signal.take_profit_1,
        "take_profit_2": signal.take_profit_2,
        "reason": signal.reason,
        "kill_switch": signal.kill_switch,
    }
