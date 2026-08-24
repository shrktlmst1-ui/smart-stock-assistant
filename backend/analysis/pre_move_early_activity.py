"""Early Activity Engine — rate-of-change detection before absolute thresholds."""

from __future__ import annotations

import pandas as pd

from config import (
    PREMOVE_CONFLUENCE_BONUS_MAX,
    PREMOVE_EARLY_RVOL_ST_STRONG,
    PREMOVE_SIGNAL_DECAY_PER_MIN,
    PREMOVE_SIGNAL_DECAY_START_MIN,
    PREMOVE_VOL_ACCEL_STRONG,
)
from models.pre_move import (
    PreMoveBreakoutMetrics,
    PreMoveCompressionMetrics,
    PreMoveEarlyActivityMetrics,
    PreMoveVolumeMetrics,
)


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default


def _session_baseline_volumes(vols: pd.Series, *, exclude_last: int = 1) -> float:
    """Rolling baseline — median of recent non-outlier bars (causal)."""
    if len(vols) <= exclude_last:
        return float(vols.mean()) if len(vols) else 1.0
    hist = vols.iloc[:-exclude_last].astype(float)
    if hist.empty:
        return 1.0
    med = float(hist.median()) or 1.0
    # Exclude stale prints far below session activity
    active = hist[hist >= med * 0.15]
    return float(active.median()) if not active.empty else med


def compute_enhanced_volume_acceleration(bars: pd.DataFrame) -> dict[str, float | int]:
    """1m/3m acceleration and slope from minute bars only."""
    out: dict[str, float | int] = {
        "vol_1m_current": 0,
        "vol_1m_prev": 0,
        "vol_1m_prev2": 0,
        "vol_3m_current": 0,
        "vol_3m_previous": 0,
        "volume_acceleration_1m": 0.0,
        "volume_acceleration_3m": 0.0,
        "volume_acceleration_slope": 0.0,
        "dollar_volume_1m": 0.0,
        "dollar_volume_3m": 0.0,
        "dollar_volume_growth": 0.0,
    }
    if bars.empty or "volume" not in bars.columns:
        return out

    vols = bars["volume"].astype(float)
    closes = bars["close"].astype(float)
    n = len(vols)

    v0 = int(vols.iloc[-1])
    v1 = int(vols.iloc[-2]) if n >= 2 else 0
    v2 = int(vols.iloc[-3]) if n >= 3 else 0
    out["vol_1m_current"] = v0
    out["vol_1m_prev"] = v1
    out["vol_1m_prev2"] = v2

    v3m = int(vols.tail(min(3, n)).sum())
    prev3 = int(vols.iloc[-6:-3].sum()) if n >= 6 else int(vols.iloc[:-3].sum()) if n > 3 else 0
    out["vol_3m_current"] = v3m
    out["vol_3m_previous"] = prev3

    baseline = _session_baseline_volumes(vols)
    out["volume_acceleration_1m"] = round(_safe_div(v0, max(v1, baseline * 0.5), 0.0), 2)
    out["volume_acceleration_3m"] = round(_safe_div(v3m, max(prev3, baseline * 1.5, 1.0), 0.0), 2)

    # Slope: linear rate across last up-to-4 volume prints
    tail = [float(x) for x in vols.tail(min(4, n)).tolist()]
    if len(tail) >= 2:
        increments = [tail[i] / max(tail[i - 1], 1.0) for i in range(1, len(tail))]
        out["volume_acceleration_slope"] = round(sum(increments) / len(increments), 2)

    px = float(closes.iloc[-1])
    dv1 = v0 * px
    dv3 = v3m * px
    prev_dv3 = prev3 * float(closes.iloc[-4]) if n >= 4 else prev3 * px
    out["dollar_volume_1m"] = round(dv1, 2)
    out["dollar_volume_3m"] = round(dv3, 2)
    out["dollar_volume_growth"] = round(_safe_div(dv3 - prev_dv3, prev_dv3, 0.0), 2)

    return out


