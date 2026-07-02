"""Institutional AI Scanner — universe manager, threaded coarse scan, deep top 20."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from config import (
    SCANNER_BOARD_SIZE,
    SCANNER_DEEP_POOL,
    SCANNER_MIN_DAY_VOLUME,
    SCANNER_TICK_SECONDS,
    SCANNER_TOP_N,
    SCANNER_UNIVERSE_REFRESH_SECONDS,
)
from analysis.professional_decision import (
    FACTOR_WEIGHTS,
    MIN_FACTOR_SCORE,
    MIN_PROFESSIONAL_SCORE,
    REQUIRED_INSTITUTIONAL_FACTORS,
)
from models.scanner import (
    MarketScanState,
    ScanRow,
    ScanSignalSummary,
    ScannerBoard,
    ScannerStageCounts,
)
from models.stock import StockSnapshot
from services.coarse_scanner import coarse_scan_threaded
from services.market_session import (
    MarketSession,
    get_us_market_session,
    is_regular_session,
    session_explanation,
)
from services.polygon_client import PolygonClient
from services.scanner_filters import (
    TickerMetrics,
    metrics_to_scan_row,
)
from services.stock_service import build_snapshots_batch
from services.universe_manager import universe_manager
from services.volume_cache import enrich_adv30_batch

logger = logging.getLogger(__name__)

WATCHLIST_DISPLAY_N = 10

BOARD_TITLES = {
    "most_active": "Most Active",
    "top_gainers": "Top Gainers",
    "top_losers": "Top Losers",
    "highest_rvol": "Highest Relative Volume",
    "unusual_volume": "Unusual Volume",
    "opening_range_breakout": "Opening Range Breakout",
    "momentum": "Momentum Scanner",
    "institutional": "Institutional Scanner",
}


class MarketScannerService:
    """Phase 3 — full US market, no fixed watchlist."""

    def __init__(self) -> None:
        self.client = PolygonClient()
        self._scored_metrics: list[tuple[TickerMetrics, float]] = []
        self._candidate_symbols: list[str] = []
        self._snapshots: dict[str, StockSnapshot] = {}
        self._snapshot_raw: dict[str, dict] = {}
        self._universe_updated: float = 0.0
        self._last_state: MarketScanState | None = None
        self.last_tick_ms: float = 0.0
        self.universe_size: int = 0
        self.market_session: MarketSession = "CLOSED"

    @staticmethod
    def _is_watchlist_candidate(snap: StockSnapshot) -> bool:
        """High-quality pre/post-market candidates — full analysis, no threshold bypass."""
        td = snap.trade_decision
        score = td.professional_ai_score or snap.ai_signal.ai_score
        signal = (td.professional_signal or td.recommendation or "WAIT").upper()
        if signal == "AVOID":
            return False
        if td.trap_risk >= 55:
            return False
        if td.news_risk >= 60:
            return False
        return score >= MIN_PROFESSIONAL_SCORE

    @staticmethod
    def _ai_score(snap: StockSnapshot) -> float:
        return snap.trade_decision.professional_ai_score or snap.ai_signal.ai_score

    @staticmethod
    def _failed_factors(snap: StockSnapshot) -> list[str]:
        fs = snap.trade_decision.factor_scores or {}
        return [k for k in REQUIRED_INSTITUTIONAL_FACTORS if fs.get(k, 0) < MIN_FACTOR_SCORE]

    @staticmethod
    def _rejection_reason(snap: StockSnapshot) -> str:
        td = snap.trade_decision
        signal = (td.professional_signal or td.recommendation or "WAIT").upper()
        if td.all_filters_passed and signal in ("BUY", "SELL"):
            return "Passed all institutional filters"
        if td.final_blocker:
            return td.final_blocker
        if td.buy_blockers:
            return td.buy_blockers[0]
        failed = MarketScannerService._failed_factors(snap)
        parts: list[str] = []
        if failed:
            labels = [f.replace("_", " ") for f in failed[:6]]
            parts.append(f"Failed institutional ({len(failed)}/{len(REQUIRED_INSTITUTIONAL_FACTORS)}): {', '.join(labels)}")
        if signal == "AVOID":
            parts.append("Signal AVOID (trap/news risk)")
        elif (td.professional_ai_score or snap.ai_signal.ai_score) < MIN_PROFESSIONAL_SCORE:
            parts.append(f"AI score below {MIN_PROFESSIONAL_SCORE}")
        elif not td.all_filters_passed:
            parts.append("Required institutional gates not passed")
        return "; ".join(parts) if parts else "Awaiting stronger confluence"

    @staticmethod
    def _aggregate_filter_failures(snapshots: list[StockSnapshot]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for snap in snapshots:
            for factor in MarketScannerService._failed_factors(snap):
                counts[factor] = counts.get(factor, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    @staticmethod
    def _build_stage_counts(
        session: MarketSession,
        symbols_scanned: int,
        universe_symbols: int,
        passed_liquidity: int,
        analyzed: list[StockSnapshot],
        passed_all: int,
    ) -> ScannerStageCounts:
        signals = [
            (s.trade_decision.professional_signal or s.trade_decision.recommendation or "WAIT").upper()
            for s in analyzed
        ]
        return ScannerStageCounts(
            market_status=session,
            symbols_scanned=symbols_scanned,
            universe_symbols=universe_symbols,
            passed_liquidity=passed_liquidity,
            deep_analysis_completed=len(analyzed),
            passed_all_filters=passed_all,
            signal_avoid=sum(1 for s in signals if s == "AVOID"),
            signal_wait=sum(1 for s in signals if s == "WAIT"),
            signal_buy=sum(1 for s in signals if s == "BUY"),
            signal_sell=sum(1 for s in signals if s == "SELL"),
            filter_failures=MarketScannerService._aggregate_filter_failures(analyzed),
        )

    @staticmethod
    def _build_no_signal_reason(
        session: MarketSession,
        symbols_scanned: int,
        passed_liquidity: int,
        deep_count: int,
        passed_all: int,
        filter_failures: dict[str, int],
    ) -> str:
        if passed_liquidity == 0:
            return (
                f"Market is {session}. Scanned {symbols_scanned:,} snapshot tickers; "
                f"none passed live liquidity filters (min day volume, RVOL, spread, market cap)."
            )
        if deep_count == 0:
            return (
                f"{passed_liquidity} symbol(s) passed liquidity but deep analysis returned no snapshots."
            )
        if passed_all == 0:
            top_fail = ", ".join(list(filter_failures.keys())[:5]) if filter_failures else "multiple factors"
            return (
                f"{deep_count} symbol(s) completed full SMC/trend/momentum analysis; "
                f"none passed all {len(REQUIRED_INSTITUTIONAL_FACTORS)} institutional factor gates (min {MIN_FACTOR_SCORE:.0f} each). "
                f"Most common failures: {top_fail}."
            )
        return ""

    @staticmethod
    def _top_watchlist_by_score(snapshots: list[StockSnapshot], limit: int = WATCHLIST_DISPLAY_N) -> list[StockSnapshot]:
        return sorted(snapshots, key=MarketScannerService._ai_score, reverse=True)[:limit]

    def get_snapshots(self) -> list[dict]:
        return [s.model_dump() for s in self._snapshots.values()]

    def get_state(self) -> MarketScanState | None:
        return self._last_state

    async def refresh_universe(self) -> None:
        t0 = time.monotonic()
        self.market_session = get_us_market_session()
        try:
            await universe_manager.ensure_loaded()
            raw = await self.client.get_full_market_snapshot()
            self.universe_size = len(raw)
            self._snapshot_raw = {(i.get("ticker") or "").upper(): i for i in raw if i.get("ticker")}

            if not is_regular_session(self.market_session):
                adv_candidates: list[str] = []
                symbol_set = universe_manager.symbol_set
                for item in raw:
                    sym = (item.get("ticker") or "").upper()
                    if sym not in symbol_set:
                        continue
                    prev = item.get("prevDay") or {}
                    prev_vol = int(prev.get("v") or 0)
                    if prev_vol >= SCANNER_MIN_DAY_VOLUME // 4:
                        adv_candidates.append(sym)
                adv_candidates.sort(
                    key=lambda s: int((self._snapshot_raw.get(s, {}).get("prevDay") or {}).get("v") or 0),
                    reverse=True,
                )
                await enrich_adv30_batch(self.client, adv_candidates)

            scored = await asyncio.to_thread(
                coarse_scan_threaded, raw, universe_manager, None, self.market_session,
            )
            self._scored_metrics = scored
            self._candidate_symbols = [m.symbol for m, _ in scored[:SCANNER_DEEP_POOL]]
            self._universe_updated = time.monotonic()

            ustats = universe_manager.stats()
            elapsed = (time.monotonic() - t0) * 1000
            logger.info(
                "Institutional scan: market=%d universe=%d liquid=%d deep_pool=%d session=%s (%.0fms)",
                self.universe_size,
                ustats.get("total", 0),
                len(scored),
                len(self._candidate_symbols),
                self.market_session,
                elapsed,
            )
        except Exception as e:
            logger.error("Universe refresh failed: %s", e)

    def _build_boards(self, metrics: list[TickerMetrics], snapshots: dict[str, StockSnapshot]) -> list[ScannerBoard]:
        now = datetime.now(timezone.utc).isoformat()
        n = SCANNER_BOARD_SIZE

        def rows_from(ms: list[TickerMetrics], reason_fn) -> list[ScanRow]:
            out: list[ScanRow] = []
            for m in ms[:n]:
                snap = snapshots.get(m.symbol)
                if snap and snap.trade_decision.professional_ai_score:
                    ai = snap.trade_decision.professional_ai_score
                elif snap:
                    ai = snap.ai_signal.ai_score
                else:
                    ai = m.composite_score
                row_data = metrics_to_scan_row(m, reason_fn(m))
                row_data["ai_score"] = ai
                out.append(ScanRow(**row_data))
            return out

        liquid = [m for m, _ in self._scored_metrics] if self._scored_metrics else metrics

        return [
            ScannerBoard(board_type="most_active", title=BOARD_TITLES["most_active"],
                rows=rows_from(sorted(liquid, key=lambda x: x.volume, reverse=True), lambda m: f"Vol {m.volume:,}"), updated_at=now),
            ScannerBoard(board_type="top_gainers", title=BOARD_TITLES["top_gainers"],
                rows=rows_from(sorted(liquid, key=lambda x: x.change_percent, reverse=True), lambda m: f"+{m.change_percent}%"), updated_at=now),
            ScannerBoard(board_type="top_losers", title=BOARD_TITLES["top_losers"],
                rows=rows_from(sorted(liquid, key=lambda x: x.change_percent), lambda m: f"{m.change_percent}%"), updated_at=now),
            ScannerBoard(board_type="highest_rvol", title=BOARD_TITLES["highest_rvol"],
                rows=rows_from(sorted(liquid, key=lambda x: x.relative_volume, reverse=True), lambda m: f"RVOL {m.relative_volume}x"), updated_at=now),
            ScannerBoard(board_type="unusual_volume", title=BOARD_TITLES["unusual_volume"],
                rows=rows_from([m for m in liquid if m.volume_spike] or sorted(liquid, key=lambda x: x.relative_volume, reverse=True)[:n],
                    lambda m: "Volume spike"), updated_at=now),
            ScannerBoard(board_type="opening_range_breakout", title=BOARD_TITLES["opening_range_breakout"],
                rows=rows_from([m for m in liquid if m.opening_range_breakout], lambda m: "ORB"), updated_at=now),
            ScannerBoard(board_type="momentum", title=BOARD_TITLES["momentum"],
                rows=rows_from(sorted(liquid, key=lambda x: x.momentum_score, reverse=True), lambda m: f"Momentum {m.momentum_score}"), updated_at=now),
            ScannerBoard(board_type="institutional", title=BOARD_TITLES["institutional"],
                rows=rows_from(self._institutional_metrics(liquid, snapshots), lambda m: "Institutional flow"), updated_at=now),
        ]

    @staticmethod
    def _institutional_metrics(liquid: list[TickerMetrics], snapshots: dict[str, StockSnapshot]) -> list[TickerMetrics]:
        inst: list[TickerMetrics] = []
        for m in liquid:
            snap = snapshots.get(m.symbol)
            if not snap:
                continue
            sm = snap.smart_money
            if sm.whale_order or sm.hidden_accumulation or sm.absorption or sm.iceberg_activity:
                inst.append(m)
        return inst or sorted(liquid, key=lambda x: x.relative_volume, reverse=True)[:SCANNER_BOARD_SIZE]

    @staticmethod
    def _snapshot_to_signal(snap: StockSnapshot, *, watchlist: bool = False) -> ScanSignalSummary:
        td = snap.trade_decision
        sm = snap.smart_money
        traps = snap.liquidity_traps
        vl = snap.volume_liquidity
        smc = snap.smc
        failed = MarketScannerService._failed_factors(snap)

        return ScanSignalSummary(
            symbol=snap.symbol,
            name=snap.name,
            price=snap.price,
            change_percent=snap.change_percent,
            entry=td.entry_zone_high if td.direction == "long" else td.entry_zone_low,
            stop_loss=td.stop_loss,
            take_profit_1=td.take_profit_1,
            take_profit_2=td.take_profit_2,
            risk_reward_ratio=td.risk_reward_ratio,
            confidence=td.ai_confidence,
            ai_score=td.professional_ai_score or snap.ai_signal.ai_score,
            ai_explanation=td.ai_explanation or td.trigger_reason,
            trap_risk=td.trap_risk,
            smart_money_score=snap.meters.institutional_activity,
            liquidity_score=snap.meters.liquidity_meter,
            news_risk=td.news_risk,
            recommendation=td.professional_signal or td.recommendation,
            expected_holding_time=td.expected_holding_time,
            all_filters_passed=td.all_filters_passed,
            failed_factors=failed,
            rejection_reason=MarketScannerService._rejection_reason(snap) if watchlist or not td.all_filters_passed else "",
            bos=smc.bos,
            choch=smc.choch,
            order_block=len(smc.order_blocks) > 0,
            fair_value_gap=any(not g.filled for g in smc.fair_value_gaps),
            liquidity_sweep=smc.liquidity_sweep,
            whale_order=sm.whale_order,
            fake_breakout=traps.fake_breakout,
            bull_trap=traps.bull_trap,
            bear_trap=traps.bear_trap,
            spoofing=traps.spoofing,
            absorption=sm.absorption,
            iceberg_order=sm.iceberg_activity,
            delta_imbalance=vl.delta_direction != "neutral" and abs(vl.buyer_pressure - vl.seller_pressure) > 15,
        )

    async def run_fast_tick(self) -> MarketScanState:
        t0 = time.monotonic()
        now_mono = time.monotonic()
        self.market_session = get_us_market_session()
        regular = is_regular_session(self.market_session)

        if now_mono - self._universe_updated > SCANNER_UNIVERSE_REFRESH_SECONDS or not self._scored_metrics:
            await self.refresh_universe()

        if not self._candidate_symbols:
            self.last_tick_ms = (time.monotonic() - t0) * 1000
            return self._empty_state()

        try:
            snapshots = await build_snapshots_batch(self._candidate_symbols, self.client)
        except Exception as e:
            logger.error("Deep analysis batch failed: %s", e)
            snapshots = []

        for snap in snapshots:
            if snap:
                self._snapshots[snap.symbol] = snap

        analyzed = [s for s in snapshots if s]
        ustats = universe_manager.stats()

        qualified = [s for s in analyzed if s.trade_decision.all_filters_passed]
        ranked = sorted(qualified, key=self._ai_score, reverse=True)[:SCANNER_TOP_N]

        if regular:
            watchlist_ranked = self._top_watchlist_by_score(analyzed, WATCHLIST_DISPLAY_N)
            if len(ranked) < SCANNER_TOP_N:
                logger.info(
                    "Institutional filter: %d/%d passed all factors (session=REGULAR)",
                    len(ranked), SCANNER_TOP_N,
                )
        else:
            watchlist_ranked = sorted(
                [s for s in analyzed if self._is_watchlist_candidate(s)],
                key=self._ai_score,
                reverse=True,
            )[:SCANNER_TOP_N]
            if not watchlist_ranked:
                watchlist_ranked = self._top_watchlist_by_score(analyzed, WATCHLIST_DISPLAY_N)
            logger.info(
                "Watchlist mode (%s): %d candidates from pool=%d",
                self.market_session,
                len(watchlist_ranked),
                len(analyzed),
            )

        filter_failures = self._aggregate_filter_failures(analyzed)
        debug = self._build_stage_counts(
            self.market_session,
            self.universe_size,
            ustats.get("total", 0),
            len(self._scored_metrics),
            analyzed,
            len(ranked),
        )
        no_signal_reason = self._build_no_signal_reason(
            self.market_session,
            self.universe_size,
            len(self._scored_metrics),
            len(analyzed),
            len(ranked),
            filter_failures,
        )

        keep_symbols = {s.symbol for s in ranked} | {s.symbol for s in watchlist_ranked}
        self._snapshots = {k: v for k, v in self._snapshots.items() if k in keep_symbols}

        opportunities = [self._snapshot_to_signal(s) for s in ranked]
        watchlist = [self._snapshot_to_signal(s, watchlist=True) for s in watchlist_ranked]
        result_snapshots = ranked if ranked else watchlist_ranked
        liquid_metrics = [m for m, _ in self._scored_metrics]
        boards = self._build_boards(liquid_metrics, self._snapshots)

        explanation = "" if regular else session_explanation(self.market_session)
        if regular and not opportunities and no_signal_reason:
            explanation = no_signal_reason

        self.last_tick_ms = (time.monotonic() - t0) * 1000
        state = MarketScanState(
            universe_size=self.universe_size,
            liquid_count=len(self._scored_metrics),
            candidate_pool=len(self._candidate_symbols),
            market_status=self.market_session,
            top_opportunities=opportunities,
            watchlist_candidates=watchlist,
            explanation=explanation,
            no_signal_reason=no_signal_reason,
            debug=debug,
            snapshots=result_snapshots,
            boards=boards,
            last_universe_refresh=datetime.fromtimestamp(
                self._universe_updated, tz=timezone.utc,
            ).isoformat() if self._universe_updated else "",
            last_tick_ms=round(self.last_tick_ms, 1),
            scan_interval_seconds=SCANNER_TICK_SECONDS,
            universe_breakdown=ustats.get("by_exchange"),
        )
        self._last_state = state
        return state

    def _empty_state(self) -> MarketScanState:
        session = get_us_market_session()
        ustats = universe_manager.stats()
        no_signal = self._build_no_signal_reason(
            session, self.universe_size, len(self._scored_metrics), 0, 0, {},
        )
        state = MarketScanState(
            universe_size=self.universe_size,
            liquid_count=len(self._scored_metrics),
            candidate_pool=0,
            market_status=session,
            explanation="" if is_regular_session(session) else session_explanation(session),
            no_signal_reason=no_signal,
            debug=ScannerStageCounts(
                market_status=session,
                symbols_scanned=self.universe_size,
                universe_symbols=ustats.get("total", 0),
                passed_liquidity=len(self._scored_metrics),
            ),
            last_tick_ms=round(self.last_tick_ms, 1),
            scan_interval_seconds=SCANNER_TICK_SECONDS,
        )
        self._last_state = state
        return state


market_scanner = MarketScannerService()
