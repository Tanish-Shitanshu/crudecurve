"""test_views.py — The VaR table stays narrow (3 columns) so it fits a phone screen."""

import pandas as pd
import pytest

from crudecurve import metrics, views


@pytest.fixture
def m(curve, history):
    return metrics.build_metrics(curve, history, lookback_years=2, n_contracts=2)


def test_var_table_has_three_narrow_columns_and_four_rows(m):
    table = views._var_table(m)
    assert list(table.columns) == ["1-day VaR", "Loss (USD, % of notional)", "Observations"]
    assert len(table) == 4
    assert list(table["1-day VaR"]) == ["95%, 2 years", "99%, 2 years", "95%, last 12 months", "99%, last 12 months"]


def test_var_table_shows_dollars_percent_and_observation_counts(m):
    table = views._var_table(m)
    v = m["risk"]["var"][0.95]
    assert table["Observations"].iloc[0] == v["observations"]
    loss = table["Loss (USD, % of notional)"].iloc[0]
    assert loss.startswith("$") and loss.endswith("%)")
    assert table["Observations"].iloc[2] < table["Observations"].iloc[0]  # 12 months has fewer than 2 years


def test_var_table_handles_missing_history():
    empty = metrics.build_metrics(
        pd.DataFrame({"ticker": ["A", "B", "C", "D"], "delivery_month": ["x"] * 4, "month_index": [0, 1, 2, 3],
                      "price": [4.0, 3.0, 2.0, 1.0], "as_of": pd.Timestamp("2026-10-30").date(),
                      "is_stale": False, "outlier_flag": False}),
        pd.DataFrame(columns=["date", "close"]), 5, 1,
    )
    table = views._var_table(empty)
    assert set(table["Loss (USD, % of notional)"]) == {"n/a (n/a)"}
    assert set(table["Observations"]) == {0}
