"""
data_fetcher.py — Pulls WTI crude oil futures prices from Yahoo Finance
(via yfinance). This is the only module that talks to the network.

1. Individual dated NYMEX WTI contracts (symbols like CLZ26.NYM):
   - fetch_candidate_quotes(): the latest close of every candidate
     contract. Missing data is kept as an empty price; deciding what is
     usable is the job of validation.py.
   - get_contract_history(): daily closes of one contract (stored in
     SQLite by storage.py).
2. The continuous front-month series (CL=F), used for long daily history
   (get_front_month_history()).

This module never fabricates a price: if Yahoo has no data for a
contract, the price is left empty rather than estimated.
"""

from datetime import date, datetime
from typing import NamedTuple

import pandas as pd
import yfinance as yf

from config import (
    CANDIDATE_CONTRACT_MONTHS,
    CONTRACT_SYMBOL_TEMPLATE,
    FRONT_MONTH_TICKER,
    FUTURES_MONTH_CODES,
    ROLL_YIELD_LOOKBACK_YEARS,
    YAHOO_SYMBOL_SUFFIX,
)

# How much recent daily history to request per contract when looking for
# its latest close (comfortably longer than the stale threshold).
_LATEST_CLOSE_LOOKBACK = "10d"


class Candidate(NamedTuple):
    """One contract we will try to fetch, e.g. CLZ26 = December 2026."""

    symbol: str  # Yahoo symbol, e.g. "CLZ26.NYM"
    ticker: str  # short name used on screen, e.g. "CLZ26"
    months_ahead: int  # delivery months after the current calendar month
    delivery_month: str  # "YYYY-MM", e.g. "2026-12"


def _candidate_contracts(today: date) -> list[Candidate]:
    """
    List the WTI contracts to try, in delivery order, starting with the
    current calendar month.

    e.g. for November 2026: CLX26 (2026-11), CLZ26 (2026-12), CLF27
    (2027-01), ... CANDIDATE_CONTRACT_MONTHS of them.
    """
    candidates = []
    for months_ahead in range(CANDIDATE_CONTRACT_MONTHS):
        month_zero_based = (today.month - 1 + months_ahead) % 12
        year = today.year + (today.month - 1 + months_ahead) // 12
        code = FUTURES_MONTH_CODES[month_zero_based]
        symbol = CONTRACT_SYMBOL_TEMPLATE.format(month_code=code, year=year % 100)
        delivery_month = f"{year}-{month_zero_based + 1:02d}"
        candidates.append(Candidate(symbol, symbol.split(".")[0], months_ahead, delivery_month))
    return candidates


def _fetch_contract_latest(symbol: str) -> dict:
    """
    Fetch the most recent daily close for one dated futures contract.

    Plain English: asks Yahoo "what did this specific contract last close
    at, and on what date?" Any failure (network error, unknown/expired
    symbol, empty or malformed data) returns no price rather than a guess.

    Returns a dict: {"price": float or None, "as_of": date or None}
    """
    none = {"price": None, "as_of": None}
    try:
        history = yf.Ticker(symbol).history(period=_LATEST_CLOSE_LOOKBACK)
        closes = history["Close"].dropna()
        if closes.empty:
            return none
        return {
            "price": float(closes.iloc[-1]),
            "as_of": pd.Timestamp(closes.index[-1]).date(),
        }
    except Exception:
        return none


def fetch_candidate_quotes(today: date | None = None) -> pd.DataFrame:
    """
    Fetch the latest close of every candidate contract, in delivery order.

    Plain English: one row per contract we tried, including the ones
    Yahoo had nothing for (price and as_of are empty for those). Nothing
    is filtered here, so validation.py can log exactly why a contract was
    not used.

    Returns a DataFrame with columns:
      ticker, delivery_month, months_ahead, price, as_of
    """
    today = today or datetime.now().date()
    rows = []
    for candidate in _candidate_contracts(today):
        result = _fetch_contract_latest(candidate.symbol)
        rows.append(
            {
                "ticker": candidate.ticker,
                "delivery_month": candidate.delivery_month,
                "months_ahead": candidate.months_ahead,
                "price": result["price"],
                "as_of": result["as_of"],
            }
        )
    return pd.DataFrame(rows)


def get_contract_history(ticker: str, period: str) -> pd.DataFrame:
    """
    Fetch daily closes for one contract (e.g. ticker "CLZ26", period "1y").

    Returns a DataFrame with columns: trade_date (a date), close.
    Any failure returns an empty frame; it is simply retried next run.
    """
    empty = pd.DataFrame(columns=["trade_date", "close"])
    try:
        closes = yf.Ticker(ticker + YAHOO_SYMBOL_SUFFIX).history(period=period)["Close"].dropna()
    except Exception:
        return empty
    if closes.empty:
        return empty
    return pd.DataFrame(
        {
            "trade_date": [pd.Timestamp(ts).date() for ts in closes.index],
            "close": closes.astype(float).tolist(),
        }
    )


def get_front_month_history(years: int = ROLL_YIELD_LOOKBACK_YEARS) -> pd.DataFrame:
    """
    Fetch daily front-month closing prices for the last `years` years
    from Yahoo Finance's continuous WTI series (CL=F).

    Plain English: this is the spot/front-month price history used to
    (a) show how the outright oil price moved over 2 years, and (b) as
    the input series the roll-yield simulation "rolls" through month by
    month in roll_yield.py. A single continuous series gives the long
    history that individual dated contracts (which expire) cannot.

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
