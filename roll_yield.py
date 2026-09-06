"""
roll_yield.py — Simulates the "hidden cost" (or hidden gain) of holding
a long futures position over time by continuously rolling contracts.

THE INTUITION (plain English):
You can't hold a futures contract forever — it expires and requires
physical delivery. So an investor who wants ongoing oil exposure must
keep "rolling": sell the contract that's about to expire, buy the next
month's contract, and repeat. That switch is not free.

- In CONTANGO (next month costs more than this month), rolling means
  selling low and buying high every time -> a steady drag on returns.
  This is why oil ETFs can lose money even when the spot price of oil
  is flat or rising: the roll yield is negative.
- In BACKWARDATION (next month costs less), rolling means selling high
  and buying low -> a steady tailwind, adding positive roll yield on
  top of any spot price move.

This module doesn't have access to a full historical ladder of forward
contracts (see README data limitations), so it approximates the roll
using the front-month continuous series itself: it treats the month-end
price move in the front-month contract (which itself reflects the
market rolling from one expiring contract to the next during that
window) as a proxy for the realized roll effect, isolated from the
smooth intra-month spot drift.
"""

import pandas as pd

from config import ROLL_DAYS_BEFORE_MONTH_END


def simulate_roll_yield(history_df):
    """
    Walk through 2 years of daily front-month closes and split the total
    price move into two pieces every month:
      - "spot drift": the price move during the normal part of the
        month (holding, not rolling)
      - "roll effect": the price move in the final
        ROLL_DAYS_BEFORE_MONTH_END trading days of the month, which is
        when the front-month continuous series absorbs the switch from
        the expiring contract to the next one.

    Plain English: think of the month as two segments. Most of the month
    you're just holding a contract and its price wiggles with the
    market ("spot drift"). Right before expiry, the continuous series
    is effectively swapping which contract it's tracking — that
    transition is where roll cost/gain gets baked in. Summing only the
    second segment across every month gives a running total of "how
    much did rolling alone cost or earn me," independent of the overall
    price trend.

    Returns a DataFrame with columns: date, cumulative_roll_yield,
    cumulative_spot_change — both expressed in price terms (dollars per
    barrel), indexed to 0 at the start of the window, so they can be
    plotted side by side.
    """
    if history_df is None or history_df.empty:
        return pd.DataFrame(columns=["date", "cumulative_roll_yield", "cumulative_spot_change"])

    df = history_df.sort_values("date").reset_index(drop=True)
    df["month_period"] = df["date"].dt.to_period("M")

    start_price = df["close"].iloc[0]
    cumulative_roll = 0.0
    records = []

    for _, month_group in df.groupby("month_period"):
        month_group = month_group.reset_index(drop=True)
        n_days = len(month_group)
        roll_window_start = max(0, n_days - ROLL_DAYS_BEFORE_MONTH_END)

        for i in range(n_days):
            row = month_group.iloc[i]
            if i >= roll_window_start and i > 0:
                # Price move during the roll window counts as roll effect.
                day_move = row["close"] - month_group.iloc[i - 1]["close"]
                cumulative_roll += day_move
            spot_change = row["close"] - start_price
            records.append(
                {
                    "date": row["date"],
                    "cumulative_roll_yield": cumulative_roll,
                    "cumulative_spot_change": spot_change,
                }
            )

    return pd.DataFrame(records)


def summarize_roll_yield(roll_yield_df):
    """
    Pull the headline 2-year cumulative roll yield (in dollars/barrel)
    out of the full daily series — the single number shown in the
    dashboard's metrics row.

    Plain English: "over the whole lookback window, how much did the
    act of rolling contracts alone add or subtract from returns?"
    """
    if roll_yield_df is None or roll_yield_df.empty:
        return 0.0
    return float(roll_yield_df["cumulative_roll_yield"].iloc[-1])
