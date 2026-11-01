"""
sql_queries.py — A small set of read-only SQL analyses over the SQLite
tables, written as plain SQL so the dashboard can show the query text next
to its result.

There is deliberately no free-text SQL box: every query below is fixed in
this file, and the only things that change are bound parameters (the
contract names and a row limit), which SQLite substitutes safely. As
defence in depth, run_query() also switches the connection to
`PRAGMA query_only`, so a query cannot modify the database.

A "spread" here is back contract close minus front contract close on the
same trade date. Positive = the back contract is dearer (contango).
"""

import sqlite3
from dataclasses import dataclass

import pandas as pd

# The spread between two contracts on every date where both have a close.
_SPREAD_CTE = """
WITH spread AS (
    SELECT front.trade_date,
           back.close - front.close AS spread
    FROM contract_prices AS front
    JOIN contract_prices AS back ON back.trade_date = front.trade_date
    WHERE front.contract = :front AND back.contract = :back
)
"""


@dataclass
class PresetQuery:
    title: str
    description: str
    sql: str
    params: tuple[str, ...]  # names of the bound parameters the query needs


QUERIES = {
    "spread_daily_change": PresetQuery(
        title="Daily change in a calendar spread",
        description=(
            "LAG() looks at the previous row, so spread minus LAG(spread) is "
            "the day-over-day change. The first day has no previous row (NULL)."
        ),
        sql=_SPREAD_CTE + """
SELECT trade_date,
       ROUND(spread, 2) AS spread,
       ROUND(spread - LAG(spread) OVER (ORDER BY trade_date), 2) AS daily_change
FROM spread
ORDER BY trade_date
""",
        params=("front", "back"),
    ),
    "spread_moving_average": PresetQuery(
        title="20-day moving average of a calendar spread",
        description=(
            "AVG() OVER a window of the current row and the 19 before it. "
            "The average is only shown once a full 20-day window exists."
        ),
        sql=_SPREAD_CTE + """
SELECT trade_date,
       ROUND(spread, 2) AS spread,
       CASE WHEN COUNT(*) OVER w = 20 THEN ROUND(AVG(spread) OVER w, 2) END AS moving_avg_20d
FROM spread
WINDOW w AS (ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
ORDER BY trade_date
""",
        params=("front", "back"),
    ),
    "top_spread_moves": PresetQuery(
        title="Largest daily spread moves",
        description=(
            "The days with the biggest absolute day-over-day change in the "
            "spread (LAG() again, then sort by the size of the change)."
        ),
        sql=_SPREAD_CTE + """
, changes AS (
    SELECT trade_date,
           spread,
           spread - LAG(spread) OVER (ORDER BY trade_date) AS daily_change
    FROM spread
)
SELECT trade_date,
       ROUND(spread, 2) AS spread,
       ROUND(daily_change, 2) AS daily_change
FROM changes
WHERE daily_change IS NOT NULL
ORDER BY ABS(daily_change) DESC
LIMIT :top_n
""",
        params=("front", "back", "top_n"),
    ),
    "quality_failures_by_rule": PresetQuery(
        title="Data-quality problems by rule",
        description=(
            "How often each validation rule failed or flagged a value across "
            "all logged runs. Expired contracts are 'skipped' and not counted."
        ),
        sql="""
SELECT rule,
       status,
       COUNT(*) AS occurrences,
       MAX(run_at) AS last_seen
FROM data_quality_log
WHERE status IN ('fail', 'flag')
GROUP BY rule, status
ORDER BY occurrences DESC, rule
""",
        params=(),
    ),
}


def run_query(conn: sqlite3.Connection, key: str, **params) -> pd.DataFrame:
    """
    Run one preset query and return its result as a DataFrame.

    `key` must be one of QUERIES; `params` must be exactly the names that
    query declares (e.g. front="CLZ26", back="CLK27").
    """
    if key not in QUERIES:
        raise KeyError(f"unknown query {key!r}")
    query = QUERIES[key]
    if set(params) != set(query.params):
        raise ValueError(f"{key} needs parameters {query.params}, got {tuple(params)}")

    conn.execute("PRAGMA query_only = ON")  # read-only while the query runs
    try:
        return pd.read_sql_query(query.sql, conn, params=params)
    finally:
        conn.execute("PRAGMA query_only = OFF")