def compute_trade_metrics(bars: pd.DataFrame) -> dict[str, float | None | bool]:
    """Trade velocity from Polygon aggregate `transactions` (n) when present."""
    out: dict[str, float | None | bool] = {
        "trades_per_minute": None,
        "trade_count_growth": None,
        "trade_velocity": None,
        "trade_velocity_acceleration": None,
        "trade_data_available": False,
    }
    if "transactions" not in bars.columns or bars.empty:
        return out

    txs = bars["transactions"].astype(float)
    if txs.isna().all() or txs.sum() <= 0:
        return out

    out["trade_data_available"] = True
    n = len(txs)
    cur = float(txs.iloc[-1])
    prev = float(txs.iloc[-2]) if n >= 2 else 0.0
    out["trades_per_minute"] = round(cur, 1)
    out["trade_velocity"] = round(cur, 1)
    if prev > 0:
        out["trade_count_growth"] = round((cur - prev) / prev, 2)
    if n >= 3:
        v1 = float(txs.iloc[-2])
        v2 = float(txs.iloc[-3])
        if v2 > 0:
            out["trade_velocity_acceleration"] = round(v1 / v2, 2)
    return out


def compute_micro_higher_lows(bars: pd.DataFrame) -> tuple[bool, float]:
    """Micro higher-low pattern from recent minute lows (no large structure needed)."""
    if bars.empty or len(bars) < 3:
        return False, 0.0
    lows = bars["low"].astype(float).tail(min(6, len(bars))).tolist()
    if len(lows) < 3:
        return False, 0.0
    higher = sum(1 for i in range(1, len(lows)) if lows[i] >= lows[i - 1] * 0.998)
    score = round(higher / max(len(lows) - 1, 1), 2)
    # Allow mild pullbacks: 3.30→3.32→3.31→3.36 pattern
    net_rise = (lows[-1] - lows[0]) / max(lows[0], 1e-9)
    holding = net_rise >= -0.005
    return score >= 0.5 and holding, score


def compute_price_volume_response(bars: pd.DataFrame) -> tuple[float, float, float]:
    """Volume rising while price holds or makes higher lows."""
    if bars.empty or len(bars) < 3:
        return 0.0, 0.0, 0.0
    vols = bars["volume"].astype(float).tail(5)
    closes = bars["close"].astype(float).tail(5)
    lows = bars["low"].astype(float).tail(5)

    vol_rising = float(vols.iloc[-1]) >= float(vols.iloc[:-1].mean()) * 1.1 if len(vols) >= 2 else False
    price_not_falling = float(closes.iloc[-1]) >= float(closes.iloc[0]) * 0.985
    higher_low_persistence = 0.0
    if len(lows) >= 3:
        hl = sum(1 for i in range(1, len(lows)) if lows.iloc[i] >= lows.iloc[i - 1] * 0.997)
        higher_low_persistence = round(hl / max(len(lows) - 1, 1), 2)

    absorption = 0.0
    if len(bars) >= 3:
        recent = bars.tail(3)
        for _, row in recent.iterrows():
            o, h, l, c, v = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row["volume"])
            body = abs(c - o)
            lower_wick = min(o, c) - l
            if body > 0 and lower_wick > body * 0.5 and v > 0:
                absorption += 0.33

    pvr = 0.0
    if vol_rising and price_not_falling:
        pvr = 0.6
    if higher_low_persistence >= 0.5:
        pvr = min(1.0, pvr + 0.25)
    if absorption > 0:
        pvr = min(1.0, pvr + absorption)

    return round(pvr, 2), round(absorption, 2), higher_low_persistence


def compute_compression_expansion(bars: pd.DataFrame) -> dict[str, float | bool]:
    out = {
        "range_compression_3m": 0.0,
        "range_compression_5m": 0.0,
        "atr_contraction": 0.0,
        "volume_rising_inside_compression": False,
    }
    if bars.empty or len(bars) < 4:
        return out

    highs = bars["high"].astype(float)
    lows = bars["low"].astype(float)
    vols = bars["volume"].astype(float)

    r3 = float(highs.tail(3).max() - lows.tail(3).min())
    prior = bars.iloc[-8:-3] if len(bars) >= 8 else bars.iloc[:-3]
    if not prior.empty:
        r_prior = float(prior["high"].astype(float).max() - prior["low"].astype(float).min()) or r3 or 1.0
        out["range_compression_3m"] = round(max(0.0, 1.0 - r3 / r_prior), 2)

    r5 = float(highs.tail(min(5, len(bars))).max() - lows.tail(min(5, len(bars))).min())
    if len(bars) >= 10:
        r5_prior = float(bars.iloc[-10:-5]["high"].astype(float).max() - bars.iloc[-10:-5]["low"].astype(float).min()) or r5 or 1.0
        out["range_compression_5m"] = round(max(0.0, 1.0 - r5 / r5_prior), 2)

    vol_tail = vols.tail(3)
    vol_rising = len(vol_tail) >= 2 and float(vol_tail.iloc[-1]) > float(vol_tail.iloc[0]) * 1.15
    tight = out["range_compression_3m"] >= 0.25 or out["range_compression_5m"] >= 0.2
    out["volume_rising_inside_compression"] = bool(tight and vol_rising)
    return out


