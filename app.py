"""
app.py — Streamlit dashboard: page layout, sidebar controls and data
loading. The calculations live in metrics.py / risk.py / term_structure.py,
the charts in charts.py and the tabs in views.py.

Run with: streamlit run app.py
"""

import pandas as pd
import streamlit as st

from crudecurve import storage, views
from crudecurve.config import (
    CACHE_TTL_SECONDS,
    DEFAULT_RISK_LOOKBACK_YEARS,
    MIN_CONTRACTS_SHOWN,
    RISK_HISTORY_YEARS,
    RISK_LOOKBACK_OPTIONS_YEARS,
)
from crudecurve.data_fetcher import get_front_month_history
from crudecurve.metrics import build_metrics
from crudecurve.pipeline import load_curve
from crudecurve.sql_queries import run_query

st.set_page_config(page_title="CrudeCurve", layout="wide")


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Fetching WTI futures data...")
def load_market_data() -> tuple:
    """Fetch, validate and save the curve, and download the CL=F history."""
    conn = storage.get_connection()
    try:
        curve_result = load_curve(conn)
    finally:
        conn.close()
    try:
        history = get_front_month_history(RISK_HISTORY_YEARS)
    except Exception:
        history = pd.DataFrame(columns=["date", "close"])  # shown as "history unavailable"
    return curve_result, history


st.title("CrudeCurve")
st.caption("WTI crude futures: term structure, roll yield and risk. Author: Tanish Shitanshu")

curve_result, history = load_market_data()
if curve_result.curve.empty:
    st.error(curve_result.message)
    st.stop()

# --- Sidebar controls ------------------------------------------------------
available = len(curve_result.curve)
with st.sidebar:
    st.header("Settings")
    lookback_years = st.radio(
        "VaR lookback window", RISK_LOOKBACK_OPTIONS_YEARS,
        index=RISK_LOOKBACK_OPTIONS_YEARS.index(DEFAULT_RISK_LOOKBACK_YEARS),
        format_func=lambda years: f"{years} years",
    )
    n_shown = (
        st.slider("Contracts on the curve", MIN_CONTRACTS_SHOWN, available, available)
        if available > MIN_CONTRACTS_SHOWN else available
    )
    n_contracts = st.number_input("Position size (contracts)", min_value=1, max_value=10_000, value=1, step=1,
                                  help="1 contract = 1,000 barrels")

    conn = storage.get_connection()
    price_contracts = storage.list_price_contracts(conn)
    front = back = None
    if len(price_contracts) >= 2:
        front = st.selectbox("Spread: front contract", price_contracts[:-1])
        later = price_contracts[price_contracts.index(front) + 1:]
        back = st.selectbox("Spread: back contract", later, index=len(later) - 1)

    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Data: Yahoo Finance (unofficial, delayed daily closes).")

# --- Compute once, show in tabs -------------------------------------------
curve = curve_result.curve.head(n_shown)
metrics = build_metrics(curve, history, lookback_years, int(n_contracts), curve_result.source)
quality = pd.DataFrame([vars(r) for r in curve_result.results], columns=["contract", "rule", "status", "detail"])

if curve_result.source == "snapshot":
    st.warning(curve_result.message)
if history.empty:
    st.warning("Price history is unavailable right now, so the roll and risk sections are empty.")

spread_df = pd.DataFrame()
if front is not None:
    spread_df = run_query(conn, "spread_moving_average", front=front, back=back)

tabs = st.tabs(["Overview", "Curve", "Roll Yield", "Risk", "SQL Analysis", "Data Quality", "Methodology"])
with tabs[0]:
    views.render_overview(metrics, curve, history, quality)
with tabs[1]:
    views.render_curve(metrics, curve, spread_df, front, back)
with tabs[2]:
    views.render_roll_yield(metrics)
with tabs[3]:
    views.render_risk(metrics)
with tabs[4]:
    views.render_sql(conn, front, back)
with tabs[5]:
    views.render_quality(metrics, quality)
with tabs[6]:
    views.render_methodology()

conn.close()
