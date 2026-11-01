# Methodology

Every number in CrudeCurve is computed from Yahoo Finance data by the code in this
repository. This page lists the formulas, sign conventions, assumptions, validation
rules and limitations. It is also shown in the dashboard's Methodology tab.

## Data

| Data | Source | Used for |
|---|---|---|
| Latest close of individual NYMEX WTI contracts (symbols such as `CLZ26.NYM`) | Yahoo Finance via `yfinance` | Current futures curve, regime, carry |
| About one year of daily closes per live contract | Yahoo Finance, stored in SQLite | Calendar-spread history and SQL analysis |
| Continuous front-month series `CL=F` (5 years) | Yahoo Finance | Returns, volatility, VaR, drawdown, roll-window proxy |

Yahoo Finance is an unofficial, free source. Prices are daily closes and can be delayed;
they are not official exchange settlements.

## Term structure

The curve is the first six live contracts, in delivery order. `month_index` is the number
of delivery months after the front contract, so a missing month leaves a gap and the
spread stays correctly scaled.

**Regime** (every consecutive pair of prices is compared, front to back):

- every step rises: **Contango**
- every step falls: **Backwardation**
- the direction changes along the curve: **Kinked (net Contango)** or **Kinked (net Backwardation)**,
  using the front-vs-back relationship
- front and back within 0.05%: **Flat**

**Annualised carry** (the curve's front-to-back spread, stretched to a year):

$$
\text{carry\%} = \frac{P_{\text{back}} - P_{\text{front}}}{P_{\text{front}}} \times \frac{12}{\text{months between}} \times 100
$$

Positive = contango (back contracts cost more). Negative = backwardation.

## Roll gain or cost (curve-based, the headline roll metric)

A long position must keep rolling into the next contract. If the curve stays as it is today:

$$
\text{roll gain per year} = -\frac{\text{carry\%}}{100} \times \text{notional}
$$

with notional = front price x 1,000 barrels x number of contracts.

Sign convention (long position): **positive = gain** (backwardation: selling the dear expiring
contract and buying the cheaper next one), **negative = cost** (contango). This is an estimate
for an unchanged curve, not a forecast.

## Roll-window proxy (the 2-year "roll yield" chart)

This is a **proxy, not a true roll yield**. A true roll yield needs the price gap between the
expiring and the next contract on each roll date; free data does not provide historical dated
contracts. Instead, for each calendar month the proxy sums the daily price changes of `CL=F`
over the last 5 trading days of the month, and accumulates that over two years. It is shown
next to the cumulative spot price change so the two can be compared. The window is a calendar
convention, not the actual contract expiry, so treat the number as indicative only.

## Risk metrics (`CL=F`, roll days excluded)

**Daily return** = today's close / yesterday's close - 1.

**Roll days.** `CL=F` is one unadjusted series that switches from the expiring contract to the
next one when the old one expires, so its close jumps by the gap between the two contracts on
that day. That jump is not a market move. The NYMEX rule is used to find expiries: trading
ends 3 business days before the 25th calendar day of the month before delivery (counting back
from the previous business day if the 25th is not one). The roll day is the first business day
after expiry. This matches how `CL=F` actually switched at the October 2026 roll. Business days
skip weekends and US federal holidays, so a date can be off by one day in rare cases. Roll days
are excluded from returns used for volatility, VaR and worst day, and are treated as a 0%
return when building the price index for drawdown.

**Trade-off.** About 5% of trading days are roll days. A few of them can also contain a real
market move, which is then discarded too, so VaR may be slightly understated.

**Volatility** = standard deviation of the last 21 non-roll daily returns x sqrt(252)
(annualised).

**Historical-simulation 1-day VaR** at confidence c: take the past non-roll daily returns,
find the (1 - c) percentile, and apply it to the position's value:

$$
\text{VaR}_c = -\,\text{percentile}_{(1-c)}(\text{returns}) \times \text{notional}
$$

VaR is shown as a positive loss. "On 95% of past days the one-day loss was smaller than this."
The number of observations used is always shown next to it: the 99% figure rests on only the
worst 1% of days, so it is rough, especially over short windows.

Two windows are shown side by side: the selected lookback (2 or 5 years) and the last 12
months. Comparing them shows how recent conditions differ from the longer history.

**Max drawdown** = the largest peak-to-trough fall of the roll-gap-free price index
(negative). **Worst day** = the lowest single non-roll daily return.

**Large moves are not removed.** Big daily moves that are not roll days are kept, because they
are part of the risk being measured. In this data (to 2026-10-30) there is a volatility cluster
in March to April 2026: daily volatility rose from about 1.5% in late 2025 to about 6%, with
front-month moves much larger than deferred contracts in the same direction, consistent with a
front-month squeeze in strong backwardation. The cause of these moves was not verified. The
effect is visible in the last-12-months VaR being higher than the 5-year VaR.

**Assumption.** Historical simulation assumes the past is representative of the future.

## Validation rules

Applied on every refresh (`crudecurve/validation.py`); every outcome is logged to SQLite.

| Rule | Level | Result when violated |
|---|---|---|
| `not_expired` | contract | Past its expiry date: **skipped** (expected, not an error). A live contract with no data: fail |
| `price_valid` | contract | Price missing, not finite, or not greater than 0: fail, contract left out |
| `price_fresh` | contract | Last close older than 5 days: fail, contract left out |
| `no_duplicate_delivery_months` | curve | Two contracts with the same delivery month: curve unusable |
| `month_index_increasing` | curve | `month_index` not strictly increasing: curve unusable |
| `min_live_contracts` | curve | Fewer than 4 live contracts: curve unusable |
| `outlier_check` | contract | More than 10% away from the average of its neighbours: **flagged**, kept |

If the live curve is unusable (for example Yahoo is unreachable) the app shows the most
recent saved snapshot with a clear banner, never presenting old data as live. If nothing has
been saved yet, it shows an error instead.

## Storage

A local SQLite file (`data/crudecurve.db`, not committed) holds `curve_snapshots`,
`contract_prices` and `data_quality_log`. Saves are idempotent (upserts). On Streamlit
Community Cloud the disk is ephemeral, so the file is rebuilt after a restart.

## Limitations

- Yahoo Finance data is unofficial and delayed, and symbols can change without notice.
- Prices are daily closes; moves within a day are invisible.
- The roll-window yield is a proxy, not a true roll yield.
- VaR is historical simulation on daily closes, assumes the past is representative of the
  future, and excludes roll days (about 5% of days).
- A 99% VaR (especially over 12 months) rests on very few observations.
- Business-day calendars are approximate (US federal holidays, not the exchange calendar).
- This tool is not investment advice.
