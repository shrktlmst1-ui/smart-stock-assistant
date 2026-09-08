"""Deterministic SPX-only decision engine.

The engine deliberately separates market-direction evidence from trade eligibility.
It never creates a CALL/PUT merely because one indicator fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd

from models.spx_signal import SPXLevels, SPXSignal

SPX_SYMBOL = "I:SPX"
MIN_TRADE_SCORE = 80


@dataclass(frozen=True)
class _Evidence:
    score: int
    decision: str
    regime: str
    factors: list[str]
    rejected: list[str]


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _vwap(df: pd.DataFrame) -> float | None:
    if df.empty or "volume" not in df:
        return None
    vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    if float(vol.sum()) <= 0:
        return None
    return float((df["close"] * vol).sum() / vol.sum())


def _levels(df: pd.DataFrame) -> SPXLevels:
    if df.empty:
        return SPXLevels()
    d = df.copy()
    d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True, errors="coerce")
    d = d.dropna(subset=["timestamp"]).sort_values("timestamp")
    if d.empty:
        return SPXLevels()
    dates = d["timestamp"].dt.date
    today = dates.iloc[-1]
    prior_days = sorted(set(dates[dates < today]), reverse=True)
    prev = d[dates == prior_days[0]] if prior_days else pd.DataFrame()
    prev_week = d[d["timestamp"].dt.isocalendar().week < d.iloc[-1]["timestamp"].isocalendar().week]

    current = d[dates == today]
    opening = current[current["timestamp"].dt.hour.between(13, 14)]
    overnight = current[~current["timestamp"].dt.hour.between(13, 20)]
    recent = current.tail(min(60, len(current)))

    def hi(x: pd.DataFrame) -> float | None:
        return float(x["high"].max()) if not x.empty else None

    def lo(x: pd.DataFrame) -> float | None:
        return float(x["low"].min()) if not x.empty else None

    sup = lo(recent)
    res = hi(recent)
    return SPXLevels(
        previous_day_high=hi(prev), previous_day_low=lo(prev),
        previous_week_high=hi(prev_week), previous_week_low=lo(prev_week),
        overnight_high=hi(overnight), overnight_low=lo(overnight),
        opening_range_high=hi(opening), opening_range_low=lo(opening),
        swing_high=hi(recent), swing_low=lo(recent), vwap=_vwap(current),
        support_zone=(sup * 0.999, sup * 1.001) if sup else None,
        resistance_zone=(res * 0.999, res * 1.001) if res else None,
    )


def _score(df1h: pd.DataFrame, df15m: pd.DataFrame, df5m: pd.DataFrame) -> _Evidence:
    if min(len(df1h), len(df15m), len(df5m)) < 30:
        return _Evidence(0, "NO TRADE", "UNKNOWN", [], ["insufficient multi-timeframe data"])

    close = float(df5m.iloc[-1]["close"])
    e1 = _ema(df1h["close"], 20)
    e2 = _ema(df15m["close"], 20)
    e3 = _ema(df5m["close"], 9)
    atr = (df5m["high"] - df5m["low"]).rolling(14).mean().iloc[-1]
    atr = float(atr) if pd.notna(atr) else 0.0

    up = down = 0
    factors: list[str] = []
    rejected: list[str] = []
    if close > float(e1.iloc[-1]): up += 20; factors.append("1H trend up")
    elif close < float(e1.iloc[-1]): down += 20; factors.append("1H trend down")
    else: rejected.append("1H trend neutral")
    if float(e2.iloc[-1]) > float(e2.iloc[-5]): up += 15; factors.append("15M structure rising")
    elif float(e2.iloc[-1]) < float(e2.iloc[-5]): down += 15; factors.append("15M structure falling")
    if close > float(e3.iloc[-1]): up += 10; factors.append("5M momentum up")
    elif close < float(e3.iloc[-1]): down += 10; factors.append("5M momentum down")

    last = df5m.tail(20)
    avg_vol = float(df5m["volume"].tail(50).mean()) if "volume" in df5m else 0
    vol = float(last["volume"].iloc[-1]) if "volume" in last else 0
    if avg_vol > 0 and vol >= avg_vol * 1.25:
        if close >= float(last["close"].iloc[:-1].max()): up += 15; factors.append("volume breakout confirmation")
        elif close <= float(last["close"].iloc[:-1].min()): down += 15; factors.append("volume breakdown confirmation")
        else: rejected.append("volume elevated without breakout")
    else:
        rejected.append("no volume confirmation")

    v = _vwap(df15m)
    if v:
        if close > v: up += 10; factors.append("above VWAP")
        elif close < v: down += 10; factors.append("below VWAP")

    range_high = float(df15m["high"].tail(20).max())
    range_low = float(df15m["low"].tail(20).min())
    if atr > 0 and range_high - range_low > atr * 2:
        if close > range_high * 0.9995: up += 10; factors.append("15M expansion")
        elif close < range_low * 1.0005: down += 10; factors.append("15M expansion")

    best = max(up, down)
    if best >= 60 and up > down + 10:
        return _Evidence(min(100, best), "CALL", "TREND_UP", factors, rejected)
    if best >= 60 and down > up + 10:
        return _Evidence(min(100, best), "PUT", "TREND_DOWN", factors, rejected)
    if abs(up - down) <= 10:
        return _Evidence(min(100, best), "NO TRADE", "RANGE", factors, rejected + ["directional conflict"])
    return _Evidence(min(100, best), "NO TRADE", "UNKNOWN", factors, rejected + ["confluence below threshold"])


def evaluate_spx(df1h: pd.DataFrame, df15m: pd.DataFrame, df5m: pd.DataFrame, *, options_ready: bool = False, max_age_minutes: int = 10) -> SPXSignal:
    now = datetime.now(timezone.utc)
    all_frames = [x for x in (df1h, df15m, df5m) if not x.empty]
    newest = max((pd.to_datetime(x["timestamp"].iloc[-1], utc=True) for x in all_frames), default=None)
    fresh = bool(newest is not None and (now - newest.to_pydatetime()).total_seconds() <= max_age_minutes * 60)
    ev = _score(df1h, df15m, df5m)
    levels = _levels(df5m)

    # Options readiness is a hard gate for an actionable 0DTE options alert.
    actionable = ev.decision in ("CALL", "PUT") and ev.score >= MIN_TRADE_SCORE and fresh and options_ready
    kill = not fresh
    decision = ev.decision if actionable else "NO TRADE"
    reason = "confluence + options/liquidity gate passed" if actionable else "; ".join(ev.rejected) or "trade quality gate not passed"
    if not fresh:
        reason = "stale market data — kill switch active"
    confidence = "EXCEPTIONAL" if ev.score >= 90 else "STRONG" if ev.score >= 80 else "POTENTIAL" if ev.score >= 65 else "WATCH" if ev.score >= 50 else "LOW"

    entry = stop = tp1 = tp2 = None
    if actionable:
        entry = float(df5m.iloc[-1]["close"])
        atr = float((df5m["high"] - df5m["low"]).rolling(14).mean().iloc[-1])
        risk = max(atr, entry * 0.0015)
        if decision == "CALL":
            stop, tp1, tp2 = entry - risk, entry + risk * 1.5, entry + risk * 2.5
        else:
            stop, tp1, tp2 = entry + risk, entry - risk * 1.5, entry - risk * 2.5

    return SPXSignal(
        decision=decision, score=ev.score, regime=ev.regime, confidence=confidence,
        reason=reason, entry=entry, stop_loss=stop, take_profit_1=tp1, take_profit_2=tp2,
        levels=levels, factors=ev.factors, rejected_factors=ev.rejected,
        data_fresh=fresh, options_ready=options_ready, kill_switch=kill,
        cycle_id=uuid4().hex[:12], timestamp=now,
    )
