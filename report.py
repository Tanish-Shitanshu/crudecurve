"""
report.py — Builds the downloadable Excel workbook (openpyxl) and the CSV
of the curve. Every cell is written from the metrics dictionary and the
data frames the dashboard already computed; nothing is typed in by hand.

Sheets: Summary, Curve, History, Risk, Data Quality.
Each sheet has a bold, shaded header row that stays visible when you
scroll (frozen), real numbers (not text) with number formats, and column
widths that fit the content.
"""

import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from config import RECENT_WINDOW_DAYS, VAR_CONFIDENCE_LEVELS
from market_summary import LIMITATIONS, build_market_summary
from risk import compute_returns, window_returns

USD = '"$"#,##0.00;[Red]-"$"#,##0.00'
USD0 = '"$"#,##0;[Red]-"$"#,##0'
PCT = "0.00%;[Red]-0.00%"
DATE = "yyyy-mm-dd"

_HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
_HEADER_FONT = Font(bold=True, color="FFFFFF")


def _write_table(ws, headers: list, rows: list, formats: list = None) -> None:
    """
    Write a header row and data rows. `formats` has one number format (or
    None) per column, or per cell if a row is given as a list of
    (value, format) pairs. Then freeze the header and fit column widths.
    """
    ws.append(headers)
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in rows:
        ws.append([item[0] if isinstance(item, tuple) else item for item in row])
        for col, item in enumerate(row):
            fmt = item[1] if isinstance(item, tuple) else (formats[col] if formats else None)
            if fmt:
                ws.cell(row=ws.max_row, column=col + 1).number_format = fmt

    ws.freeze_panes = "A2"
    for col in range(1, len(headers) + 1):
        longest = max(len(str(ws.cell(row=r, column=col).value or "")) for r in range(1, ws.max_row + 1))
        ws.column_dimensions[get_column_letter(col)].width = min(max(longest + 2, 10), 70)


def _cell(value, number_format: str):
    """A (value, number_format) cell, or the text "n/a" when there is no value."""
    return "n/a" if value is None else (value, number_format)


def _summary_rows(m: dict) -> list:
    risk = m["risk"]
    rows = [
        ["As-of date", (m["as_of"], DATE), "Date of the front contract's close"],
        ["Data status", "Live" if m["source"] == "live" else "Saved snapshot", ""],
        ["Market regime", m["label"], ""],
        ["Front contract", m["front_ticker"], ""],
        ["Front price ($/bbl)", (m["front_price"], USD), ""],
        ["Back contract", m["back_ticker"], f"{m['months_between']} delivery months after the front"],
        ["Back price ($/bbl)", (m["back_price"], USD), ""],
        ["Annualised carry", (m["annualised_carry_pct"] / 100, PCT), "Positive = contango, negative = backwardation"],
        ["Position size (contracts)", m["n_contracts"], "1 contract = 1,000 barrels"],
        ["Position notional", (m["notional"], USD0), "Front price x 1,000 x contracts"],
        [
            "Annual roll gain / (cost)", (m["roll_gain_per_year"], USD0),
            "Long position, curve unchanged; positive = gain",
        ],
        [
            "2-year roll-window proxy ($/bbl)", (m["roll_window_proxy"], USD),
            "A proxy from month-end price moves, not a true roll yield",
        ],
    ]
    for confidence in VAR_CONFIDENCE_LEVELS:
        v = risk["var"][confidence]
        rows.append([
            f"1-day VaR {int(confidence * 100)}% ({m['lookback_years']}y)",
            _cell(v["var_usd"], USD0),
            f"{v['observations']} observations",
        ])
    rows += [
        ["Volatility (21-day, annualised)", _cell(risk["volatility"], PCT), ""],
        ["Max drawdown", _cell(risk["max_drawdown"]["max_drawdown"], PCT), "Roll days treated as 0%"],
        ["Market summary", build_market_summary(m), ""],
        ["Limitations", LIMITATIONS, ""],
    ]
    return rows


def _risk_rows(m: dict) -> list:
    risk = m["risk"]
    recent_label = f"Last {RECENT_WINDOW_DAYS // 30} months"
    windows = (
        (f"{m['lookback_years']} years", "var"),
        (recent_label, "var_recent"),
    )
    rows = []
    for label, key in windows:
        for confidence in VAR_CONFIDENCE_LEVELS:
            v = risk[key][confidence]
            rows.append([
                f"1-day VaR {int(confidence * 100)}%", label,
                _cell(v["var_pct"], PCT), _cell(v["var_usd"], USD0), v["observations"],
            ])
    dd, worst = risk["max_drawdown"], risk["worst_day"]
    span = f"{risk['window_start']} to {risk['window_end']}"
    rows += [
        ["Volatility (21-day, annualised)", "latest", _cell(risk["volatility"], PCT), "n/a", ""],
        ["Max drawdown", f"{dd['peak_date']} to {dd['trough_date']}", _cell(dd["max_drawdown"], PCT), "n/a", ""],
        ["Worst day", str(worst["date"]), _cell(worst["return"], PCT), "n/a", ""],
        ["Roll days excluded", span, "n/a", "n/a", risk["roll_days_excluded"]],
    ]
    return rows


def build_workbook(m: dict, curve: pd.DataFrame, history: pd.DataFrame, quality: pd.DataFrame) -> bytes:
    """
    Build the Excel report and return it as bytes (ready for a download button).

    m: metrics from metrics.build_metrics. curve: the curve shown on screen.
    history: CL=F closes (date, close). quality: this run's validation
    results (columns contract, rule, status, detail).
    """
    wb = Workbook()

    ws = wb.active
    ws.title = "Summary"
    _write_table(ws, ["Metric", "Value", "Note"], _summary_rows(m))
    ws.column_dimensions["B"].width = 40
    for row in ws.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")

    ws = wb.create_sheet("Curve")
    _write_table(
        ws,
        ["Contract", "Delivery month", "Month index", "Price ($/bbl)", "As-of date", "Outlier flag"],
        [[r.ticker, r.delivery_month, int(r.month_index), float(r.price), r.as_of, "yes" if r.outlier_flag else "no"]
         for r in curve.itertuples()],
        [None, None, "0", USD, DATE, None],
    )

    ws = wb.create_sheet("History")
    window = window_returns(compute_returns(history), years=m["lookback_years"])
    _write_table(
        ws,
        ["Date", "CL=F close ($/bbl)", "Daily return", "Roll day"],
        [[r.date.date(), float(r.close), None if pd.isna(r.daily_return) else float(r.daily_return),
          "yes" if r.is_roll_day else "no"] for r in window.itertuples()],
        [DATE, USD, PCT, None],
    )

    ws = wb.create_sheet("Risk")
    _write_table(ws, ["Metric", "Window", "Value (%)", "Value ($)", "Observations"], _risk_rows(m))

    ws = wb.create_sheet("Data Quality")
    _write_table(
        ws,
        ["Contract", "Rule", "Status", "Detail"],
        [[r.contract, r.rule, r.status, r.detail] for r in quality.itertuples()],
    )

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def curve_to_csv(curve: pd.DataFrame) -> str:
    """The curve as CSV text (ticker, delivery month, month index, price, as-of date)."""
    columns = ["ticker", "delivery_month", "month_index", "price", "as_of"]
    return curve[columns].to_csv(index=False)
