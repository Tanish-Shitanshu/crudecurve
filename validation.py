"""
validation.py — Explicit business rules that decide whether market data
is fit to use. Every rule is one small function that returns a
RuleResult (pass / fail / flag plus a plain-English reason), so each rule
can be tested on its own and every outcome can be logged to SQLite.

Contract-level rules (run on every candidate contract):
  not_expired   the contract still trades (and Yahoo returned data for it)
  price_valid   the price is a real number and greater than zero
  price_fresh   the last close is not older than STALE_DATA_THRESHOLD_DAYS

Curve-level rules (run on the contracts that passed, contract = "CURVE"):
  no_duplicate_delivery_months   each delivery month appears once
  month_index_increasing         contracts are in strictly increasing order
  min_live_contracts             at least MIN_LIVE_CONTRACTS contracts
  outlier_check                  FLAGS (never drops) a contract whose price
                                 is far from the average of its neighbours

A "fail" on a contract means that contract is left out of the curve.
A "fail" on a curve-level rule means the whole curve is not usable.
A "flag" is a warning only: the data is kept and shown.
"""

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from config import (
    CURVE_CONTRACT_COUNT,
    MIN_LIVE_CONTRACTS,
    OUTLIER_PCT,
    STALE_DATA_THRESHOLD_DAYS,
)
from expiry import contract_expiry

CURVE = "CURVE"  # the "contract" name used for curve-level rules

CURVE_COLUMNS = [
    "ticker", "delivery_month", "month_index", "price", "as_of", "is_stale", "outlier_flag",
]


@dataclass
class RuleResult:
    """The outcome of one rule applied to one contract (or to the curve)."""

    contract: str
    rule: str
    status: str  # "pass", "fail" or "flag"
    detail: str


# --- Contract-level rules ---------------------------------------------------

def check_not_expired(contract: str, delivery_month: str, has_data: bool, today: date) -> RuleResult:
    """Fail if Yahoo returned nothing, or the calculated expiry date has passed."""
    year, month = (int(part) for part in delivery_month.split("-"))
    expiry = contract_expiry(year, month)
    if today > expiry:
        return RuleResult(contract, "not_expired", "fail", f"expired on {expiry}")
    if not has_data:
        return RuleResult(contract, "not_expired", "fail", "no price data returned")
    return RuleResult(contract, "not_expired", "pass", f"trades until {expiry}")


def check_price_valid(contract: str, price) -> RuleResult:
    """Fail unless the price is a finite number greater than zero."""
    if price is None or not math.isfinite(price) or price <= 0:
        return RuleResult(contract, "price_valid", "fail", f"price {price} is not a finite number > 0")
    return RuleResult(contract, "price_valid", "pass", f"price {price:.2f}")


def check_price_fresh(contract: str, as_of: date, today: date) -> RuleResult:
    """Fail if the last close is older than STALE_DATA_THRESHOLD_DAYS."""
    age_days = (today - as_of).days
    if age_days > STALE_DATA_THRESHOLD_DAYS:
        return RuleResult(
            contract, "price_fresh", "fail",
            f"last close {as_of} is {age_days} days old (limit {STALE_DATA_THRESHOLD_DAYS})",
        )
    return RuleResult(contract, "price_fresh", "pass", f"last close {as_of} ({age_days} days old)")


# --- Curve-level rules --------------------------------------------------------

def check_no_duplicate_delivery_months(curve: pd.DataFrame) -> RuleResult:
    """Fail if two contracts in the curve deliver in the same month."""
    duplicated = curve["delivery_month"][curve["delivery_month"].duplicated()].tolist()
    if duplicated:
        return RuleResult(CURVE, "no_duplicate_delivery_months", "fail", f"repeated: {duplicated}")
    return RuleResult(CURVE, "no_duplicate_delivery_months", "pass", "all delivery months unique")


