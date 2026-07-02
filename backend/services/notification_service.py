"""Notification service — WebSocket broadcast, Telegram prep."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

import httpx

from config import MIN_CONFIDENCE_PRODUCTION, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED
from models.trading import AISignal, TradeDecision

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]
_broadcast: BroadcastFn | None = None
_last_notified: dict[str, str] = {}


def set_broadcast(fn: BroadcastFn) -> None:
    global _broadcast
    _broadcast = fn


async def notify_signal(
    symbol: str,
    ai_signal: AISignal,
    price: float,
    decision: TradeDecision | None = None,
) -> None:
    """Notify only on ENTRY CONFIRMED (decision engine) or legacy high-confidence Buy/Sell."""
    actionable = False
    if decision and decision.recommendation == "ENTRY CONFIRMED":
        actionable = decision.ai_confidence >= MIN_CONFIDENCE_PRODUCTION
    elif ai_signal.confidence >= MIN_CONFIDENCE_PRODUCTION and ai_signal.signal != "Wait":
        actionable = True

    if not actionable:
        return

    signal_label = decision.recommendation if decision else ai_signal.signal
    key = f"{symbol}:{signal_label}"
    if _last_notified.get(symbol) == key:
        return
    _last_notified[symbol] = key

    payload = {
        "type": "notification",
        "data": {
            "symbol": symbol,
            "signal": signal_label,
            "confidence": decision.ai_confidence if decision else ai_signal.confidence,
            "reason": decision.trigger_reason if decision else ai_signal.reason,
            "risk_level": ai_signal.risk_level,
            "entry": ai_signal.entry,
            "stop_loss": ai_signal.stop_loss,
            "target_1": ai_signal.target_1,
            "target_2": ai_signal.target_2,
            "price": price,
            "sound": True,
            "desktop": True,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if _broadcast:
        await _broadcast(payload)

    if TELEGRAM_ENABLED:
        await send_telegram(symbol, ai_signal, price)


async def send_telegram(symbol: str, ai_signal: AISignal, price: float) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    text = (
        f"*{symbol}* — {ai_signal.signal}\n"
        f"Confidence: {ai_signal.confidence}%\n"
        f"Price: ${price}\n"
        f"Entry: ${ai_signal.entry} | SL: ${ai_signal.stop_loss}\n"
        f"T1: ${ai_signal.target_1} | T2: ${ai_signal.target_2}\n"
        f"Risk: {ai_signal.risk_level}\n"
        f"{ai_signal.reason}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            )
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
