"""
test_validation.py — Every validation rule, passing and failing, plus the
way validate_curve() puts them together.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validation
from validation import RuleResult

TODAY = date(2026, 11, 1)


def _curve(prices, delivery_months=None, month_index=None):
    n = len(prices)
    return pd.DataFrame(
        {
            "ticker": [f"C{i}" for i in range(n)],
            "delivery_month": delivery_months or [f"2027-{i + 1:02d}" for i in range(n)],
            "month_index": month_index if month_index is not None else list(range(n)),
            "price": prices,
        }
    )


# --- contract-level rules --------------------------------------------------

def test_not_expired_passes_for_a_contract_that_still_trades():
    r = validation.check_not_expired("CLZ26", "2026-12", True, TODAY)  # expires 2026-11-20
    assert r.status == "pass"


def test_not_expired_passes_on_the_expiry_day_itself():
    r = validation.check_not_expired("CLZ26", "2026-12", True, date(2026, 11, 20))
    assert r.status == "pass"


def test_not_expired_skips_a_contract_after_its_expiry_date():
    # Expired is expected, so it is "skipped", not a failure.
    r = validation.check_not_expired("CLX26", "2026-11", False, TODAY)  # expired 2026-10-20
    assert r.status == "skipped" and r.detail == "expired on 2026-10-20"


def test_not_expired_skips_an_expired_contract_even_if_old_data_exists():
    r = validation.check_not_expired("CLX26", "2026-11", True, TODAY)
    assert r.status == "skipped"


def test_not_expired_fails_when_a_live_contract_returned_no_data():
    r = validation.check_not_expired("CLZ26", "2026-12", False, TODAY)  # trades until 2026-11-20
    assert r.status == "fail" and "no price data" in r.detail


def test_price_valid_passes_for_a_positive_number():
    assert validation.check_price_valid("CLZ26", 104.12).status == "pass"


def test_price_valid_fails_for_zero_negative_nan_inf_and_none():
    for bad in (0.0, -5.0, float("nan"), float("inf"), None):
        assert validation.check_price_valid("CLZ26", bad).status == "fail", bad


def test_price_fresh_passes_within_the_limit():
    assert validation.check_price_fresh("CLZ26", TODAY - timedelta(days=5), TODAY).status == "pass"


def test_price_fresh_fails_beyond_the_limit():
    r = validation.check_price_fresh("CLZ26", TODAY - timedelta(days=6), TODAY)
    assert r.status == "fail" and "6 days old" in r.detail


# --- curve-level rules ---------------------------------------------------------

def test_no_duplicate_delivery_months():
    ok = _curve([1, 2], delivery_months=["2026-12", "2027-01"])
    bad = _curve([1, 2], delivery_months=["2026-12", "2026-12"])
    assert validation.check_no_duplicate_delivery_months(ok).status == "pass"
    assert validation.check_no_duplicate_delivery_months(bad).status == "fail"


def test_month_index_must_be_strictly_increasing():
    assert validation.check_month_index_increasing(_curve([1, 2, 3])).status == "pass"
    repeated = _curve([1, 2, 3], month_index=[0, 1, 1])
    backwards = _curve([1, 2, 3], month_index=[0, 2, 1])
    assert validation.check_month_index_increasing(repeated).status == "fail"
    assert validation.check_month_index_increasing(backwards).status == "fail"


def test_min_live_contracts_needs_four():
    assert validation.check_min_live_contracts(_curve([1, 2, 3, 4])).status == "pass"
    assert validation.check_min_live_contracts(_curve([1, 2, 3])).status == "fail"


def test_outlier_is_flagged_not_dropped():
    # The 3rd price (150) is far from the average of its neighbours (~99).
    results = validation.find_outliers(_curve([100, 99, 150, 98, 97]))
    flagged = [r.contract for r in results if r.status == "flag"]
    assert "C2" in flagged
    assert len(results) == 5  # every contract still has a result


def test_smooth_curve_has_no_outliers():
    results = validation.find_outliers(_curve([104, 102, 100, 98, 96, 94]))
    assert all(r.status == "pass" for r in results)


# --- validate_curve --------------------------------------------------------------

def _quotes(rows):
    """rows: (ticker, delivery_month, months_ahead, price, as_of)"""
    return pd.DataFrame(rows, columns=["ticker", "delivery_month", "months_ahead", "price", "as_of"])


def _fresh_rows(first_ahead=1, count=8):
    """Consecutive live contracts delivering from 2026-12 onwards."""
    months = ["2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06", "2027-07"]
    return [
        (f"C{i}", months[i], first_ahead + i, 100.0 - i, TODAY - timedelta(days=2))
        for i in range(count)
    ]


def test_validate_curve_keeps_first_six_live_contracts_with_front_at_index_zero():
    rows = [("CLX26", "2026-11", 0, None, None)] + _fresh_rows()  # CLX26 expired
    curve, results = validation.validate_curve(_quotes(rows), TODAY)

    assert not any(r.status == "fail" for r in results)  # an expired contract is not an error
    assert len(curve) == 6
    assert list(curve["month_index"]) == [0, 1, 2, 3, 4, 5]
    assert curve["ticker"].iloc[0] == "C0"
    assert validation.curve_is_usable(results)


def test_validate_curve_skips_expired_and_drops_stale_and_invalid_contracts_and_logs_why():
    rows = _fresh_rows(count=6)
    rows[0] = ("C0", "2026-12", 1, 100.0, TODAY - timedelta(days=30))  # stale
    rows[1] = ("C1", "2027-01", 2, -3.0, TODAY)  # invalid price
    rows.append(("CLX26", "2026-11", 0, None, None))  # expired / no data
    curve, results = validation.validate_curve(_quotes(rows), TODAY)

    assert list(curve["ticker"]) == ["C2", "C3", "C4", "C5"]
    failed = {(r.contract, r.rule) for r in results if r.status == "fail"}
    assert ("C0", "price_fresh") in failed
    assert ("C1", "price_valid") in failed
    # The expired contract is recorded as skipped, never as a failure.
    assert ("CLX26", "not_expired") not in failed
    skipped = [(r.contract, r.rule, r.detail) for r in results if r.status == "skipped"]
    assert skipped == [("CLX26", "not_expired", "expired on 2026-10-20")]


def test_validate_curve_month_index_keeps_gaps():
    rows = _fresh_rows(count=5)
    rows.pop(2)  # the 3rd delivery month is missing
    curve, _ = validation.validate_curve(_quotes(rows), TODAY)
    assert list(curve["month_index"]) == [0, 1, 3, 4]


def test_validate_curve_with_too_few_contracts_is_not_usable():
    curve, results = validation.validate_curve(_quotes(_fresh_rows(count=3)), TODAY)
    assert len(curve) == 3
    assert not validation.curve_is_usable(results)


def test_validate_curve_with_no_contracts_is_not_usable_and_does_not_crash():
    rows = [("CLX26", "2026-11", 0, None, None)]
    curve, results = validation.validate_curve(_quotes(rows), TODAY)
    assert curve.empty
    assert list(curve.columns) == validation.CURVE_COLUMNS
    assert not validation.curve_is_usable(results)


def test_validate_curve_flags_an_outlier_but_keeps_it():
    rows = _fresh_rows(count=6)
    rows[2] = ("C2", "2027-02", 3, 160.0, TODAY - timedelta(days=2))  # far from neighbours
    curve, results = validation.validate_curve(_quotes(rows), TODAY)
    assert len(curve) == 6
    assert curve.loc[curve["ticker"] == "C2", "outlier_flag"].iloc[0]
    assert validation.curve_is_usable(results)  # a flag is a warning, not a failure


def test_curve_is_usable_ignores_contract_level_failures():
    results = [RuleResult("CLX26", "not_expired", "fail", "x"), RuleResult("CURVE", "min_live_contracts", "pass", "x")]
    assert validation.curve_is_usable(results)
