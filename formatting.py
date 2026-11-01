"""
formatting.py — Turn numbers into the text shown on screen and in the
summary. Kept in one place (and tested) so a sign or currency symbol can
never be formatted two different ways.

Rule for negatives: the minus sign goes in front of the dollar sign
("-$1.88", not "$-1.88").
"""

from collections.abc import Callable
from typing import Any


def format_usd(value: float, decimals: int = 2) -> str:
    """1234.5 -> "$1,234.50", -1.88 -> "-$1.88"."""
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.{decimals}f}"


def format_signed_usd(value: float, decimals: int = 2) -> str:
    """Like format_usd but always shows a sign: 1.88 -> "+$1.88", -1.88 -> "-$1.88"."""
    sign = "-" if value < 0 else "+"
    return f"{sign}${abs(value):,.{decimals}f}"


def format_pct(value: float, decimals: int = 2, signed: bool = False) -> str:
    """
    Format a number that is already in percent points: 3.94 -> "3.94%".
    With signed=True: -25.72 -> "-25.72%", 3.1 -> "+3.10%".
    (Multiply a fraction such as 0.0394 by 100 before calling.)
    """
    if signed:
        return f"{value:+.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def format_optional(value: Any, formatter: Callable[[Any], str], missing: str = "n/a") -> str:
    """Apply `formatter` to value, or return `missing` if there is no value."""
    return missing if value is None else formatter(value)
