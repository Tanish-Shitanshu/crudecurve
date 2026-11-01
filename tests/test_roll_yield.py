"""
test_roll_yield.py — Unit tests for the roll-yield simulation in
roll_yield.py, using small synthetic price series with hand-computable
answers (no network access needed).

The simulation treats the last ROLL_DAYS_BEFORE_MONTH_END (5) trading
days of each calendar month as the "roll window": price moves inside
that window are summed into the cumulative roll yield, while the total
move since the first day is tracked separately as cumulative spot change.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROLL_DAYS_BEFORE_MONTH_END
from roll_yield import simulate_roll_yield, summarize_roll_yield

EXPECTED_COLUMNS = ["date", "cumulative_roll_yield", "cumulative_spot_change"]


def _history(prices, start="2026-01-05"):
    """Build a daily (business-day) front-month history from a price list."""
    dates = pd.bdate_range(start=start, periods=len(prices))
    return pd.DataFrame({"date": dates, "close": prices})


def test_roll_window_constant_matches_assumption():
    # The hand-computed tests below assume a 5-day roll window.
    assert ROLL_DAYS_BEFORE_MONTH_END == 5


def test_empty_history_returns_empty_frame_with_expected_columns():
    empty = pd.DataFrame(columns=["date", "close"])
    result = simulate_roll_yield(empty)
    assert result.empty
    assert list(result.columns) == EXPECTED_COLUMNS


def test_none_history_returns_empty_frame_with_expected_columns():
    result = simulate_roll_yield(None)
    assert result.empty
    assert list(result.columns) == EXPECTED_COLUMNS


def test_flat_prices_give_zero_roll_yield_and_zero_spot_change():
    result = simulate_roll_yield(_history([80.0] * 10))
    assert (result["cumulative_roll_yield"] == 0).all()
    assert (result["cumulative_spot_change"] == 0).all()


def test_roll_window_moves_are_separated_from_spot_drift():
    # 10 trading days, all in January 2026. The first 5 days drift up by
    # $1/day (normal holding period). Days 6-10 are the roll window:
    # +6 on the jump day, then +1 on each of the next four days.
    prices = [100, 101, 102, 103, 104, 110, 111, 112, 113, 114]
    result = simulate_roll_yield(_history(prices))

    # Roll effect = 6 + 1 + 1 + 1 + 1 = 10; total move = 114 - 100 = 14.
    assert result["cumulative_roll_yield"].iloc[-1] == pytest.approx(10.0)
    assert result["cumulative_spot_change"].iloc[-1] == pytest.approx(14.0)

    # Nothing is attributed to rolling before the roll window starts.
    assert (result["cumulative_roll_yield"].iloc[:5] == 0).all()


def test_falling_prices_in_roll_window_give_negative_roll_yield():
    # Mirror image of the test above: a drop inside the roll window is a
    # negative roll effect (the "contango drag" shape).
    prices = [100, 100, 100, 100, 100, 95, 94, 93, 92, 91]
    result = simulate_roll_yield(_history(prices))
    assert result["cumulative_roll_yield"].iloc[-1] == pytest.approx(-9.0)
    assert result["cumulative_spot_change"].iloc[-1] == pytest.approx(-9.0)


def test_spot_change_is_indexed_to_zero_at_start():
    result = simulate_roll_yield(_history([75.0, 76.5, 74.0, 77.0, 78.0, 79.0]))
    assert result["cumulative_spot_change"].iloc[0] == 0
    assert result["cumulative_spot_change"].iloc[-1] == pytest.approx(79.0 - 75.0)


def test_output_has_one_row_per_input_row_and_expected_columns():
    prices = [70 + (i % 7) for i in range(60)]  # spans several months
    result = simulate_roll_yield(_history(prices, start="2026-01-05"))
    assert len(result) == len(prices)
    assert list(result.columns) == EXPECTED_COLUMNS


def test_unsorted_input_is_sorted_by_date_before_simulating():
    prices = [100, 101, 102, 103, 104, 110, 111, 112, 113, 114]
    ordered = _history(prices)
    shuffled = ordered.sample(frac=1.0, random_state=0)
    result = simulate_roll_yield(shuffled)
    assert result["date"].is_monotonic_increasing
    assert result["cumulative_roll_yield"].iloc[-1] == pytest.approx(10.0)


def test_input_dataframe_is_not_modified():
    history = _history([100, 101, 102, 103, 104, 110, 111, 112, 113, 114])
    before = history.copy()
    simulate_roll_yield(history)
    pd.testing.assert_frame_equal(history, before)


def test_summarize_returns_final_cumulative_roll_yield_as_float():
    prices = [100, 101, 102, 103, 104, 110, 111, 112, 113, 114]
    summary = summarize_roll_yield(simulate_roll_yield(_history(prices)))
    assert isinstance(summary, float)
    assert summary == pytest.approx(10.0)


def test_summarize_handles_empty_and_none():
    assert summarize_roll_yield(None) == 0.0
    assert summarize_roll_yield(pd.DataFrame(columns=EXPECTED_COLUMNS)) == 0.0
