"""Smart signal persistence — stores smart opportunity signals and outcomes."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "signals.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def init_smart_signals_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS smart_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_state TEXT NOT NULL,
                ai_score REAL NOT NULL,
                price REAL NOT NULL,
                change_percent REAL,
                rvol REAL,
                spread_pct REAL,
                entry_zone_low REAL,
                entry_zone_high REAL,
                stop_loss REAL,
                take_profit_1 REAL,
                take_profit_2 REAL,
                risk_reward_ratio REAL,
                signal_created_at TEXT NOT NULL,
                signal_expires_at TEXT NOT NULL,
                outcome TEXT DEFAULT 'open',
                outcome_at TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smart_symbol ON smart_signals(symbol)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_smart_created ON smart_signals(created_at)"
        )
        conn.commit()


def log_smart_signal(
    symbol: str,
    entry_state: str,
    ai_score: float,
    price: float,
    *,
    change_percent: float = 0.0,
    rvol: float = 0.0,
    spread_pct: float = 0.0,
    entry_zone_low: float = 0.0,
    entry_zone_high: float = 0.0,
    stop_loss: float = 0.0,
    take_profit_1: float = 0.0,
    take_profit_2: float = 0.0,
    risk_reward_ratio: float = 0.0,
    signal_created_at: str = "",
    signal_expires_at: str = "",
    payload: dict | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO smart_signals
               (symbol, entry_state, ai_score, price, change_percent, rvol, spread_pct,
                entry_zone_low, entry_zone_high, stop_loss, take_profit_1, take_profit_2,
                risk_reward_ratio, signal_created_at, signal_expires_at, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol.upper(), entry_state, ai_score, price, change_percent, rvol, spread_pct,
                entry_zone_low, entry_zone_high, stop_loss, take_profit_1, take_profit_2,
                risk_reward_ratio, signal_created_at or now, signal_expires_at or now,
                json.dumps(payload or {}, ensure_ascii=False), now,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0


def update_smart_signal_outcome(symbol: str, outcome: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """UPDATE smart_signals SET outcome = ?, outcome_at = ?
               WHERE symbol = ? AND outcome = 'open'
               ORDER BY created_at DESC LIMIT 1""",
            (outcome, now, symbol.upper()),
        )
        conn.commit()


def get_smart_signal_history(symbol: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM smart_signals WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM smart_signals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]
