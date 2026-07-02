"""Trading Journal — persistent signal log with outcomes."""

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


def init_journal_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                entry REAL NOT NULL,
                stop_loss REAL NOT NULL,
                target_1 REAL NOT NULL,
                target_2 REAL NOT NULL,
                confidence REAL NOT NULL,
                ai_score REAL NOT NULL,
                market_regime TEXT NOT NULL,
                risk_reward_ratio REAL NOT NULL,
                reason TEXT,
                result TEXT DEFAULT 'open',
                profit_pct REAL DEFAULT 0.0,
                exit_price REAL,
                closed_at TEXT,
                factor_scores_json TEXT,
                strategy TEXT,
                timeframe TEXT DEFAULT 'live',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_symbol ON journal(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_created ON journal(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_result ON journal(result)")
        conn.commit()


def log_journal_entry(
    symbol: str,
    signal: str,
    entry: float,
    stop_loss: float,
    target_1: float,
    target_2: float,
    confidence: float,
    ai_score: float,
    market_regime: str,
    risk_reward_ratio: float,
    reason: str,
    factor_scores: dict | None = None,
    strategy: str = "confluence",
    timeframe: str = "live",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO journal
               (symbol, signal, entry, stop_loss, target_1, target_2, confidence, ai_score,
                market_regime, risk_reward_ratio, reason, factor_scores_json, strategy,
                timeframe, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol.upper(), signal, entry, stop_loss, target_1, target_2,
                confidence, ai_score, market_regime, risk_reward_ratio, reason,
                json.dumps(factor_scores or {}), strategy, timeframe, now,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0


def get_open_trades(symbol: str | None = None) -> list[dict]:
    with _conn() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM journal WHERE result = 'open' AND symbol = ? ORDER BY created_at DESC",
                (symbol.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM journal WHERE result = 'open' ORDER BY created_at DESC"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def close_trade(trade_id: int, result: str, profit_pct: float, exit_price: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """UPDATE journal SET result = ?, profit_pct = ?, exit_price = ?, closed_at = ?
               WHERE id = ?""",
            (result, profit_pct, exit_price, now, trade_id),
        )
        conn.commit()


def get_journal_entries(
    symbol: str | None = None,
    limit: int = 100,
    result: str | None = None,
) -> list[dict]:
    with _conn() as conn:
        q = "SELECT * FROM journal WHERE 1=1"
        params: list = []
        if symbol:
            q += " AND symbol = ?"
            params.append(symbol.upper())
        if result:
            q += " AND result = ?"
            params.append(result)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("factor_scores_json"):
        try:
            d["factor_scores"] = json.loads(d["factor_scores_json"])
        except json.JSONDecodeError:
            d["factor_scores"] = {}
    return d
