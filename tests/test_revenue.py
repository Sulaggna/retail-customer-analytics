import numpy as np
import pytest

from retail_analytics.revenue import lmdi_bridge


def test_lmdi_contributions_sum_exactly_to_total_change():
    before = {"sales": 2 * 3 * 50.0, "customers": 2, "freq": 3, "aov": 50.0}
    after = {"sales": 3 * 2.5 * 55.0, "customers": 3, "freq": 2.5, "aov": 55.0}
    c = lmdi_bridge(before, after, "sales")
    assert c.sum() == pytest.approx(after["sales"] - before["sales"])


def test_lmdi_signs_follow_driver_direction():
    before = {"s": 100.0, "a": 10.0, "b": 10.0}
    after = {"s": 99.0, "a": 11.0, "b": 9.0}
    c = lmdi_bridge(before, after, "s")
    assert c["a"] > 0 > c["b"]


def test_lmdi_unchanged_driver_contributes_zero():
    before = {"s": 100.0, "a": 10.0, "b": 10.0}
    after = {"s": 120.0, "a": 12.0, "b": 10.0}
    c = lmdi_bridge(before, after, "s")
    assert np.isclose(c["b"], 0.0)
