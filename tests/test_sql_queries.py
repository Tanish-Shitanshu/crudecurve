"""
test_sql_queries.py — Each preset query run on a small in-memory fixture
where the answers can be worked out by hand.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sql_queries
import storage
from validation import RuleResult

# Spread (back - front) on 25 consecutive days. Front is flat at 100, so the
# spread is just the back price minus 100.
SPREADS = [1, 2, 3, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 25, 26]
START = date(2026, 1, 1)


def _day(i):
    return START + timedelta(days=i)


@pytest.fixture
def conn():
    conn = storage.get_connection(":memory:")
    front = pd.DataFrame({"trade_date": [_day(i) for i in range(25)], "close": [100.0] * 25})
    back = pd.DataFrame({"trade_date": [_day(i) for i in range(25)], "close": [100.0 + s for s in SPREADS]})
    storage.save_contract_prices(conn, "CLZ26", front)
    storage.save_contract_prices(conn, "CLK27", back)
    return conn


def test_daily_change_uses_the_previous_day(conn):
    df = sql_queries.run_query(conn, "spread_daily_change", front="CLZ26", back="CLK27")
    assert len(df) == 25
    assert pd.isna(df["daily_change"].iloc[0])  # no previous day
    assert df["daily_change"].iloc[1] == 1.0  # 2 - 1
    assert df["daily_change"].iloc[3] == 10.0  # 13 - 3
    assert df["daily_change"].iloc[23] == -7.0  # 25 - 32


def test_moving_average_starts_after_20_days(conn):
    df = sql_queries.run_query(conn, "spread_moving_average", front="CLZ26", back="CLK27")
    assert df["moving_avg_20d"].iloc[:19].isna().all()
    # Day 20 averages the first 20 spreads: (1+2+3+13+14+...+30) / 20.
    expected = sum(SPREADS[:20]) / 20
    assert df["moving_avg_20d"].iloc[19] == pytest.approx(round(expected, 2))
    # Day 21 drops the first spread (1) and adds the 21st (31).
    assert df["moving_avg_20d"].iloc[20] == pytest.approx(round(sum(SPREADS[1:21]) / 20, 2))


def test_top_moves_are_sorted_by_absolute_size(conn):
    df = sql_queries.run_query(conn, "top_spread_moves", front="CLZ26", back="CLK27", top_n=3)
    assert list(df["daily_change"]) == [10.0, -7.0, 1.0]
    assert df["trade_date"].iloc[0] == str(_day(3))
    assert df["trade_date"].iloc[1] == str(_day(23))
    assert len(df) == 3


def test_top_moves_respects_the_limit(conn):
    df = sql_queries.run_query(conn, "top_spread_moves", front="CLZ26", back="CLK27", top_n=5)
    assert len(df) == 5


def test_spread_only_uses_dates_both_contracts_have():
    conn = storage.get_connection(":memory:")
    front = pd.DataFrame({"trade_date": [_day(0), _day(1), _day(2)], "close": [100.0, 100.0, 100.0]})
    back = pd.DataFrame({"trade_date": [_day(0), _day(2)], "close": [101.0, 103.0]})  # day 1 missing
    storage.save_contract_prices(conn, "CLZ26", front)
    storage.save_contract_prices(conn, "CLK27", back)
    df = sql_queries.run_query(conn, "spread_daily_change", front="CLZ26", back="CLK27")
    assert list(df["spread"]) == [1.0, 3.0]
    assert list(df["daily_change"].iloc[1:]) == [2.0]


def test_quality_failures_grouped_by_rule_ignore_pass_and_skipped():
    conn = storage.get_connection(":memory:")
    storage.log_quality_results(conn, "2026-11-01T10:00:00", [
        RuleResult("C1", "price_valid", "fail", "x"),
        RuleResult("C2", "price_valid", "fail", "x"),
        RuleResult("C3", "outlier_check", "flag", "x"),
        RuleResult("C4", "price_valid", "pass", "x"),
        RuleResult("CLX26", "not_expired", "skipped", "expired"),
    ])
    storage.log_quality_results(conn, "2026-11-02T10:00:00", [RuleResult("C1", "price_valid", "fail", "x")])

    df = sql_queries.run_query(conn, "quality_failures_by_rule")

    assert list(zip(df["rule"], df["status"], df["occurrences"])) == [
        ("price_valid", "fail", 3),
        ("outlier_check", "flag", 1),
    ]
    assert df["last_seen"].iloc[0] == "2026-11-02T10:00:00"


def test_queries_on_an_empty_database_return_empty_frames():
    conn = storage.get_connection(":memory:")
    assert sql_queries.run_query(conn, "spread_daily_change", front="A", back="B").empty
    assert sql_queries.run_query(conn, "quality_failures_by_rule").empty


def test_unknown_query_and_wrong_parameters_are_rejected(conn):
    with pytest.raises(KeyError):
        sql_queries.run_query(conn, "drop_everything")
    with pytest.raises(ValueError):
        sql_queries.run_query(conn, "spread_daily_change", front="CLZ26")  # missing "back"
    with pytest.raises(ValueError):
        sql_queries.run_query(conn, "quality_failures_by_rule", front="CLZ26")  # unexpected parameter


def test_parameters_are_bound_not_pasted_into_the_sql(conn):
    # A hostile "contract name" is just a value that matches no rows.
    df = sql_queries.run_query(conn, "spread_daily_change", front="x' OR '1'='1", back="CLK27")
    assert df.empty


def test_connection_is_writable_again_after_a_query(conn):
    sql_queries.run_query(conn, "spread_daily_change", front="CLZ26", back="CLK27")
    storage.log_quality_results(conn, "2026-11-01T10:00:00", [RuleResult("C", "r", "pass", "x")])  # would raise if still read-only


def test_every_preset_query_is_read_only_sql():
    for key, query in sql_queries.QUERIES.items():
        first_word = query.sql.strip().split()[0].upper()
        assert first_word in ("WITH", "SELECT"), key
        for banned in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE "):
            assert banned not in query.sql.upper(), (key, banned)
