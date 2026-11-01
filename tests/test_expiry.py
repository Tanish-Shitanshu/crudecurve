"""
test_expiry.py — The NYMEX WTI expiry rule, checked against real, known
contract expiry dates.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from expiry import contract_expiry


def test_december_2025_contract_expires_20_nov_2025():
    # 25 Nov 2025 is a Tuesday: 3 business days earlier is Thursday 20 Nov.
    assert contract_expiry(2025, 12) == date(2025, 11, 20)


def test_when_the_25th_is_a_weekend_count_back_from_the_friday_before():
    # 25 Oct 2026 is a Sunday -> anchor Fri 23 Oct -> 3 business days = Tue 20 Oct.
    assert contract_expiry(2026, 11) == date(2026, 10, 20)


def test_when_the_25th_is_a_holiday_count_back_from_the_day_before():
    # 25 Dec 2025 is Christmas -> anchor Wed 24 Dec -> 3 business days = Fri 19 Dec.
    assert contract_expiry(2026, 1) == date(2025, 12, 19)


def test_january_delivery_uses_december_of_the_previous_year():
    assert contract_expiry(2027, 1).year == 2026
    assert contract_expiry(2027, 1).month == 12


# --- roll_dates --------------------------------------------------------------

from expiry import roll_dates


def test_roll_day_is_the_first_business_day_after_expiry():
    # CLX26 expires Tue 20 Oct 2026, so CL=F switches contracts on Wed 21 Oct.
    assert date(2026, 10, 21) in roll_dates(date(2026, 10, 1), date(2026, 10, 31))
    # CLZ25 expires Thu 20 Nov 2025 -> roll day Fri 21 Nov 2025.
    assert roll_dates(date(2025, 11, 1), date(2025, 11, 30)) == [date(2025, 11, 21)]


def test_roll_dates_only_returns_days_inside_the_window():
    assert roll_dates(date(2026, 10, 22), date(2026, 11, 19)) == []
    assert roll_dates(date(2026, 10, 21), date(2026, 10, 21)) == [date(2026, 10, 21)]


def test_there_is_about_one_roll_day_per_month():
    days = roll_dates(date(2025, 1, 1), date(2025, 12, 31))
    assert len(days) == 12
    assert days == sorted(days)
