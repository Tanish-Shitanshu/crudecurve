"""
risk.py — Market-risk numbers for a long WTI futures position, computed
from the continuous front-month series CL=F.

All inputs are real history; nothing here is assumed or hardcoded.

WHY ROLL DAYS ARE EXCLUDED
CL=F is an unadjusted continuous series. On the day a contract expires it
switches to the next contract, so the close jumps by the price gap between
the two contracts. That jump is not a market move, but a return calculation
would treat it as one. expiry.roll_dates() finds those days (the first
business day after each contract's expiry) and they are left out of every
return used for volatility, VaR, drawdown and worst day.

TRADE-OFF (read this before quoting a VaR figure)
About 5% of trading days are roll days. A few of them may also contain a
real market move, which is then thrown away too, so VaR may be slightly
understated. Large moves that are NOT roll days are kept, never treated as
outliers: removing them would hide real risk.

OTHER LIMITS
- Historical simulation assumes the past is representative of the future.
- It uses daily closes, so it cannot see moves within a day.
- 99% VaR rests on very few observations (the worst ~1% of days), so the
  observation count is always reported next to it.

SIGN CONVENTIONS
- A return is (today's close / yesterday's close) - 1.
- VaR is reported as a positive number: the loss that was exceeded on only
  (1 - confidence) of past days.
- Drawdown and worst day are negative numbers (they are losses).
- Roll gain/cost is for a LONG position: positive = gain, negative = cost.
"""

from datetime import timedelta

import numpy as np
import pandas as pd

from config import (
    BARRELS_PER_CONTRACT,
    RECENT_WINDOW_DAYS,
    TRADING_DAYS_PER_YEAR,
    VAR_CONFIDENCE_LEVELS,
    VOLATILITY_WINDOW_DAYS,
)
from expiry import roll_dates


def compute_returns(history: pd.DataFrame) -> pd.DataFrame:
    """
    Daily returns of the close series, with roll days marked.

    history has columns date, close. Returns a DataFrame with columns:
      date, close, daily_return (NaN on the first day), is_roll_day
    """
    df = history.sort_values("date").reset_index(drop=True)[["date", "close"]].copy()
    df["daily_return"] = df["close"].pct_change()
    if df.empty:
        df["is_roll_day"] = pd.Series(dtype=bool)
        return df
    rolls = {pd.Timestamp(d) for d in roll_dates(df["date"].min().date(), df["date"].max().date())}
    df["is_roll_day"] = df["date"].isin(rolls)
    return df


def window_returns(returns: pd.DataFrame, years: float = None, days: int = None) -> pd.DataFrame:
    """The rows of `returns` within the last `years` years (or `days` days) of its last date."""
    if returns.empty:
        return returns
    span = timedelta(days=days) if days is not None else timedelta(days=round(365.25 * years))
    cutoff = returns["date"].max() - span
    return returns[returns["date"] > cutoff]


def usable_returns(returns: pd.DataFrame) -> pd.Series:
    """Daily returns with roll days and the empty first day removed, indexed by date."""
    keep = returns[~returns["is_roll_day"]].dropna(subset=["daily_return"])
    return keep.set_index("date")["daily_return"]


def rolling_volatility(returns: pd.DataFrame, window: int = VOLATILITY_WINDOW_DAYS) -> pd.Series:
    """
    Annualised rolling volatility: the standard deviation of the last
    `window` non-roll daily returns, times sqrt(252) (trading days a year).
    """
    clean = usable_returns(returns)
    return clean.rolling(window).std() * np.sqrt(TRADING_DAYS_PER_YEAR)


def historical_var(clean_returns: pd.Series, confidence: float, notional: float) -> dict:
    """
    Historical-simulation 1-day Value at Risk.

    Method: take the past daily returns, find the (1 - confidence)
    percentile (the 5th percentile for 95% VaR), and apply that return to
    today's position value. "On 95% of past days the loss was smaller than
    this."

    Returns {"var_pct", "var_usd", "observations"}; var_pct and var_usd are
    positive loss amounts (None if there are no returns).
    """
    if clean_returns.empty:
        return {"var_pct": None, "var_usd": None, "observations": 0}
    cutoff_return = float(np.percentile(clean_returns, 100 * (1 - confidence)))
    loss_pct = -cutoff_return
    return {"var_pct": loss_pct, "var_usd": loss_pct * notional, "observations": len(clean_returns)}


