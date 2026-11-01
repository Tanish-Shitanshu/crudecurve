"""
test_data_fetcher.py — Unit tests for data_fetcher.py with all network
calls mocked out, so the suite runs offline and never touches the EIA or
Yahoo Finance servers (or your real API key).

What is covered: parsing of EIA responses, graceful handling of missing /
malformed data (a price is dropped rather than invented), stale-data
flagging, and the yfinance history cleanup.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data_fetcher


class _FakeResponse:
    def __init__(self, payload, raise_error=False):
        self._payload = payload
        self._raise_error = raise_error

    def raise_for_status(self):
        if self._raise_error:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._payload


def _patch_requests(monkeypatch, response=None, exc=None):
    def fake_get(*args, **kwargs):
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(data_fetcher.requests, "get", fake_get)


# --- _fetch_eia_series_latest --------------------------------------------

def test_fetch_series_parses_price_and_date(monkeypatch):
    payload = {"response": {"data": [{"period": "2026-09-01", "value": "71.25"}]}}
    _patch_requests(monkeypatch, _FakeResponse(payload))
    result = data_fetcher._fetch_eia_series_latest("RCLC1", "key")
    assert result == {"price": 71.25, "as_of": date(2026, 9, 1)}


def test_fetch_series_no_rows_returns_none(monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse({"response": {"data": []}}))
    result = data_fetcher._fetch_eia_series_latest("RCLC1", "key")
    assert result == {"price": None, "as_of": None}


def test_fetch_series_malformed_row_returns_none(monkeypatch):
    payload = {"response": {"data": [{"period": "not-a-date", "value": "abc"}]}}
    _patch_requests(monkeypatch, _FakeResponse(payload))
    result = data_fetcher._fetch_eia_series_latest("RCLC1", "key")
    assert result == {"price": None, "as_of": None}


def test_fetch_series_network_error_returns_none(monkeypatch):
    _patch_requests(monkeypatch, exc=ConnectionError("offline"))
    result = data_fetcher._fetch_eia_series_latest("RCLC1", "key")
    assert result == {"price": None, "as_of": None}


def test_fetch_series_http_error_returns_none(monkeypatch):
    _patch_requests(monkeypatch, _FakeResponse({}, raise_error=True))
    result = data_fetcher._fetch_eia_series_latest("RCLC1", "key")
    assert result == {"price": None, "as_of": None}


# --- _get_eia_api_key -----------------------------------------------------

def test_api_key_comes_from_environment(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "my-test-key")
    assert data_fetcher._get_eia_api_key() == "my-test-key"


def test_api_key_falls_back_to_demo_key(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    assert data_fetcher._get_eia_api_key() == "DEMO_KEY"


# --- get_current_curve ----------------------------------------------------

def test_get_current_curve_drops_missing_and_flags_stale(monkeypatch):
    today = date.today()
    fake = {
        "RCLC1": {"price": 70.0, "as_of": today},
        "RCLC2": {"price": 71.0, "as_of": today - timedelta(days=30)},  # stale
        "RCLC3": {"price": None, "as_of": None},  # no data -> dropped
        "RCLC4": {"price": 73.0, "as_of": today},
    }
    monkeypatch.setattr(
        data_fetcher, "_fetch_eia_series_latest", lambda series_id, key: fake[series_id]
    )

    curve = data_fetcher.get_current_curve()

    assert list(curve["ticker"]) == ["RCLC1", "RCLC2", "RCLC4"]
    # month_index keeps the original contract position (0, 1, 3), not 0, 1, 2.
    assert list(curve["month_index"]) == [0, 1, 3]
    assert list(curve["is_stale"]) == [False, True, False]
    assert list(curve["price"]) == [70.0, 71.0, 73.0]


def test_get_current_curve_with_no_data_returns_empty_frame(monkeypatch):
    monkeypatch.setattr(
        data_fetcher,
        "_fetch_eia_series_latest",
        lambda series_id, key: {"price": None, "as_of": None},
    )
    curve = data_fetcher.get_current_curve()
    assert curve.empty


# --- get_front_month_history ---------------------------------------------

class _FakeTicker:
    def __init__(self, history):
        self._history = history

    def history(self, period):
        return self._history


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
