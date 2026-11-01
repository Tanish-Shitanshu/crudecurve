"""test_metrics.py — The headline metrics are computed from the inputs."""

import pandas as pd
import pytest

from crudecurve import metrics, risk


def test_metrics_follow_from_the_curve(curve, history):
    m = metrics.build_metrics(curve, history, lookback_years=2, n_contracts=3)

    assert m["label"] == "Backwardation"
    assert m["front_ticker"] == "CLZ26" and m["back_ticker"] == "CLK27"
    assert m["front_price"] == 104.0 and m["back_price"] == 94.0
    assert m["months_between"] == 5
    # (94 - 104) / 104 * (12 / 5) * 100 = -23.0769...
    assert m["annualised_carry_pct"] == pytest.approx(-23.0769, rel=1e-4)
    assert m["notional"] == 104.0 * 1000 * 3
    # A long position in backwardation gains from rolling.
    assert m["roll_gain_per_year"] == pytest.approx(0.230769 * 312_000, rel=1e-4)
    assert m["source"] == "live"


def test_roll_window_proxy_uses_the_last_two_years_only(curve, history):
    m = metrics.build_metrics(curve, history, lookback_years=5, n_contracts=1)
    assert m["roll_yield_df"]["date"].min() > history["date"].max() - pd.DateOffset(years=2)


def test_risk_comes_from_risk_module(curve, history):
    m = metrics.build_metrics(curve, history, lookback_years=2, n_contracts=1)
    expected = risk.summarize_risk(history, 2, 104.0, 1)
    assert m["risk"]["var"][0.95]["var_usd"] == pytest.approx(expected["var"][0.95]["var_usd"])


def test_a_rising_curve_is_contango_and_a_roll_cost(curve, history):
    curve = curve.assign(price=[94.0, 96.0, 98.0, 100.0, 102.0, 104.0])
    m = metrics.build_metrics(curve, history, 2, 1)
    assert m["label"] == "Contango"
    assert m["annualised_carry_pct"] > 0
    assert m["roll_gain_per_year"] < 0


def test_snapshot_source_is_passed_through(curve, history):
    assert metrics.build_metrics(curve, history, 2, 1, source="snapshot")["source"] == "snapshot"


def test_volatility_series_covers_the_lookback_window(curve, history):
    m = metrics.build_metrics(curve, history, lookback_years=2, n_contracts=1)
    series = m["volatility_series"]
    assert not series.empty
    assert series.index.min() > history["date"].max() - pd.DateOffset(years=2)
    assert series.iloc[-1] == pytest.approx(m["risk"]["volatility"])
