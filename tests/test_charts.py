"""
test_charts.py — Every figure builds from data, has a title and axis titles,
and the time series have a range slider. Titles stay short so they are not
cut off on a phone screen.
"""

import pandas as pd

from crudecurve import charts, metrics
from crudecurve.risk import compute_returns, rolling_volatility


def _figures(curve, history):
    m = metrics.build_metrics(curve, history, lookback_years=2, n_contracts=1)
    spread = pd.DataFrame({
        "trade_date": ["2026-01-02", "2026-01-05"], "spread": [1.0, 2.0], "moving_avg_20d": [None, None],
    })
    return {
        "curve": charts.curve_figure(curve),
        "roll": charts.roll_yield_figure(m["roll_yield_df"]),
        "volatility": charts.volatility_figure(rolling_volatility(compute_returns(history)).dropna()),
        "spread": charts.spread_figure(spread, "CLZ26", "CLK27"),
    }


def test_every_figure_has_a_title_and_axis_titles(curve, history):
    for name, fig in _figures(curve, history).items():
        assert fig.layout.title.text, name
        assert fig.layout.xaxis.title.text, name
        assert fig.layout.yaxis.title.text, name


def test_titles_are_short_enough_for_a_phone_screen(curve, history):
    for name, fig in _figures(curve, history).items():
        assert len(fig.layout.title.text) <= 40, (name, fig.layout.title.text)


def test_legend_sits_below_the_title_not_beside_it(curve, history):
    for name, fig in _figures(curve, history).items():
        assert fig.layout.legend.x == 0 and fig.layout.legend.y > 1, name
        assert fig.layout.title.y < 1, name


def test_time_series_have_a_range_slider_and_the_curve_does_not(curve, history):
    figs = _figures(curve, history)
    assert not figs["curve"].layout.xaxis.rangeslider.visible
    for name in ("roll", "volatility", "spread"):
        assert figs[name].layout.xaxis.rangeslider.visible, name


def test_curve_figure_marks_flagged_outliers(curve):
    flagged = curve.assign(outlier_flag=[False, False, True, False, False, False])
    fig = charts.curve_figure(flagged)
    assert [trace.name for trace in fig.data] == ["Futures price", "Flagged outlier"]
    assert list(fig.data[1].x) == ["CLG27"]


def test_spread_title_names_the_pair(curve, history):
    assert _figures(curve, history)["spread"].layout.title.text == "Calendar spread: CLK27 minus CLZ26"
