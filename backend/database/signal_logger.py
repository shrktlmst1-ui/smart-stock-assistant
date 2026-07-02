"""Signal logging — SQLite database."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from models.trading import AISignal

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "signals.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL,
                reason TEXT,
                risk_level TEXT,
                entry REAL,
                stop_loss REAL,
                target_1 REAL,
                target_2 REAL,
                price REAL,
                change_percent REAL,
                meters_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at)")
        conn.commit()


def log_signal(
    symbol: str,
    ai_signal: AISignal,
    price: float,
    change_percent: float,
    meters: dict | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (symbol, signal, confidence, reason, risk_level, entry, stop_loss,
                target_1, target_2, price, change_percent, meters_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol, ai_signal.signal, ai_signal.confidence, ai_signal.reason,
                ai_signal.risk_level, ai_signal.entry, ai_signal.stop_loss,
                ai_signal.target_1, ai_signal.target_2, price, change_percent,
                json.dumps(meters or {}), now,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0


def get_signal_history(symbol: str | None = None, limit: int = 50) -> list[dict]:
    with _get_conn() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM signals WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]
