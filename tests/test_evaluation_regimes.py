"""Regime-classification utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.backtest.result import BacktestResult
from statarb.evaluation import (
    evaluate_by_regime,
    period_regime,
    strategy_vol_regime,
    trailing_return_regime,
    vix_regime,
)


def _make_result(net_returns: pd.Series) -> BacktestResult:
    idx = net_returns.index
    zeros_series = pd.Series(0.0, index=idx)
    zeros_df = pd.DataFrame(0.0, index=idx, columns=["A"])
    return BacktestResult(
        weights_applied=zeros_df,
        turnover=zeros_series,
        gross_returns=net_returns,
        costs=zeros_series,
        net_returns=net_returns,
        equity_curve=(1.0 + net_returns.fillna(0)).cumprod(),
        meta={},
    )


def test_vix_regime_fixed_threshold():
    vix = pd.Series([10.0, 20.0, 30.0, 15.0], index=pd.date_range("2020-01-01", periods=4, freq="B"))
    out = vix_regime(vix, threshold=18.0)
    assert out.tolist() == [False, True, True, False]


def test_vix_regime_expanding_median():
    """Expanding-median mode: True when today's VIX exceeds median to date."""
    vix = pd.Series([10.0, 20.0, 30.0, 5.0], index=pd.date_range("2020-01-01", periods=4, freq="B"))
    out = vix_regime(vix, threshold=None)
    # Day 0: median is 10, value is 10 -> NOT > median, False.
    # Day 1: median over [10,20] = 15, value is 20 -> True.
    # Day 2: median over [10,20,30] = 20, value is 30 -> True.
    # Day 3: median over [10,20,30,5] = 15, value is 5 -> False.
    assert out.tolist() == [False, True, True, False]


def test_trailing_return_regime_hand_traced():
    prices = pd.Series([100, 105, 110, 95, 100], index=pd.date_range("2020-01-01", periods=5, freq="B"))
    out = trailing_return_regime(prices, lookback=2)
    # row 2: 110/100 - 1 = +0.10 -> True
    # row 3: 95/105 - 1 = -0.095 -> False
    # row 4: 100/110 - 1 = -0.091 -> False
    assert out.iloc[2]
    assert not out.iloc[3]
    assert not out.iloc[4]
    # First lookback rows: NaN return -> False after fillna
    assert not out.iloc[0]
    assert not out.iloc[1]


def test_trailing_return_regime_validates_lookback():
    prices = pd.Series([1.0, 2.0], index=pd.date_range("2020-01-01", periods=2, freq="B"))
    with pytest.raises(ValueError):
        trailing_return_regime(prices, lookback=0)


def test_period_regime_strictly_after_split_date():
    idx = pd.date_range("2021-12-30", periods=5, freq="B")
    out = period_regime(idx, split_date="2022-01-01")
    # 2021-12-30 < 2022-01-01, 2021-12-31 < 2022-01-01,
    # 2022-01-03 > 2022-01-01, 2022-01-04 > 2022-01-01, 2022-01-05 > 2022-01-01
    assert out.iloc[0] is np.False_ or not out.iloc[0]
    assert not out.iloc[1]
    assert out.iloc[2]
    assert out.iloc[3]
    assert out.iloc[4]


def test_strategy_vol_regime_high_vs_low():
    """A series with one calm period and one volatile period should produce
    a True mask only during the volatile stretch."""
    n = 200
    rng = np.random.default_rng(seed=0)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    calm = rng.normal(0, 0.002, size=n // 2)
    storm = rng.normal(0, 0.04, size=n // 2)
    net = pd.Series(np.concatenate([calm, storm]), index=idx)
    mask = strategy_vol_regime(net, lookback=20)
    # The second half (volatile) should mostly be True; first half mostly False.
    second_half_true_rate = mask.iloc[n // 2 + 30 : n].mean()
    first_half_true_rate = mask.iloc[20:80].mean()
    assert second_half_true_rate > first_half_true_rate


def test_evaluate_by_regime_isolates_in_out():
    """Days flagged True should be the only ones contributing to in_regime."""
    n = 200
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # First half: +0.01/day. Second half: -0.01/day.
    net = pd.Series(np.concatenate([np.full(n // 2, 0.01), np.full(n // 2, -0.01)]), index=idx)
    result = _make_result(net)
    # Mask = True for first half only
    mask = pd.Series([True] * (n // 2) + [False] * (n // 2), index=idx)
    out = evaluate_by_regime(result, regime_mask=mask)
    # In-regime should be positive (only +0.01 days), out-regime negative.
    assert out["in_regime"].cagr > 0
    assert out["out_regime"].cagr < 0


def test_evaluate_by_regime_nan_mask_excluded_from_both():
    """A NaN mask cell should be in neither side."""
    n = 6
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    net = pd.Series([0.01] * n, index=idx)
    result = _make_result(net)
    mask = pd.Series([True, True, float("nan"), False, False, float("nan")], index=idx)
    out = evaluate_by_regime(result, regime_mask=mask)
    # in_regime: only 2 True days -> n_days = 2
    # out_regime: only 2 False days -> n_days = 2
    # (NaN days excluded)
    assert out["in_regime"].n_days == 2
    assert out["out_regime"].n_days == 2
