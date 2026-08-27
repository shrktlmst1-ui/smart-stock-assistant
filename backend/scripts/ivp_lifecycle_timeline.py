"""Generate IVP move_start lifecycle timeline after fix — causal 1m replay."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_real_jump_ivp_move_start_lifecycle import (
    EXPECTED_MS,
    MS_TOLERANCE,
    replay_ivp,
    _primary_wave_rows,
)


def _verdicts(result) -> dict:
    primary = _primary_wave_rows(result)
    ms_locked = (
        len({r.move_start_price for r in primary if r.move_start_price > 0}) == 1
        and primary
        and abs(primary[0].move_start_price - EXPECTED_MS) <= MS_TOLERANCE
    )
    bad_resets = [
        r for r in result.ms_resets
        if r.get("from_ms") and abs(r["from_ms"] - EXPECTED_MS) <= MS_TOLERANCE
        and abs(r.get("to_ms", 0) - EXPECTED_MS) > MS_TOLERANCE
    ]
    return {
        "MOVE_START LIFECYCLE FIX": "PASS" if ms_locked and len(bad_resets) == 0 else "FAIL",
        "IVP +100% LIVE": "PASS" if result.cross_100 else "FAIL",
        "IVP +150% EXPLOSIVE": "PASS" if result.explosive_first else "FAIL",
        "FIRST_DETECTED IMMUTABLE": "PASS" if not result.fd_changed and result.first_alert else "FAIL",
    }


async def main() -> None:
    result = await replay_ivp()
    out_dir = Path(__file__).resolve().parent

    milestones = []
    for r in result.timeline:
        tags = []
        if result.first_alert and r.time == result.first_alert["time"]:
            tags.append("FIRST_ALERT")
        if result.cross_100 and r.time == result.cross_100["time"]:
            tags.append("CROSS_100")
        if result.cross_150 and r.time == result.cross_150["time"]:
            tags.append("CROSS_150")
        if result.section_first and r.time == result.section_first["time"]:
            tags.append("SECTION_ON")
        if result.explosive_first and r.time == result.explosive_first["time"]:
            tags.append("EXPLOSIVE_ON")
        if r.reset_reason:
            tags.append(f"RESET:{r.reset_reason}")
        if tags:
            milestones.append({**r.__dict__, "tags": tags})

    step = max(1, len(result.timeline) // 35)
    sample = [r.__dict__ for r in result.timeline[::step][:45]]

    payload = {
        "symbol": "IVP",
        "session": "2026-01-14",
        "first_alert": result.first_alert,
        "cross_100": result.cross_100,
        "cross_150": result.cross_150,
        "section_first": result.section_first,
        "explosive_first": result.explosive_first,
        "ms_resets_count": len(result.ms_resets),
        "ms_resets_sample": result.ms_resets[:15],
        "fd_changed": result.fd_changed,
        "verdicts": _verdicts(result),
        "timeline_sample": sample,
        "milestones": milestones,
    }
    path = out_dir / "ivp_lifecycle_timeline.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload["verdicts"], indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