def compute_baseline_deviation(bars: pd.DataFrame, spread_pct: float) -> dict[str, float]:
    out = {
        "baseline_volume": 0.0,
        "baseline_range": 0.0,
        "baseline_spread": 0.0,
        "activity_deviation_score": 0.0,
    }
    if bars.empty or len(bars) < 3:
        return out

    vols = bars["volume"].astype(float)
    highs = bars["high"].astype(float)
    lows = bars["low"].astype(float)

    hist = bars.iloc[:-1] if len(bars) > 1 else bars
    out["baseline_volume"] = round(_session_baseline_volumes(vols), 2)
    if len(hist) >= 2:
        ranges = (hist["high"].astype(float) - hist["low"].astype(float)).tail(8)
        out["baseline_range"] = round(float(ranges.median()), 4)

    cur_vol = float(vols.iloc[-1])
    cur_range = float(highs.iloc[-1] - lows.iloc[-1])
    vol_dev = _safe_div(cur_vol, out["baseline_volume"], 0.0)
    range_dev = _safe_div(cur_range, out["baseline_range"] or cur_range or 1.0, 1.0)

    score = 0.0
    if vol_dev >= 2.0:
        score += 0.35
    elif vol_dev >= 1.4:
        score += 0.22
    elif vol_dev >= 1.15:
        score += 0.12

    if range_dev <= 0.85 and vol_dev >= 1.2:
        score += 0.2  # tight range + rising vol

    if spread_pct <= 2.0 and vol_dev >= 1.3:
        score += 0.1

    out["activity_deviation_score"] = round(min(1.0, score), 2)
    out["baseline_spread"] = spread_pct
    return out


def compute_resistance_pressure(
    bars: pd.DataFrame,
    price: float,
    breakout: PreMoveBreakoutMetrics,
) -> tuple[float, float]:
    """Gradual approach to resistance with rising lows/volume."""
    if bars.empty or price <= 0:
        return 0.0, breakout.distance_to_breakout_pct

    dist = breakout.distance_to_breakout_pct
    pts = 0.0
    if 0.5 <= dist <= 5.0:
        pts += 0.35 * (1.0 - min(dist, 5.0) / 5.0)
    elif dist <= 0.5:
        pts += 0.15

    _, hl_score = compute_micro_higher_lows(bars)
    pts += hl_score * 0.25

    vols = bars["volume"].astype(float)
    if len(vols) >= 3 and float(vols.iloc[-1]) > float(vols.iloc[-3]) * 1.1:
        pts += 0.2

    if len(bars) >= 4:
        pullbacks = bars["close"].astype(float).diff().tail(3).abs()
        if float(pullbacks.mean()) < price * 0.008:
            pts += 0.15

    return round(min(1.0, pts), 2), dist


def compute_confluence_bonus(m: PreMoveEarlyActivityMetrics) -> tuple[float, list[str]]:
    """Small bonus only when multiple independent early signals align."""
    factors: list[str] = []
    strong_vol = (
        m.volume_acceleration_1m >= PREMOVE_VOL_ACCEL_STRONG
        or m.volume_acceleration_slope >= 1.35
    )
    if strong_vol:
        factors.append("vol_accel")
    if m.micro_higher_lows:
        factors.append("higher_lows")
    if m.volume_rising_inside_compression or m.range_compression_3m >= 0.25:
        factors.append("compression")
    rvol_st = m.rvol_same_time
    if rvol_st is not None and rvol_st >= PREMOVE_EARLY_RVOL_ST_STRONG:
        factors.append("rvol_same_time")
    if m.activity_deviation_score >= 0.35:
        factors.append("baseline_deviation")
    if m.price_volume_response >= 0.5:
        factors.append("price_volume_response")

    if len(factors) >= 3:
        bonus = min(PREMOVE_CONFLUENCE_BONUS_MAX, 2.0 + (len(factors) - 3) * 1.25)
        return round(bonus, 1), factors
    return 0.0, factors


