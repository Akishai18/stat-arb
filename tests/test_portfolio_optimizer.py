"""cvxpy optimizer: constraint respect + closed-form sanity checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.portfolio.optimizer import OptimizerInfeasible, optimize_one_day


@pytest.fixture
def two_asset_setup():
    tickers = ["A", "B"]
    alpha = pd.Series([0.10, -0.10], index=tickers)
    cov = pd.DataFrame(
        [[0.04, 0.0], [0.0, 0.04]],  # 20% vol, uncorrelated
        index=tickers, columns=tickers,
    )
    prev = pd.Series([0.0, 0.0], index=tickers)
    return alpha, cov, prev


def test_unconstrained_solution_signs_match_alpha(two_asset_setup):
    """With positive alpha for A and negative for B, the optimizer should
    go long A and short B."""
    alpha, cov, prev = two_asset_setup
    w = optimize_one_day(
        alpha, cov, prev,
        gross_cap=1.0, net_cap=1.0, position_cap=1.0,
        risk_aversion=1.0,
    )
    assert w["A"] > 0
    assert w["B"] < 0


def test_gross_cap_is_respected(two_asset_setup):
    """sum(|w|) must not exceed gross_cap."""
    alpha, cov, prev = two_asset_setup
    # Loose risk aversion + tiny cov -> wants huge positions; gross_cap stops it.
    w = optimize_one_day(
        alpha, cov, prev,
        gross_cap=0.5, net_cap=1.0, position_cap=1.0,
        risk_aversion=0.01,
    )
    assert w.abs().sum() <= 0.5 + 1e-3


def test_position_cap_is_respected(two_asset_setup):
    alpha, cov, prev = two_asset_setup
    w = optimize_one_day(
        alpha, cov, prev,
        gross_cap=2.0, net_cap=1.0, position_cap=0.1,
        risk_aversion=0.01,
    )
    # OSQP default tolerance is ~1e-3 to 1e-4; allow a small overshoot
    assert (w.abs() <= 0.1 + 1e-3).all()


def test_net_cap_is_respected():
    """With both alphas positive, optimizer wants to go long both -> net
    cap must enforce dollar-neutrality."""
    tickers = ["A", "B"]
    alpha = pd.Series([0.10, 0.05], index=tickers)
    cov = pd.DataFrame(np.eye(2) * 0.04, index=tickers, columns=tickers)
    prev = pd.Series([0.0, 0.0], index=tickers)
    w = optimize_one_day(
        alpha, cov, prev,
        gross_cap=1.0, net_cap=0.0, position_cap=1.0,
        risk_aversion=0.01,
    )
    assert abs(w.sum()) <= 1e-6


def test_turnover_cap_is_respected():
    """Hard turnover cap clips the rebalance distance from prev weights."""
    tickers = ["A", "B"]
    alpha = pd.Series([1.0, -1.0], index=tickers)
    cov = pd.DataFrame(np.eye(2) * 0.01, index=tickers, columns=tickers)
    prev = pd.Series([0.5, -0.5], index=tickers)
    # Start at full quantile; let alpha drag us elsewhere but cap turnover at 0.1
    w = optimize_one_day(
        alpha, cov, prev,
        gross_cap=1.0, net_cap=0.05, position_cap=1.0,
        risk_aversion=0.01, turnover_cap=0.1,
    )
    turnover = (w - prev).abs().sum()
    assert turnover <= 0.1 + 1e-3


def test_zero_alpha_zero_weights():
    """No signal -> the only thing in the objective is risk + cost penalty,
    so w = 0 dominates."""
    tickers = ["A", "B", "C"]
    alpha = pd.Series([0.0, 0.0, 0.0], index=tickers)
    cov = pd.DataFrame(np.eye(3) * 0.04, index=tickers, columns=tickers)
    prev = pd.Series([0.0, 0.0, 0.0], index=tickers)
    w = optimize_one_day(alpha, cov, prev, risk_aversion=1.0)
    np.testing.assert_allclose(w.to_numpy(), 0.0, atol=1e-6)


def test_cost_penalty_discourages_rebalance():
    """High turnover cost should keep weights close to prev_weights."""
    tickers = ["A", "B"]
    alpha = pd.Series([0.01, -0.01], index=tickers)
    cov = pd.DataFrame(np.eye(2) * 0.04, index=tickers, columns=tickers)
    prev = pd.Series([0.3, -0.3], index=tickers)
    w_no_cost = optimize_one_day(
        alpha, cov, prev, cost_bps_per_side=0, risk_aversion=0.1,
    )
    # Huge cost -> any move costs more than the alpha gain
    w_high_cost = optimize_one_day(
        alpha, cov, prev, cost_bps_per_side=10_000, risk_aversion=0.1,
    )
    # Distance from prev should be smaller with high cost
    no_cost_dist = (w_no_cost - prev).abs().sum()
    high_cost_dist = (w_high_cost - prev).abs().sum()
    assert high_cost_dist < no_cost_dist


def test_nan_alpha_treated_as_zero():
    """NaN alpha on an asset should not break the solver and should not
    yield strong positions on that asset."""
    tickers = ["A", "B"]
    alpha = pd.Series([0.10, float("nan")], index=tickers)
    cov = pd.DataFrame(np.eye(2) * 0.04, index=tickers, columns=tickers)
    prev = pd.Series([0.0, 0.0], index=tickers)
    w = optimize_one_day(alpha, cov, prev, risk_aversion=1.0)
    assert w.notna().all()
    assert abs(w["B"]) < abs(w["A"])  # B has no signal


def test_infeasible_raises():
    """Set up an infeasible problem (position cap incompatible with gross)."""
    tickers = ["A", "B"]
    alpha = pd.Series([0.1, 0.1], index=tickers)
    cov = pd.DataFrame(np.eye(2) * 0.04, index=tickers, columns=tickers)
    prev = pd.Series([0.0, 0.0], index=tickers)
    # gross_cap < 0 is plainly infeasible
    with pytest.raises(OptimizerInfeasible):
        optimize_one_day(
            alpha, cov, prev,
            gross_cap=-1.0,
        )
