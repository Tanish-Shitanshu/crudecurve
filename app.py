"""
app.py — Streamlit dashboard tying together the data, term structure,
and roll yield modules into one page.

Run with: streamlit run app.py
"""

import plotly.graph_objects as go
import streamlit as st

from config import EIA_CONTRACT_MONTH_SPACING
from data_fetcher import get_current_curve, get_front_month_history
from term_structure import classify_curve, compute_annualized_spread
from roll_yield import simulate_roll_yield, summarize_roll_yield

st.set_page_config(page_title="CrudeCurve", layout="wide")

st.title("CrudeCurve: WTI Crude Oil Term Structure & Roll Yield")
st.caption(
    "Author: Tanish Shitanshu — built for the Intern Market Analyst role at Futures First"
)

# --- Load data ---------------------------------------------------------
with st.spinner("Fetching WTI futures data..."):
    curve_df = get_current_curve()
    history_df = get_front_month_history()

if curve_df.empty:
    st.error("Could not fetch any futures price data right now. Please try again later.")
    st.stop()

curve_df = curve_df.sort_values("month_index").reset_index(drop=True)

# --- Term structure classification -------------------------------------
classification = classify_curve(curve_df)
front_row = curve_df.iloc[0]
back_row = curve_df.iloc[-1]
months_between = (back_row["month_index"] - front_row["month_index"]) * EIA_CONTRACT_MONTH_SPACING

annualized_spread = compute_annualized_spread(
    front_price=front_row["price"],
    far_price=back_row["price"],
    months_between=months_between,
) if months_between > 0 else 0.0

roll_yield_df = simulate_roll_yield(history_df)
cumulative_roll_yield = summarize_roll_yield(roll_yield_df)

if curve_df["is_stale"].any():
    stale_dates = curve_df.loc[curve_df["is_stale"], "as_of"].unique()
    st.warning(f"Some contracts show stale data (last updated: {', '.join(str(d) for d in stale_dates)}).")

st.caption(f"Front-month data as of: {front_row['as_of']}")

# --- Metrics row ---------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Front-Month Price (EIA Contract 1)", f"${front_row['price']:.2f}")
col2.metric("Annualized Carry/Backwardation", f"{annualized_spread:+.2f}%")
col3.metric("2-Year Cumulative Roll Yield", f"${cumulative_roll_yield:+.2f}/bbl")

# --- Chart 1: Current futures curve ---------------------------------------
st.subheader(f"Current Futures Curve — {classification['label']}")

fig_curve = go.Figure()
fig_curve.add_trace(
    go.Scatter(
        x=curve_df["ticker"],
        y=curve_df["price"],
        mode="lines+markers",
        name="Futures Price",
        line=dict(width=3),
        marker=dict(size=9),
    )
)
fig_curve.update_layout(
    xaxis_title="Contract (front → back)",
    yaxis_title="Price (USD/barrel)",
    height=420,
)
st.plotly_chart(fig_curve, use_container_width=True)
st.caption(
    f"Annualized spread from front to back month: {annualized_spread:+.2f}%. "
    "Positive = Contango (future delivery costs more, implying storage cost). "
    "Negative = Backwardation (near-term delivery costs more, implying scarcity)."
)

# --- Chart 2: Roll yield vs spot price change ---------------------------
st.subheader("2-Year History: Cumulative Roll Yield vs. Spot Price Change")

if roll_yield_df.empty:
    st.info("Not enough historical data to compute roll yield.")
else:
    fig_roll = go.Figure()
    fig_roll.add_trace(
        go.Scatter(
            x=roll_yield_df["date"],
            y=roll_yield_df["cumulative_spot_change"],
            mode="lines",
            name="Spot Price Change",
        )
    )
    fig_roll.add_trace(
        go.Scatter(
            x=roll_yield_df["date"],
            y=roll_yield_df["cumulative_roll_yield"],
            mode="lines",
            name="Cumulative Roll Yield",
        )
    )
    fig_roll.update_layout(
        xaxis_title="Date",
        yaxis_title="Cumulative Change (USD/barrel)",
        height=420,
    )
    st.plotly_chart(fig_roll, use_container_width=True)
    st.caption(
        "The gap between these two lines is the 'hidden cost' (or gain) an investor "
        "experiences from continuously rolling futures contracts, separate from the "
        "outright change in the oil price itself."
    )

# --- How this works -----------------------------------------------------
with st.expander("How this works"):
    st.markdown(
        """
**Contango** is when futures contracts for later delivery cost more than
contracts for sooner delivery. This is the "normal" state for a
storable commodity like oil, because holding barrels in a tank until a
future date costs money (storage, insurance, financing) — buyers of the
far-month contract pay a premium to compensate whoever stores the oil.

**Backwardation** is the opposite: near-term contracts cost more than
far-term ones. This usually signals the market expects a near-term
supply squeeze — buyers will pay up to get oil *now* rather than wait
for a cheaper contract later.

**Roll yield** is the return (or cost) an investor experiences purely
from rotating out of an expiring futures contract into the next one,
separate from any change in the underlying price of oil. In contango,
rolling means constantly selling a cheaper near contract and buying a
more expensive far one — a steady drag. In backwardation, it's the
reverse — a steady tailwind.

**Historical examples:** In April 2020, collapsing demand during the
COVID-19 pandemic pushed WTI into extreme contango (even briefly
negative front-month prices), making roll yield sharply negative for
anyone holding long oil ETFs. In 2022, supply concerns following
Russia's invasion of Ukraine pushed the WTI curve into backwardation,
which briefly made rolling long futures positions a source of
additional return rather than a drag.
        """
    )