def max_drawdown(returns: pd.DataFrame) -> dict:
    """
    Largest peak-to-trough fall of a price index built from the daily
    returns. Roll days count as 0% so contract-switch gaps do not create
    fake drawdowns.

    Returns {"max_drawdown", "peak_date", "trough_date"}; max_drawdown is
    negative (e.g. -0.5 = a 50% fall from the peak).
    """
    if returns.empty:
        return {"max_drawdown": None, "peak_date": None, "trough_date": None}
    step = returns["daily_return"].fillna(0.0).where(~returns["is_roll_day"], 0.0)
    index = pd.Series((1 + step).cumprod().to_numpy(), index=returns["date"].to_numpy())
    drawdown = index / index.cummax() - 1
    trough_date = drawdown.idxmin()
    peak_date = index.loc[:trough_date].idxmax()
    return {
        "max_drawdown": float(drawdown.min()),
        "peak_date": pd.Timestamp(peak_date).date(),
        "trough_date": pd.Timestamp(trough_date).date(),
    }


def worst_day(clean_returns: pd.Series) -> dict:
    """The single worst non-roll daily return and its date (None if no returns)."""
    if clean_returns.empty:
        return {"return": None, "date": None}
    return {"return": float(clean_returns.min()), "date": pd.Timestamp(clean_returns.idxmin()).date()}


def roll_gain_per_year(annualised_carry_pct: float, notional: float) -> float:
    """
    Estimated yearly roll gain (positive) or cost (negative) of a LONG
    position if the curve stays as it is today.

    annualised_carry_pct is the curve's annualised front-to-back spread
    (term_structure.compute_annualized_spread): positive in contango.
    A long position rolling in contango sells cheap and buys dear, a cost,
    so the sign is flipped:  gain = -carry% / 100 * notional.
    """
    return -annualised_carry_pct / 100 * notional


def position_notional(price: float, n_contracts: int) -> float:
    """Dollar value of the position: price per barrel x 1,000 barrels x contracts."""
    return price * BARRELS_PER_CONTRACT * n_contracts


def summarize_risk(history: pd.DataFrame, lookback_years: float, price: float, n_contracts: int) -> dict:
    """
    All the risk numbers the dashboard and the Excel report show.

    history: CL=F closes (columns date, close), as long as available.
    lookback_years: the selected VaR window; the "recent" VaR always uses
    the last RECENT_WINDOW_DAYS days.
    price: today's price per barrel used to value the position.

    Returns a dict with: notional, lookback_years, window_start, window_end,
    roll_days_excluded, var (lookback window) and var_recent, each a dict
    keyed by confidence level, plus volatility (latest rolling, annualised),
    max_drawdown and worst_day over the lookback window.
    """
    notional = position_notional(price, n_contracts)
    returns = compute_returns(history)
    selected = window_returns(returns, years=lookback_years)
    recent = window_returns(returns, days=RECENT_WINDOW_DAYS)

    selected_clean = usable_returns(selected)
    recent_clean = usable_returns(recent)
    volatility = rolling_volatility(selected).dropna()

    return {
        "notional": notional,
        "lookback_years": lookback_years,
        "window_start": selected["date"].min().date() if not selected.empty else None,
        "window_end": selected["date"].max().date() if not selected.empty else None,
        "roll_days_excluded": int(selected["is_roll_day"].sum()),
        "var": {c: historical_var(selected_clean, c, notional) for c in VAR_CONFIDENCE_LEVELS},
        "var_recent": {c: historical_var(recent_clean, c, notional) for c in VAR_CONFIDENCE_LEVELS},
        "volatility": float(volatility.iloc[-1]) if not volatility.empty else None,
        "max_drawdown": max_drawdown(selected),
        "worst_day": worst_day(selected_clean),
    }
