"""Trade Replay — persistent post-trade analytics and timeline."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "signals.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def init_trade_replay_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_replay (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL UNIQUE,
                risk_reward_ratio REAL NOT NULL DEFAULT 0,
                highest_price REAL,
                lowest_price REAL,
                max_profit_pct REAL NOT NULL DEFAULT 0,
                max_drawdown_pct REAL NOT NULL DEFAULT 0,
                final_result TEXT,
                time_to_tp1_seconds INTEGER,
                time_to_tp2_seconds INTEGER,
                time_to_tp3_seconds INTEGER,
                time_to_stop_seconds INTEGER,
                trade_duration_seconds INTEGER,
                entry_quality_score REAL NOT NULL DEFAULT 0,
                post_trade_quality TEXT,
                is_closed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                closed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                event_time TEXT NOT NULL,
                event_label TEXT NOT NULL,
                price REAL,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_price_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                observed_at TEXT NOT NULL,
                price REAL NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_replay_signal ON trade_replay(signal_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timeline_signal ON trade_timeline(signal_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticks_signal ON trade_price_ticks(signal_id)"
        )
        conn.commit()


def create_replay(
    signal_id: int,
    *,
    risk_reward_ratio: float,
    entry_quality_score: float,
    created_at: str,
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO trade_replay
               (signal_id, risk_reward_ratio, entry_quality_score, created_at)
               VALUES (?, ?, ?, ?)""",
            (signal_id, risk_reward_ratio, entry_quality_score, created_at),
        )
        conn.commit()
        return cur.lastrowid or 0


def add_timeline_event(
    signal_id: int,
    *,
    event_time: str,
    event_label: str,
    price: float | None = None,
    sort_order: int = 0,
) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO trade_timeline
               (signal_id, event_time, event_label, price, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (signal_id, event_time, event_label, price, sort_order),
        )
        conn.commit()


def add_price_tick(signal_id: int, observed_at: str, price: float) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO trade_price_ticks (signal_id, observed_at, price) VALUES (?, ?, ?)",
            (signal_id, observed_at, price),
        )
        conn.commit()


def update_replay_metrics(
    signal_id: int,
    *,
    highest_price: float | None = None,
    lowest_price: float | None = None,
    max_profit_pct: float | None = None,
    max_drawdown_pct: float | None = None,
    time_to_tp1_seconds: int | None = None,
    time_to_tp2_seconds: int | None = None,
    time_to_tp3_seconds: int | None = None,
    time_to_stop_seconds: int | None = None,
) -> None:
    fields: list[str] = []
    params: list = []
    for col, val in (
        ("highest_price", highest_price),
        ("lowest_price", lowest_price),
        ("max_profit_pct", max_profit_pct),
        ("max_drawdown_pct", max_drawdown_pct),
        ("time_to_tp1_seconds", time_to_tp1_seconds),
        ("time_to_tp2_seconds", time_to_tp2_seconds),
        ("time_to_tp3_seconds", time_to_tp3_seconds),
        ("time_to_stop_seconds", time_to_stop_seconds),
    ):
        if val is not None:
            fields.append(f"{col} = ?")
            params.append(val)
    if not fields:
        return
    params.append(signal_id)
    with _conn() as conn:
        conn.execute(
            f"UPDATE trade_replay SET {', '.join(fields)} WHERE signal_id = ?",
            params,
        )
        conn.commit()


def finalize_replay(
    signal_id: int,
    *,
    final_result: str,
    trade_duration_seconds: int,
    post_trade_quality: str,
    max_profit_pct: float,
    max_drawdown_pct: float,
    highest_price: float,
    lowest_price: float,
    closed_at: str,
) -> None:
    with _conn() as conn:
        conn.execute(
            """UPDATE trade_replay SET
               final_result = ?, trade_duration_seconds = ?,
               post_trade_quality = ?, max_profit_pct = ?,
               max_drawdown_pct = ?, highest_price = ?, lowest_price = ?,
               is_closed = 1, closed_at = ?
               WHERE signal_id = ?""",
            (
                final_result,
                trade_duration_seconds,
                post_trade_quality,
                max_profit_pct,
                max_drawdown_pct,
                highest_price,
                lowest_price,
                closed_at,
                signal_id,
            ),
        )
        conn.commit()


def get_replay_by_signal_id(signal_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM trade_replay WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()
    return dict(row) if row else None


def get_timeline(signal_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trade_timeline WHERE signal_id = ? ORDER BY sort_order, event_time",
            (signal_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_closed_replays(limit: int = 5000) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trade_replay WHERE is_closed = 1 ORDER BY closed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_replays_with_signals(limit: int = 100) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT r.*, s.symbol, s.signal, s.signal_date, s.signal_time,
                      s.entry_price, s.stop_loss, s.target_1, s.target_2, s.target_3,
                      s.ai_score, s.confidence_score, s.timeframe, s.track_status,
                      s.profit_pct, s.created_at AS signal_created_at
               FROM trade_replay r
               JOIN signal_analytics s ON s.id = r.signal_id
               ORDER BY s.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