def compute_signal_decay(
    *,
    minutes_since_peak: float,
    minutes_since_status: float,
    peak_score: int,
    current_raw_score: int,
) -> float:
    """Gradual decay when setup stalls without progression."""
    decay = 0.0
    if minutes_since_peak >= PREMOVE_SIGNAL_DECAY_START_MIN:
        decay += (minutes_since_peak - PREMOVE_SIGNAL_DECAY_START_MIN) * PREMOVE_SIGNAL_DECAY_PER_MIN
    if minutes_since_status >= PREMOVE_SIGNAL_DECAY_START_MIN + 2:
        decay += (minutes_since_status - PREMOVE_SIGNAL_DECAY_START_MIN - 2) * (PREMOVE_SIGNAL_DECAY_PER_MIN * 0.5)
    if peak_score >= 60 and current_raw_score < peak_score - 8:
        decay += 2.0
    return round(min(15.0, decay), 1)


def check_failed_setup(
    bars: pd.DataFrame,
    early: PreMoveEarlyActivityMetrics,
    *,
    base_price: float,
    price: float,
    had_early_watch: bool,
) -> bool:
    """EARLY_WATCH → FAILED_SETUP when acceleration dies or base breaks."""
    if not had_early_watch or bars.empty:
        return False
    vols = bars["volume"].astype(float)
    if len(vols) >= 3:
        fading = float(vols.iloc[-1]) < float(vols.iloc[-3]) * 0.55
        accel_dead = early.volume_acceleration_1m < 0.85 and early.volume_acceleration_slope < 1.05
        if fading and accel_dead:
            return True
    if base_price > 0 and price < base_price * 0.985:
        return True
    return False


def compute_early_activity_metrics(
    bars: pd.DataFrame,
    price: float,
    *,
    vol_metrics: PreMoveVolumeMetrics,
    compression: PreMoveCompressionMetrics,
    breakout: PreMoveBreakoutMetrics,
    spread_pct: float = 0.5,
    rvol_same_time: float | None = None,
) -> PreMoveEarlyActivityMetrics:
    m = PreMoveEarlyActivityMetrics()
    unavailable: list[str] = []

    vol_accel = compute_enhanced_volume_acceleration(bars)
    for k, v in vol_accel.items():
        setattr(m, k, v)

    trade = compute_trade_metrics(bars)
    for k, v in trade.items():
        setattr(m, k, v)
    if not trade["trade_data_available"]:
        unavailable.append("TRADE_VELOCITY")

    baseline = compute_baseline_deviation(bars, spread_pct)
    m.baseline_volume = baseline["baseline_volume"]
    m.baseline_range = baseline["baseline_range"]
    m.baseline_spread = baseline["baseline_spread"]
    m.activity_deviation_score = baseline["activity_deviation_score"]

    m.micro_higher_lows, m.micro_higher_lows_score = compute_micro_higher_lows(bars)
    pvr, absorption, hlp = compute_price_volume_response(bars)
    m.price_volume_response = pvr
    m.absorption_score = absorption
    m.higher_low_persistence = hlp

    comp_exp = compute_compression_expansion(bars)
    m.range_compression_3m = comp_exp["range_compression_3m"]
    m.range_compression_5m = comp_exp["range_compression_5m"]
    m.volume_rising_inside_compression = comp_exp["volume_rising_inside_compression"]
    m.atr_contraction = compression.atr_contraction

    bp_score, dist = compute_resistance_pressure(bars, price, breakout)
    m.breakout_pressure_score = bp_score
    m.resistance_distance_pct = dist

    m.rvol_same_time = rvol_same_time
    if rvol_same_time is None:
        unavailable.append("RVOL_SAME_TIME")

    m.unavailable_factors = unavailable
    m.early_activity_score = score_early_activity_component(m)
    bonus, factors = compute_confluence_bonus(m)
    m.confluence_bonus = bonus
    m.confluence_factors = factors
    return m


