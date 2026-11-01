"""
term_structure.py — Classifies today's futures curve and measures how
steep it is.

THE INTUITION (plain English):
Storing a barrel of oil for a month costs money — tanks, insurance,
financing the cash tied up in it. So under normal conditions, a
contract for delivery further in the future should cost a bit MORE than
one for delivery sooner, to compensate whoever is holding the barrels.
A curve that rises with time-to-delivery is called CONTANGO.

Sometimes the opposite happens: buyers are willing to pay MORE for oil
right now than for oil next month. That happens when the market is
worried about a near-term shortage (e.g. a supply disruption) — they'd
rather have the barrel today than a cheaper promise of a barrel later.
A curve that falls with time-to-delivery is called BACKWARDATION.

This module takes a snapshot of prices across contract months and
answers two questions:
  1. Contango, backwardation, or "kinked" (non-monotonic) — see
     classify_curve().
  2. How steep, expressed as an annualized percentage — see
     compute_annualized_spread().
"""

import pandas as pd

from config import MONTHS_PER_YEAR

# If the front-to-back price difference is smaller than this fraction of
# the front price, we call the curve "flat" rather than forcing a
# contango/backwardation label on what is really just noise.
FLAT_CURVE_THRESHOLD_PCT = 0.05  # 0.05% of front price


def classify_curve(curve_df: pd.DataFrame) -> dict:
    """
    Label the curve as "Contango", "Backwardation", "Flat", or note that
    it is "kinked" (not a straight monotonic slope end-to-end).

    Method: sort contracts by month_index (front to back), then compare
    every price to the next one.
      - If every step price[i+1] >= price[i]: strictly rising -> Contango
      - If every step price[i+1] <= price[i]: strictly falling -> Backwardation
      - Otherwise the curve changes direction somewhere in the middle
        (e.g. dips then rises) -> "Kinked". In that case we do NOT force
        a clean label; we report the primary front-vs-back relationship
        instead, since the headline signal (front cheaper or dearer than
        the far month) is still the main tradeable fact.

    Returns a dict:
      {
        "label": "Contango" | "Backwardation" | "Flat" | "Kinked (net Contango)" | "Kinked (net Backwardation)",
        "is_monotonic": bool,
      }
    """
    if curve_df is None or len(curve_df) < 2:
        return {"label": "Insufficient data", "is_monotonic": False}

    sorted_curve = curve_df.sort_values("month_index")
    prices = sorted_curve["price"].tolist()

    diffs = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    all_rising = all(d >= 0 for d in diffs)
    all_falling = all(d <= 0 for d in diffs)
    is_monotonic = all_rising or all_falling

    front_price = prices[0]
    back_price = prices[-1]
    net_change_pct = 100 * (back_price - front_price) / front_price

    if abs(net_change_pct) < FLAT_CURVE_THRESHOLD_PCT:
        net_label = "Flat"
    elif net_change_pct > 0:
        net_label = "Contango"
    else:
        net_label = "Backwardation"

    if is_monotonic:
        label = net_label
    else:
        label = f"Kinked (net {net_label})"

    return {"label": label, "is_monotonic": is_monotonic}


def compute_annualized_spread(front_price: float, far_price: float, months_between: float) -> float:
    """
    Convert the raw price gap between the front month and a farther-out
    month into an annualized percentage — the implied yearly storage
    cost (if positive/contango) or supply-tightness premium (if
    negative/backwardation).

    Formula (as specified):
        spread_pct = (far_price - front_price) / front_price
                     * (MONTHS_PER_YEAR / months_between) * 100

    Plain English: the raw dollar gap between two contracts isn't
    comparable across different curves unless you know how far apart
    the two months are. Dividing by front_price turns it into a
    percentage; multiplying by (12 / months_between) "stretches" that
    percentage out to what it would be over a full year, so a 2%
    3-month spread and an 8% 12-month spread can be compared on equal
    footing (both annualize to 8%).

    Raises ValueError if months_between <= 0, since the ratio is
    undefined (can't annualize a spread between the same or reversed
    months).
    """
    if months_between <= 0:
        raise ValueError("months_between must be positive")

    return (far_price - front_price) / front_price * (MONTHS_PER_YEAR / months_between) * 100
