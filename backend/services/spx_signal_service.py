"""SPX-only live signal service and 20-minute scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from analysis.spx_options_engine import SPX_SYMBOL, evaluate_spx
from models.spx_signal import SPXHealth, SPXOptionCandidate, SPXSignal
from services.polygon_client import PolygonClient, PolygonAPIError

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")


class SPXSignalService:
    def __init__(self) -> None:
        self.client = PolygonClient()
        self.last_signal: SPXSignal | None = None
        self.cycles = 0
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_alert_key: str | None = None

    async def evaluate(self) -> SPXSignal:
        """Build a fresh SPX-only multi-timeframe decision."""
        d1h, d15m, d5m = await asyncio.gather(
            self.client.get_aggregates(SPX_SYMBOL, 1, "hour", 120, 10),
            self.client.get_aggregates(SPX_SYMBOL, 15, "minute", 160, 10),
            self.client.get_aggregates(SPX_SYMBOL, 5, "minute", 220, 5),
        )
        spot = float(d5m.iloc[-1]["close"]) if not d5m.empty else 0.0
        option = await self._best_0dte_option(spot)
        signal = evaluate_spx(
            d1h, d15m, d5m,
            options_ready=bool(option and option.liquid),
        )
        signal.option = option
        if signal.decision == "NO TRADE" and not option:
            signal.rejected_factors.append("0DTE option liquidity gate unavailable")
        self.last_signal = signal
        self.cycles += 1
        return signal

    async def _best_0dte_option(self, spot: float) -> SPXOptionCandidate | None:
        """Select the nearest ATM liquid 0DTE contract in the requested direction.

        The chain endpoint is used only for discovery; no option is considered
        executable unless bid/ask, spread, delta and liquidity checks pass.
        """
        today = datetime.now(NY).date().isoformat()
        try:
            chain = await self.client.get_options_chain(
                SPX_SYMBOL, expiration_date=today, limit=250,
            )
        except (PolygonAPIError, Exception) as exc:
            logger.warning("SPX 0DTE chain unavailable: %s", exc)
            return None

        candidates: list[SPXOptionCandidate] = []
        for item in chain:
            details = item.get("details") or {}
            quote = item.get("last_quote") or {}
            greeks = item.get("greeks") or {}
            day = item.get("day") or {}
            strike = details.get("strike_price")
            bid, ask = quote.get("bid"), quote.get("ask")
            if strike is None or bid is None or ask is None:
                continue
            bid, ask = float(bid), float(ask)
            mid = (bid + ask) / 2
            if mid <= 0 or ask < bid:
                continue
            spread_pct = (ask - bid) / mid
            delta = greeks.get("delta")
            volume = int(day.get("volume") or 0)
            oi = int(item.get("open_interest") or 0)
            liquid = spread_pct <= 0.15 and 0.30 <= abs(float(delta or 0)) <= 0.70 and (volume >= 10 or oi >= 100)
            candidates.append(SPXOptionCandidate(
                ticker=item.get("ticker"),
                contract_type=details.get("contract_type"),
                expiration_date=details.get("expiration_date"),
                strike=float(strike), bid=bid, ask=ask, midpoint=mid,
                spread_pct=spread_pct, delta=float(delta) if delta is not None else None,
                iv=float(item.get("implied_volatility")) if item.get("implied_volatility") is not None else None,
                volume=volume, open_interest=oi, liquid=liquid,
            ))
        if not candidates:
            return None
        liquid = [x for x in candidates if x.liquid]
        if not liquid:
            return None
        return min(liquid, key=lambda x: abs((x.strike or spot) - spot))

    def health(self) -> SPXHealth:
        signal = self.last_signal
        return SPXHealth(
            running=self._running,
            last_cycle=signal.timestamp if signal else None,
            last_decision=signal.decision if signal else "NO TRADE",
            last_score=signal.score if signal else 0,
            stale=signal is None or not signal.data_fresh,
            kill_switch=signal.kill_switch if signal else True,
            cycles=self.cycles,
        )

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.evaluate()
            except Exception:
                logger.exception("SPX signal cycle failed")
            await asyncio.sleep(20 * 60)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="spx-20m-signal-cycle")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.client.close()


spx_signal_service = SPXSignalService()
