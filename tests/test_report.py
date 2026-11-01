"""
test_report.py — The Excel workbook opens, is formatted, and its contents
match the inputs it was built from.
"""

import io

import pandas as pd
import pytest
from openpyxl import load_workbook

from crudecurve import metrics, report
from crudecurve.risk import compute_returns, window_returns
from crudecurve.validation import RuleResult


@pytest.fixture
def m(curve, history):
    return metrics.build_metrics(curve, history, lookback_years=2, n_contracts=2)


@pytest.fixture
def quality():
    return pd.DataFrame([vars(r) for r in [
        RuleResult("CLX26", "not_expired", "skipped", "expired on 2026-10-20"),
        RuleResult("CLZ26", "price_valid", "pass", "price 104.00"),
    ]])


@pytest.fixture
def workbook(m, curve, history, quality):
    data = report.build_workbook(m, curve, history, quality)
    return load_workbook(io.BytesIO(data))


def _summary(workbook):
    """The Summary sheet as {metric: (value, note)}."""
    ws = workbook["Summary"]
    return {row[0].value: (row[1].value, row[2].value) for row in ws.iter_rows(min_row=2)}


def test_workbook_has_the_five_sheets(workbook):
    assert workbook.sheetnames == ["Summary", "Curve", "History", "Risk", "Data Quality"]


def test_every_sheet_has_a_bold_frozen_header(workbook):
    for ws in workbook.worksheets:
        assert ws.freeze_panes == "A2", ws.title
        assert all(cell.font.bold for cell in ws[1]), ws.title


def test_summary_values_match_the_metrics(workbook, m):
    summary = _summary(workbook)
    assert summary["Market regime"][0] == m["label"]
    assert summary["Front price ($/bbl)"][0] == pytest.approx(m["front_price"])
    assert summary["Annualised carry"][0] == pytest.approx(m["annualised_carry_pct"] / 100)
    assert summary["Position notional"][0] == pytest.approx(m["notional"])
    assert summary["Annual roll gain / (cost)"][0] == pytest.approx(m["roll_gain_per_year"])
    assert summary["2-year roll-window proxy ($/bbl)"][0] == pytest.approx(m["roll_window_proxy"])
    var95 = m["risk"]["var"][0.95]
    assert summary["1-day VaR 95% (2y)"][0] == pytest.approx(var95["var_usd"])
    assert summary["1-day VaR 95% (2y)"][1] == f"{var95['observations']} observations"
    assert str(summary["As-of date"][0].date()) == str(m["as_of"])
    assert summary["Data status"][0] == "Live"


def test_summary_paragraph_and_limitations_are_included(workbook):
    summary = _summary(workbook)
    assert "WTI futures curve" in summary["Market summary"][0]
    assert "not investment advice" in summary["Limitations"][0]
    assert "not a true roll yield" in summary["2-year roll-window proxy ($/bbl)"][1]


def test_number_formats_are_applied(workbook):
    ws = workbook["Summary"]
    rows = {row[0].value: row[1] for row in ws.iter_rows(min_row=2)}
    assert rows["Front price ($/bbl)"].number_format == report.USD
    assert rows["Annualised carry"].number_format == report.PCT
    assert rows["As-of date"].number_format == report.DATE


def test_curve_sheet_matches_the_curve(workbook, curve):
    ws = workbook["Curve"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert [r[0] for r in rows] == list(curve["ticker"])
    assert [r[3] for r in rows] == list(curve["price"])
    assert ws["D2"].number_format == report.USD


def test_history_sheet_covers_the_selected_window(workbook, history):
    ws = workbook["History"]
    expected = window_returns(compute_returns(history), years=2)
    assert ws.max_row - 1 == len(expected)
    assert ws["B2"].value == pytest.approx(float(expected["close"].iloc[0]))
    assert ws["A2"].number_format == report.DATE


def test_risk_sheet_has_var_with_observation_counts(workbook, m):
    ws = workbook["Risk"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    var_rows = [r for r in rows if r[0].startswith("1-day VaR")]
    assert len(var_rows) == 4  # 95% and 99%, for the selected window and the last 12 months
    first = m["risk"]["var"][0.95]
    assert var_rows[0][2] == pytest.approx(first["var_pct"])
    assert var_rows[0][3] == pytest.approx(first["var_usd"])
    assert var_rows[0][4] == first["observations"]
    assert any(r[0] == "Max drawdown" for r in rows)


def test_data_quality_sheet_matches_the_results(workbook, quality):
    rows = list(workbook["Data Quality"].iter_rows(min_row=2, values_only=True))
    assert rows[0] == ("CLX26", "not_expired", "skipped", "expired on 2026-10-20")
    assert len(rows) == len(quality)


def test_snapshot_status_is_labelled(curve, history, quality):
    m = metrics.build_metrics(curve, history, 2, 1, source="snapshot")
    wb = load_workbook(io.BytesIO(report.build_workbook(m, curve, history, quality)))
    assert _summary(wb)["Data status"][0] == "Saved snapshot"


def test_csv_round_trips_the_curve(curve):
    parsed = pd.read_csv(io.StringIO(report.curve_to_csv(curve)))
    assert list(parsed["ticker"]) == list(curve["ticker"])
    assert list(parsed["price"]) == list(curve["price"])
    assert list(parsed.columns) == ["ticker", "delivery_month", "month_index", "price", "as_of"]
