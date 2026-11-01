"""
test_data_fetcher.py — Unit tests for data_fetcher.py with all network
calls mocked out, so the suite runs offline and never touches the Yahoo
Finance servers.

What is covered: candidate contract generation, parsing of per-contract
closes, graceful handling of missing / expired / failing contracts (a
price is dropped rather than invented), month_index spacing, and the
yfinance history cleanup.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data_fetcher


class _FakeTicker:
    """Stands in for yf.Ticker; .history() returns a canned frame or raises."""

    def __init__(self, history=None, exc=None):
        self._history = history
        self._exc = exc

    def history(self, period):
        if self._exc is not None:
            raise self._exc
        return self._history


def _closes(values, last_date):
    """Build a yfinance-like history frame ending on last_date."""
    index = pd.date_range(end=last_date, periods=len(values), freq="D", tz="America/New_York")
    return pd.DataFrame({"Close": values}, index=index)


# --- _candidate_contracts -------------------------------------------------

def test_candidates_start_at_current_month_and_use_month_codes():
    cands = data_fetcher._candidate_contracts(date(2026, 11, 1))
    assert [c[0] for c in cands[:4]] == [
        "CLX26.NYM", "CLZ26.NYM", "CLF27.NYM", "CLG27.NYM"
    ]
    assert [c[1] for c in cands[:2]] == ["CLX26", "CLZ26"]
    assert [c[2] for c in cands] == list(range(len(cands)))


def test_candidates_roll_over_the_year_boundary():
    cands = data_fetcher._candidate_contracts(date(2026, 12, 15))
    assert [c[0] for c in cands[:3]] == ["CLZ26.NYM", "CLF27.NYM", "CLG27.NYM"]


# --- _fetch_contract_latest -----------------------------------------------

def test_fetch_contract_parses_latest_close_and_date(monkeypatch):
    raw = _closes([70.0, 71.5], date(2026, 10, 30))
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(raw))
    result = data_fetcher._fetch_contract_latest("CLZ26.NYM")
    assert result == {"price": 71.5, "as_of": date(2026, 10, 30)}


def test_fetch_contract_skips_trailing_nan_close(monkeypatch):
    raw = _closes([70.0, float("nan")], date(2026, 10, 30))
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(raw))
    result = data_fetcher._fetch_contract_latest("CLZ26.NYM")
    assert result["price"] == 70.0


def test_fetch_contract_empty_history_returns_none(monkeypatch):
    monkeypatch.setattr(
        data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(pd.DataFrame())
    )
    assert data_fetcher._fetch_contract_latest("CLX26.NYM") == {"price": None, "as_of": None}


def test_fetch_contract_network_error_returns_none(monkeypatch):
    monkeypatch.setattr(
        data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(exc=ConnectionError("offline"))
    )
    assert data_fetcher._fetch_contract_latest("CLZ26.NYM") == {"price": None, "as_of": None}


# --- get_current_curve ----------------------------------------------------

def _patch_contracts(monkeypatch, by_months_ahead):
    """
    Patch _fetch_contract_latest so each candidate contract's result is
    looked up by its months-ahead position; unlisted ones return no data.
    """
    today = date.today()
    symbol_to_ahead = {c[0]: c[2] for c in data_fetcher._candidate_contracts(today)}
    none = {"price": None, "as_of": None}
    monkeypatch.setattr(
        data_fetcher,
        "_fetch_contract_latest",
        lambda symbol: by_months_ahead.get(symbol_to_ahead[symbol], none),
    )


def test_get_current_curve_keeps_first_six_live_contracts(monkeypatch):
    today = date.today()
    _patch_contracts(
        monkeypatch,
        {i: {"price": 70.0 + i, "as_of": today} for i in range(9)},
    )
    curve = data_fetcher.get_current_curve()

    assert len(curve) == 6
    assert list(curve["month_index"]) == [0, 1, 2, 3, 4, 5]
    assert list(curve["price"]) == [70.0, 71.0, 72.0, 73.0, 74.0, 75.0]
    assert not curve["is_stale"].any()
    assert list(curve.columns) == ["ticker", "month_index", "price", "as_of", "is_stale"]


def test_get_current_curve_drops_expired_and_missing_contracts(monkeypatch):
    today = date.today()
    fresh = lambda price: {"price": price, "as_of": today}
    _patch_contracts(
        monkeypatch,
        {
            # months_ahead 0: no data (expired) -> dropped
            1: {"price": 99.0, "as_of": today - timedelta(days=30)},  # expired/old -> dropped
            2: fresh(70.0),
            # 3: no data -> dropped, leaving a gap in delivery months
            4: fresh(72.0),
            5: fresh(73.0),
        },
    )
    curve = data_fetcher.get_current_curve()

    assert list(curve["price"]) == [70.0, 72.0, 73.0]
    assert 99.0 not in list(curve["price"])
    assert not curve["is_stale"].any()


def test_get_current_curve_month_index_is_relative_to_front_and_keeps_gaps(monkeypatch):
    today = date.today()
    fresh = lambda price: {"price": price, "as_of": today}
    _patch_contracts(monkeypatch, {1: fresh(70.0), 2: fresh(71.0), 4: fresh(73.0)})
    curve = data_fetcher.get_current_curve()

    # Front live contract is index 0; the missing 4th delivery month leaves a gap.
    assert list(curve["month_index"]) == [0, 1, 3]


def test_get_current_curve_with_no_live_contracts_returns_empty_frame(monkeypatch):
    _patch_contracts(monkeypatch, {})
    assert data_fetcher.get_current_curve().empty


def test_get_current_curve_handles_network_errors(monkeypatch):
    monkeypatch.setattr(
        data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(exc=ConnectionError("offline"))
    )
    assert data_fetcher.get_current_curve().empty


# --- get_front_month_history ---------------------------------------------

def test_front_month_history_empty_returns_expected_columns(monkeypatch):
    monkeypatch.setattr(
        data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(pd.DataFrame())
    )
    result = data_fetcher.get_front_month_history()
    assert result.empty
    assert list(result.columns) == ["date", "close"]


def test_front_month_history_removes_timezone_and_renames_columns(monkeypatch):
    index = pd.DatetimeIndex(
        ["2026-09-01", "2026-09-02"], tz="America/New_York", name="Date"
    )
    raw = pd.DataFrame(
        {"Open": [1.0, 2.0], "Close": [70.5, 71.5], "Volume": [10, 20]}, index=index
    )
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(raw))

    result = data_fetcher.get_front_month_history()

    assert list(result.columns) == ["date", "close"]
    assert result["date"].dt.tz is None
    assert list(result["close"]) == [70.5, 71.5]
