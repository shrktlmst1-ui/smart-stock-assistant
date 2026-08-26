"""Tests for Jump Engine monitor and self-healing hooks."""

from __future__ import annotations

from services.jump_engine_monitor import jump_engine_monitor


def test_jump_engine_status_log_fields():
    jump_engine_monitor.tick_started(
        scanner_task_alive=True,
        websocket_connected=True,
        last_ws_message_time="2026-08-26T14:00:00+00:00",
        reconnect_count=1,
        refresh_in_progress=False,
        refresh_skipped=0,
    )
    jump_engine_monitor.log_stage2("BTCT")
    jump_engine_monitor.log_promoted_stage3("BTCT")
    jump_engine_monitor.log_jump_qualified("BTCT")
    jump_engine_monitor.tick_finished(scanned_count=100, candidate_count=12)

    snap = jump_engine_monitor.get_snapshot()
    assert snap.status == "RUNNING"
    assert snap.cycle_number >= 1
    assert snap.scanned_count == 100
    assert snap.candidate_count == 12
    assert snap.stage3_count == 1
    assert snap.alerts_generated == 1


def test_stuck_refresh_release():
    from services import snapshot_cache_service as scs

    with scs._refresh_guard:
        scs._refresh_in_progress = True
        scs._refresh_started_mono = 0.0
    scs._release_stuck_refresh("test_stuck")
    assert scs._refresh_in_progress is False
