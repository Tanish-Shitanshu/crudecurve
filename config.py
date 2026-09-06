"""
config.py — All the "knobs" for CrudeCurve in one place.

Keeping tickers, windows, and constants here (instead of scattered magic
numbers in the code) means anyone reviewing the project can see exactly
what assumptions drive the analysis, and change them in one spot.
"""

# --- Data source tickers -----------------------------------------------
# yfinance exposes CME WTI Crude Oil futures as continuous contracts:
#   CL=F  -> front-month (nearest expiry) continuous contract
#   CL1.F..CL6.F are NOT reliably available on Yahoo Finance for retail
#   free access. In practice, Yahoo only reliably publishes the single
#   front-month continuous series (CL=F) plus a small number of dated
#   contract symbols (e.g. CLZ25.NYM for Dec 2025 WTI) that are only
#   listed close to their trading window.
#
# LIMITATION (see README "Data Limitations" section for full detail):
# Free APIs (yfinance/Yahoo Finance) do not provide a clean, always-on
# ladder of forward-month continuous contracts (CL2!, CL3!, ... like a
# paid terminal such as Bloomberg/Refinitiv would). To build a real term
# structure without paying for data, CrudeCurve fetches the front-month
# continuous contract (CL=F) plus a set of dated NYMEX WTI futures
# symbols for specific expiry months. These dated symbols are the actual
# tradable forward-month contracts, not synthetic/faked prices — but
# they can go stale or unlisted outside their active trading window,
# which is why data_fetcher.py checks each fetch and reports staleness
# instead of silently failing.
FRONT_MONTH_TICKER = "CL=F"

# Dated NYMEX WTI contract symbols: CL + month code + 2-digit year.
# Month codes follow the standard futures naming convention:
# F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun, N=Jul, Q=Aug, U=Sep, V=Oct,
# X=Nov, Z=Dec. Example: "CLZ25.NYM" = WTI Crude, December 2025, NYMEX.
# We list the next 5 calendar months after "front month" as forward legs.
FORWARD_MONTH_TICKERS = [
    "CLX25.NYM",  # Nov 2025
    "CLZ25.NYM",  # Dec 2025
    "CLF26.NYM",  # Jan 2026
    "CLG26.NYM",  # Feb 2026
    "CLH26.NYM",  # Mar 2026
]

# --- Lookback windows -----------------------------------------------
# 2 years of daily history, matching the roll-yield backtest requirement.
ROLL_YIELD_LOOKBACK_YEARS = 2

# Number of trading days considered "1 week" before a contract's rough
# monthly expiry, used to decide when to roll from one contract to the
# next in the roll-yield simulation. NYMEX WTI contracts expire ~3
# business days before the 25th of the month prior to delivery, but for
# a portfolio-level backtest using only front-month daily closes, we
# approximate "roll day" as 5 trading days before each month's end.
ROLL_DAYS_BEFORE_MONTH_END = 5

# --- Annualization ----------------------------------------------------
# Used to convert a price spread between two contract months into an
# annualized percentage: there are 12 months in a year.
MONTHS_PER_YEAR = 12

# Approximate number of trading days in a year, used to annualize
# daily-return based statistics if needed.
TRADING_DAYS_PER_YEAR = 252
