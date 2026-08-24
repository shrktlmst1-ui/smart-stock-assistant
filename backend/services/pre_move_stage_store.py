"""In-memory rolling stage state per symbol — production-safe cache."""

from __future__ import annotations

import time
from threading import Lock

from config import STAGE_HISTORY_MAX, STAGE_STATE_TTL_SECONDS
from models.pre_move_stage import RollingStageState, StageSnapshot

_lock = Lock()
_store: dict[str, RollingStageState] = {}


def _key(symbol: str, session_date: str) -> str:
    return f"{symbol.upper()}:{session_date}"


def get_stage_state(symbol: str, session_date: str) -> RollingStageState | None:
    with _lock:
        state = _store.get(_key(symbol, session_date))
        if state is None:
            return None
        if time.time() - state.last_updated > STAGE_STATE_TTL_SECONDS:
            del _store[_key(symbol, session_date)]
            return None
        return state


def get_or_create_state(symbol: str, session_date: str) -> RollingStageState:
    with _lock:
        k = _key(symbol, session_date)
        state = _store.get(k)
        if state is None or time.time() - state.last_updated > STAGE_STATE_TTL_SECONDS:
            from collections import deque

            state = RollingStageState(
                symbol=symbol.upper(),
                session_date=session_date,
                snapshots=deque(maxlen=STAGE_HISTORY_MAX),
            )
            _store[k] = state
        return state


def update_stage_state(
    symbol: str,
    session_date: str,
    snap: StageSnapshot,
    new_stage: str,
    metrics,
) -> RollingStageState:
    state = get_or_create_state(symbol, session_date)
    with _lock:
        prev_stage = state.current_stage
        state.append(snap)
        state.last_updated = time.time()

        if new_stage != prev_stage:
            state.stage_entered_at = snap.timestamp
            state.minutes_in_stage = 0.0
            if new_stage != "PRE_BREAKOUT":
                state.pb_consecutive_windows = 0
        else:
            state.minutes_in_stage += 1.0

        state.current_stage = new_stage  # type: ignore[assignment]
        if _stage_rank(new_stage) > _stage_rank(state.peak_stage):
            state.peak_stage = new_stage  # type: ignore[assignment]

        state.peak_progression_score = max(
            state.peak_progression_score,
            metrics.stage_progression_score,
        )

        if new_stage in ("EARLY_WATCH", "PRE_BREAKOUT", "EARLY_ENTRY") and not state.first_detected_at:
            state.first_detected_at = snap.timestamp
            state.first_detected_price = snap.price

        return state


def _stage_rank(stage: str) -> int:
    order = {
        "DISCOVERED": 0,
        "EARLY_WATCH": 1,
        "PRE_BREAKOUT": 2,
        "EARLY_ENTRY": 3,
        "BREAKOUT_CONFIRMED": 4,
    }
    return order.get(stage, -1)


def clear_stale_states() -> int:
    """Remove expired entries — call periodically from scanner."""
    now = time.time()
    removed = 0
    with _lock:
        stale = [k for k, v in _store.items() if now - v.last_updated > STAGE_STATE_TTL_SECONDS]
        for k in stale:
            del _store[k]
            removed += 1
    return removed


def reset_store() -> None:
    """Test helper."""
    with _lock:
        _store.clear()


def create_replay_state(symbol: str, session_date: str) -> RollingStageState:
    """Fresh state for causal replay (no cross-session bleed)."""
    from collections import deque

    return RollingStageState(
        symbol=symbol.upper(),
        session_date=session_date,
        snapshots=deque(maxlen=STAGE_HISTORY_MAX),
    )
