"""Causal timeline replay — CRE/AIXI/WVVIP-style early upward surge (no future leak)."""

from __future__ import annotations

from analysis.early_upward_surge import relative_surge_from_snapshot
from analysis.pre_move_stage_progression import build_snapshot, evaluate_stage_transition
from analysis.upward_jump_gate import evaluate_upward_jump, upward_stage_label
from models.pre_move import (
    PreMoveBreakoutMetrics,
    PreMoveCompressionMetrics,
    PreMoveEarlyActivityMetrics,
    PreMoveLateMoveMetrics,
    PreMoveLiquidityMetrics,
    PreMoveSignal,
    PreMoveStageProgressionMetrics,
    PreMoveVolumeMetrics,
    PreMoveVwapMetrics,
)
from services.pre_move_stage_store import create_replay_state


def _minute_snap(
    *,
    minute: int,
    price: float,
    change_pct: float,
    vol_1m: float,
    vol_slope: float,
    rvol: float,
    rvol_st: float,
    trade_growth: float,
    dist_breakout: float,
    breakout_pressure: float = 45.0,
    base_price: float = 1.0,
) -> dict:
    trigger = base_price * 1.06
    snap = build_snapshot(
        timestamp=f"2026-08-26T09:{minute:02d}:00-04:00",
        price=price,
        change_pct=change_pct,
        pre_move_score=50 + minute * 3,
        volume_acceleration_1m=vol_1m,
        volume_acceleration_3m=max(1.0, vol_1m - 0.1),
        volume_acceleration_slope=vol_slope,
        rvol=rvol,
        rvol_same_time=rvol_st,
        dollar_volume_growth=0.2 + minute * 0.08,
        trade_velocity=40.0 + minute * 15,
        trade_velocity_growth=trade_growth,
        early_activity_score=10.0 + minute * 2,
        compression_score=0.45,
        range_compression_3m=0.72,
        micro_higher_lows=True,
        higher_lows_score=0.55,
        resistance_distance_pct=dist_breakout,
        distance_to_breakout_pct=dist_breakout,
        breakout_pressure=breakout_pressure,
        vwap_hold=True,
        vwap_reclaim=minute >= 2,
        distance_from_vwap_pct=1.2,
        liquidity_score=55.0,
        spread_pct=1.5,
        price_volume_response=0.45,
        news_catalyst_score=0.0,
        risk_reward=1.6,
        trigger_price=trigger,
        late_guard=False,
        failed_setup=False,
        base_price=base_price,
    )
    return {
        "snap": snap,
        "rvol": rvol_st,
        "vol_accel": vol_1m,
        "trade_velocity_growth": trade_growth,
        "trigger_distance_pct": dist_breakout,
        "vwap": "RECLAIM" if minute >= 2 else "HOLD",
        "surge": relative_surge_from_snapshot(snap),
    }


# CRE-like: 1.00 → 1.50 → 2.00 — detect during prep / first lift (not at +100%)
CRE_STYLE_MINUTES = [
    {"minute": 0, "price": 1.00, "change_pct": 0.4, "vol_1m": 1.05, "vol_slope": 1.02, "rvol": 1.05, "rvol_st": 1.08, "trade_growth": 0.05, "dist_breakout": 5.5},
    {"minute": 1, "price": 1.03, "change_pct": 3.0, "vol_1m": 1.18, "vol_slope": 1.08, "rvol": 1.35, "rvol_st": 1.45, "trade_growth": 0.18, "dist_breakout": 4.0},
    {"minute": 2, "price": 1.06, "change_pct": 6.0, "vol_1m": 1.28, "vol_slope": 1.12, "rvol": 1.7, "rvol_st": 1.85, "trade_growth": 0.22, "dist_breakout": 3.0},
    {"minute": 3, "price": 1.10, "change_pct": 10.0, "vol_1m": 1.35, "vol_slope": 1.15, "rvol": 2.1, "rvol_st": 2.4, "trade_growth": 0.28, "dist_breakout": 2.2},
    {"minute": 4, "price": 1.15, "change_pct": 15.0, "vol_1m": 1.42, "vol_slope": 1.18, "rvol": 2.5, "rvol_st": 2.8, "trade_growth": 0.32, "dist_breakout": 1.5},
    {"minute": 5, "price": 1.22, "change_pct": 22.0, "vol_1m": 1.50, "vol_slope": 1.20, "rvol": 2.9, "rvol_st": 3.2, "trade_growth": 0.35, "dist_breakout": 0.8},
    {"minute": 8, "price": 1.50, "change_pct": 50.0, "vol_1m": 1.55, "vol_slope": 1.10, "rvol": 3.5, "rvol_st": 4.0, "trade_growth": 0.20, "dist_breakout": 0.0},
    {"minute": 12, "price": 2.00, "change_pct": 100.0, "vol_1m": 1.30, "vol_slope": 1.05, "rvol": 4.0, "rvol_st": 5.0, "trade_growth": 0.10, "dist_breakout": 0.0},
]

