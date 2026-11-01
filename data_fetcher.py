"""
data_fetcher.py — Pulls WTI crude oil futures prices from Yahoo Finance
(via yfinance):

1. Individual dated NYMEX WTI contracts (symbols like CLZ26.NYM), which
   build the current term-structure "curve" (get_current_curve()).
2. The continuous front-month series (CL=F), used for 2 years of daily
   history to drive the roll-yield backtest (get_front_month_history()).

This module never fabricates a price: a contract with no data (e.g. one
that has already expired) is dropped rather than estimated, and a
contract whose latest close is older than STALE_DATA_THRESHOLD_DAYS is
treated as expired and dropped too.
"""

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from config import (
    CANDIDATE_CONTRACT_MONTHS,
    CONTRACT_SYMBOL_TEMPLATE,
    CURVE_CONTRACT_COUNT,
    FRONT_MONTH_TICKER,
    FUTURES_MONTH_CODES,
    ROLL_YIELD_LOOKBACK_YEARS,
)

# A price is considered "stale" if the most recent available close is
# older than this many calendar days. 5 days covers a normal long
# weekend/holiday without masking a genuinely dead/expired contract.
STALE_DATA_THRESHOLD_DAYS = 5

# How much recent daily history to request per contract when looking for
# its latest close (comfortably longer than the stale threshold).
_LATEST_CLOSE_LOOKBACK = "10d"


def _candidate_contracts(today):
    """
    List the WTI contracts to try, in delivery order, starting with the
    current calendar month: [(symbol, display_ticker, months_ahead), ...].

    e.g. for November 2026: ("CLX26.NYM", "CLX26", 0), ("CLZ26.NYM",
    "CLZ26", 1), ("CLF27.NYM", "CLF27", 2), ...
    """
    candidates = []
    for months_ahead in range(CANDIDATE_CONTRACT_MONTHS):
        month_zero_based = (today.month - 1 + months_ahead) % 12
        year = today.year + (today.month - 1 + months_ahead) // 12
        code = FUTURES_MONTH_CODES[month_zero_based]
        symbol = CONTRACT_SYMBOL_TEMPLATE.format(month_code=code, year=year % 100)
        candidates.append((symbol, symbol.split(".")[0], months_ahead))
    return candidates


def _fetch_contract_latest(symbol: str):
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


def get_current_curve():
    """
    Build today's futures curve from individual dated WTI contracts.

    Plain English: this is the "term structure" snapshot — the front
    (nearest live expiry) contract followed by the next live delivery
    months. Lining these prices up shows whether the market is in
    contango (rising) or backwardation (falling); see term_structure.py
    for the classification logic.

    Contracts are tried in delivery order starting from the current
    month. Ones with no data (already expired) or a last close older than
    STALE_DATA_THRESHOLD_DAYS are dropped; the first CURVE_CONTRACT_COUNT
    live contracts are kept.

    Returns a pandas DataFrame with columns:
      ticker, month_index (delivery months after the front contract:
      0 = front month; a skipped delivery month leaves a gap, so spacing
      stays correct), price, as_of, is_stale
    Returns an empty frame if no contract is live.
    """
    today = datetime.now().date()
    rows = []
    front_months_ahead = None

    for symbol, ticker, months_ahead in _candidate_contracts(today):
        if len(rows) >= CURVE_CONTRACT_COUNT:
            break

        result = _fetch_contract_latest(symbol)
        if result["price"] is None:
            continue  # no data (e.g. expired contract) — skip, don't fake it

        is_stale = (today - result["as_of"]) > timedelta(days=STALE_DATA_THRESHOLD_DAYS)
        if is_stale:
            continue  # last bar is old: the contract has expired/stopped trading

        if front_months_ahead is None:
            front_months_ahead = months_ahead
        rows.append(
            {
                "ticker": ticker,
                "month_index": months_ahead - front_months_ahead,
                "price": result["price"],
                "as_of": result["as_of"],
                "is_stale": is_stale,
            }
        )

    return pd.DataFrame(rows)


def get_front_month_history(years: int = ROLL_YIELD_LOOKBACK_YEARS):
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
