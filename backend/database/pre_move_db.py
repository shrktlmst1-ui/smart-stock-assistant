"""Pre-Move Predictor — prediction history and lifecycle tracking."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "signals.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def init_pre_move_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pre_move_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                detected_price REAL NOT NULL,
                pre_move_score INTEGER NOT NULL,
                status TEXT NOT NULL,
                lifecycle TEXT NOT NULL DEFAULT 'DISCOVERED',
                trigger_price REAL,
                entry_low REAL,
                entry_high REAL,
                stop_loss REAL,
                tp1 REAL,
                tp2 REAL,
                rvol REAL,
                volume_acceleration REAL,
                news_score REAL,
                liquidity_score REAL,
                late_move_score REAL,
                reason TEXT,
                lifecycle_json TEXT,
                highest_price REAL,
                lowest_price REAL,
                return_5m REAL,
                return_15m REAL,
                return_30m REAL,
                return_60m REAL,
                hit_trigger INTEGER DEFAULT 0,
                hit_tp1 INTEGER DEFAULT 0,
                hit_tp2 INTEGER DEFAULT 0,
                hit_stop INTEGER DEFAULT 0,
                prediction_result TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_symbol ON pre_move_predictions(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_detected ON pre_move_predictions(detected_at)")
        conn.commit()


def _make_signal_id(symbol: str, session_date: str) -> str:
    return f"{symbol.upper()}:{session_date}"


def upsert_prediction(data: dict) -> str:
    now = datetime.now(timezone.utc).isoformat()
    sym = data["symbol"].upper()
    day = data.get("session_date") or now[:10]
    signal_id = data.get("signal_id") or _make_signal_id(sym, day)

    with _conn() as conn:
        row = conn.execute(
            "SELECT id, detected_at, detected_price, pre_move_score, lifecycle_json FROM pre_move_predictions WHERE signal_id=?",
            (signal_id,),
        ).fetchone()

        lifecycle = data.get("lifecycle_history") or []
        if row:
            existing_lifecycle = json.loads(row["lifecycle_json"] or "[]")
            if lifecycle and (not existing_lifecycle or lifecycle[-1] != existing_lifecycle[-1]):
                existing_lifecycle.extend(lifecycle[len(existing_lifecycle):])
            lifecycle = existing_lifecycle or lifecycle
            detected_at = row["detected_at"]
            detected_price = row["detected_price"]
            first_score = row["pre_move_score"]
        else:
            detected_at = data.get("first_detected_at") or now
            detected_price = data.get("first_detected_price") or data.get("detected_price", 0)
            first_score = data.get("first_detected_score") or data.get("pre_move_score", 0)

        conn.execute(
            """INSERT INTO pre_move_predictions
               (signal_id, symbol, detected_at, detected_price, pre_move_score, status, lifecycle,
                trigger_price, entry_low, entry_high, stop_loss, tp1, tp2,
                rvol, volume_acceleration, news_score, liquidity_score, late_move_score,
                reason, lifecycle_json, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(signal_id) DO UPDATE SET
                 pre_move_score=excluded.pre_move_score,
                 status=excluded.status,
                 lifecycle=excluded.lifecycle,
                 trigger_price=excluded.trigger_price,
                 entry_low=excluded.entry_low,
                 entry_high=excluded.entry_high,
                 stop_loss=excluded.stop_loss,
                 tp1=excluded.tp1,
                 tp2=excluded.tp2,
                 rvol=excluded.rvol,
                 volume_acceleration=excluded.volume_acceleration,
                 news_score=excluded.news_score,
                 liquidity_score=excluded.liquidity_score,
                 late_move_score=excluded.late_move_score,
                 reason=excluded.reason,
                 lifecycle_json=excluded.lifecycle_json,
                 updated_at=excluded.updated_at
            """,
            (
                signal_id, sym, detected_at, detected_price, first_score,
                data.get("status", "NO_SETUP"), data.get("lifecycle", "DISCOVERED"),
                data.get("trigger_price"), data.get("entry_low"), data.get("entry_high"),
                data.get("stop_loss"), data.get("tp1"), data.get("tp2"),
                data.get("rvol"), data.get("volume_acceleration"),
                data.get("news_score"), data.get("liquidity_score"), data.get("late_move_score"),
                data.get("reason", ""), json.dumps(lifecycle, ensure_ascii=False), now,
            ),
        )
        conn.commit()
    return signal_id


def compute_kpis() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM pre_move_predictions").fetchall()
    if not rows:
        return {"total_predictions": 0}

    total = len(rows)
    tp1 = sum(1 for r in rows if r["hit_tp1"])
    tp2 = sum(1 for r in rows if r["hit_tp2"])
    stops = sum(1 for r in rows if r["hit_stop"])
    late = sum(1 for r in rows if r["status"] == "TOO_LATE_TO_CHASE")

    returns = [r["return_15m"] for r in rows if r["return_15m"] is not None]
    avg_ret = sum(returns) / len(returns) if returns else 0.0
    sorted_ret = sorted(returns)
    median = sorted_ret[len(sorted_ret) // 2] if sorted_ret else 0.0

    return {
        "total_predictions": total,
        "tp1_hit_rate": round(tp1 / total * 100, 1) if total else 0.0,
        "tp2_hit_rate": round(tp2 / total * 100, 1) if total else 0.0,
        "stop_rate": round(stops / total * 100, 1) if total else 0.0,
        "avg_return_after_signal": round(avg_ret, 2),
        "median_return": round(median, 2),
        "late_detection_rate": round(late / total * 100, 1) if total else 0.0,
    }
