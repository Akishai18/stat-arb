"""Linear cost model arithmetic."""

import pandas as pd
import pytest

from statarb.costs import LinearCostModel, ZeroCostModel


def test_linear_cost_full_rotation_at_10bps_costs_20bps_total():
    """A full rotation -> turnover = 2.0 -> cost = 2 * 10bps = 20bps."""
    model = LinearCostModel(bps_per_side=10)
    turnover = pd.Series([2.0])
    assert model.cost(turnover).iloc[0] == pytest.approx(0.0020)


def test_linear_cost_partial_rotation():
    model = LinearCostModel(bps_per_side=25)
    turnover = pd.Series([0.5, 1.0, 0.0])
    expected = pd.Series([0.5 * 25e-4, 1.0 * 25e-4, 0.0])
    pd.testing.assert_series_equal(model.cost(turnover), expected)


def test_linear_cost_zero_bps_zero_cost():
    model = LinearCostModel(bps_per_side=0)
    turnover = pd.Series([0.5, 1.0, 0.0])
    assert (model.cost(turnover) == 0).all()


def test_linear_cost_rejects_negative_bps():
    with pytest.raises(ValueError):
        LinearCostModel(bps_per_side=-1)


def test_zero_cost_model_always_zero():
    model = ZeroCostModel()
    out = model.cost(pd.Series([10.0, 0.5]))
    assert (out == 0).all()
