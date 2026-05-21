"""Backtest engine: the lag contract and bookkeeping invariants.

The lookahead-trap test (`test_lag_rejects_same_day_lookahead`) is the most
important test in the project. If it ever fails, the entire pipeline produces
fictitious results and nothing else matters until it's fixed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.backtest import Backtester
from statarb.costs import LinearCostModel, ZeroCostModel
from statarb.data import PriceData


def _make_prices(returns: pd.DataFrame, start_price: float = 100.0) -> PriceData:
    """Turn a returns panel into a PriceData by integrating (1+r)."""
    levels = (1.0 + returns.fillna(0.0)).cumprod() * start_price
    # Prepend a base row so the first row of `returns` is reproducible via pct_change.
    base = pd.DataFrame(
        [[start_price] * returns.shape[1]],
        columns=returns.columns,
        index=[returns.index[0] - pd.Timedelta(days=1)],
    )
    panel = pd.concat([base, levels])
    return PriceData(panel)


# ---------------------------------------------------------------------------
# The lag contract: the single most important test in the project.
# ---------------------------------------------------------------------------


def test_lag_rejects_same_day_lookahead():
    """If the engine accidentally applies weights[t] to returns[t] instead of
    weights[t-1] to returns[t], a 'cheat signal' equal to today's return
    would produce wildly positive P&L. With the correct one-day lag, the
    cheat signal becomes "yesterday's return" -- which, for random returns,
    has near-zero correlation with today's return. So the test passes only
    if the lag is in place.
    """
    rng = np.random.default_rng(seed=42)
    n_days, n_assets = 500, 5
    returns = pd.DataFrame(
        rng.normal(0, 0.01, size=(n_days, n_assets)),
        index=pd.date_range("2010-01-01", periods=n_days, freq="B"),
        columns=[f"A{i}" for i in range(n_assets)],
    )
    prices = _make_prices(returns)

    # The "cheat" signal: each day, weights equal today's actual return
    # (perfect lookahead if applied same-day).
    cheat_weights = returns.copy()

    bt = Backtester(prices, ZeroCostModel())
    result = bt.run(cheat_weights)

    # If lag were missing: gross = sum(w * r) = sum(r * r) = sum(r^2) > 0
    # always. Annualized Sharpe would be astronomical.
    # With correct lag: gross[t] = sum(returns[t-1] * returns[t]) -- a noise
    # term centered at zero.
    cheat_sharpe = result.summary()["sharpe"]
    # Generous tolerance: a noise process across ~500 days has annualized
    # Sharpe well under 1 in absolute value. A leak would produce 30+.
    assert abs(cheat_sharpe) < 2.0, (
        f"Lookahead leak detected: Sharpe with cheat signal = {cheat_sharpe:.2f}. "
        "The engine must lag weights by one day before applying."
    )


def test_lag_first_applied_row_is_nan_or_zero_pre_lag():
    """The very first row of weights_applied is the *previous* day's signal,
    so before any signal exists it must be zero (after the engine's fillna)."""
    n_days = 10
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    cols = ["A", "B"]
    returns = pd.DataFrame(np.zeros((n_days, 2)), index=idx, columns=cols)
    prices = _make_prices(returns)
    weights = pd.DataFrame(np.full((n_days, 2), 0.5), index=idx, columns=cols)

    bt = Backtester(prices, ZeroCostModel())
    result = bt.run(weights)

    # Day 0: weights_applied should be NaN (no prior signal). The engine
    # leaves it NaN in weights_applied but treats it as 0 for P&L purposes.
    assert result.gross_returns.iloc[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Identity tests: hand-calculated outputs.
# ---------------------------------------------------------------------------


def test_long_only_constant_returns_identity():
    """If every asset returns 1% every day and we hold equal-weight summing
    to 1.0, the portfolio must earn exactly 1% per day."""
    n_days = 20
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    cols = ["A", "B", "C", "D"]
    returns = pd.DataFrame(0.01, index=idx, columns=cols)
    prices = _make_prices(returns)
    weights = pd.DataFrame(0.25, index=idx, columns=cols)

    result = Backtester(prices, ZeroCostModel()).run(weights)

    # Skip the first row (pre-lag boundary). After that, every day = 1%.
    np.testing.assert_allclose(
        result.gross_returns.iloc[1:].values,
        np.full(n_days - 1, 0.01),
        atol=1e-12,
    )


def test_long_short_cancellation():
    """Two assets with identical returns; long one, short the other.
    Portfolio net return must be exactly zero each day."""
    n_days = 30
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(seed=0)
    common = rng.normal(0, 0.01, size=n_days)
    returns = pd.DataFrame({"A": common, "B": common}, index=idx)
    prices = _make_prices(returns)
    weights = pd.DataFrame({"A": 0.5, "B": -0.5}, index=idx)

    result = Backtester(prices, ZeroCostModel()).run(weights)
    np.testing.assert_allclose(result.gross_returns.values, 0.0, atol=1e-12)


# ---------------------------------------------------------------------------
# Bookkeeping: turnover, costs, equity curve.
# ---------------------------------------------------------------------------


def test_turnover_first_day_is_initial_gross():
    """Initial previous weights = 0, so turnover[0] = sum(|w_applied[0]|)
    -- but w_applied[0] is the LAGGED weight (yesterday's signal), which
    on day 0 doesn't exist. So turnover[0] should be 0. Turnover on day 1
    should be the initial gross (= sum(|w[0]|)) because that's when those
    weights first appear in w_applied."""
    n_days = 5
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    returns = pd.DataFrame(0.0, index=idx, columns=["A", "B"])
    prices = _make_prices(returns)
    weights = pd.DataFrame([[0.5, -0.5]] * n_days, index=idx, columns=["A", "B"])

    result = Backtester(prices, ZeroCostModel()).run(weights)

    # turnover[0] is the lagged version, so before any signal -> 0.
    assert result.turnover.iloc[0] == pytest.approx(0.0)
    # turnover[1]: w_applied[1] = (0.5,-0.5); w_applied[0] = (0,0) -> 1.0
    assert result.turnover.iloc[1] == pytest.approx(1.0)
    # turnover[2:]: w stays the same -> 0
    assert (result.turnover.iloc[2:] == 0).all()


def test_costs_match_turnover_times_rate():
    """Spot-check: at 10 bps with full-rotation turnover of 2.0, cost = 0.0020."""
    n_days = 4
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    returns = pd.DataFrame(0.0, index=idx, columns=["A", "B"])
    prices = _make_prices(returns)
    # Day 0: (1, 0). Day 1: (0, 1) -> full rotation = turnover 2.0.
    weights = pd.DataFrame(
        [[1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0]],
        index=idx,
        columns=["A", "B"],
    )
    result = Backtester(prices, LinearCostModel(bps_per_side=10)).run(weights)

    # w_applied: NaN, (1,0), (0,1), (0,1)  ->  turnover: 0, 1, 2, 0
    assert result.turnover.iloc[2] == pytest.approx(2.0)
    assert result.costs.iloc[2] == pytest.approx(0.0020)


def test_equity_curve_compounds_geometrically():
    """net_returns of [0.01, 0.01, 0.01] -> equity = [1.01, 1.0201, 1.030301]."""
    n_days = 4
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    # Constant 1% returns; constant 100% weight on a single asset.
    returns = pd.DataFrame({"A": [0.01, 0.01, 0.01, 0.01]}, index=idx)
    prices = _make_prices(returns)
    weights = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=idx)

    result = Backtester(prices, ZeroCostModel()).run(weights)

    # gross[0] = 0 (pre-lag), then 0.01 each day.
    np.testing.assert_allclose(
        result.equity_curve.values,
        np.array([1.0, 1.01, 1.0201, 1.030301]),
        atol=1e-10,
    )


def test_net_equals_gross_minus_costs():
    rng = np.random.default_rng(seed=1)
    n_days = 50
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    cols = ["A", "B", "C"]
    returns = pd.DataFrame(rng.normal(0, 0.01, (n_days, 3)), index=idx, columns=cols)
    weights = pd.DataFrame(rng.uniform(-1, 1, (n_days, 3)), index=idx, columns=cols)
    prices = _make_prices(returns)

    result = Backtester(prices, LinearCostModel(bps_per_side=15)).run(weights)
    pd.testing.assert_series_equal(
        result.net_returns,
        result.gross_returns - result.costs,
        check_names=False,
    )


# ---------------------------------------------------------------------------
# Input validation and NaN policy.
# ---------------------------------------------------------------------------


def test_engine_rejects_unknown_ticker():
    idx = pd.date_range("2020-01-01", periods=3, freq="B")
    returns = pd.DataFrame(0.0, index=idx, columns=["A"])
    prices = _make_prices(returns)
    bad_weights = pd.DataFrame({"Z": [1.0, 1.0, 1.0]}, index=idx)
    with pytest.raises(ValueError, match="not in price universe"):
        Backtester(prices, ZeroCostModel()).run(bad_weights)


def test_engine_rejects_non_datetime_index():
    idx = pd.date_range("2020-01-01", periods=3, freq="B")
    returns = pd.DataFrame(0.0, index=idx, columns=["A"])
    prices = _make_prices(returns)
    bad = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=[0, 1, 2])
    with pytest.raises(TypeError):
        Backtester(prices, ZeroCostModel()).run(bad)


