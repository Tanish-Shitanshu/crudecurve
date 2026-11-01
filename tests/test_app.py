"""
test_app.py — Smoke tests that run the whole Streamlit app in-process with
Streamlit's AppTest. The network is replaced by synthetic data and the
database is a temporary file, so nothing real is touched.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import data_fetcher
import storage

APP = str(Path(__file__).resolve().parent.parent / "app.py")
TODAY = date.today()
MONTHS = ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06", "2027-07", "2027-08"]


def _quotes(prices):
    """Candidate quotes for 8 live contracts; a None price means no data."""
    rows = [
        (f"CX{i}", MONTHS[i], i + 1, price, None if price is None else TODAY - timedelta(days=1))
        for i, price in enumerate(prices)
    ]
    return pd.DataFrame(rows, columns=["ticker", "delivery_month", "months_ahead", "price", "as_of"])


def _contract_history(ticker, period):
    dates = pd.bdate_range(end=TODAY, periods=60)
    return pd.DataFrame({"trade_date": [d.date() for d in dates], "close": [90.0 + i * 0.1 for i in range(60)]})


def _front_history(years=2):
    dates = pd.bdate_range(end=TODAY, periods=1000)
    return pd.DataFrame({"date": dates, "close": [70.0 + (i % 40) * 0.3 for i in range(1000)]})


@pytest.fixture
def offline_app(monkeypatch, tmp_path):
    """Patch the network and point the database at a temp file; return a factory for the app."""
    real_connection = storage.get_connection
    monkeypatch.setattr(storage, "get_connection", lambda path=None: real_connection(str(tmp_path / "test.db")))
    monkeypatch.setattr(data_fetcher, "get_contract_history", _contract_history)
    monkeypatch.setattr(data_fetcher, "get_front_month_history", _front_history)

    def make(prices):
        monkeypatch.setattr(data_fetcher, "fetch_candidate_quotes", lambda today: _quotes(prices))
        st.cache_data.clear()  # the app caches market data between runs
        return AppTest.from_file(APP, default_timeout=60)

    return make


def test_app_runs_and_shows_the_tabs_and_kpis(offline_app):
    at = offline_app([100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0]).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == [
        "Overview", "Curve", "Roll Yield", "Risk", "SQL Analysis", "Data Quality", "Methodology"
    ]
    labels = [m.label for m in at.metric]
    assert "Front price" in labels and "1-day VaR (95%)" in labels
    assert not at.warning  # live data: no banner


def test_app_shows_a_banner_when_using_a_saved_snapshot(offline_app):
    live = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0]
    offline_app(live).run()  # a good run saves a snapshot
    at = offline_app([None] * 8).run()  # now Yahoo returns nothing
    assert not at.exception
    banners = [w.value for w in at.warning]
    assert any("Showing saved snapshot" in text and "live data unavailable" in text for text in banners)


def test_app_shows_a_clean_error_when_offline_with_nothing_saved(offline_app):
    at = offline_app([None] * 8).run()
    assert not at.exception  # no raw traceback
    assert any("no saved snapshot" in e.value for e in at.error)


def test_sidebar_controls_exist(offline_app):
    at = offline_app([100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0]).run()
    assert at.sidebar.radio[0].label == "VaR lookback window"
    assert at.sidebar.radio[0].value == 5  # default 5 years
    assert at.sidebar.number_input[0].label == "Position size (contracts)"
    assert [b.label for b in at.sidebar.button] == ["Refresh data"]


def test_changing_position_size_scales_the_roll_gain(offline_app):
    at = offline_app([100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0]).run()
    one = next(m.value for m in at.metric if m.label == "Annual roll gain / (cost)")
    at.sidebar.number_input[0].set_value(2).run()
    two = next(m.value for m in at.metric if m.label == "Annual roll gain / (cost)")
    to_number = lambda text: float(text.replace("$", "").replace(",", "").replace("+", ""))
    assert to_number(two) == pytest.approx(2 * to_number(one), rel=0.01)


def test_dollar_signs_in_the_summary_are_escaped_so_they_do_not_become_latex(offline_app):
    at = offline_app([100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0]).run()
    summary = next(md.value for md in at.markdown if "futures curve is in" in md.value)
    assert "\\$" in summary
    assert "$" not in summary.replace("\\$", "")  # every $ is escaped


def test_no_info_error_or_warning_banners_on_live_data(offline_app):
    at = offline_app([100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0]).run()
    assert not at.error and not at.warning and not at.info
