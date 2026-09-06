"""
data_fetcher.py — Pulls WTI crude oil futures prices from two sources:

1. EIA (U.S. Energy Information Administration) Open Data API — the
   official government source for WTI Futures Contract 1 through
   Contract 4 daily settlement prices. This is what builds the current
   term structure "curve" (get_current_curve()).
2. yfinance (Yahoo Finance) — the continuous front-month series (CL=F),
   used only for 2 years of daily history to drive the roll-yield
   backtest (get_front_month_history()).

Why two sources: yfinance does not publish dated forward-month WTI
contracts on its free tier (verified directly — those symbols return no
data), so it can't build a real forward curve. The EIA API does publish
real forward contract prices (Contract 1-4), for free, with an API key.
See config.py and the README's "Data Limitations" section for the full
reasoning.

This module never fabricates a price: if EIA or yfinance has no data
for a series, that point is dropped rather than estimated, and stale
data (older than STALE_DATA_THRESHOLD_DAYS) is flagged rather than
silently presented as current.
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

from config import (
    EIA_API_BASE_URL,
    EIA_API_KEY_ENV_VAR,
    EIA_CONTRACT_SERIES,
    FRONT_MONTH_TICKER,
    ROLL_YIELD_LOOKBACK_YEARS,
)

load_dotenv()

# A price is considered "stale" if the most recent available close is
# older than this many calendar days. 5 days covers a normal long
# weekend/holiday without masking a genuinely dead/delisted series.
STALE_DATA_THRESHOLD_DAYS = 5

# EIA's DEMO_KEY is a public, rate-limited key EIA provides for testing
# without registration. It works but is not meant for real usage — see
# README for how to get a free personal key.
_FALLBACK_DEMO_KEY = "DEMO_KEY"


def _get_eia_api_key():
    """
    Read the EIA API key from the environment (loaded from .env by
    load_dotenv() above). Falls back to EIA's public DEMO_KEY so the app
    still runs out of the box, but a real key should be used for
    anything beyond quick testing (DEMO_KEY is rate-limited).
    """
    return os.environ.get(EIA_API_KEY_ENV_VAR, _FALLBACK_DEMO_KEY)


def _fetch_eia_series_latest(series_id: str, api_key: str):
    """
    Fetch the most recent daily value for one EIA WTI futures contract
    series (e.g. "RCLC1" = Contract 1 / front month).

    Plain English: this asks EIA "what did this specific forward
    contract last settle at, and on what date?" — sorted newest first
    and capped to 1 row, so we get exactly the latest official price.

    Returns a dict: {"price": float or None, "as_of": date or None}
    """
    params = {
        "api_key": api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": series_id,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 1,
    }

    try:
        response = requests.get(EIA_API_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return {"price": None, "as_of": None}

    rows = payload.get("response", {}).get("data", [])
    if not rows:
        return {"price": None, "as_of": None}

    row = rows[0]
    try:
        price = float(row["value"])
        as_of = datetime.strptime(row["period"], "%Y-%m-%d").date()
    except (KeyError, TypeError, ValueError):
        return {"price": None, "as_of": None}

    return {"price": price, "as_of": as_of}


def get_current_curve():
    """
    Build today's futures curve from EIA's official WTI Futures
    Contract 1 through Contract 4 daily settlement prices.

    Plain English: this is the "term structure" snapshot — Contract 1
    is the front (nearest-expiry) contract, Contract 4 is roughly 3
    months further out. Lining these four prices up shows whether the
    market is in contango (rising) or backwardation (falling); see
    term_structure.py for the classification logic.

    Returns a pandas DataFrame with columns:
      ticker, month_index (0 = Contract 1 / front month, 1 = Contract 2,
      ...), price, as_of, is_stale
    Contracts with no data at all are dropped; contracts with old data
    are kept but flagged is_stale=True so the dashboard can warn the
    user instead of silently plotting a dead price.
    """
    api_key = _get_eia_api_key()
    rows = []
    today = datetime.now().date()

    for month_index, series_id in enumerate(EIA_CONTRACT_SERIES):
        result = _fetch_eia_series_latest(series_id, api_key)
        if result["price"] is None:
            continue  # no data at all for this contract — skip, don't fake it

        is_stale = (today - result["as_of"]) > timedelta(days=STALE_DATA_THRESHOLD_DAYS)
        rows.append(
            {
                "ticker": series_id,
                "month_index": month_index,
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
    month in roll_yield.py. yfinance's continuous front-month series is
    reliable for this purpose (unlike its dated forward contracts).

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
