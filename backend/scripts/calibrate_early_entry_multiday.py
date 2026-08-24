"""
Multi-day EARLY_ENTRY calibration — 60/20/20 temporal split, resumable checkpoints.

Run: python scripts/calibrate_early_entry_multiday.py [--end-date 2026-08-24] [--days 10]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ee_calibration_lib import (
    EECandidate,
    candidate_to_row,
    compute_kpis,
    extract_candidates_from_timeline,
    search_thresholds,
    temporal_split,
    thresholds_to_config_dict,
    trading_days_before,
)
from scripts.premove_replay_lib import filter_premarket_regular, replay_session
from scripts.replay_stage_progression_market import classify_universe, fetch_grouped_daily
from services.news_service import fetch_stock_news
from services.polygon_client import PolygonClient

ET = ZoneInfo("America/New_York")

SYMBOL_TIMEOUT_SEC = 90
SESSION_TIMEOUT_SEC = 3600


def _log(msg: str) -> None:
    print(msg, flush=True)


class CheckpointStore:
    """Persist progress after each completed session — resume without restarting."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {
            "dates": [],
            "completed_dates": [],
            "candidates": [],
            "sessions": [],
            "errors": [],
            "started_at": datetime.now(ET).isoformat(),
            "last_updated": None,
            "api_retries": 0,
        }
        if path.exists():
            self.load()

    def load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.data.update(raw)

    def save(self) -> None:
        self.data["last_updated"] = datetime.now(ET).isoformat()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def add_session(
        self,
        session_date: str,
        candidates: list[EECandidate],
        sessions: list[tuple[str, str]],
        errors: list[dict],
        api_retries: int,
    ) -> None:
        if session_date not in self.data["completed_dates"]:
            self.data["completed_dates"].append(session_date)
        self.data["candidates"].extend([asdict(c) for c in candidates])
        self.data["sessions"].extend(sessions)
        self.data["errors"].extend(errors)
        self.data["api_retries"] = self.data.get("api_retries", 0) + api_retries
        self.save()

    def candidates(self) -> list[EECandidate]:
        return [EECandidate(**c) for c in self.data.get("candidates", [])]

    def sessions(self) -> list[tuple[str, str]]:
        return [tuple(x) for x in self.data.get("sessions", [])]


