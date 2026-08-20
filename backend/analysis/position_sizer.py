"""Position sizing calculator — حاسبة المخاطرة."""

from __future__ import annotations

from dataclasses import dataclass

from config import DEFAULT_ACCOUNT_SIZE, DEFAULT_RISK_PCT


@dataclass
class PositionSizeResult:
    capital: float
    risk_pct: float
    risk_amount: float
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    loss_per_share: float
    shares: int
    position_value: float
    expected_profit_tp1: float
    expected_profit_tp2: float
    capped_by_capital: bool
    valid: bool
    error: str = ""


def calculate_position_size(
    *,
    capital: float = DEFAULT_ACCOUNT_SIZE,
    risk_pct: float = DEFAULT_RISK_PCT,
    entry_price: float,
    stop_loss: float,
    take_profit_1: float = 0.0,
    take_profit_2: float = 0.0,
    direction: str = "long",
) -> PositionSizeResult:
    """
    shares = risk_amount / |entry - stop_loss|
    Position value must not exceed available capital.
    """
    if capital <= 0:
        return PositionSizeResult(
            capital=capital, risk_pct=risk_pct, risk_amount=0,
            entry_price=entry_price, stop_loss=stop_loss,
            take_profit_1=take_profit_1, take_profit_2=take_profit_2,
            loss_per_share=0, shares=0, position_value=0,
            expected_profit_tp1=0, expected_profit_tp2=0,
            capped_by_capital=False, valid=False,
            error="رأس المال يجب أن يكون أكبر من صفر",
        )
    if risk_pct <= 0 or risk_pct > 100:
        return PositionSizeResult(
            capital=capital, risk_pct=risk_pct, risk_amount=0,
            entry_price=entry_price, stop_loss=stop_loss,
            take_profit_1=take_profit_1, take_profit_2=take_profit_2,
            loss_per_share=0, shares=0, position_value=0,
            expected_profit_tp1=0, expected_profit_tp2=0,
            capped_by_capital=False, valid=False,
            error="نسبة المخاطرة يجب أن تكون بين 0 و 100",
        )
    if entry_price <= 0:
        return PositionSizeResult(
            capital=capital, risk_pct=risk_pct, risk_amount=0,
            entry_price=entry_price, stop_loss=stop_loss,
            take_profit_1=take_profit_1, take_profit_2=take_profit_2,
            loss_per_share=0, shares=0, position_value=0,
            expected_profit_tp1=0, expected_profit_tp2=0,
            capped_by_capital=False, valid=False,
            error="سعر الدخول غير صالح",
        )

    loss_per_share = abs(entry_price - stop_loss)
    if loss_per_share <= 0:
        return PositionSizeResult(
            capital=capital, risk_pct=risk_pct, risk_amount=0,
            entry_price=entry_price, stop_loss=stop_loss,
            take_profit_1=take_profit_1, take_profit_2=take_profit_2,
            loss_per_share=0, shares=0, position_value=0,
            expected_profit_tp1=0, expected_profit_tp2=0,
            capped_by_capital=False, valid=False,
            error="وقف الخسارة يجب أن يختلف عن سعر الدخول",
        )

    risk_amount = round(capital * (risk_pct / 100), 2)
    raw_shares = int(risk_amount / loss_per_share)
    max_shares_by_capital = int(capital / entry_price) if entry_price > 0 else 0

    capped = False
    if raw_shares > max_shares_by_capital:
        shares = max_shares_by_capital
        capped = True
    elif raw_shares >= max_shares_by_capital > 0:
        shares = max_shares_by_capital
        capped = True
    else:
        shares = raw_shares

    if shares <= 0:
        shares = 0

    position_value = round(shares * entry_price, 2)

    is_long = direction != "short"
    if is_long:
        profit_tp1 = round(shares * max(take_profit_1 - entry_price, 0), 2) if take_profit_1 else 0
        profit_tp2 = round(shares * max(take_profit_2 - entry_price, 0), 2) if take_profit_2 else 0
    else:
        profit_tp1 = round(shares * max(entry_price - take_profit_1, 0), 2) if take_profit_1 else 0
        profit_tp2 = round(shares * max(entry_price - take_profit_2, 0), 2) if take_profit_2 else 0

    return PositionSizeResult(
        capital=round(capital, 2),
        risk_pct=round(risk_pct, 4),
        risk_amount=risk_amount,
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        take_profit_1=round(take_profit_1, 2),
        take_profit_2=round(take_profit_2, 2),
        loss_per_share=round(loss_per_share, 4),
        shares=shares,
        position_value=position_value,
        expected_profit_tp1=profit_tp1,
        expected_profit_tp2=profit_tp2,
        capped_by_capital=capped,
        valid=shares > 0,
        error="" if shares > 0 else "حجم الصفقة صفر — راجع المخاطرة أو وقف الخسارة",
    )
