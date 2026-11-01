"""
charts.py — Every Plotly chart in the dashboard, built from data frames.

One shared look so the charts read as a set: the same fonts, margins,
hover style and colours. Backgrounds are left transparent and the colours
are mid-tone, so the charts work in both Streamlit's light and dark themes.
Every chart has a title and axis titles with units. Time series get a
range slider.
"""

import pandas as pd
import plotly.graph_objects as go

COLORS = {
    "primary": "#2E86DE",    # blue
    "secondary": "#F39C12",  # orange
    "warning": "#E74C3C",    # red
    "neutral": "#8395A7",    # grey-blue
}


def _style(fig: go.Figure, title: str, x_title: str, y_title: str, range_slider: bool = False) -> go.Figure:
    """Apply the shared layout to a figure."""
    fig.update_layout(
        title=dict(text=title, x=0),
        xaxis_title=x_title,
        yaxis_title=y_title,
        hovermode="x unified",
        height=460 if range_slider else 400,
        margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False, rangeslider_visible=range_slider)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.25)")
    return fig


def curve_figure(curve: pd.DataFrame) -> go.Figure:
    """The futures curve: price of each contract, front to back."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=curve["ticker"], y=curve["price"], mode="lines+markers", name="Futures price",
        line=dict(width=3, color=COLORS["primary"]), marker=dict(size=9),
        hovertemplate="%{x}: $%{y:.2f} per barrel<extra></extra>",
    ))
    flagged = curve[curve["outlier_flag"]]
    if not flagged.empty:
        fig.add_trace(go.Scatter(
            x=flagged["ticker"], y=flagged["price"], mode="markers", name="Flagged outlier",
            marker=dict(size=14, symbol="x", color=COLORS["warning"]),
            hovertemplate="%{x}: $%{y:.2f} (flagged)<extra></extra>",
        ))
    return _style(fig, "WTI futures curve", "Contract (front to back)", "Price (USD per barrel)")


def roll_yield_figure(roll_yield_df: pd.DataFrame) -> go.Figure:
    """Cumulative roll-window proxy next to the cumulative spot price change."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=roll_yield_df["date"], y=roll_yield_df["cumulative_spot_change"], mode="lines",
        name="Spot price change", line=dict(color=COLORS["primary"]),
        hovertemplate="$%{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=roll_yield_df["date"], y=roll_yield_df["cumulative_roll_yield"], mode="lines",
        name="Roll-window proxy (cumulative)", line=dict(color=COLORS["secondary"]),
        hovertemplate="$%{y:.2f}<extra></extra>",
    ))
    return _style(
        fig, "Roll-window proxy vs spot price change (last 2 years)",
        "Date", "Cumulative change (USD per barrel)", range_slider=True,
    )


def volatility_figure(volatility: pd.Series) -> go.Figure:
    """21-day rolling annualised volatility, as a percentage."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=volatility.index, y=volatility * 100, mode="lines", name="21-day volatility",
        line=dict(color=COLORS["primary"]), hovertemplate="%{y:.1f}%<extra></extra>",
    ))
    return _style(
        fig, "Rolling 21-day volatility (annualised, roll days excluded)",
        "Date", "Annualised volatility (%)", range_slider=True,
    )


def spread_figure(spread_df: pd.DataFrame, front: str, back: str) -> go.Figure:
    """Calendar spread (back minus front) over time, with its 20-day moving average."""
    dates = pd.to_datetime(spread_df["trade_date"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=spread_df["spread"], mode="lines", name="Spread",
        line=dict(color=COLORS["primary"]), hovertemplate="$%{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=spread_df["moving_avg_20d"], mode="lines", name="20-day average",
        line=dict(color=COLORS["secondary"], dash="dot"), hovertemplate="$%{y:.2f}<extra></extra>",
    ))
    return _style(
        fig, f"Calendar spread: {back} minus {front}",
        "Date", "USD per barrel (back minus front)", range_slider=True,
    )