def score_early_activity_component(m: PreMoveEarlyActivityMetrics, *, max_pts: float = 28.0) -> float:
    """Early Activity Score — emphasizes rate-of-change, not absolute size."""
    pts = 0.0

    # Volume acceleration (rate of change) — up to 10
    accel = max(m.volume_acceleration_1m, m.volume_acceleration_slope)
    if accel >= 3.0:
        pts += 10.0
    elif accel >= 2.0:
        pts += 8.0
    elif accel >= 1.5:
        pts += 6.0
    elif accel >= 1.25:
        pts += 4.0
    elif accel >= 1.1:
        pts += 2.0

    if m.volume_acceleration_3m >= 2.0:
        pts += 3.0
    elif m.volume_acceleration_3m >= 1.4:
        pts += 2.0
    elif m.volume_acceleration_3m >= 1.15:
        pts += 1.0

    # Dollar volume growth — up to 4
    if m.dollar_volume_growth >= 1.5:
        pts += 4.0
    elif m.dollar_volume_growth >= 0.8:
        pts += 2.5
    elif m.dollar_volume_growth >= 0.35:
        pts += 1.5

    # Same-time RVOL — up to 6 (premarket priority)
    if m.rvol_same_time is not None:
        r = m.rvol_same_time
        if r >= 5.0:
            pts += 6.0
        elif r >= 3.0:
            pts += 5.0
        elif r >= 2.0:
            pts += 3.5
        elif r >= 1.5:
            pts += 2.0
        elif r >= 1.2:
            pts += 1.0

    # Baseline deviation — up to 4
    if m.activity_deviation_score >= 0.5:
        pts += 4.0
    elif m.activity_deviation_score >= 0.35:
        pts += 2.5
    elif m.activity_deviation_score >= 0.2:
        pts += 1.5

    # Micro structure + price/volume — up to 5
    if m.micro_higher_lows:
        pts += 2.5
    elif m.micro_higher_lows_score >= 0.33:
        pts += 1.0
    if m.price_volume_response >= 0.6:
        pts += 2.5
    elif m.price_volume_response >= 0.35:
        pts += 1.5

    # Compression + rising vol — up to 3
    if m.volume_rising_inside_compression:
        pts += 3.0
    elif m.range_compression_3m >= 0.3:
        pts += 1.5

    # Resistance pressure — up to 3
    if m.breakout_pressure_score >= 0.55:
        pts += 3.0
    elif m.breakout_pressure_score >= 0.35:
        pts += 1.5

    # Trade velocity when available — up to 5
    if m.trade_data_available and m.trade_count_growth is not None:
        tg = m.trade_count_growth
        if tg >= 1.0:
            pts += 3.0
        elif tg >= 0.5:
            pts += 2.0
        elif tg >= 0.25:
            pts += 1.0
    if m.trade_data_available and m.trades_per_minute is not None:
        tpm = m.trades_per_minute
        if tpm >= 200:
            pts += 2.0
        elif tpm >= 80:
            pts += 1.0

    return min(max_pts, round(pts, 1))


def compute_pre_expansion_bonus(
    m: PreMoveEarlyActivityMetrics,
    *,
    change_pct: float,
    too_late: bool,
) -> tuple[float, list[str]]:
    """Bonus for pre-spike activity while move is still small — not a threshold change."""
    if too_late or change_pct >= 12.0:
        return 0.0, []
    factors: list[str] = []
    bonus = 0.0
    if m.early_activity_score >= 20.0:
        factors.append("early_activity_strong")
        bonus += 2.0
    if m.volume_acceleration_1m >= 1.4 or m.volume_acceleration_slope >= 1.5:
        factors.append("pre_spike_accel")
        bonus += 3.0
    if m.price_volume_response >= 0.5 and change_pct < 10.0:
        factors.append("price_holding")
        bonus += 2.0
    if m.trade_data_available and (m.trades_per_minute or 0) >= 80:
        factors.append("trade_surge")
        bonus += 2.0
    if m.activity_deviation_score >= 0.3 and change_pct < 8.0:
        factors.append("baseline_deviation")
        bonus += 1.0
    if len(factors) >= 3:
        bonus += 1.0
    cap = 11.0 if change_pct < 6.0 and len(factors) >= 4 else 10.0
    return round(min(cap, bonus), 1), factors


def passes_early_activity_fast_gate(
    early: PreMoveEarlyActivityMetrics,
    *,
    vol_metrics: PreMoveVolumeMetrics | None = None,
    has_fresh_news: bool = False,
) -> bool:
    """Stage-2 gate: strong early patterns without requiring large % move."""
    if early.volume_acceleration_1m >= 1.4 and early.price_volume_response >= 0.35:
        return True
    if early.rvol_same_time is not None and early.rvol_same_time >= 2.0 and early.micro_higher_lows_score >= 0.33:
        return True
    if has_fresh_news and early.trade_data_available and (early.trade_count_growth or 0) >= 0.3:
        return True
    if early.volume_rising_inside_compression or (
        early.range_compression_3m >= 0.25 and early.volume_acceleration_1m >= 1.2
    ):
        return True
    if early.activity_deviation_score >= 0.35 and early.volume_acceleration_slope >= 1.2:
        return True
    if vol_metrics and vol_metrics.volume_acceleration >= 1.5 and early.price_volume_response >= 0.3:
        return True
    return False
