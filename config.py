"""
config.py — All the "knobs" for CrudeCurve in one place.

Keeping tickers, windows, and constants here (instead of scattered magic
numbers in the code) means anyone reviewing the project can see exactly
what assumptions drive the analysis, and change them in one spot.
"""

# --- Data sources -------------------------------------------------------
# Everything comes from Yahoo Finance via yfinance.
#
# Front-month history: CL=F is the continuous front-month (nearest expiry)
# WTI contract. It feeds the 2-year daily history for the roll-yield
# backtest in roll_yield.py.
FRONT_MONTH_TICKER = "CL=F"

# Current term structure: individual dated NYMEX WTI contracts, using
# Yahoo's per-contract symbols CL<month code><2-digit year>.NYM, e.g.
# CLZ26.NYM = December 2026 delivery. Candidates are generated from the
# current month forward; contracts with no data (already expired) or an
# old last bar are dropped, and the first CURVE_CONTRACT_COUNT live
# contracts form the curve.
CONTRACT_SYMBOL_TEMPLATE = "CL{month_code}{year:02d}.NYM"
FUTURES_MONTH_CODES = "FGHJKMNQUVXZ"  # Jan..Dec (CME month codes)
CANDIDATE_CONTRACT_MONTHS = 9  # delivery months to try, starting this month
CURVE_CONTRACT_COUNT = 6  # live contracts kept for the curve

# Consecutive WTI contracts are one delivery month apart (used to turn the
# front-to-back price gap into an annualized percentage).
CONTRACT_MONTH_SPACING = 1

# --- Storage (SQLite) ----------------------------------------------------
# One local file, created on first run. It is git-ignored: it only holds
# data fetched from Yahoo Finance, never anything secret.
DB_PATH = "data/crudecurve.db"

# Yahoo suffix for NYMEX contracts, used when fetching a contract's history.
YAHOO_SYMBOL_SUFFIX = ".NYM"

# Daily closes kept per live contract. First run downloads BACKFILL_PERIOD;
# later runs only top up with REFRESH_PERIOD (if the last stored bar is
# not older than REFRESH_MAX_GAP_DAYS, otherwise we backfill again).
BACKFILL_PERIOD = "1y"
REFRESH_PERIOD = "1mo"
REFRESH_MAX_GAP_DAYS = 20

# --- Validation rules (see validation.py) ----------------------------------
# A price is "stale" if the most recent available close is older than this
# many calendar days. 5 days covers a normal long weekend/holiday without
# masking a genuinely dead/expired contract.
STALE_DATA_THRESHOLD_DAYS = 5

# A curve needs at least this many live contracts to be usable.
MIN_LIVE_CONTRACTS = 4

# A contract whose price is more than this % away from the average of its
# neighbours on the curve is flagged (not dropped) as a possible bad print.
OUTLIER_PCT = 10.0

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
