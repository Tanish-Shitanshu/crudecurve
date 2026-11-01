"""
expiry.py — When does a NYMEX WTI futures contract stop trading?

The exchange rule: trading in a contract ends 3 business days before the
25th calendar day of the month BEFORE the delivery month. If the 25th is
not a business day, count back from the business day before the 25th.

Example: the December 2026 contract (CLZ26). The 25th of November 2026 is
a Wednesday (a business day), and 3 business days before it is Friday
20 November 2026, so CLZ26 stops trading on 2026-11-20.

Approximation: business days here skip weekends and US federal holidays
(pandas' USFederalHolidayCalendar). The exchange calendar differs slightly
(for example it closes on Good Friday), so a computed date can be off by
a day in rare cases.
"""

from datetime import date

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

_BUSINESS_DAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())


def contract_expiry(delivery_year: int, delivery_month: int) -> date:
    """Last trading day of the contract delivering in this year and month."""
    # The 25th of the month before delivery (DateOffset handles January -> December).
    the_25th = pd.Timestamp(delivery_year, delivery_month, 25) - pd.DateOffset(months=1)
    # rollback() leaves a business day alone, otherwise moves to the one before it.
    anchor = _BUSINESS_DAY.rollback(the_25th)
    return (anchor - 3 * _BUSINESS_DAY).date()


def roll_dates(start: date, end: date) -> list:
    """
    The "roll days" between start and end (inclusive): the first business
    day after each contract's last trading day.

    Why: Yahoo's CL=F is one unadjusted series that switches from the
    expiring contract to the next one when the old one expires. On that
    day the series jumps by the price gap between the two contracts, which
    is not a real market move. Risk calculations leave these days out.
    """
    roll_days = []
    # A contract delivering in month M expires in month M-1, so delivery
    # months from `start`'s month to two months after `end` cover every
    # expiry in the window.
    delivery = pd.Timestamp(start.year, start.month, 1)
    last_delivery = pd.Timestamp(end.year, end.month, 1) + pd.DateOffset(months=2)
    while delivery <= last_delivery:
        expiry = contract_expiry(delivery.year, delivery.month)
        roll_day = (pd.Timestamp(expiry) + _BUSINESS_DAY).date()
        if start <= roll_day <= end:
            roll_days.append(roll_day)
        delivery += pd.DateOffset(months=1)
    return roll_days
