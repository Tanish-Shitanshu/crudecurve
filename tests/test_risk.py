"""
test_risk.py — Risk metrics checked against synthetic series where the
right answer can be worked out by hand.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import risk


def _history(closes, start="2025-03-03"):
    """Business-day closes starting on a date that is nowhere near a roll day."""
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"date": dates, "close": closes})


# --- compute_returns ---------------------------------------------------------

def test_returns_are_simple_percentage_changes():
    r = risk.compute_returns(_history([100.0, 110.0, 99.0]))
    assert np.isnan(r["daily_return"].iloc[0])
    assert r["daily_return"].iloc[1] == pytest.approx(0.10)
    assert r["daily_return"].iloc[2] == pytest.approx(-0.10)
    assert not r["is_roll_day"].any()


def test_roll_day_is_flagged():
    # CLZ25 expired Thu 20 Nov 2025, so Fri 21 Nov 2025 is the roll day.
    history = pd.DataFrame(
        {"date": pd.to_datetime(["2025-11-19", "2025-11-20", "2025-11-21", "2025-11-24"]),
         "close": [60.0, 61.0, 58.0, 58.5]}
    )
    r = risk.compute_returns(history)
    assert list(r["is_roll_day"]) == [False, False, True, False]


def test_usable_returns_drop_roll_days_and_the_first_day():
    history = pd.DataFrame(
        {"date": pd.to_datetime(["2025-11-19", "2025-11-20", "2025-11-21", "2025-11-24"]),
         "close": [60.0, 61.0, 58.0, 58.5]}
    )
    clean = risk.usable_returns(risk.compute_returns(history))
    assert len(clean) == 2  # 20 Nov and 24 Nov only
    assert list(clean.index.strftime("%Y-%m-%d")) == ["2025-11-20", "2025-11-24"]


def test_window_returns_keeps_only_the_recent_days():
    r = risk.compute_returns(_history([100.0] * 400))
    recent = risk.window_returns(r, days=30)
    assert recent["date"].min() > r["date"].max() - pd.Timedelta(days=30)
    assert len(recent) < len(r)


# --- volatility ------------------------------------------------------------------

def test_rolling_volatility_by_hand():
    # Returns +1% and -1%: sample std = sqrt((0.01^2 + 0.01^2) / (2 - 1)) = 0.0141421.
    # Annualised: x sqrt(252) = 0.224499.
    closes = [100.0, 101.0, 101.0 * 0.99]
    vol = risk.rolling_volatility(risk.compute_returns(_history(closes)), window=2)
    assert vol.dropna().iloc[-1] == pytest.approx(0.0141421 * np.sqrt(252), rel=1e-4)


def test_constant_prices_have_zero_volatility():
    vol = risk.rolling_volatility(risk.compute_returns(_history([100.0] * 30)), window=5)
    assert vol.dropna().iloc[-1] == pytest.approx(0.0)


# --- VaR ------------------------------------------------------------------------

def test_historical_var_by_hand():
    # 100 returns: -5.0%, -4.9%, ... , +4.9%. The 5th percentile (linear
    # interpolation) sits at position 0.05 * 99 = 4.95, between the 5th
    # value (-4.6%) and the 6th (-4.5%): -4.6% + 0.95 * 0.1% = -4.505%.
    returns = pd.Series(np.arange(-50, 50) / 1000)
    result = risk.historical_var(returns, 0.95, notional=100_000)
    assert result["var_pct"] == pytest.approx(0.04505)
    assert result["var_usd"] == pytest.approx(4505.0)
    assert result["observations"] == 100


def test_var_99_is_larger_than_var_95():
    returns = pd.Series(np.arange(-50, 50) / 1000)
    v95 = risk.historical_var(returns, 0.95, 1.0)["var_pct"]
    v99 = risk.historical_var(returns, 0.99, 1.0)["var_pct"]
    assert v99 > v95


def test_var_scales_with_position_size():
    returns = pd.Series(np.arange(-50, 50) / 1000)
    one = risk.historical_var(returns, 0.95, risk.position_notional(80.0, 1))["var_usd"]
    five = risk.historical_var(returns, 0.95, risk.position_notional(80.0, 5))["var_usd"]
    assert five == pytest.approx(5 * one)


def test_var_with_no_returns_is_none():
    result = risk.historical_var(pd.Series(dtype=float), 0.95, 1000.0)
    assert result == {"var_pct": None, "var_usd": None, "observations": 0}


def test_position_notional_uses_1000_barrels_per_contract():
    assert risk.position_notional(100.0, 3) == 300_000.0


# --- drawdown and worst day --------------------------------------------------------

def test_max_drawdown_by_hand():
    # 100 -> 120 -> 60 -> 90: the fall from the 120 peak to 60 is -50%.
    result = risk.max_drawdown(risk.compute_returns(_history([100.0, 120.0, 60.0, 90.0])))
    assert result["max_drawdown"] == pytest.approx(-0.5)
    assert result["peak_date"] == date(2025, 3, 4)
    assert result["trough_date"] == date(2025, 3, 5)


def test_a_rising_series_has_no_drawdown():
    result = risk.max_drawdown(risk.compute_returns(_history([100.0, 101.0, 102.0])))
    assert result["max_drawdown"] == pytest.approx(0.0)


def test_roll_day_gap_does_not_create_a_drawdown():
    # The 21 Nov 2025 roll day shows -30%, but that is a contract switch.
    history = pd.DataFrame(
        {"date": pd.to_datetime(["2025-11-19", "2025-11-20", "2025-11-21", "2025-11-24"]),
         "close": [100.0, 100.0, 70.0, 70.0]}
    )
    assert risk.max_drawdown(risk.compute_returns(history))["max_drawdown"] == pytest.approx(0.0)


def test_worst_day_ignores_roll_days():
    history = pd.DataFrame(
        {"date": pd.to_datetime(["2025-11-19", "2025-11-20", "2025-11-21", "2025-11-24"]),
         "close": [100.0, 98.0, 70.0, 69.3]}
    )
    clean = risk.usable_returns(risk.compute_returns(history))
    result = risk.worst_day(clean)
    assert result["return"] == pytest.approx(-0.02)  # 20 Nov; the -28.6% roll day is excluded
    assert result["date"] == date(2025, 11, 20)


# --- roll gain/cost -------------------------------------------------------------------

def test_backwardation_is_a_roll_gain_for_a_long_position():
    # Carry -25% (backwardation) on $100,000: rolling earns +$25,000 a year.
    assert risk.roll_gain_per_year(-25.0, 100_000) == pytest.approx(25_000)


def test_contango_is_a_roll_cost_for_a_long_position():
    assert risk.roll_gain_per_year(10.0, 100_000) == pytest.approx(-10_000)


# --- summarize_risk --------------------------------------------------------------------

def test_summarize_risk_puts_the_pieces_together():
    rng = np.random.default_rng(0)
    closes = 80 * np.cumprod(1 + rng.normal(0, 0.01, 800))
    history = _history(list(closes), start="2023-01-02")

    summary = risk.summarize_risk(history, lookback_years=2, price=80.0, n_contracts=2)

    assert summary["notional"] == 160_000.0
    assert summary["var"][0.99]["var_pct"] > summary["var"][0.95]["var_pct"] > 0
    # The 12-month window has fewer observations than the 2-year window.
    assert summary["var_recent"][0.95]["observations"] < summary["var"][0.95]["observations"]
    assert summary["var"][0.95]["var_usd"] == pytest.approx(summary["var"][0.95]["var_pct"] * 160_000)
    assert summary["max_drawdown"]["max_drawdown"] <= 0
    assert summary["worst_day"]["return"] < 0
    assert 0 < summary["volatility"] < 1
    assert summary["roll_days_excluded"] > 0


def test_summarize_risk_with_empty_history_does_not_crash():
    summary = risk.summarize_risk(pd.DataFrame(columns=["date", "close"]), 5, 80.0, 1)
    assert summary["var"][0.95]["var_pct"] is None
    assert summary["volatility"] is None
