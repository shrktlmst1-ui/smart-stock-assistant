"""SPX-only live signal service and 20-minute scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from analysis.spx_options_engine import SPX_SYMBOL, evaluate_spx
from models.spx_signal import SPXHealth, SPXOptionCandidate, SPXSignal
from services.polygon_client import PolygonAPIError, PolygonClient
from services.spx_options_snapshot import get_spx_option_chain
from services.spx_yahoo_fallback import get_spx_fallback_frames

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")


class SPXSignalService:
    def __init__(self) -> None:
        self.client = PolygonClient()
        self.last_signal: SPXSignal | None = None
        self.cycles = 0
        self._task: asyncio.Task | None = None
        self._running = False

    async def evaluate(self) -> SPXSignal:
        """Evaluate SPX and never leak provider failures as a 500 to the UI."""
        try:
            d1h, d15m, d5m = await asyncio.gather(
                self.client.get_aggregates(SPX_SYMBOL, 1, "hour", 120, 10),
                self.client.get_aggregates(SPX_SYMBOL, 15, "minute", 160, 10),
                self.client.get_aggregates(SPX_SYMBOL, 5, "minute", 220, 5),
            )
        except PolygonAPIError as exc:
            logger.warning("SPX Polygon data unavailable (%s): %s", exc.status_code, exc.message)
            try:
                d1h, d15m, d5m = await get_spx_fallback_frames()
                logger.info("SPX underlying fallback active: Yahoo ^SPX")
            except Exception as fallback_exc:
                logger.exception("SPX fallback failed: %s", fallback_exc)
                return self._safe_no_trade(
                    f"SPX market data unavailable ({exc.status_code}); kill switch active"
                )
        except Exception as exc:
            logger.exception("SPX market-data cycle failed: %s", exc)
            try:
                d1h, d15m, d5m = await get_spx_fallback_frames()
                logger.info("SPX underlying fallback active: Yahoo ^SPX")
            except Exception as fallback_exc:
                logger.exception("SPX fallback failed: %s", fallback_exc)
                return self._safe_no_trade("SPX market data unavailable; kill switch active")

        if d5m.empty or len(d5m) < 20:
            return self._safe_no_trade("SPX market data is insufficient; kill switch active")

        # First pass determines the candidate direction from the underlying only.
        base = evaluate_spx(d1h, d15m, d5m, options_ready=False)
        spot = float(d5m.iloc[-1]["close"]) if not d5m.empty else 0.0
        option = await self._best_0dte_option(spot, base.decision)

        # Final pass applies the 0DTE liquidity/options gate.
        signal = evaluate_spx(
            d1h,
            d15m,
            d5m,
            options_ready=bool(option and option.liquid),
        )
        signal.option = option
        if not option:
            signal.rejected_factors.append("0DTE option liquidity gate unavailable")
            signal.kill_switch = True
            signal.decision = "NO TRADE"
            signal.reason = f"{signal.reason}; 0DTE option data unavailable — no trade"
        self.last_signal = signal
        self.cycles += 1
        return signal

    def _safe_no_trade(self, reason: str) -> SPXSignal:
        signal = SPXSignal(
            decision="NO TRADE",
            score=0,
            regime="UNKNOWN",
            confidence="LOW",
            reason=reason,
            factors=[],
            rejected_factors=[reason],
            data_fresh=False,
            options_ready=False,
            kill_switch=True,
            cycle_id=str(uuid4()),
            timestamp=datetime.now(NY),
        )
        self.last_signal = signal
        self.cycles += 1
        return signal

    async def _best_0dte_option(self, spot: float, direction: str) -> SPXOptionCandidate | None:
        """Select the nearest ATM liquid 0DTE contract matching CALL/PUT direction."""
        if direction not in ("CALL", "PUT") or spot <= 0:
            return None

        today = datetime.now(NY).date().isoformat()
        try:
            chain = await get_spx_option_chain(
                self.client,
                expiration_date=today,
                contract_type=direction,
                limit=250,
            )
        except Exception as exc:
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
            liquid = (
                spread_pct <= 0.15
                and 0.30 <= abs(float(delta or 0)) <= 0.70
                and (volume >= 10 or oi >= 100)
            )
            candidates.append(SPXOptionCandidate(
                ticker=item.get("ticker"),
                contract_type=details.get("contract_type"),
                expiration_date=details.get("expiration_date"),
                strike=float(strike),
                bid=bid,
                ask=ask,
                midpoint=mid,
                spread_pct=spread_pct,
                delta=float(delta) if delta is not None else None,
                iv=float(item.get("implied_volatility")) if item.get("implied_volatility") is not None else None,
                volume=volume,
                open_interest=oi,
                liquid=liquid,
            ))

        liquid = [x for x in candidates if x.liquid]
        return min(liquid, key=lambda x: abs((x.strike or spot) - spot)) if liquid else None

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
