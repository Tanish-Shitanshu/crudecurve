"""
storage.py — A small SQLite database (one local file, no server) that
remembers what the app has seen, so it can show a saved snapshot when
Yahoo Finance is unreachable and so later features can run SQL on it.

Tables:
  curve_snapshots  one row per contract per as-of date: the curve we saw.
                   PRIMARY KEY (asof_date, contract), so saving the same
                   curve twice updates the rows instead of duplicating them.
  contract_prices  daily closes of each live contract (about a year).
  data_quality_log the outcome of every validation rule on every run.

Dates are stored as ISO text ("2026-10-30"), which sorts correctly and
works with SQLite's date functions.

Every function takes an open sqlite3 connection, so tests can pass an
in-memory database (":memory:") and never touch the real file.
"""

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS curve_snapshots (
    asof_date      TEXT NOT NULL,
    contract       TEXT NOT NULL,
    delivery_month TEXT NOT NULL,
    month_index    INTEGER NOT NULL,
    price          REAL NOT NULL,
    source         TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    PRIMARY KEY (asof_date, contract)
);

CREATE TABLE IF NOT EXISTS contract_prices (
    trade_date TEXT NOT NULL,
    contract   TEXT NOT NULL,
    close      REAL NOT NULL,
    PRIMARY KEY (trade_date, contract)
);

CREATE TABLE IF NOT EXISTS data_quality_log (
    run_at   TEXT NOT NULL,
    contract TEXT NOT NULL,
    rule     TEXT NOT NULL,
    status   TEXT NOT NULL,
    detail   TEXT NOT NULL
);
"""


def get_connection(path: str = DB_PATH) -> sqlite3.Connection:
    """Open (and create, if needed) the database and make sure the tables exist."""
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


# --- Curve snapshots ---------------------------------------------------------

def save_snapshot(conn: sqlite3.Connection, curve: pd.DataFrame, fetched_at: str, source: str = "yahoo") -> None:
    """
    Save the curve. Safe to call repeatedly: a row with the same
    (asof_date, contract) is updated in place (an "upsert").
    """
    rows = [
        (str(r.as_of), r.ticker, r.delivery_month, int(r.month_index), float(r.price), source, fetched_at)
        for r in curve.itertuples()
    ]
    conn.executemany(
        """
        INSERT INTO curve_snapshots
            (asof_date, contract, delivery_month, month_index, price, source, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (asof_date, contract) DO UPDATE SET
            delivery_month = excluded.delivery_month,
            month_index    = excluded.month_index,
            price          = excluded.price,
            source         = excluded.source,
            fetched_at     = excluded.fetched_at
        """,
        rows,
    )
    conn.commit()


def load_latest_snapshot(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Load the curve saved by the most recent run (the rows with the newest
    fetched_at), in the same column layout validation.validate_curve returns.
    Returns an empty frame if nothing has been saved yet.
    """
    curve = pd.read_sql_query(
        """
        SELECT contract AS ticker, delivery_month, month_index, price, asof_date AS as_of
        FROM curve_snapshots
        WHERE fetched_at = (SELECT MAX(fetched_at) FROM curve_snapshots)
        ORDER BY month_index
        """,
        conn,
    )
    curve["as_of"] = pd.to_datetime(curve["as_of"]).dt.date
    curve["is_stale"] = False
    curve["outlier_flag"] = False
    return curve


# --- Contract price history ----------------------------------------------------

def save_contract_prices(conn: sqlite3.Connection, contract: str, history: pd.DataFrame) -> None:
    """Save daily closes (columns trade_date, close) for one contract; idempotent."""
    rows = [(str(r.trade_date), contract, float(r.close)) for r in history.itertuples()]
    conn.executemany(
        """
        INSERT INTO contract_prices (trade_date, contract, close)
        VALUES (?, ?, ?)
        ON CONFLICT (trade_date, contract) DO UPDATE SET close = excluded.close
        """,
        rows,
    )
    conn.commit()


def latest_trade_date(conn: sqlite3.Connection, contract: str):
    """The newest stored trade date for a contract, or None if it has none yet."""
    value = conn.execute(
        "SELECT MAX(trade_date) FROM contract_prices WHERE contract = ?", (contract,)
    ).fetchone()[0]
    return date.fromisoformat(value) if value else None


# --- Data quality log -----------------------------------------------------------

def log_quality_results(conn: sqlite3.Connection, run_at: str, results: list) -> None:
    """Append one row per validation RuleResult."""
    rows = [(run_at, r.contract, r.rule, r.status, r.detail) for r in results]
    conn.executemany(
        "INSERT INTO data_quality_log (run_at, contract, rule, status, detail) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
