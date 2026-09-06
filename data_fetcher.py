"""
data_fetcher.py — Pulls WTI crude oil futures prices from Yahoo Finance
via yfinance.

Two jobs:
1. get_current_curve() — a snapshot "ladder" of prices across contract
   months right now, used to draw the term structure curve.
2. get_front_month_history() — 2 years of daily front-month closes,
   used as the raw material for the roll-yield backtest.

Why yfinance: it's free and needs no API key, which matters for a
student portfolio project. The tradeoff (documented in the README) is
that Yahoo Finance does not give retail users a full paid-terminal-style
ladder of forward contracts, so forward months are fetched as individual
dated contract symbols that can go stale outside their trading window.
This module never fabricates a price — if a symbol has no recent data,
it is reported as missing/stale rather than filled in.
"""

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from config import (
    FRONT_MONTH_TICKER,
    FORWARD_MONTH_TICKERS,
    ROLL_YIELD_LOOKBACK_YEARS,
)

# A price is considered "stale" if the most recent available close is
# older than this many calendar days. 5 days covers a normal long
# weekend/holiday without masking a genuinely dead/delisted symbol.
STALE_DATA_THRESHOLD_DAYS = 5


def _latest_close(ticker: str):
    """
    Fetch the most recent daily close for a single ticker.

    Plain English: this is "what did this contract last trade at, and
    when?" We ask for one month of history (not just the last day) so
    that if the most recent day has no trade, we can fall back to the
    last day that did trade instead of returning nothing.

    Returns a dict: {"price": float or None, "as_of": date or None}
    """
    try:
        history = yf.Ticker(ticker).history(period="1mo")
    except Exception:
        return {"price": None, "as_of": None}

    if history.empty:
        return {"price": None, "as_of": None}

    last_row = history.iloc[-1]
    as_of_date = history.index[-1].date()
    return {"price": float(last_row["Close"]), "as_of": as_of_date}


def get_current_curve():
    """
    Build today's futures curve: one price per contract month, from the
    front month out through the listed forward months.

    Plain English: this is the "term structure" snapshot — if you lined
    up the prices for delivery next month, the month after, and so on,
    what does that price ladder look like? A rising ladder is contango,
    a falling one is backordation (see term_structure.py).

    Returns a pandas DataFrame with columns:
      ticker, month_index (0 = front month, 1 = next month, ...),
      price, as_of, is_stale
    Contracts with no data at all are dropped; contracts with old data
    are kept but flagged is_stale=True so the dashboard can warn the
    user instead of silently plotting a dead price.
    """
    tickers = [FRONT_MONTH_TICKER] + FORWARD_MONTH_TICKERS
    rows = []
    today = datetime.now().date()

    for month_index, ticker in enumerate(tickers):
        result = _latest_close(ticker)
        if result["price"] is None:
            continue  # no data at all for this contract — skip, don't fake it

        is_stale = (today - result["as_of"]) > timedelta(days=STALE_DATA_THRESHOLD_DAYS)
        rows.append(
            {
                "ticker": ticker,
                "month_index": month_index,
                "price": result["price"],
                "as_of": result["as_of"],
                "is_stale": is_stale,
            }
        )

    return pd.DataFrame(rows)


def get_front_month_history(years: int = ROLL_YIELD_LOOKBACK_YEARS):
    """
    Fetch daily front-month closing prices for the last `years` years.

    Plain English: this is the spot/front-month price history used to
    (a) show how the outright oil price moved over 2 years, and (b) as
    the input series the roll-yield simulation "rolls" through month by
    month in roll_yield.py.

    Returns a pandas DataFrame with columns: date, close.
    """
    period_str = f"{years}y"
    history = yf.Ticker(FRONT_MONTH_TICKER).history(period=period_str)

    if history.empty:
        return pd.DataFrame(columns=["date", "close"])

    out = history.reset_index()[["Date", "Close"]]
    out.columns = ["date", "close"]
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    return out
