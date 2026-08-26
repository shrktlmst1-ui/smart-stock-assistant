"""Jump Alert Registry — persistent alerts independent of scan snapshots."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

from config import JUMP_ALERT_TTL_SECONDS
from models.jump_alert import JumpAlert
from models.pre_move import PreMoveSignal
from models.scanner import OpportunitiesResponse
from models.stock import StockOpportunity

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class JumpAlertRegistry:
    """Thread-safe in-memory registry for sticky Jump Alerts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._alerts: dict[str, JumpAlert] = {}
        self._history: list[JumpAlert] = []

    def reset(self) -> None:
        with self._lock:
            self._alerts.clear()
            self._history.clear()

    def create_from_signal(self, sig: PreMoveSignal) -> JumpAlert:
        sym = sig.symbol.upper()
        now = _utc_now()
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=JUMP_ALERT_TTL_SECONDS)).isoformat()
        stage = sig.stage_progression.stage_lifecycle or sig.lifecycle or sig.status
        score = max(sig.pre_move_score, int(sig.stage_progression.stage_progression_score))
        reason = sig.reason or f"PreMove {sig.pre_move_score}/100"

        with self._lock:
            for alert in self._alerts.values():
                if alert.symbol == sym and alert.status == "ACTIVE":
                    alert.price = sig.current_price
                    alert.change_percent = sig.change_percent
                    alert.stage = stage
                    alert.score = score
                    alert.ai_signal = sig.status
                    alert.status_reason_ar = reason
                    logger.info(
                        "JUMP_ALERT_CREATED symbol=%s alert_id=%s created_at=%s price=%s "
                        "stage=%s score=%s action=updated",
                        sym,
                        alert.alert_id,
                        alert.created_at,
                        alert.price,
                        alert.stage,
                        alert.score,
                    )
                    return alert

            alert_id = str(uuid.uuid4())[:12]
            alert = JumpAlert(
                alert_id=alert_id,
                symbol=sym,
                name=sig.name or sym,
                created_at=created_at,
                expires_at=expires_at,
                price=sig.current_price,
                change_percent=sig.change_percent,
                stage=stage,
                score=score,
                ai_signal=sig.status,
                status="ACTIVE",
                status_reason_ar=reason,
            )
            self._alerts[alert_id] = alert

        logger.info(
            "JUMP_ALERT_CREATED symbol=%s alert_id=%s created_at=%s price=%s stage=%s score=%s",
            sym,
            alert.alert_id,
            alert.created_at,
            alert.price,
            alert.stage,
            alert.score,
        )
        return alert

    def purge_expired(self) -> list[JumpAlert]:
        now = _utc_now()
        expired: list[JumpAlert] = []
        with self._lock:
            for alert_id, alert in list(self._alerts.items()):
                if alert.status != "ACTIVE":
                    continue
                try:
                    exp = _parse_iso(alert.expires_at)
                except ValueError:
                    exp = now
                if now >= exp:
                    alert.status = "EXPIRED"
                    alert.removal_reason = "EXPIRED"
                    expired.append(alert)
                    self._history.append(alert)
                    del self._alerts[alert_id]
        for alert in expired:
            self._log_status(
                alert,
                still_stored=False,
                still_returned_by_api=False,
                displayed_by_ui=False,
                removal_reason="EXPIRED",
            )
        return expired

    def get_active_alerts(self) -> list[JumpAlert]:
        self.purge_expired()
        with self._lock:
            return sorted(
                [a for a in self._alerts.values() if a.status == "ACTIVE"],
                key=lambda a: a.created_at,
                reverse=True,
            )

    def get_history(self, *, limit: int = 50) -> list[JumpAlert]:
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def alert_to_opportunity(self, alert: JumpAlert) -> StockOpportunity:
        is_entry = alert.ai_signal in ("EARLY_ENTRY", "HIGH_CONVICTION_EARLY", "CONFIRMED_ENTRY")
        prefix = "🚀 قفزة محفوظة | "
        return StockOpportunity(
            symbol=alert.symbol,
            name=alert.name or alert.symbol,
            price=alert.price,
            change_percent=alert.change_percent,
            score=alert.score,
            trend="صاعد" if alert.change_percent > 0.5 else "محايد",
            risk_level="متوسط",
            status="شراء" if is_entry else "انتظار",
            ai_signal=alert.ai_signal or "EARLY_ENTRY",
            confidence=0.0,
            confirmed_factors=0,
            total_factors=17,
            safety_passed=is_entry,
            status_reason_ar=prefix + (alert.status_reason_ar or f"Stage {alert.stage}"),
            is_sticky_jump_alert=True,
            jump_alert_id=alert.alert_id,
        )

    def merge_into_response(
        self,
        response: OpportunitiesResponse,
        *,
        limit: int,
    ) -> OpportunitiesResponse:
        """Merge active registry alerts into opportunities; log status per alert."""
        self.purge_expired()
        active = self.get_active_alerts()
        by_symbol: dict[str, StockOpportunity] = {}

        for opp in response.opportunities:
            by_symbol[opp.symbol.upper()] = opp

        for alert in active:
            sym = alert.symbol.upper()
            if sym in by_symbol:
                existing = by_symbol[sym]
                if not existing.jump_alert_id:
                    by_symbol[sym] = existing.model_copy(
                        update={
                            "is_sticky_jump_alert": True,
                            "jump_alert_id": alert.alert_id,
                        }
                    )
                self._log_status(
                    alert,
                    still_stored=True,
                    still_returned_by_api=True,
                    displayed_by_ui=True,
                    removal_reason="",
                )
            else:
                by_symbol[sym] = self.alert_to_opportunity(alert)
                self._log_status(
                    alert,
                    still_stored=True,
                    still_returned_by_api=True,
                    displayed_by_ui=True,
                    removal_reason="",
                )

        ranked = sorted(
            by_symbol.values(),
            key=lambda o: (o.is_sticky_jump_alert, o.score),
            reverse=True,
        )
        merged = ranked[:limit]
        merged_symbols = {o.symbol.upper() for o in merged}

        for alert in active:
            if alert.symbol.upper() not in merged_symbols:
                self._log_status(
                    alert,
                    still_stored=True,
                    still_returned_by_api=False,
                    displayed_by_ui=False,
                    removal_reason="NOT_RETURNED_BY_API",
                )

        data = response.model_dump()
        data["opportunities"] = merged
        data["jump_alerts"] = active
        if merged and data.get("api_status") == "NO_OPPORTUNITIES":
            data["api_status"] = "OK"
        return OpportunitiesResponse(**data)

    def log_refresh_cycle(
        self,
        *,
        scan_opportunity_symbols: set[str],
        merged_symbols: set[str],
    ) -> None:
        """Log alert status after a background scan refresh."""
        self.purge_expired()
        for alert in self.get_active_alerts():
            sym = alert.symbol.upper()
            in_scan = sym in scan_opportunity_symbols
            in_merged = sym in merged_symbols
            if in_merged:
                reason = ""
            elif in_scan:
                reason = "FILTERED_FROM_MERGE"
            else:
                reason = "OVERWRITTEN_BY_REFRESH"
            self._log_status(
                alert,
                still_stored=True,
                still_returned_by_api=in_merged,
                displayed_by_ui=in_merged,
                removal_reason=reason,
            )

    def _log_status(
        self,
        alert: JumpAlert,
        *,
        still_stored: bool,
        still_returned_by_api: bool,
        displayed_by_ui: bool,
        removal_reason: str,
    ) -> None:
        logger.info(
            "JUMP_ALERT_STATUS symbol=%s alert_id=%s still_stored=%s "
            "still_returned_by_api=%s displayed_by_ui=%s removal_reason=%s",
            alert.symbol,
            alert.alert_id,
            still_stored,
            still_returned_by_api,
            displayed_by_ui,
            removal_reason or "none",
        )


jump_alert_registry = JumpAlertRegistry()
