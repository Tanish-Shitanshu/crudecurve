"""test_market_summary.py — The rule-based summary uses the computed numbers."""

import market_summary
import metrics


def _metrics(curve, history, **kwargs):
    return metrics.build_metrics(curve, history, lookback_years=2, n_contracts=2, **kwargs)


def test_summary_contains_the_computed_numbers(curve, history):
    m = _metrics(curve, history)
    text = market_summary.build_market_summary(m)
    assert "Backwardation" in text
    assert "CLZ26" in text and "$104.00" in text and "CLK27" in text and "$94.00" in text
    assert "-23.08%" in text  # annualised carry
    assert "roll gain" in text
    assert "roll-window proxy" in text
    assert f"{m['risk']['var'][0.95]['observations']} observations" in text


def test_summary_is_deterministic(curve, history):
    m = _metrics(curve, history)
    assert market_summary.build_market_summary(m) == market_summary.build_market_summary(m)


def test_contango_wording_and_roll_cost(curve, history):
    rising = curve.assign(price=[94.0, 96.0, 98.0, 100.0, 102.0, 104.0])
    text = market_summary.build_market_summary(_metrics(rising, history))
    assert "Contango means later delivery costs more" in text
    assert "roll cost" in text


def test_kinked_wording(curve, history):
    kinked = curve.assign(price=[100.0, 98.0, 99.0, 101.0, 103.0, 105.0])
    text = market_summary.build_market_summary(_metrics(kinked, history))
    assert "Kinked" in text and "changes direction" in text


def _set_recent(m, factor95, factor99):
    for confidence, factor in ((0.95, factor95), (0.99, factor99)):
        m["risk"]["var_recent"][confidence]["var_pct"] = m["risk"]["var"][confidence]["var_pct"] * factor


def test_recent_risk_comparison_wording(curve, history):
    m = _metrics(curve, history)
    _set_recent(m, 1.5, 1.5)
    assert "Recent risk is higher" in market_summary.build_market_summary(m)
    _set_recent(m, 0.5, 0.5)
    assert "Recent risk is lower" in market_summary.build_market_summary(m)
    _set_recent(m, 1.0, 1.0)
    assert "Recent risk is similar" in market_summary.build_market_summary(m)


def test_higher_at_either_confidence_level_counts_as_higher(curve, history):
    m = _metrics(curve, history)
    _set_recent(m, 1.0, 1.5)  # only the 99% figure is clearly higher
    assert "Recent risk is higher" in market_summary.build_market_summary(m)


def test_summary_mentions_both_var_levels_and_the_recent_observation_count(curve, history):
    m = _metrics(curve, history)
    text = market_summary.build_market_summary(m)
    assert "At 99%" in text
    assert f"{m['risk']['var_recent'][0.99]['observations']} recent observations" in text


def test_snapshot_note_only_for_snapshots(curve, history):
    assert "saved snapshot" not in market_summary.build_market_summary(_metrics(curve, history))
    assert "saved snapshot" in market_summary.build_market_summary(_metrics(curve, history, source="snapshot"))


def test_limitations_note_mentions_the_key_caveats():
    note = market_summary.LIMITATIONS
    for phrase in ("unofficial", "historical simulation", "proxy", "not investment advice"):
        assert phrase in note
