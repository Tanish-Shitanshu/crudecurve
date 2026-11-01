"""
views.py — One function per dashboard tab. Each takes already-computed
data (the metrics dictionary, data frames) and only decides how to show it;
no market calculations happen here.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from crudecurve import charts, sql_queries
from crudecurve.config import RECENT_WINDOW_DAYS, VAR_CONFIDENCE_LEVELS
from crudecurve.formatting import format_optional, format_pct, format_signed_usd, format_usd
from crudecurve.market_summary import LIMITATIONS, build_market_summary
from crudecurve.report import build_workbook, curve_to_csv

METHODOLOGY_FILE = Path(__file__).resolve().parent.parent / "docs" / "METHODOLOGY.md"

_REGIME_COLORS = {"Backwardation": "blue", "Contango": "orange", "Kinked": "violet", "Flat": "gray"}


def _escape_dollars(text: str) -> str:
    """
    Streamlit markdown treats a pair of $ signs as a LaTeX formula, which
    garbles text such as "$104.12 ... $92.96". A backslash shows a plain $.
    """
    return text.replace("$", "\\$")


def _regime_color(label: str) -> str:
    """Badge colour for a regime label such as "Kinked (net Contango)"."""
    for name, color in _REGIME_COLORS.items():
        if label.startswith(name):
            return color
    return "gray"


def render_overview(m: dict, curve: pd.DataFrame, history: pd.DataFrame, quality: pd.DataFrame) -> None:
    """KPI cards, the written market summary and the download buttons."""
    status_col, date_col = st.columns([1, 4])
    if m["source"] == "live":
        status_col.badge("Live data", color="green")
    else:
        status_col.badge("Saved snapshot", color="orange")
    date_col.caption(f"As of {m['as_of']} (daily close)")

    risk95 = m["risk"]["var"][0.95]
    cards = st.columns(5)
    cards[0].metric(
        "Front price", format_usd(m["front_price"]), help=f"{m['front_ticker']}, USD per barrel", border=True
    )
    cards[1].metric(
        "Annualised carry", format_pct(m["annualised_carry_pct"], signed=True),
        help="Front-to-back spread stretched to a year. Positive = contango, negative = backwardation.",
        border=True,
    )
    with cards[2].container(border=True):
        st.caption("Market regime")
        st.badge(m["label"], color=_regime_color(m["label"]))
    cards[3].metric(
        "Roll gain/(cost) p.a.", format_signed_usd(m["roll_gain_per_year"], 0),
        help=f"Per year, long position of {m['n_contracts']} contract(s) if the curve stays unchanged. "
             "Positive = gain (backwardation), negative = cost (contango).",
        border=True,
    )
    cards[4].metric(
        "1-day VaR (95%)", format_optional(risk95["var_usd"], lambda v: format_usd(v, 0)),
        help=f"Historical simulation over {m['lookback_years']} years, {risk95['observations']} observations.",
        border=True,
    )

    st.subheader("Market summary")
    st.markdown(_escape_dollars(build_market_summary(m)))
    st.caption(LIMITATIONS)

    excel_col, csv_col, _ = st.columns([1, 1, 2])
    excel_col.download_button(
        "Download Excel report",
        data=build_workbook(m, curve, history, quality),
        file_name=f"crudecurve_report_{m['as_of']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    csv_col.download_button(
        "Download curve (CSV)", data=curve_to_csv(curve),
        file_name=f"crudecurve_curve_{m['as_of']}.csv", mime="text/csv",
    )


def render_curve(m: dict, curve: pd.DataFrame, spread_df: pd.DataFrame, front: str | None, back: str | None) -> None:
    """The current curve, its table and the spread history of the chosen pair."""
    st.plotly_chart(charts.curve_figure(curve), use_container_width=True)
    st.caption(
        f"Regime: {m['label']}. Annualised front-to-back spread: "
        f"{format_pct(m['annualised_carry_pct'], signed=True)} over {m['months_between']} delivery months."
    )
    table = curve[["ticker", "delivery_month", "price", "as_of", "outlier_flag"]].rename(columns={
        "ticker": "Contract", "delivery_month": "Delivery month", "price": "Price (USD/bbl)",
        "as_of": "As of", "outlier_flag": "Flagged outlier",
    })
    st.dataframe(table, hide_index=True, use_container_width=True)

    st.subheader("Spread history")
    if front is None or spread_df.empty:
        st.caption("Not enough stored contract history yet to chart a spread.")
    else:
        st.plotly_chart(charts.spread_figure(spread_df, front, back), use_container_width=True)
        st.caption("Back contract minus front contract on each date both traded. "
                   "Positive = contango, negative = backwardation. Pick the pair in the sidebar.")


def render_roll_yield(m: dict) -> None:
    """The curve-based roll gain (headline) and the 2-year roll-window proxy."""
    left, right = st.columns(2)
    left.metric(
        "Annual roll gain / (cost)", format_signed_usd(m["roll_gain_per_year"], 0), border=True,
        help="Headline roll metric: from today's curve, for a long position, if the curve stays unchanged.",
    )
    right.metric(
        "2-year roll-window proxy", f"{format_signed_usd(m['roll_window_proxy'])} / bbl", border=True,
        help="A proxy from month-end price moves of CL=F. Not a true roll yield.",
    )
    if m["roll_yield_df"].empty:
        st.caption("Not enough price history to draw the roll-window chart.")
        return
    st.plotly_chart(charts.roll_yield_figure(m["roll_yield_df"]), use_container_width=True)
    st.caption(
        "The roll-window proxy adds up CL=F price moves over the last 5 trading days of each month. "
        "It is a proxy, not a true roll yield (that needs the gap between the expiring and next contract). "
        "The headline roll metric is the curve-based figure above."
    )


def _var_table(m: dict) -> pd.DataFrame:
    """VaR for the selected window and the last 12 months, with observation counts."""
    rows = []
    risk = m["risk"]
    windows = (
        (f"{m['lookback_years']} years", "var"),
        (f"Last {RECENT_WINDOW_DAYS // 30} months", "var_recent"),
    )
    for label, key in windows:
        for confidence in VAR_CONFIDENCE_LEVELS:
            v = risk[key][confidence]
            rows.append({
                "Measure": f"1-day VaR {int(confidence * 100)}%",
                "Window": label,
                "VaR (% of notional)": format_optional(v["var_pct"], lambda x: format_pct(x * 100)),
                "VaR (USD)": format_optional(v["var_usd"], lambda x: format_usd(x, 0)),
                "Observations": v["observations"],
            })
    return pd.DataFrame(rows)


def render_risk(m: dict) -> None:
    """VaR table, volatility, drawdown and worst day."""
    risk = m["risk"]
    if risk["var"][0.95]["var_pct"] is None:
        st.info("Price history is unavailable, so risk figures cannot be shown.")
        return
    st.caption(_escape_dollars(
        f"Position: {m['n_contracts']} contract(s), notional {format_usd(m['notional'], 0)}. "
        f"Window {risk['window_start']} to {risk['window_end']}; "
        f"{risk['roll_days_excluded']} roll days excluded."
    ))
    st.dataframe(_var_table(m), hide_index=True, use_container_width=True)

    drawdown, worst = risk["max_drawdown"], risk["worst_day"]
    cols = st.columns(3)
    cols[0].metric(
        "Volatility (21-day, annualised)",
        format_optional(risk["volatility"], lambda v: format_pct(v * 100, 1)),
        border=True,
    )
    cols[1].metric(
        "Max drawdown", format_pct(drawdown["max_drawdown"] * 100, 1), border=True,
        help=f"Peak {drawdown['peak_date']}, trough {drawdown['trough_date']}.",
    )
    cols[2].metric(
        "Worst day", format_pct(worst["return"] * 100, 1), border=True, help=f"On {worst['date']}.",
    )
    st.plotly_chart(charts.volatility_figure(m["volatility_series"]), use_container_width=True)
    st.caption(
        "Historical simulation on daily closes, roll days excluded (about 5% of days, a few of which may "
        "hold real moves, so VaR may be slightly understated). It assumes the past is representative of "
        "the future. Large non-roll moves are kept, not removed. The 99% figure rests on very few "
        "observations. See the Methodology tab."
    )


def render_sql(conn: sqlite3.Connection, front: str | None, back: str | None) -> None:
    """The preset SQL queries: SQL text, then the result table."""
    st.write(
        "These analyses run as SQL on the SQLite database the app fills on every refresh. "
        "The queries are fixed (no free-text box); only the contract pair and the row limit are parameters."
    )
    params_by_key = {"front": front, "back": back, "top_n": 5}
    for key, query in sql_queries.QUERIES.items():
        st.subheader(query.title)
        st.caption(query.description)
        with st.expander("Show SQL"):
            st.code(query.sql.strip(), language="sql")
        if {"front", "back"} <= set(query.params) and front is None:
            st.caption("Not enough stored contract history yet.")
            continue
        result = sql_queries.run_query(conn, key, **{name: params_by_key[name] for name in query.params})
        if result.empty:
            st.caption("No rows to show: nothing has been recorded for this analysis.")
        else:
            st.dataframe(result, hide_index=True, use_container_width=True, height=min(400, 38 * (len(result) + 1)))


def render_quality(m: dict, quality: pd.DataFrame) -> None:
    """The validation outcome of this run."""
    counts = quality["status"].value_counts() if not quality.empty else pd.Series(dtype=int)
    cols = st.columns(4)
    for col, status in zip(cols, ("pass", "flag", "fail", "skipped"), strict=True):
        col.metric(status.capitalize(), int(counts.get(status, 0)), border=True)
    st.caption(
        "Pass: rule satisfied. Flag: a warning, data kept (outlier check). Fail: a real violation. "
        "Skipped: an expired contract (expected, not an error)."
    )
    if m["source"] == "snapshot":
        st.warning("The live curve did not pass validation, so a saved snapshot is shown.")
    st.dataframe(quality, hide_index=True, use_container_width=True)


def render_methodology() -> None:
    """The methodology document (docs/METHODOLOGY.md)."""
    try:
        st.markdown(METHODOLOGY_FILE.read_text(encoding="utf-8"))
    except OSError:
        st.info("The methodology document could not be loaded.")
