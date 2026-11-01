"""
test_data_fetcher.py — Unit tests for data_fetcher.py with all network
calls mocked out, so the suite runs offline and never touches the Yahoo
Finance servers.

What is covered: candidate contract generation, parsing of per-contract
closes, graceful handling of missing / expired / failing contracts (a
price is left empty rather than invented), and the yfinance history
cleanup. Deciding which contracts are usable is tested in test_validation.py.
"""

from datetime import date

import pandas as pd

from crudecurve import data_fetcher


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


# --- fetch_candidate_quotes -----------------------------------------------

def test_fetch_candidate_quotes_returns_one_row_per_candidate(monkeypatch):
    today = date(2026, 11, 1)
    fake = {
        "CLX26.NYM": {"price": None, "as_of": None},  # expired: no data
        "CLZ26.NYM": {"price": 104.0, "as_of": date(2026, 10, 30)},
    }
    none = {"price": None, "as_of": None}
    monkeypatch.setattr(data_fetcher, "_fetch_contract_latest", lambda symbol: fake.get(symbol, none))

    quotes = data_fetcher.fetch_candidate_quotes(today)

    assert len(quotes) == len(data_fetcher._candidate_contracts(today))
    assert list(quotes.columns) == ["ticker", "delivery_month", "months_ahead", "price", "as_of"]
    assert list(quotes["ticker"][:2]) == ["CLX26", "CLZ26"]
    assert list(quotes["delivery_month"][:3]) == ["2026-11", "2026-12", "2027-01"]
    assert pd.isna(quotes["price"][0])  # missing data is kept as empty, not invented
    assert quotes["price"][1] == 104.0


def test_fetch_candidate_quotes_handles_network_errors(monkeypatch):
    monkeypatch.setattr(
        data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(exc=ConnectionError("offline"))
    )
    quotes = data_fetcher.fetch_candidate_quotes(date(2026, 11, 1))
    assert quotes["price"].isna().all()


# --- get_contract_history --------------------------------------------------

def test_contract_history_returns_dates_and_closes(monkeypatch):
    raw = _closes([70.0, 71.5], date(2026, 10, 30))
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(raw))
    result = data_fetcher.get_contract_history("CLZ26", "1y")
    assert list(result.columns) == ["trade_date", "close"]
    assert list(result["trade_date"]) == [date(2026, 10, 29), date(2026, 10, 30)]
    assert list(result["close"]) == [70.0, 71.5]


def test_contract_history_uses_yahoo_symbol(monkeypatch):
    seen = []

    def fake_ticker(symbol):
        seen.append(symbol)
        return _FakeTicker(pd.DataFrame())

    monkeypatch.setattr(data_fetcher.yf, "Ticker", fake_ticker)
    result = data_fetcher.get_contract_history("CLZ26", "1y")
    assert seen == ["CLZ26.NYM"]
    assert result.empty and list(result.columns) == ["trade_date", "close"]


def test_contract_history_network_error_returns_empty(monkeypatch):
    monkeypatch.setattr(
        data_fetcher.yf, "Ticker", lambda symbol: _FakeTicker(exc=ConnectionError("offline"))
    )
    assert data_fetcher.get_contract_history("CLZ26", "1y").empty


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