async def collect_symbol(
    client: PolygonClient,
    sym: str,
    session_date: str,
) -> tuple[list[EECandidate], tuple[str, str] | None, dict | None]:
    """Collect one symbol — raises on timeout via wait_for wrapper."""
    from datetime import timedelta

    prior_str = (datetime.strptime(session_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    bars_raw = await client.get_minute_bars_on_date(sym, session_date)
    try:
        prior_bars = await client.get_minute_bars_on_date(sym, prior_str)
    except Exception:
        prior_bars = None

    try:
        snap = await client.get_snapshot(sym)
    except Exception:
        snap = {}
    try:
        news = await fetch_stock_news(client, sym, limit=10)
    except Exception:
        news = []

    bars = filter_premarket_regular(bars_raw)
    if bars.empty or len(bars) < 5:
        return [], None, None

    prev = snap.get("prevDay") or {}
    previous_close = float(prev.get("c") or 0)
    if previous_close <= 0 and prior_bars is not None and not prior_bars.empty:
        previous_close = float(prior_bars["close"].iloc[-1])

    timeline = replay_session(
        bars, prior_bars, news, previous_close,
        symbol=sym, session_date=session_date,
        quality_gate_enabled=True,
    )
    base = float(bars["low"].min())
    session_high = float(bars["high"].max())
    cands = extract_candidates_from_timeline(
        sym, session_date, timeline, bars,
        base_price=base, session_high=session_high,
    )
    sess = None
    if cands or any(t.get("lifecycle") == "PRE_BREAKOUT" for t in timeline):
        sess = (sym, session_date)
    return cands, sess, None


async def collect_day(
    client: PolygonClient,
    session_date: str,
    *,
    max_symbols: int,
    session_idx: int,
    total_sessions: int,
    t0: float,
) -> tuple[list[EECandidate], list[tuple[str, str]], list[dict], int]:
    """Replay one session with per-symbol timeout and progress logs."""
    errors: list[dict] = []
    retries_before = client.retry_count

    try:
        grouped = await asyncio.wait_for(
            fetch_grouped_daily(client, session_date),
            timeout=60,
        )
        symbols = classify_universe(grouped, max_movers=max_symbols // 2)["all"][:max_symbols]
    except Exception as exc:
        _log(f"  WARN: universe fetch failed for {session_date}: {exc}")
        symbols = []

    all_candidates: list[EECandidate] = []
    sessions: list[tuple[str, str]] = []
    total_syms = len(symbols)

    for i, sym in enumerate(symbols, start=1):
        elapsed = time.monotonic() - t0
        _log(
            f"  session {session_idx}/{total_sessions} | {session_date} | "
            f"symbol {i}/{total_syms} {sym} | elapsed {elapsed:.0f}s | api_retries {client.retry_count}"
        )
        try:
            cands, sess, _ = await asyncio.wait_for(
                collect_symbol(client, sym, session_date),
                timeout=SYMBOL_TIMEOUT_SEC,
            )
            all_candidates.extend(cands)
            if sess:
                sessions.append(sess)
        except asyncio.TimeoutError:
            err = {
                "session_date": session_date,
                "symbol": sym,
                "error": f"symbol_timeout_{SYMBOL_TIMEOUT_SEC}s",
            }
            errors.append(err)
            _log(f"    SKIP {sym}: timeout after {SYMBOL_TIMEOUT_SEC}s")
        except Exception as exc:
            err = {
                "session_date": session_date,
                "symbol": sym,
                "error": str(exc)[:200],
            }
            errors.append(err)
            _log(f"    SKIP {sym}: {exc}")

    api_retries = client.retry_count - retries_before
    return all_candidates, sessions, errors, api_retries


async def collect_all_resumable(
    dates: list[str],
    *,
    max_symbols: int,
    checkpoint: CheckpointStore,
) -> tuple[list[EECandidate], list[tuple[str, str]]]:
    completed = set(checkpoint.data.get("completed_dates", []))
    pending = [d for d in dates if d not in completed]
    if completed:
        _log(f"Resuming — {len(completed)} sessions done, {len(pending)} remaining")

    checkpoint.data["dates"] = dates
    checkpoint.save()

    client = PolygonClient()
    t0 = time.monotonic()
    total = len(dates)

    try:
        for idx, session_date in enumerate(dates, start=1):
            if session_date in completed:
                _log(f"session {idx}/{total} | {session_date} — already checkpointed, skip")
                continue

            _log(f"session {idx}/{total} | Collecting {session_date}...")
            try:
                cands, sessions, errors, api_retries = await asyncio.wait_for(
                    collect_day(
                        client, session_date,
                        max_symbols=max_symbols,
                        session_idx=idx,
                        total_sessions=total,
                        t0=t0,
                    ),
                    timeout=SESSION_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                _log(f"  SESSION TIMEOUT {session_date} after {SESSION_TIMEOUT_SEC}s — saving partial errors")
                errors = [{"session_date": session_date, "symbol": "*", "error": "session_timeout"}]
                cands, sessions, api_retries = [], [], 0

            checkpoint.add_session(session_date, cands, sessions, errors, api_retries)
            _log(
                f"  DONE {session_date}: {len(cands)} candidates, {len(sessions)} sessions, "
                f"{len(errors)} errors | checkpoint saved"
            )
    finally:
        await client.close()

    return checkpoint.candidates(), checkpoint.sessions()


def filter_by_dates(candidates: list[EECandidate], dates: list[str]) -> list[EECandidate]:
    ds = set(dates)
    return [c for c in candidates if c.session_date in ds]


def filter_sessions(sessions: list[tuple[str, str]], dates: list[str]) -> list[tuple[str, str]]:
    ds = set(dates)
    return [(s, d) for s, d in sessions if d in ds]


def oos_examples(
    candidates: list[EECandidate],
    *,
    thresholds,
    dates: list[str],
) -> dict:
    from scripts.ee_calibration_lib import _first_ee_per_session, apply_quality_thresholds

    oos = filter_by_dates(candidates, dates)
    selected = filter_by_dates(candidates, dates)

    after_ee = _first_ee_per_session(selected, use_quality=True, thresholds=thresholds)
    before_ee = _first_ee_per_session(selected, use_quality=False)

    successes = [candidate_to_row(c, result="SUCCESS") for c in after_ee if c.ee_success][:5]
    failed = [candidate_to_row(c, result="FALSE_POS") for c in after_ee if not c.ee_success][:5]

    rejected_correct: list[dict] = []
    for c in oos:
        if (c.symbol, c.session_date) in {(x.symbol, x.session_date) for x in after_ee}:
            continue
        ok, blocks = apply_quality_thresholds(
            price_holding=c.price_holding,
            liquidity_score=c.liquidity_score,
            rrr_value=c.rrr,
            stop_distance_pct=c.stop_distance_pct,
            rejection_score=c.rejection_score,
            breakout_failure_risk=c.breakout_failure_risk,
            volume_efficiency=c.volume_efficiency,
            entry_location=c.entry_location,
            spread_stability=c.spread_stability,
            liquidity_consistency=c.liquidity_consistency,
            confluence_quality=c.confluence_quality,
            catalyst_confirmed=c.catalyst_confirmed,
            higher_low_broken=c.higher_low_broken,
            thresholds=thresholds,
        )
        if not ok:
            reason = blocks[0] if blocks else "quality_gate"
            rejected_correct.append(candidate_to_row(c, result="REJECTED", rejection=reason))
        if len(rejected_correct) >= 5:
            break

    fake_failed = [
        candidate_to_row(c, result="FAKE_BREAKOUT", rejection="stop_hit")
        for c in after_ee if c.stop_hit and not c.ee_success
    ][:5]

    return {
        "successes": successes,
        "rejected_correctly": rejected_correct[:5],
        "fake_or_failed": fake_failed or failed,
        "before_ee_count": len(before_ee),
        "after_ee_count": len(after_ee),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--end-date", default="2026-08-24")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--max-symbols", type=int, default=35)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--fresh", action="store_true", help="Ignore checkpoint and start over")
    args = parser.parse_args()

    dates = trading_days_before(args.end_date, args.days)
    splits = temporal_split(dates)

    ckpt_path = Path(args.checkpoint) if args.checkpoint else (
        Path(__file__).resolve().parent / "ee_calibration_checkpoint.json"
    )
    if args.fresh and ckpt_path.exists():
        ckpt_path.unlink()
        _log("Removed existing checkpoint (--fresh)")

    checkpoint = CheckpointStore(ckpt_path)

    if checkpoint.data.get("completed_dates") and not args.fresh:
        candidates = checkpoint.candidates()
        sessions = checkpoint.sessions()
        if len(checkpoint.data.get("completed_dates", [])) < len(dates):
            candidates, sessions = await collect_all_resumable(
                dates, max_symbols=args.max_symbols, checkpoint=checkpoint,
            )
    elif checkpoint.data.get("candidates") and len(checkpoint.data.get("completed_dates", [])) == len(dates):
        _log(f"All {len(dates)} sessions already in checkpoint — skipping collection")
        candidates = checkpoint.candidates()
        sessions = checkpoint.sessions()
    else:
        candidates, sessions = await collect_all_resumable(
            dates, max_symbols=args.max_symbols, checkpoint=checkpoint,
        )

    _log(f"Collection complete: {len(candidates)} candidates, {len(sessions)} sessions")

    cal_c = filter_by_dates(candidates, splits["calibration"])
    cal_s = filter_sessions(sessions, splits["calibration"])

    best_th, best_w, cal_score, _ = search_thresholds(cal_c)

    def split_report(split_dates: list[str], *, use_quality: bool, th=None) -> dict:
        c = filter_by_dates(candidates, split_dates)
        s = filter_sessions(sessions, split_dates)
        return compute_kpis(c, use_quality=use_quality, thresholds=th, all_sessions=s)

    before = {
        "calibration": split_report(splits["calibration"], use_quality=False),
        "validation": split_report(splits["validation"], use_quality=False),
        "out_of_sample": split_report(splits["out_of_sample"], use_quality=False),
        "all_days": split_report(dates, use_quality=False),
    }
    after = {
        "calibration": split_report(splits["calibration"], use_quality=True, th=best_th),
        "validation": split_report(splits["validation"], use_quality=True, th=best_th),
        "out_of_sample": split_report(splits["out_of_sample"], use_quality=True, th=best_th),
        "all_days": split_report(dates, use_quality=True, th=best_th),
    }

    comparison_rows = []
    for key in (
        "early_entry_precision", "stop_hit_rate_after_ee", "tp1_hit_rate_after_ee",
        "tp2_hit_rate_after_ee", "early_entry_false_positive_rate", "pb_to_ee_conversion",
        "median_ee_lead_time_min", "median_remaining_after_ee_pct",
    ):
        comparison_rows.append({
            "metric": key,
            "before_all": before["all_days"].get(key),
            "after_all": after["all_days"].get(key),
            "before_oos": before["out_of_sample"].get(key),
            "after_oos": after["out_of_sample"].get(key),
        })

    report = {
        "generated_at": datetime.now(ET).isoformat(),
        "collection_diagnostics": {
            "completed_dates": checkpoint.data.get("completed_dates", []),
            "total_errors": len(checkpoint.data.get("errors", [])),
            "error_samples": checkpoint.data.get("errors", [])[:20],
            "api_retries_total": checkpoint.data.get("api_retries", 0),
            "hang_fix": {
                "root_cause": "No per-symbol progress/checkpoint; sequential API calls appeared hung on 2026-08-14",
                "fixes_applied": [
                    "Per-symbol timeout (90s)",
                    "Per-session timeout (3600s)",
                    "Polygon HTTP timeout (25s) + max 3 retries with backoff",
                    "Checkpoint after each session",
                    "Resume from last completed session",
                    "Per-symbol progress logs",
                ],
            },
        },
        "methodology": {
            "temporal_split": splits,
            "trading_days": dates,
            "no_look_ahead": True,
            "no_symbol_specific_logic": True,
            "aug_24_oos_only": "2026-08-24 in OOS split, not used for threshold tuning",
        },
        "calibrated_config": thresholds_to_config_dict(best_th, best_w),
        "calibration_search_score": round(cal_score, 4),
        "before_timing_gate_only": before,
        "after_calibrated_quality_gate": after,
        "before_after_comparison": comparison_rows,
        "out_of_sample_examples": oos_examples(
            candidates, thresholds=best_th, dates=splits["out_of_sample"],
        ),
    }

    out = Path(__file__).resolve().parent / "early_entry_multiday_calibration_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _log(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    _log(f"\nSaved: {out}")


if __name__ == "__main__":
    asyncio.run(main())