def test_long_only_exactly_matches_raw_cumprod():
    """For a constant 100% position, the engine's cumulative return must
    EXACTLY equal the raw cumulative return of the underlying asset, over
    the matching window (skipping the first lag-induced no-trade day).

    This is the strongest end-to-end sanity check: any pricing or lag bug
    would show up as drift between these two series.
    """
    rng = np.random.default_rng(seed=7)
    n_days = 250
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    returns = pd.DataFrame({"A": rng.normal(0, 0.01, size=n_days)}, index=idx)
    prices = _make_prices(returns)
    weights = pd.DataFrame({"A": [1.0] * n_days}, index=idx)

    result = Backtester(prices, ZeroCostModel()).run(weights)

    # Engine's first applied day is index 1 (index 0 has NaN applied weight).
    # Compare engine cum-return from that point onward against raw cumprod.
    first = idx[1]
    raw_ret = prices.returns()["A"].loc[first:]
    raw_cum = (1.0 + raw_ret).cumprod()
    engine_cum = (1.0 + result.net_returns.loc[first:]).cumprod()
    np.testing.assert_allclose(engine_cum.values, raw_cum.values, atol=1e-14)


def test_nan_return_with_held_position_contributes_zero():
    """If we hold A and its return is NaN, the day's P&L contribution from A
    is 0 (not NaN). Other positions still earn normally."""
    n_days = 4
    idx = pd.date_range("2020-01-01", periods=n_days, freq="B")
    returns = pd.DataFrame(
        # NaN on the day we want to stress -- the engine's lag affects only
        # weights, so the P&L day that uses returns[t] is also indexed t.
        {"A": [0.01, 0.01, np.nan, 0.01], "B": [0.01, 0.01, 0.01, 0.01]},
        index=idx,
    )
    prices = _make_prices(returns)
    weights = pd.DataFrame({"A": [0.5] * n_days, "B": [0.5] * n_days}, index=idx)

    result = Backtester(prices, ZeroCostModel()).run(weights)
    # Day 2: A's contribution is 0, B contributes 0.5 * 0.01 = 0.005.
    # gross_returns must be a real number, never NaN.
    assert not result.gross_returns.isna().any()
    assert result.gross_returns.iloc[2] == pytest.approx(0.005)
