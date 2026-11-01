"""
pipeline.py — Glue that turns "fetch, validate, save" into one call the
dashboard can make: load_curve().

Flow:
  1. data_fetcher.fetch_candidate_quotes()   ask Yahoo for every candidate
  2. validation.validate_curve()             apply the business rules
  3. storage.log_quality_results()           record every rule outcome
  4a. curve usable  -> save snapshot, top up price history, source = "live"
  4b. curve unusable (e.g. Yahoo down) -> load the last saved snapshot,
      source = "snapshot", with a message that says so.
      Nothing saved either -> source = "none" and a clean error message.

Old data is never presented as live: the caller always gets `source`.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd

import data_fetcher
import storage
import validation
from config import BACKFILL_PERIOD, REFRESH_MAX_GAP_DAYS, REFRESH_PERIOD
from validation import RuleResult


@dataclass
class CurveResult:
    """What the dashboard gets back from load_curve()."""

    curve: pd.DataFrame
    results: list[RuleResult]  # validation outcomes from this run
    source: str  # "live", "snapshot" or "none"
    as_of: date | None  # front contract's close date (None if source is "none")
    message: str  # banner/error text; empty for live data


def _history_period(latest_stored: date | None, today: date) -> str:
    """Backfill a full year the first time (or after a long gap), else just top up."""
    if latest_stored is None or (today - latest_stored).days > REFRESH_MAX_GAP_DAYS:
        return BACKFILL_PERIOD
    return REFRESH_PERIOD


def update_contract_prices(conn: sqlite3.Connection, curve: pd.DataFrame, today: date) -> None:
    """Store daily closes for every contract on the curve (a year on first run)."""
    for contract in curve["ticker"]:
        period = _history_period(storage.latest_trade_date(conn, contract), today)
        history = data_fetcher.get_contract_history(contract, period)
        if not history.empty:
            storage.save_contract_prices(conn, contract, history)


def load_curve(conn: sqlite3.Connection, today: date | None = None) -> CurveResult:
    """Fetch and validate the live curve, falling back to the saved snapshot."""
    today = today or datetime.now().date()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    quotes = data_fetcher.fetch_candidate_quotes(today)
    curve, results = validation.validate_curve(quotes, today)
    storage.log_quality_results(conn, now, results)

    if validation.curve_is_usable(results):
        storage.save_snapshot(conn, curve, fetched_at=now)
        update_contract_prices(conn, curve, today)
        return CurveResult(curve, results, "live", curve["as_of"].iloc[0], "")

    snapshot = storage.load_latest_snapshot(conn)
    if snapshot.empty:
        message = "Live data is unavailable and there is no saved snapshot yet. Please try again later."
        return CurveResult(snapshot, results, "none", None, message)

    as_of = snapshot["as_of"].iloc[0]  # front contract's close date (rows are in month_index order)
    message = f"Showing saved snapshot from {as_of} (live data unavailable)."
    return CurveResult(snapshot, results, "snapshot", as_of, message)
