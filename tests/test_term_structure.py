"""
test_term_structure.py — Unit tests for the slope classification and
annualized spread math in term_structure.py, using synthetic prices
with known, hand-computable answers.
"""


import pandas as pd
import pytest

from crudecurve.term_structure import classify_curve, compute_annualized_spread


def _make_curve(prices):
    return pd.DataFrame(
        {
            "month_index": list(range(len(prices))),
            "price": prices,
        }
    )


def test_classify_curve_contango():
    # Strictly rising prices -> Contango
    curve = _make_curve([70.0, 71.0, 72.0, 73.0])
    result = classify_curve(curve)
    assert result["label"] == "Contango"
    assert result["is_monotonic"] is True


def test_classify_curve_backwardation():
    # Strictly falling prices -> Backwardation
    curve = _make_curve([80.0, 78.0, 76.0, 74.0])
    result = classify_curve(curve)
    assert result["label"] == "Backwardation"
    assert result["is_monotonic"] is True


def test_classify_curve_kinked():
    # Dips then rises above the front price -> not monotonic, net contango
    curve = _make_curve([70.0, 68.0, 69.0, 75.0])
    result = classify_curve(curve)
    assert result["is_monotonic"] is False
    assert result["label"] == "Kinked (net Contango)"


def test_classify_curve_flat():
    # Front and back price nearly identical -> Flat
    curve = _make_curve([70.00, 70.00, 70.01, 70.02])
    result = classify_curve(curve)
    assert result["label"] == "Flat"


def test_compute_annualized_spread_contango():
    # Front $70, far month (6 months out) $73.50 -> 5% raw spread,
    # annualized over 6 months = 5% * (12/6) = 10%
    spread = compute_annualized_spread(front_price=70.0, far_price=73.5, months_between=6)
    assert spread == pytest.approx(10.0)


def test_compute_annualized_spread_backwardation():
    # Front $80, far month (3 months out) $78 -> -2.5% raw spread,
    # annualized over 3 months = -2.5% * (12/3) = -10%
    spread = compute_annualized_spread(front_price=80.0, far_price=78.0, months_between=3)
    assert spread == pytest.approx(-10.0)


def test_compute_annualized_spread_invalid_months():
    with pytest.raises(ValueError):
        compute_annualized_spread(front_price=70.0, far_price=72.0, months_between=0)
