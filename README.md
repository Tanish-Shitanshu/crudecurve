# CrudeCurve

**WTI Crude Oil Term Structure & Roll Yield Visualizer**

Author: **Tanish Shitanshu** — built as a portfolio project targeting the
**Intern Market Analyst** role at Futures First.

CrudeCurve visualizes the WTI crude oil futures curve (front-month vs.
forward-month prices) to classify the market as **contango** or
**backwardation**, and quantifies the **roll yield** an investor
experiences from continuously rolling a long futures position over time.

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
streamlit run app.py
```

Run the unit tests:

```bash
pytest tests/
```

## Data limitations

Free market data APIs (Yahoo Finance via `yfinance`) do not provide the
same always-on ladder of forward-month continuous contracts (e.g. `CL2!`,
`CL3!`, ...) that a paid terminal like Bloomberg or Refinitiv offers.
CrudeCurve fetches:

- `CL=F` — the front-month continuous WTI contract, which is reliably
  updated.
- A set of **dated NYMEX WTI contract symbols** (e.g. `CLZ25.NYM` for
  December 2025 delivery) as forward-month legs. These are real,
  specific tradable contracts, not synthetic data — but they can be
  thinly listed or return stale/no data outside their active trading
  window, since Yahoo Finance's free tier doesn't guarantee continuous
  coverage for every dated contract at every point in time.

The app never fabricates a price for a missing contract: if a symbol
returns no data, it's dropped from the curve; if its most recent data
is more than 5 days old, it's flagged as stale in the dashboard rather
than presented as current. See `config.py` for the exact ticker list
and the reasoning behind it.

The roll-yield simulation similarly works around the lack of a full
historical forward ladder by using the front-month continuous series'
own month-end price behavior as a proxy for the realized roll effect
(see the docstring in `roll_yield.py` for the full explanation).

## Screenshot

_Add a screenshot of the running dashboard here, e.g.:_

```
![CrudeCurve dashboard](docs/screenshot.png)
```

## Project structure

```
crudecurve/
├── README.md
├── requirements.txt
├── config.py            # tickers, lookback window, data source notes
├── data_fetcher.py       # yfinance data pulls
├── term_structure.py     # curve classification + annualized spread
├── roll_yield.py         # 2-year roll yield backtest
├── app.py                # Streamlit dashboard
└── tests/
    └── test_term_structure.py
```
