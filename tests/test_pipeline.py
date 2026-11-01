"""
test_pipeline.py — fetch -> validate -> save, and the saved-snapshot
fallback. The network is mocked and the database is in memory.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline
import storage

TODAY = date(2026, 11, 1)
MONTHS = ["2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05"]


def _live_quotes():
    rows = [
        (f"C{i}", MONTHS[i], i + 1, 100.0 - i, TODAY - timedelta(days=2))
        for i in range(6)
    ]
    return pd.DataFrame(rows, columns=["ticker", "delivery_month", "months_ahead", "price", "as_of"])


def _dead_quotes():
    """What a Yahoo outage looks like: every contract has no data."""
    rows = [(f"C{i}", MONTHS[i], i + 1, None, None) for i in range(6)]
    return pd.DataFrame(rows, columns=["ticker", "delivery_month", "months_ahead", "price", "as_of"])


def _history(*args):
    return pd.DataFrame({"trade_date": [date(2026, 10, 29), date(2026, 10, 30)], "close": [70.0, 71.0]})


def _patch(monkeypatch, quotes):
    monkeypatch.setattr(pipeline.data_fetcher, "fetch_candidate_quotes", lambda today: quotes)
    monkeypatch.setattr(pipeline.data_fetcher, "get_contract_history", _history)


def test_live_path_saves_snapshot_history_and_quality_log(monkeypatch):
    conn = storage.get_connection(":memory:")
    _patch(monkeypatch, _live_quotes())

    result = pipeline.load_curve(conn, TODAY)

    assert result.source == "live"
    assert result.message == ""
    assert len(result.curve) == 6
    assert conn.execute("SELECT COUNT(*) FROM curve_snapshots").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM contract_prices").fetchone()[0] == 12  # 6 contracts x 2 bars
    assert conn.execute("SELECT COUNT(*) FROM data_quality_log").fetchone()[0] > 0


def test_running_twice_does_not_duplicate_rows(monkeypatch):
    conn = storage.get_connection(":memory:")
    _patch(monkeypatch, _live_quotes())
    pipeline.load_curve(conn, TODAY)
    pipeline.load_curve(conn, TODAY)
    assert conn.execute("SELECT COUNT(*) FROM curve_snapshots").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM contract_prices").fetchone()[0] == 12


def test_falls_back_to_saved_snapshot_when_live_data_fails(monkeypatch):
    conn = storage.get_connection(":memory:")
    _patch(monkeypatch, _live_quotes())
    pipeline.load_curve(conn, TODAY)  # a good run first, so a snapshot exists

    _patch(monkeypatch, _dead_quotes())
    result = pipeline.load_curve(conn, TODAY + timedelta(days=3))

    assert result.source == "snapshot"
    assert result.message == f"Showing saved snapshot from {TODAY - timedelta(days=2)} (live data unavailable)."
    assert list(result.curve["price"]) == [100.0, 99.0, 98.0, 97.0, 96.0, 95.0]


def test_failed_live_run_does_not_overwrite_the_saved_snapshot(monkeypatch):
    conn = storage.get_connection(":memory:")
    _patch(monkeypatch, _live_quotes())
    pipeline.load_curve(conn, TODAY)
    _patch(monkeypatch, _dead_quotes())
    pipeline.load_curve(conn, TODAY)
    assert conn.execute("SELECT COUNT(*) FROM curve_snapshots").fetchone()[0] == 6


def test_empty_database_and_no_live_data_gives_a_clean_error(monkeypatch):
    conn = storage.get_connection(":memory:")
    _patch(monkeypatch, _dead_quotes())

    result = pipeline.load_curve(conn, TODAY)

    assert result.source == "none"
    assert result.curve.empty
    assert "no saved snapshot" in result.message


def test_history_period_backfills_first_then_tops_up():
    assert pipeline._history_period(None, TODAY) == "1y"
    assert pipeline._history_period(TODAY - timedelta(days=3), TODAY) == "1mo"
    assert pipeline._history_period(TODAY - timedelta(days=60), TODAY) == "1y"
