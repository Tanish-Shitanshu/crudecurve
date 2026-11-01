"""
test_storage.py — SQLite storage, tested on an in-memory database so the
real data/crudecurve.db file is never touched.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import storage
from validation import RuleResult


def _conn():
    return storage.get_connection(":memory:")


def _curve(prices, as_of=date(2026, 10, 30)):
    return pd.DataFrame(
        {
            "ticker": [f"C{i}" for i in range(len(prices))],
            "delivery_month": [f"2027-{i + 1:02d}" for i in range(len(prices))],
            "month_index": list(range(len(prices))),
            "price": prices,
            "as_of": as_of,
        }
    )


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_tables_are_created():
    conn = _conn()
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"curve_snapshots", "contract_prices", "data_quality_log"} <= names


def test_save_snapshot_is_idempotent():
    conn = _conn()
    curve = _curve([100.0, 99.0, 98.0])
    storage.save_snapshot(conn, curve, fetched_at="2026-11-01T10:00:00")
    storage.save_snapshot(conn, curve, fetched_at="2026-11-01T10:05:00")
    assert _count(conn, "curve_snapshots") == 3  # no duplicates


def test_save_snapshot_updates_a_changed_price_for_the_same_date():
    conn = _conn()
    storage.save_snapshot(conn, _curve([100.0, 99.0]), fetched_at="2026-11-01T10:00:00")
    storage.save_snapshot(conn, _curve([101.0, 99.0]), fetched_at="2026-11-01T10:05:00")
    price = conn.execute("SELECT price FROM curve_snapshots WHERE contract = 'C0'").fetchone()[0]
    assert price == 101.0
    assert _count(conn, "curve_snapshots") == 2


def test_load_latest_snapshot_returns_the_most_recent_run():
    conn = _conn()
    storage.save_snapshot(conn, _curve([100.0, 99.0], as_of=date(2026, 10, 29)), "2026-10-29T20:00:00")
    storage.save_snapshot(conn, _curve([105.0, 104.0, 103.0], as_of=date(2026, 10, 30)), "2026-10-30T20:00:00")

    snapshot = storage.load_latest_snapshot(conn)

    assert list(snapshot["price"]) == [105.0, 104.0, 103.0]
    assert list(snapshot["month_index"]) == [0, 1, 2]
    assert snapshot["as_of"].iloc[0] == date(2026, 10, 30)
    assert not snapshot["is_stale"].any()
    assert {"ticker", "delivery_month", "month_index", "price", "as_of"} <= set(snapshot.columns)


def test_load_latest_snapshot_on_empty_database_is_empty():
    assert storage.load_latest_snapshot(_conn()).empty


def test_contract_prices_are_saved_idempotently_and_latest_date_found():
    conn = _conn()
    history = pd.DataFrame({"trade_date": [date(2026, 10, 29), date(2026, 10, 30)], "close": [70.0, 71.0]})
    assert storage.latest_trade_date(conn, "CLZ26") is None

    storage.save_contract_prices(conn, "CLZ26", history)
    storage.save_contract_prices(conn, "CLZ26", history)

    assert _count(conn, "contract_prices") == 2
    assert storage.latest_trade_date(conn, "CLZ26") == date(2026, 10, 30)
    assert storage.latest_trade_date(conn, "CLF27") is None


def test_quality_results_are_logged():
    conn = _conn()
    results = [
        RuleResult("CLX26", "not_expired", "skipped", "expired on 2026-10-20"),
        RuleResult("CURVE", "min_live_contracts", "pass", "6 live"),
    ]
    storage.log_quality_results(conn, "2026-11-01T10:00:00", results)
    rows = conn.execute("SELECT contract, rule, status FROM data_quality_log ORDER BY contract").fetchall()
    assert rows == [("CLX26", "not_expired", "skipped"), ("CURVE", "min_live_contracts", "pass")]


def test_list_price_contracts_is_ordered_by_delivery_month_not_alphabetically():
    conn = _conn()
    # CLZ26 (2026-12) is delivered before CLF27 (2027-01), but "CLF27" sorts first alphabetically.
    curve = pd.DataFrame(
        {"ticker": ["CLF27", "CLZ26"], "delivery_month": ["2027-01", "2026-12"],
         "month_index": [1, 0], "price": [1.0, 2.0], "as_of": date(2026, 10, 30)}
    )
    storage.save_snapshot(conn, curve, "2026-11-01T10:00:00")
    history = pd.DataFrame({"trade_date": [date(2026, 10, 30)], "close": [1.0]})
    storage.save_contract_prices(conn, "CLF27", history)
    storage.save_contract_prices(conn, "CLZ26", history)
    assert storage.list_price_contracts(conn) == ["CLZ26", "CLF27"]
