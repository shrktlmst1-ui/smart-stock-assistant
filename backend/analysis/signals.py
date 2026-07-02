"""Trading signal detection — liquidity, smart money, order flow, traps."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from models.alerts import Alert, SignalAnalysis, StockStatus, TechnicalIndicators


def _volume_ratio(df: pd.DataFrame, period: int = 20) -> float:
    if len(df) < period:
        return 1.0
    avg_vol = df["volume"].tail(period).mean()
    if avg_vol == 0:
        return 1.0
    return float(df["volume"].iloc[-1] / avg_vol)


def _price_momentum(df: pd.DataFrame, bars: int = 5) -> float:
    if len(df) < bars + 1:
        return 0.0
    return float((df["close"].iloc[-1] - df["close"].iloc[-bars - 1]) / df["close"].iloc[-bars - 1] * 100)


def _buy_sell_pressure(df: pd.DataFrame) -> tuple[float, float]:
    if len(df) < 5:
        return 50.0, 50.0
    recent = df.tail(10)
    buy_score = 0.0
    sell_score = 0.0
    for _, row in recent.iterrows():
        body = row["close"] - row["open"]
        range_ = row["high"] - row["low"]
        if range_ == 0:
            continue
        if body > 0:
            buy_score += abs(body) / range_
        else:
            sell_score += abs(body) / range_
    total = buy_score + sell_score
    if total == 0:
        return 50.0, 50.0
    return round(buy_score / total * 100, 1), round(sell_score / total * 100, 1)


def _order_flow(df: pd.DataFrame) -> tuple[bool, bool]:
    """Order flow from close position within candle range + volume trend."""
    if len(df) < 10:
        return False, False
    recent = df.tail(5)
    bullish = 0
    bearish = 0
    for _, row in recent.iterrows():
        range_ = row["high"] - row["low"]
        if range_ == 0:
            continue
        close_pos = (row["close"] - row["low"]) / range_
        vol_weight = row["volume"] / max(recent["volume"].mean(), 1)
        if close_pos > 0.65:
            bullish += close_pos * vol_weight
        elif close_pos < 0.35:
            bearish += (1 - close_pos) * vol_weight
    return bullish > bearish * 1.3, bearish > bullish * 1.3


def _smart_money(df: pd.DataFrame, vol_ratio: float) -> tuple[bool, bool]:
    """Smart money: high volume with small spread and directional close."""
    if len(df) < 15:
        return False, False
    row = df.iloc[-1]
    range_pct = (row["high"] - row["low"]) / row["close"] * 100 if row["close"] else 0
    body_pct = abs(row["close"] - row["open"]) / row["close"] * 100 if row["close"] else 0

    # Accumulation: high vol, tight range, closes up
    inflow = vol_ratio > 1.8 and range_pct < 0.8 and row["close"] > row["open"] and body_pct > 0.1
    # Distribution: high vol, closes down after extension
    outflow = vol_ratio > 1.8 and row["close"] < row["open"] and body_pct > 0.15
    return inflow, outflow


def analyze_signals(
    symbol: str,
    df: pd.DataFrame,
    indicators: TechnicalIndicators,
    price: float,
) -> tuple[SignalAnalysis, list[Alert], StockStatus]:
    vol_ratio = _volume_ratio(df)
    momentum = _price_momentum(df)
    buy_p, sell_p = _buy_sell_pressure(df)
    order_bull, order_bear = _order_flow(df)
    smart_in, smart_out = _smart_money(df, vol_ratio)

    volume_spike = vol_ratio > 2.0
    liquidity_inflow = (vol_ratio > 1.5 and momentum > 0.3 and buy_p > 55) or smart_in
    liquidity_outflow = (vol_ratio > 1.3 and momentum < -0.3 and sell_p > 55) or smart_out
    large_buy_volume = vol_ratio > 2.0 and buy_p > 60
    abnormal_volume = vol_ratio > 2.5

    above_resistance = price > indicators.resistance * 0.998
    below_support = price < indicators.support * 1.002
    volume_confirms = vol_ratio > 1.2

    true_breakout = above_resistance and volume_confirms and indicators.rsi < 75 and not order_bear
    false_breakout = above_resistance and (not volume_confirms or indicators.rsi > 70)

    if len(df) >= 3:
        prev_high = float(df["high"].iloc[-2])
        trap = prev_high > indicators.resistance and price < indicators.resistance
    else:
        trap = False

    fake_pump = momentum > 3 and indicators.rsi > 78 and vol_ratio > 2 and sell_p > 45
    liquidity_trap = below_support and abnormal_volume and sell_p > 58

    liquidity_strength = min(100, round(vol_ratio * 25 + abs(momentum) * 5 + max(buy_p, sell_p) * 0.3, 1))

    parts = []
    if liquidity_inflow:
        parts.append("دخول سيولة")
    if liquidity_outflow:
        parts.append("خروج سيولة")
    if smart_in:
        parts.append("أموال ذكية تدخل")
    if smart_out:
        parts.append("أموال ذكية تخرج")
    if order_bull:
        parts.append("تدفق أوامر شراء")
    if order_bear:
        parts.append("تدفق أوامر بيع")
    if volume_spike:
        parts.append("قفزة فوليوم")
    if true_breakout:
        parts.append("اختراق حقيقي")
    if false_breakout:
        parts.append("اختراق وهمي")
    if trap:
        parts.append("فخ سوق")
    if fake_pump:
        parts.append("ضخ وهمي")
    if liquidity_trap:
        parts.append("مصيدة سيولة")

    signals = SignalAnalysis(
        liquidity_inflow=liquidity_inflow,
        liquidity_outflow=liquidity_outflow,
        buy_pressure=buy_p,
        sell_pressure=sell_p,
        large_buy_volume=large_buy_volume,
        abnormal_volume=abnormal_volume,
        volume_spike=volume_spike,
        true_breakout=true_breakout,
        false_breakout=false_breakout,
        market_trap=trap,
        fake_pump=fake_pump,
        liquidity_trap=liquidity_trap,
        smart_money_inflow=smart_in,
        smart_money_outflow=smart_out,
        order_flow_bullish=order_bull,
        order_flow_bearish=order_bear,
        liquidity_strength=liquidity_strength,
        summary=" | ".join(parts) if parts else "لا إشارات قوية حالياً",
    )

    alerts = _build_alerts(symbol, signals, indicators, vol_ratio)
    status = _determine_status(signals, indicators)
    return signals, alerts, status


def _build_alerts(
    symbol: str,
    signals: SignalAnalysis,
    indicators: TechnicalIndicators,
    vol_ratio: float,
) -> list[Alert]:
    now = datetime.now(timezone.utc).isoformat()
    alerts: list[Alert] = []

    # Buy AI alerts
    if signals.true_breakout and signals.liquidity_inflow:
        alerts.append(Alert(
            symbol=symbol, alert_type="buy_alert", title="تنبيه شراء — اختراق مؤكد",
            message=f"اختراق حقيقي + سيولة — RSI {indicators.rsi}", severity="high", timestamp=now,
        ))
    elif signals.smart_money_inflow and signals.order_flow_bullish:
        alerts.append(Alert(
            symbol=symbol, alert_type="buy_alert", title="تنبيه شراء — أموال ذكية",
            message="دخول أموال ذكية مع تدفق أوامر شراء", severity="high", timestamp=now,
        ))
    elif signals.liquidity_inflow and indicators.macd_histogram > 0 and 40 < indicators.rsi < 65:
        alerts.append(Alert(
            symbol=symbol, alert_type="entry_opportunity", title="فرصة دخول",
            message="دخول سيولة مع زخم إيجابي", severity="medium", timestamp=now,
        ))

    # Sell AI alerts
    if signals.smart_money_outflow and signals.order_flow_bearish:
        alerts.append(Alert(
            symbol=symbol, alert_type="sell_alert", title="تنبيه بيع — خروج أموال ذكية",
            message="خروج أموال ذكية مع ضغط بيع", severity="high", timestamp=now,
        ))
    elif signals.liquidity_outflow or (indicators.rsi > 75 and signals.sell_pressure > 60):
        alerts.append(Alert(
            symbol=symbol, alert_type="sell_alert", title="تنبيه بيع / خروج",
            message="سحب سيولة أو ضغط بيع قوي", severity="medium", timestamp=now,
        ))

    if signals.volume_spike and not signals.true_breakout:
        alerts.append(Alert(
            symbol=symbol, alert_type="high_liquidity_no_confirm", title="قفزة فوليوم بدون تأكيد",
            message=f"فوليوم {vol_ratio:.1f}x المتوسط — انتظر تأكيد", severity="medium", timestamp=now,
        ))

    if signals.market_trap or signals.liquidity_trap:
        alerts.append(Alert(
            symbol=symbol, alert_type="trap_warning", title="تحذير فخ سيولة",
            message="فخ سوق أو مصيدة سيولة", severity="high", timestamp=now,
        ))

    if signals.fake_pump or signals.false_breakout:
        alerts.append(Alert(
            symbol=symbol,
            alert_type="fake_pump_warning" if signals.fake_pump else "trap_warning",
            title="تحذير ضخ/اختراق وهمي",
            message=signals.summary, severity="high", timestamp=now,
        ))

    return alerts


def _determine_status(signals: SignalAnalysis, indicators: TechnicalIndicators) -> StockStatus:
    if signals.fake_pump or signals.market_trap or signals.liquidity_trap or signals.false_breakout:
        return "خطر"
    if signals.liquidity_outflow or signals.smart_money_outflow or signals.order_flow_bearish:
        if indicators.rsi > 65 or signals.sell_pressure > 58:
            return "خروج"
    if signals.true_breakout or signals.smart_money_inflow or (
        signals.liquidity_inflow and indicators.macd_histogram > 0
    ):
        return "شراء"
    if signals.large_buy_volume and 45 < indicators.rsi < 68:
        return "شراء"
    return "انتظار"
