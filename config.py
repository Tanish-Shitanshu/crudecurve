"""
config.py — All the "knobs" for CrudeCurve in one place.

Keeping tickers, windows, and constants here (instead of scattered magic
numbers in the code) means anyone reviewing the project can see exactly
what assumptions drive the analysis, and change them in one spot.
"""

# --- Data sources -------------------------------------------------------
# yfinance exposes CME WTI Crude Oil futures as a single continuous
# front-month series:
#   CL=F  -> front-month (nearest expiry) continuous contract
# This series is reliable and used for the 2-year daily history that
# feeds the roll-yield backtest in roll_yield.py.
FRONT_MONTH_TICKER = "CL=F"

# LIMITATION (see README "Data Limitations" section for full detail):
# Yahoo Finance (via yfinance) does not publish dated forward-month WTI
# contracts (e.g. a December-2025-delivery contract) on its free tier —
# verified directly: those symbols return no data at all. So the actual
# term structure (front vs. forward months) is instead sourced from the
# U.S. Energy Information Administration's free, official Open Data API,
# which publishes daily settlement prices for WTI "Future Contract 1"
# through "Future Contract 4" (Contract 1 = front month, Contract 4 =
# roughly 4 months out). This is real government market data, not a
# synthetic estimate — it just gives 4 points instead of a long ladder.
#
# EIA v2 API route: /v2/petroleum/pri/fut/data/
# Series IDs (facet "series"), confirmed via the EIA API browser under
# Petroleum > Prices > Spot & Futures Prices > WTI Futures:
#   RCLC1 = Cushing, OK Crude Oil Future Contract 1 (Dollars per Barrel)
#   RCLC2 = Cushing, OK Crude Oil Future Contract 2
#   RCLC3 = Cushing, OK Crude Oil Future Contract 3
#   RCLC4 = Cushing, OK Crude Oil Future Contract 4
# Contracts roll roughly monthly, so Contract 1 -> Contract 4 spans
# roughly 3 months of separation (used as EIA_CONTRACT_MONTH_SPACING
# below for the annualized spread calculation).
EIA_API_BASE_URL = "https://api.eia.gov/v2/petroleum/pri/fut/data/"
EIA_CONTRACT_SERIES = ["RCLC1", "RCLC2", "RCLC3", "RCLC4"]

# The EIA API key is a secret and must never be hardcoded here. It is
# loaded from the EIA_API_KEY environment variable (see .env, which is
# git-ignored) by data_fetcher.py using python-dotenv. Register a free
# key at https://www.eia.gov/opendata/register.php.
EIA_API_KEY_ENV_VAR = "EIA_API_KEY"

# Approximate month spacing between consecutive EIA WTI futures
# contracts (Contract 1, 2, 3, 4 are consecutive monthly deliveries).
EIA_CONTRACT_MONTH_SPACING = 1

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