AIXI_STYLE_MINUTES = [
    {"minute": 0, "price": 2.00, "change_pct": 0.6, "vol_1m": 1.06, "vol_slope": 1.03, "rvol": 1.1, "rvol_st": 1.12, "trade_growth": 0.08, "dist_breakout": 4.8},
    {"minute": 1, "price": 2.06, "change_pct": 3.0, "vol_1m": 1.20, "vol_slope": 1.09, "rvol": 1.4, "rvol_st": 1.55, "trade_growth": 0.20, "dist_breakout": 3.5},
    {"minute": 2, "price": 2.12, "change_pct": 6.0, "vol_1m": 1.30, "vol_slope": 1.14, "rvol": 1.75, "rvol_st": 1.95, "trade_growth": 0.25, "dist_breakout": 2.5},
    {"minute": 3, "price": 2.20, "change_pct": 10.0, "vol_1m": 1.38, "vol_slope": 1.17, "rvol": 2.2, "rvol_st": 2.5, "trade_growth": 0.30, "dist_breakout": 1.8},
    {"minute": 5, "price": 2.35, "change_pct": 17.5, "vol_1m": 1.45, "vol_slope": 1.19, "rvol": 2.7, "rvol_st": 3.0, "trade_growth": 0.33, "dist_breakout": 1.0},
    {"minute": 10, "price": 3.00, "change_pct": 50.0, "vol_1m": 1.40, "vol_slope": 1.08, "rvol": 3.2, "rvol_st": 3.8, "trade_growth": 0.15, "dist_breakout": 0.0},
]

WVVIP_STYLE_MINUTES = [
    {"minute": 0, "price": 0.50, "change_pct": 0.5, "vol_1m": 1.04, "vol_slope": 1.02, "rvol": 1.0, "rvol_st": 1.05, "trade_growth": 0.06, "dist_breakout": 6.0},
    {"minute": 1, "price": 0.52, "change_pct": 4.0, "vol_1m": 1.22, "vol_slope": 1.10, "rvol": 1.5, "rvol_st": 1.6, "trade_growth": 0.22, "dist_breakout": 4.2},
    {"minute": 2, "price": 0.54, "change_pct": 8.0, "vol_1m": 1.32, "vol_slope": 1.14, "rvol": 1.9, "rvol_st": 2.1, "trade_growth": 0.28, "dist_breakout": 3.0},
    {"minute": 4, "price": 0.58, "change_pct": 16.0, "vol_1m": 1.40, "vol_slope": 1.16, "rvol": 2.4, "rvol_st": 2.7, "trade_growth": 0.30, "dist_breakout": 1.6},
    {"minute": 8, "price": 0.75, "change_pct": 50.0, "vol_1m": 1.35, "vol_slope": 1.06, "rvol": 3.0, "rvol_st": 3.5, "trade_growth": 0.12, "dist_breakout": 0.0},
]


