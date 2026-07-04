"""Professional Signal Analytics — persistent history and live trade tracking."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "signals.db"

TRACK_STATUSES = (
    "Waiting",
    "Active",
    "Target 1 Hit",
    "Target 2 Hit",
    "Target 3 Hit",
    "Stop Loss Hit",
    "Expired",
)

TERMINAL_STATUSES = frozenset({
    "Target 1 Hit",
    "Target 2 Hit",
    "Target 3 Hit",
    "Stop Loss Hit",
    "Expired",
})


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def init_signal_analytics_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                signal_time TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT 'live',
                ai_score REAL NOT NULL,
                confidence_score REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                target_1 REAL NOT NULL,
                target_2 REAL NOT NULL,
                target_3 REAL NOT NULL,
                trend_direction TEXT NOT NULL,
                market_status TEXT NOT NULL,
                sector TEXT NOT NULL DEFAULT '',
                industry TEXT NOT NULL DEFAULT '',
                track_status TEXT NOT NULL DEFAULT 'Waiting',
                trade_quality_stars INTEGER NOT NULL DEFAULT 1,
                trade_quality_label TEXT NOT NULL DEFAULT 'Weak',
                explanation_json TEXT,
                factor_scores_json TEXT,
                filters_passed_json TEXT,
                filters_failed_json TEXT,
                trend_strength REAL NOT NULL DEFAULT 0,
                relative_volume REAL NOT NULL DEFAULT 0,
                failure_reason TEXT,
                profit_pct REAL DEFAULT 0.0,
                exit_price REAL,
                activated_at TEXT,
                closed_at TEXT,
                holding_seconds INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sa_symbol ON signal_analytics(symbol)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sa_created ON signal_analytics(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sa_track ON signal_analytics(track_status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sa_signal ON signal_analytics(signal)"
        )
        conn.commit()


def insert_signal_record(data: dict) -> int:
    now = datetime.now(timezone.utc)
    created = data.get("created_at") or now.isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO signal_analytics
               (symbol, signal, signal_date, signal_time, timeframe,
                ai_score, confidence_score, entry_price, stop_loss,
                target_1, target_2, target_3, trend_direction, market_status,
                sector, industry, track_status, trade_quality_stars,
                trade_quality_label, explanation_json, factor_scores_json,
                filters_passed_json, filters_failed_json, trend_strength,
                relative_volume, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["symbol"].upper(),
                data["signal"],
                data["signal_date"],
                data["signal_time"],
                data.get("timeframe", "live"),
                data["ai_score"],
                data["confidence_score"],
                data["entry_price"],
                data["stop_loss"],
                data["target_1"],
                data["target_2"],
                data["target_3"],
                data["trend_direction"],
                data["market_status"],
                data.get("sector", ""),
                data.get("industry", ""),
                data.get("track_status", "Waiting"),
                data.get("trade_quality_stars", 1),
                data.get("trade_quality_label", "Weak"),
                json.dumps(data.get("explanation", [])),
                json.dumps(data.get("factor_scores", {})),
                json.dumps(data.get("filters_passed", [])),
                json.dumps(data.get("filters_failed", [])),
                data.get("trend_strength", 0),
                data.get("relative_volume", 0),
                created,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0


def update_track(
    record_id: int,
    *,
    track_status: str,
    profit_pct: float = 0.0,
    exit_price: float | None = None,
    failure_reason: str | None = None,
    activated_at: str | None = None,
    closed_at: str | None = None,
    holding_seconds: int = 0,
) -> None:
    with _conn() as conn:
        conn.execute(
            """UPDATE signal_analytics
               SET track_status = ?, profit_pct = ?, exit_price = ?,
                   failure_reason = COALESCE(?, failure_reason),
                   activated_at = COALESCE(activated_at, ?),
                   closed_at = ?, holding_seconds = ?
               WHERE id = ?""",
            (
                track_status,
                profit_pct,
                exit_price,
                failure_reason,
                activated_at,
                closed_at,
                holding_seconds,
                record_id,
            ),
        )
        conn.commit()


def get_open_tracks(symbol: str | None = None) -> list[dict]:
    statuses = [s for s in TRACK_STATUSES if s not in TERMINAL_STATUSES]
    with _conn() as conn:
        if symbol:
            rows = conn.execute(
                f"""SELECT * FROM signal_analytics
                    WHERE symbol = ? AND track_status IN ({", ".join("?" * len(statuses))})
                    ORDER BY created_at DESC""",
                [symbol.upper(), *statuses],
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT * FROM signal_analytics
                    WHERE track_status IN ({", ".join("?" * len(statuses))})
                    ORDER BY created_at DESC""",
                statuses,
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_signal_records(
    *,
    symbol: str | None = None,
    limit: int = 200,
    track_status: str | None = None,
    since: str | None = None,
) -> list[dict]:
    q = "SELECT * FROM signal_analytics WHERE 1=1"
    params: list = []
    if symbol:
        q += " AND symbol = ?"
        params.append(symbol.upper())
    if track_status:
        q += " AND track_status = ?"
        params.append(track_status)
    if since:
        q += " AND created_at >= ?"
        params.append(since)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_record_by_id(record_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM signal_analytics WHERE id = ?",
            (record_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_all_records(limit: int = 5000) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signal_analytics ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key, fallback in (
        ("explanation_json", "explanation"),
        ("factor_scores_json", "factor_scores"),
        ("filters_passed_json", "filters_passed"),
        ("filters_failed_json", "filters_failed"),
    ):
        raw = d.pop(key, None)
        try:
            d[fallback] = json.loads(raw) if raw else ([] if fallback == "explanation" else {})
        except json.JSONDecodeError:
            d[fallback] = [] if fallback == "explanation" else {}
    return d
