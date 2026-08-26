"""Jump Alert Registry — persistent alerts independent of scan snapshots."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

from config import JUMP_ALERT_DISPLAY_LIMIT, JUMP_ALERT_TTL_SECONDS
from models.jump_alert import QUALIFIED_JUMP_SIGNALS, JumpAlert
from models.pre_move import PreMoveSignal
from models.scanner import OpportunitiesResponse
from models.stock import StockOpportunity

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _timing_label_ar(timing: str, *, is_too_late: bool) -> str:
    if is_too_late:
        return "متأخر — لا دخول جديد"
    if timing == "EARLY":
        return "دخول مبكر"
    if timing == "LATE":
        return "دخول متأخر"
    return "دخول طبيعي"


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

    def _payload_from_signal(self, sig: PreMoveSignal) -> dict:
        stage = sig.stage_progression.stage_lifecycle or sig.lifecycle or sig.status
        score = max(sig.pre_move_score, int(sig.stage_progression.stage_progression_score))
        vol_accel = sig.volume.volume_acceleration_1m or sig.volume.volume_acceleration
        is_too_late = sig.status == "TOO_LATE_TO_CHASE" or sig.late_move.is_too_late
        return {
            "price": sig.current_price,
            "change_percent": sig.change_percent,
            "stage": stage,
            "score": score,
            "ai_signal": sig.status,
            "status_reason_ar": sig.reason or f"PreMove {sig.pre_move_score}/100",
            "jump_qualified": True,
            "jump_alert_created": True,
            "jump_type": sig.status,
            "entry_low": sig.entry_low,
            "entry_high": sig.entry_high,
            "stop_loss": sig.stop_loss,
            "tp1": sig.tp1,
            "tp2": sig.tp2,
            "rvol": sig.volume.rvol,
            "volume_acceleration": vol_accel,
            "trigger_price": sig.trigger_price,
            "timing": sig.timing,
            "persistence_minutes": sig.stage_progression.persistence_minutes,
            "risk_reward": sig.risk_reward,
            "is_too_late": is_too_late,
        }

    def create_from_signal(self, sig: PreMoveSignal) -> JumpAlert | None:
        if not sig.validated or sig.status not in QUALIFIED_JUMP_SIGNALS:
            return None
        if sig.late_move.is_too_late or sig.status == "TOO_LATE_TO_CHASE":
            return None

        sym = sig.symbol.upper()
        now = _utc_now()
        created_at = now.isoformat()
        expires_at = (now + timedelta(seconds=JUMP_ALERT_TTL_SECONDS)).isoformat()
        payload = self._payload_from_signal(sig)

        with self._lock:
            for alert in self._alerts.values():
                if alert.symbol == sym and alert.status == "ACTIVE":
                    updated = alert.model_copy(update=payload)
                    self._alerts[alert.alert_id] = updated
                    logger.info(
                        "JUMP_ALERT_CREATED symbol=%s alert_id=%s created_at=%s price=%s "
                        "stage=%s score=%s action=updated",
                        sym,
                        alert.alert_id,
                        alert.created_at,
                        updated.price,
                        updated.stage,
                        updated.score,
                    )
                    return updated

            alert_id = str(uuid.uuid4())[:12]
            alert = JumpAlert(
                alert_id=alert_id,
                symbol=sym,
                name=sig.name or sym,
                created_at=created_at,
                expires_at=expires_at,
                **payload,
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

    def get_qualified_alerts(self, *, limit: int | None = None) -> list[JumpAlert]:
        """Only JUMP_QUALIFIED + JUMP_ALERT_CREATED alerts for UI display."""
        self.purge_expired()
        cap = limit if limit is not None else JUMP_ALERT_DISPLAY_LIMIT
        with self._lock:
            qualified = [
                a
                for a in self._alerts.values()
                if a.status == "ACTIVE"
                and a.jump_qualified
                and a.jump_alert_created
                and a.ai_signal in QUALIFIED_JUMP_SIGNALS
                and not a.is_too_late
            ]
        return sorted(qualified, key=lambda a: a.score, reverse=True)[:cap]

    def count_jump_qualified(self) -> int:
        self.purge_expired()
        with self._lock:
            return sum(
                1
                for a in self._alerts.values()
                if a.status == "ACTIVE" and a.jump_qualified
            )

    def count_jump_alert_created(self) -> int:
        self.purge_expired()
        with self._lock:
            return sum(
                1
                for a in self._alerts.values()
                if a.status == "ACTIVE" and a.jump_alert_created
            )

    def get_history(self, *, limit: int = 50) -> list[JumpAlert]:
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def alert_to_opportunity(self, alert: JumpAlert) -> StockOpportunity:
        timing = _timing_label_ar(alert.timing, is_too_late=alert.is_too_late)
        prefix = "🚀 قفزة مؤكدة | "
        detail = (
            f"{prefix}{alert.jump_type or alert.stage} | "
            f"Entry ${alert.entry_low:.2f} | Stop ${alert.stop_loss:.2f} | "
            f"TP1 ${alert.tp1:.2f} | TP2 ${alert.tp2:.2f} | "
            f"RVOL {alert.rvol:.1f}x | VolAcc {alert.volume_acceleration:.2f} | "
            f"Trigger ${alert.trigger_price:.2f} | {timing} | "
            f"{alert.status_reason_ar or ''}"
        )
        return StockOpportunity(
            symbol=alert.symbol,
            name=alert.name or alert.symbol,
            price=alert.price,
            change_percent=alert.change_percent,
            score=alert.score,
            trend="صاعد" if alert.change_percent > 0.5 else "محايد",
            risk_level="متوسط",
            status="شراء",
            ai_signal=alert.ai_signal or "EARLY_ENTRY",
            confidence=0.0,
            confirmed_factors=0,
            total_factors=17,
            safety_passed=True,
            status_reason_ar=detail.strip(),
            is_sticky_jump_alert=True,
            jump_alert_id=alert.alert_id,
        )

    def merge_into_response(
        self,
        response: OpportunitiesResponse,
        *,
        limit: int,
    ) -> OpportunitiesResponse:
        """Attach qualified jump alerts only — do not mix into opportunities list."""
        self.purge_expired()
        display_limit = min(JUMP_ALERT_DISPLAY_LIMIT, limit)
        display_alerts = self.get_qualified_alerts(limit=display_limit)
        display_symbols = {a.symbol.upper() for a in display_alerts}

        for alert in display_alerts:
            self._log_status(
                alert,
                still_stored=True,
                still_returned_by_api=True,
                displayed_by_ui=True,
                removal_reason="",
            )

        for alert in self.get_active_alerts():
            if alert.symbol.upper() in display_symbols:
                continue
            self._log_status(
                alert,
                still_stored=True,
                still_returned_by_api=False,
                displayed_by_ui=False,
                removal_reason="NOT_QUALIFIED_FOR_DISPLAY",
            )

        data = response.model_dump()
        data["jump_alerts"] = display_alerts
        return OpportunitiesResponse(**data)

    def log_refresh_cycle(
        self,
        *,
        scan_opportunity_symbols: set[str],
        merged_symbols: set[str],
    ) -> None:
        """Log alert status after a background scan refresh."""
        self.purge_expired()
        display_symbols = {a.symbol.upper() for a in self.get_qualified_alerts()}
        for alert in self.get_active_alerts():
            sym = alert.symbol.upper()
            in_display = sym in display_symbols
            if in_display:
                reason = ""
            elif sym in scan_opportunity_symbols:
                reason = "NOT_QUALIFIED_FOR_DISPLAY"
            else:
                reason = "NOT_IN_SCAN"
            self._log_status(
                alert,
                still_stored=True,
                still_returned_by_api=in_display,
                displayed_by_ui=in_display,
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
