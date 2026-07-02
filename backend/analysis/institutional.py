"""Legacy shim — use smart_money_tracker instead."""

from analysis.smart_money_tracker import analyze_smart_money as analyze_institutional

__all__ = ["analyze_institutional"]