def _run_timeline(symbol: str, minutes: list[dict], *, base_price: float | None = None) -> dict:
    state = create_replay_state(symbol, "2026-08-26")
    base = base_price or minutes[0]["price"]
    timeline: dict[str, dict | None] = {
        "first_detected_at": None,
        "first_detected_price": None,
        "EARLY_WATCH_UP": None,
        "PRE_BREAKOUT_UP": None,
        "EARLY_ENTRY_UP": None,
        "JUMP_QUALIFIED": None,
        "JUMP_ALERT_CREATED": None,
        "TOO_LATE_TO_CHASE": None,
    }
    stages_seen: list[str] = []

    for row in minutes:
        meta = _minute_snap(**row, base_price=base)
        snap = meta["snap"]
        lifecycle, metrics = evaluate_stage_transition(
            state,
            snap,
            quality_gate_enabled=False,
        )
        stage_up = upward_stage_label(lifecycle)
        stages_seen.append(stage_up)

        if timeline["first_detected_at"] is None and lifecycle in (
            "EARLY_WATCH", "PRE_BREAKOUT", "EARLY_ENTRY",
        ):
            timeline["first_detected_at"] = snap.timestamp
            timeline["first_detected_price"] = snap.price

        for key in ("EARLY_WATCH_UP", "PRE_BREAKOUT_UP", "EARLY_ENTRY_UP", "TOO_LATE_TO_CHASE"):
            stage_base = key.replace("_UP", "")
            if timeline[key] is None and lifecycle == stage_base:
                timeline[key] = {
                    "at": snap.timestamp,
                    "price": snap.price,
                    "change_pct": snap.change_pct,
                    "rvol": meta["rvol"],
                    "volume_acceleration": meta["vol_accel"],
                    "trade_velocity_growth": meta["trade_velocity_growth"],
                    "vwap": meta["vwap"],
                    "trigger_distance_pct": meta["trigger_distance_pct"],
                }

        if lifecycle == "EARLY_ENTRY" and timeline["JUMP_QUALIFIED"] is None:
            sig = PreMoveSignal(
                signal_id=f"{symbol}:2026-08-26",
                symbol=symbol,
                name=symbol,
                current_price=snap.price,
                change_percent=snap.change_pct,
                pre_move_score=int(snap.pre_move_score),
                status="EARLY_ENTRY",
                trigger_price=snap.trigger_price,
                volume=PreMoveVolumeMetrics(
                    rvol=snap.rvol,
                    rvol_same_time=snap.rvol_same_time,
                    volume_acceleration_1m=snap.volume_acceleration_1m,
                    volume_acceleration=snap.volume_acceleration_1m,
                ),
                early_activity=PreMoveEarlyActivityMetrics(
                    micro_higher_lows=snap.micro_higher_lows,
                    breakout_pressure_score=snap.breakout_pressure,
                    trade_velocity=snap.trade_velocity,
                    trade_count_growth=snap.trade_velocity_growth,
                    dollar_volume_growth=snap.dollar_volume_growth,
                ),
                compression=PreMoveCompressionMetrics(higher_lows_score=snap.higher_lows_score),
                vwap=PreMoveVwapMetrics(
                    vwap_hold=snap.vwap_hold,
                    vwap_reclaim=snap.vwap_reclaim,
                    distance_from_vwap_pct=snap.distance_from_vwap_pct,
                ),
                breakout=PreMoveBreakoutMetrics(distance_to_breakout_pct=snap.distance_to_breakout_pct),
                liquidity=PreMoveLiquidityMetrics(liquidity_score=snap.liquidity_score),
                late_move=PreMoveLateMoveMetrics(is_too_late=snap.late_guard),
                stage_progression=PreMoveStageProgressionMetrics(
                    stage_lifecycle=lifecycle,
                    regression_signals=metrics.regression_signals,
                ),
                validated=True,
            )
            ok, _ = evaluate_upward_jump(sig)
            if ok:
                timeline["JUMP_QUALIFIED"] = {
                    "at": snap.timestamp,
                    "price": snap.price,
                    "change_pct": snap.change_pct,
                    "rvol": meta["rvol"],
                    "volume_acceleration": meta["vol_accel"],
                    "trade_velocity_growth": meta["trade_velocity_growth"],
                    "vwap": meta["vwap"],
                    "trigger_distance_pct": meta["trigger_distance_pct"],
                }
                timeline["JUMP_ALERT_CREATED"] = dict(timeline["JUMP_QUALIFIED"])

        state.append(snap)
        state.current_stage = lifecycle
        state.minutes_in_stage += 1.0
        if lifecycle == "PRE_BREAKOUT":
            from analysis.pre_move_stage_progression import _pb_quality_window, _update_pb_persistence

            if _pb_quality_window(snap):
                state.pb_consecutive_windows = _update_pb_persistence(state, snap)

    alert_pct = (
        timeline["JUMP_ALERT_CREATED"]["change_pct"]
        if timeline["JUMP_ALERT_CREATED"]
        else None
    )
    peak_pct = max(m["change_pct"] for m in minutes)
    early_enough = alert_pct is not None and alert_pct <= 25.0 and alert_pct < peak_pct * 0.35

    return {
        "symbol": symbol,
        "timeline": timeline,
        "stages_seen": stages_seen,
        "alert_change_pct": alert_pct,
        "peak_change_pct": peak_pct,
        "pass": early_enough and timeline["EARLY_ENTRY_UP"] is not None,
    }


