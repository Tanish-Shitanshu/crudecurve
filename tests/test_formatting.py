"""test_formatting.py — The sign always goes in front of the dollar sign."""


from crudecurve.formatting import format_optional, format_pct, format_signed_usd, format_usd


def test_usd_negative_has_minus_before_the_dollar_sign():
    assert format_usd(-1.88) == "-$1.88"
    assert format_usd(1.88) == "$1.88"


def test_usd_uses_thousands_separators_and_decimals():
    assert format_usd(104120) == "$104,120.00"
    assert format_usd(104120.4, 0) == "$104,120"


def test_signed_usd_always_shows_a_sign():
    assert format_signed_usd(1.88) == "+$1.88"
    assert format_signed_usd(-1.88) == "-$1.88"
    assert format_signed_usd(0) == "+$0.00"


def test_pct_takes_percent_points():
    assert format_pct(3.944) == "3.94%"
    assert format_pct(3.944, decimals=1) == "3.9%"
    assert format_pct(-25.72, signed=True) == "-25.72%"
    assert format_pct(3.1, signed=True) == "+3.10%"


def test_optional_shows_a_placeholder_for_missing_values():
    assert format_optional(None, format_usd) == "n/a"
    assert format_optional(2.5, format_usd) == "$2.50"
