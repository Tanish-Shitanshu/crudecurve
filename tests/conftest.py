"""Shared synthetic data for the tests (no network, no database file)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def curve():
    """A falling (backwardated) 6-contract curve."""
    prices = [104.0, 102.0, 100.0, 98.0, 96.0, 94.0]
    return pd.DataFrame(
        {
            "ticker": ["CLZ26", "CLF27", "CLG27", "CLH27", "CLJ27", "CLK27"],
            "delivery_month": ["2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05"],
            "month_index": [0, 1, 2, 3, 4, 5],
            "price": prices,
            "as_of": date(2026, 10, 30),
            "is_stale": False,
            "outlier_flag": [False, False, False, False, False, False],
        }
    )


@pytest.fixture
def history():
    """About 4 years of seeded random-walk closes (so tests are repeatable)."""
    rng = np.random.default_rng(42)
    closes = 80 * np.cumprod(1 + rng.normal(0, 0.015, 1000))
    dates = pd.bdate_range(end="2026-10-30", periods=1000)
    return pd.DataFrame({"date": dates, "close": closes})