def check_month_index_increasing(curve: pd.DataFrame) -> RuleResult:
    """Fail unless month_index goes up with every contract (strictly increasing)."""
    steps = curve["month_index"].diff().dropna()
    if (steps <= 0).any():
        return RuleResult(CURVE, "month_index_increasing", "fail", f"month_index = {curve['month_index'].tolist()}")
    return RuleResult(CURVE, "month_index_increasing", "pass", "strictly increasing")


def check_min_live_contracts(curve: pd.DataFrame) -> RuleResult:
    """Fail if fewer than MIN_LIVE_CONTRACTS contracts are live."""
    if len(curve) < MIN_LIVE_CONTRACTS:
        return RuleResult(CURVE, "min_live_contracts", "fail", f"{len(curve)} live, need {MIN_LIVE_CONTRACTS}")
    return RuleResult(CURVE, "min_live_contracts", "pass", f"{len(curve)} live contracts")


def find_outliers(curve: pd.DataFrame) -> list:
    """
    Flag (never drop) a contract whose price is more than OUTLIER_PCT away
    from the average of its neighbours on the curve. The first and last
    contracts have one neighbour, so they are compared with that one.
    """
    prices = curve["price"].tolist()
    results = []
    for i, contract in enumerate(curve["ticker"]):
        neighbours = [prices[j] for j in (i - 1, i + 1) if 0 <= j < len(prices)]
        if not neighbours:
            results.append(RuleResult(contract, "outlier_check", "pass", "no neighbours to compare"))
            continue
        reference = sum(neighbours) / len(neighbours)
        jump_pct = 100 * abs(prices[i] - reference) / reference
        if jump_pct > OUTLIER_PCT:
            detail = f"{jump_pct:.1f}% away from neighbours (limit {OUTLIER_PCT:.0f}%)"
            results.append(RuleResult(contract, "outlier_check", "flag", detail))
        else:
            results.append(RuleResult(contract, "outlier_check", "pass", f"{jump_pct:.1f}% from neighbours"))
    return results


# --- Putting the rules together -------------------------------------------------

def validate_curve(quotes: pd.DataFrame, today: date):
    """
    Apply every rule to the candidate quotes from data_fetcher.

    Steps:
      1. Contract-level rules on each candidate. Failing contracts are left out.
      2. Keep the first CURVE_CONTRACT_COUNT contracts that passed; month_index
         counts delivery months after the front contract (0 = front month).
      3. Curve-level rules on that set; outliers get outlier_flag = True.

    Returns (curve, results): the curve DataFrame and a list of RuleResult.
    """
    results = []
    live = []

    for row in quotes.itertuples(index=False):
        has_price = not pd.isna(row.price)
        expiry_result = check_not_expired(row.ticker, row.delivery_month, has_price, today)
        results.append(expiry_result)
        if expiry_result.status == "fail":
            continue  # nothing more to check on a dead contract

        valid_result = check_price_valid(row.ticker, row.price)
        results.append(valid_result)
        if valid_result.status == "fail":
            continue

        fresh_result = check_price_fresh(row.ticker, row.as_of, today)
        results.append(fresh_result)
        if fresh_result.status == "fail":
            continue

        live.append(row)

    live = sorted(live, key=lambda row: row.months_ahead)[:CURVE_CONTRACT_COUNT]
    curve = pd.DataFrame(
        [
            {
                "ticker": row.ticker,
                "delivery_month": row.delivery_month,
                "month_index": row.months_ahead - live[0].months_ahead,
                "price": float(row.price),
                "as_of": row.as_of,
                "is_stale": False,  # stale contracts were already left out above
                "outlier_flag": False,
            }
            for row in live
        ],
        columns=CURVE_COLUMNS,
    )

    results.append(check_no_duplicate_delivery_months(curve))
    results.append(check_month_index_increasing(curve))
    results.append(check_min_live_contracts(curve))

    outlier_results = find_outliers(curve)
    results.extend(outlier_results)
    curve["outlier_flag"] = [r.status == "flag" for r in outlier_results]

    return curve, results


def curve_is_usable(results: list) -> bool:
    """The curve can be used unless a curve-level rule failed."""
    return not any(r.contract == CURVE and r.status == "fail" for r in results)
