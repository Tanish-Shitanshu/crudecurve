"""
metrics.py — Combines the curve, the CL=F history and the risk numbers
into one dictionary of headline metrics. The dashboard, the Excel report
and the market summary all read from this one place, so they can never
disagree with each other.

Every value is computed from real data passed in; nothing is hardcoded.
"""

import pandas as pd

from config import CONTRACT_MONTH_SPACING, ROLL_YIELD_LOOKBACK_YEARS
from risk import compute_returns, roll_gain_per_year, rolling_volatility, summarize_risk, window_returns
from roll_yield import simulate_roll_yield, summarize_roll_yield
from term_structure import classify_curve, compute_annualized_spread


def build_metrics(
    curve: pd.DataFrame,
    history: pd.DataFrame,
    lookback_years: float,
    n_contracts: int,
    source: str = "live",
) -> dict:
    """
    curve: validated curve (ticker, month_index, price, as_of, ...).
    history: CL=F closes (date, close), as long as available.
    lookback_years: the VaR window selected by the user.
    n_contracts: position size in contracts (1 contract = 1,000 barrels).
    source: "live" or "snapshot" (where the curve came from).

    Returns a dict with: as_of, source, label, is_monotonic, front_ticker,
    back_ticker, front_price, back_price, months_between,
    annualised_carry_pct, n_contracts, notional, roll_gain_per_year,
    roll_window_proxy (2-year, $/bbl), roll_yield_df, risk, volatility_series
    (rolling 21-day annualised volatility over the lookback window), lookback_years.
    """
    curve = curve.sort_values("month_index").reset_index(drop=True)
    classification = classify_curve(curve)
    front, back = curve.iloc[0], curve.iloc[-1]

    months_between = (back["month_index"] - front["month_index"]) * CONTRACT_MONTH_SPACING
    carry_pct = (
        compute_annualized_spread(front["price"], back["price"], months_between)
        if months_between > 0
        else 0.0
    )

    # The roll-window proxy chart and number always use the last 2 years.
    roll_history = history
    if not history.empty:
        cutoff = history["date"].max() - pd.DateOffset(years=ROLL_YIELD_LOOKBACK_YEARS)
        roll_history = history[history["date"] > cutoff]
    roll_yield_df = simulate_roll_yield(roll_history)

    risk = summarize_risk(history, lookback_years, float(front["price"]), n_contracts)
    selected_returns = window_returns(compute_returns(history), years=lookback_years)
    volatility_series = rolling_volatility(selected_returns).dropna()

    return {
        "as_of": front["as_of"],
        "source": source,
        "label": classification["label"],
        "is_monotonic": classification["is_monotonic"],
        "front_ticker": front["ticker"],
        "back_ticker": back["ticker"],
        "front_price": float(front["price"]),
        "back_price": float(back["price"]),
        "months_between": int(months_between),
        "annualised_carry_pct": float(carry_pct),
        "n_contracts": n_contracts,
        "notional": risk["notional"],
        "roll_gain_per_year": roll_gain_per_year(carry_pct, risk["notional"]),
        "roll_window_proxy": summarize_roll_yield(roll_yield_df),
        "roll_yield_df": roll_yield_df,
        "risk": risk,
        "volatility_series": volatility_series,
        "lookback_years": lookback_years,
    }
