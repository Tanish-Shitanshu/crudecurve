# CrudeCurve

**WTI Crude Oil Term Structure & Roll Yield Visualizer**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Built with Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)

Visualizing what the oil futures curve reveals about storage costs and
market stress, and quantifying the cost of holding a rolling futures
position over time.

Author: **Tanish Shitanshu** — built as a portfolio project targeting the
**Intern Market Analyst** role at Futures First.

CrudeCurve visualizes the WTI crude oil futures curve (front-month vs.
forward-month prices) to classify the market as **contango** or
**backwardation**, and quantifies the **roll yield** an investor
experiences from continuously rolling a long futures position over time.

## Table of Contents

- [Quick Start](#quick-start)
- [Why This Matters](#why-this-matters-plain-english)
- [Formulas Used](#formulas-used)
- [Setup](#setup)
- [Data Limitations](#data-limitations)
- [Screenshot](#screenshot)
- [Project Structure](#project-structure)

## Quick Start

```bash
git clone https://github.com/Tanish-Shitanshu/crudecurve.git
cd crudecurve
pip install -r requirements.txt
cp .env.example .env  # add your free EIA API key
streamlit run app.py
```

See [Setup](#setup) below for details on getting an EIA API key and
running the test suite.

## Why this matters (plain English)

A futures contract is a promise to buy or sell oil at a set price on a
future date. Storing a physical barrel of oil costs money — tanks,
insurance, and the financing cost of cash tied up in inventory. Because
of that, a contract for delivery further in the future would "normally"
cost a bit more than one for delivery sooner, to compensate whoever is
holding the barrels in the meantime. A curve that rises with time to
delivery is called **contango**.

Sometimes the opposite happens: the market pays *more* for oil right
now than for oil delivered later. That's **backwardation**, and it
usually signals the market is worried about a near-term shortage —
buyers would rather have a barrel today than a cheaper promise of one
next month.

This matters to anyone trading or analyzing futures because you can't
hold a single futures contract forever — it expires. An investor who
wants ongoing oil exposure (e.g. via an ETF) must keep "rolling":
selling the contract about to expire and buying the next month's
contract. In contango, that means constantly selling low and buying
high — a steady drag on returns called **negative roll yield**, even if
the spot price of oil doesn't move at all. In backwardation, rolling
works in the investor's favor — **positive roll yield**. This is why
long-oil ETFs can lose money in a flat oil market, or make money before
the spot price even moves.

## Formulas used

**Annualized contango/backwardation spread** (`term_structure.py`):

```
spread_pct = (far_price - front_price) / front_price * (12 / months_between) * 100
```

- `front_price`: price of the nearest-expiry contract
- `far_price`: price of the furthest-out contract in the ladder
- `months_between`: number of contract months separating them
- Positive result → contango (annualized implied storage cost)
- Negative result → backwardation (annualized implied scarcity premium)

**Curve classification** (`term_structure.py`): contracts are sorted
front-to-back and every consecutive pair is compared. If every step
rises, the curve is Contango; if every step falls, it's Backwardation.
If the curve changes direction partway through, it's reported as
"Kinked" along with the net front-vs-back relationship, rather than
forcing a clean label onto a curve that isn't actually monotonic.

**Roll yield simulation** (`roll_yield.py`): for each calendar month in
the 2-year lookback, the last `ROLL_DAYS_BEFORE_MONTH_END` (5) trading
days are treated as the "roll window," where the front-month continuous
series absorbs the switch from the expiring contract to the next one.
Price moves during that window are summed into a running
**cumulative roll yield**; the total price move since the start of the
window is tracked separately as **cumulative spot change**, so the two
can be compared side by side.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then edit .env and add your free EIA API key
streamlit run app.py
```

CrudeCurve's term structure curve is powered by the free EIA (U.S.
Energy Information Administration) Open Data API, which requires an API
key:

1. Register for a free key at https://www.eia.gov/opendata/register.php
2. Put it in `.env` as `EIA_API_KEY=your_key_here` (`.env` is
   git-ignored and never committed — see `.env.example` for the
   template). If no key is set, the app falls back to EIA's public
   `DEMO_KEY`, which works but is rate-limited, so it's meant for quick
   testing only, not everyday use.

Run the unit tests (offline: all network calls are mocked, so no API key
or internet connection is needed):

```bash
pytest tests/
```

The suite covers curve classification and the annualized spread
(`test_term_structure.py`), the roll-yield simulation against
hand-computed price series (`test_roll_yield.py`), and EIA/yfinance
parsing, missing-data handling and stale-data flagging
(`test_data_fetcher.py`).

## Data limitations

**Forward curve (EIA API):** Yahoo Finance (via `yfinance`) does not
publish dated forward-month WTI contracts on its free tier — verified
directly, those symbols return no data at all. CrudeCurve instead
sources the actual forward curve from the EIA's Open Data API, which
publishes official daily settlement prices for WTI **Future Contract 1
through Contract 4** (`RCLC1`–`RCLC4`; Contract 1 = front month,
Contract 4 ≈ 3 months out, spaced roughly monthly). This is real,
verified U.S. government market data with no gaps — but it is only
**4 points**, not the longer 5-6 month ladder the original design
envisioned. The curve shown will therefore look shorter than a paid
terminal's, but every point on it is genuinely traded, current data
rather than an estimate. See `config.py` for the exact series IDs and
API route.

**Front-month history (yfinance):** `CL=F`, the continuous front-month
WTI contract, remains sourced from yfinance for the 2-year daily
history used in the roll-yield backtest — this series is reliable and
has no gaps.

The app never fabricates a price for a missing contract: if EIA has no
data for a contract series, it's dropped from the curve; if its most
recent data is more than 5 days old, it's flagged as stale in the
dashboard rather than presented as current.

The roll-yield simulation works around the lack of a full historical
forward ladder by using the front-month continuous series' own
month-end price behavior as a proxy for the realized roll effect (see
the docstring in `roll_yield.py` for the full explanation).

## Screenshot

_Add a screenshot of the running dashboard here, e.g.:_

```
![CrudeCurve dashboard](docs/screenshot.png)
```

**Sample output:** Screenshot coming soon — see [Quick Start](#quick-start)
above to run it locally in the meantime.

## Project structure

```
crudecurve/
├── README.md
├── requirements.txt
├── .env.example          # template for EIA_API_KEY (copy to .env)
├── config.py              # tickers, EIA series IDs, lookback window, notes
├── data_fetcher.py        # EIA API (curve) + yfinance (history) data pulls
├── term_structure.py      # curve classification + annualized spread
├── roll_yield.py          # 2-year roll yield backtest
├── app.py                 # Streamlit dashboard
└── tests/
    ├── test_term_structure.py   # curve classification + annualized spread
    ├── test_roll_yield.py       # roll-yield simulation on synthetic series
    └── test_data_fetcher.py     # EIA / yfinance parsing (network mocked)
```