def test_cre_style_early_surge_timeline():
    result = _run_timeline("CRE", CRE_STYLE_MINUTES, base_price=1.0)
    assert result["timeline"]["EARLY_WATCH_UP"] is not None
    assert result["timeline"]["PRE_BREAKOUT_UP"] is not None
    assert result["pass"] is True
    assert result["alert_change_pct"] is not None
    assert result["alert_change_pct"] <= 25.0


def test_aixi_style_early_surge_timeline():
    result = _run_timeline("AIXI", AIXI_STYLE_MINUTES, base_price=2.0)
    assert result["timeline"]["EARLY_WATCH_UP"] is not None
    assert result["pass"] is True


def test_wvvip_style_early_surge_timeline():
    result = _run_timeline("WVVIP", WVVIP_STYLE_MINUTES, base_price=0.50)
    assert result["timeline"]["EARLY_WATCH_UP"] is not None
    assert result["pass"] is True


def test_late_extended_move_not_new_opportunity():
    """After +100% extension, should not qualify as fresh jump."""
    late_minutes = [
        {"minute": 20, "price": 2.00, "change_pct": 100.0, "vol_1m": 1.2, "vol_slope": 1.0, "rvol": 2.0, "rvol_st": 2.5, "trade_growth": 0.05, "dist_breakout": 0.0},
    ]
    snap_meta = _minute_snap(**late_minutes[0], base_price=1.0)
    snap = snap_meta["snap"]
    snap = build_snapshot(
        timestamp=snap.timestamp,
        price=snap.price,
        change_pct=100.0,
        pre_move_score=80,
        volume_acceleration_1m=1.2,
        volume_acceleration_3m=1.1,
        volume_acceleration_slope=1.0,
        rvol=2.0,
        rvol_same_time=2.5,
        dollar_volume_growth=0.1,
        trade_velocity=50.0,
        trade_velocity_growth=0.05,
        early_activity_score=15.0,
        compression_score=0.3,
        range_compression_3m=0.9,
        micro_higher_lows=True,
        higher_lows_score=0.4,
        resistance_distance_pct=0.0,
        distance_to_breakout_pct=0.0,
        breakout_pressure=60.0,
        vwap_hold=True,
        vwap_reclaim=False,
        distance_from_vwap_pct=0.5,
        liquidity_score=60.0,
        spread_pct=2.0,
        price_volume_response=0.3,
        news_catalyst_score=0.0,
        risk_reward=0.5,
        trigger_price=1.06,
        late_guard=True,
        failed_setup=False,
        base_price=1.0,
    )
    state = create_replay_state("LATE", "2026-08-26")
    lifecycle, _ = evaluate_stage_transition(state, snap, quality_gate_enabled=False)
    assert lifecycle == "TOO_LATE_TO_CHASE"


if __name__ == "__main__":
    for sym, data in (
        ("CRE", CRE_STYLE_MINUTES),
        ("AIXI", AIXI_STYLE_MINUTES),
        ("WVVIP", WVVIP_STYLE_MINUTES),
    ):
        r = _run_timeline(sym, data, base_price=data[0]["price"])
        print(f"\n=== {sym} ===")
        print(f"PASS={r['pass']} alert_pct={r['alert_change_pct']} peak={r['peak_change_pct']}")
        for k, v in r["timeline"].items():
            print(f"  {k}: {v}")
