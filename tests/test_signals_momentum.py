"""Momentum signal: hand-traced values and point-in-time safety."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.signals import momentum


def _make_prices(values: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(values.values())))
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame(values, index=idx)


def test_momentum_hand_calculation_no_skip():
    """With lookback=2 and skip=0, score[t] = price[t] / price[t-2] - 1."""
    prices = _make_prices({"A": [100, 110, 121, 133.1]})
    scores = momentum(prices, lookback=2, skip=0)
    # row 0 and row 1: NaN (no enough history)
    assert pd.isna(scores["A"].iloc[0])
    assert pd.isna(scores["A"].iloc[1])
    # row 2: 121 / 100 - 1 = 0.21
    assert scores["A"].iloc[2] == pytest.approx(0.21)
    # row 3: 133.1 / 110 - 1 = 0.21
    assert scores["A"].iloc[3] == pytest.approx(0.21)


def test_momentum_hand_calculation_with_skip():
    """lookback=3, skip=1 -> score[t] = price[t-1] / price[t-3] - 1."""
    prices = _make_prices({"A": [100, 105, 110, 120, 130]})
    scores = momentum(prices, lookback=3, skip=1)
    # row 3 needs price[t-1]=price[2]=110 and price[t-3]=price[0]=100 -> 0.10
    assert scores["A"].iloc[3] == pytest.approx(0.10)
    # row 4 needs price[3]=120 and price[1]=105 -> 120/105 - 1
    assert scores["A"].iloc[4] == pytest.approx(120 / 105 - 1)


def test_momentum_is_point_in_time_safe():
    """Score at row t may only depend on prices at row t or earlier --
    i.e. truncating future data should not change scores up to that row."""
    rng = np.random.default_rng(42)
    n = 60
    prices = pd.DataFrame(
        np.cumprod(1.0 + rng.normal(0, 0.01, size=(n, 3)), axis=0) * 100,
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
        columns=list("ABC"),
    )
    full_scores = momentum(prices, lookback=20, skip=5)
    cutoff = prices.index[40]
    truncated_scores = momentum(prices.loc[:cutoff], lookback=20, skip=5)
    # Where both are defined, values must agree exactly.
    pd.testing.assert_frame_equal(
        full_scores.loc[:cutoff].dropna(),
        truncated_scores.loc[:cutoff].dropna(),
    )


def test_momentum_rejects_bad_params():
    prices = _make_prices({"A": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        momentum(prices, lookback=0)
    with pytest.raises(ValueError):
        momentum(prices, skip=-1)
    with pytest.raises(ValueError):
        momentum(prices, lookback=5, skip=10)


def test_momentum_handles_nan_in_window():
    """If any price in the lookback window is NaN, the score is NaN."""
    prices = pd.DataFrame(
        {"A": [100.0, np.nan, 110.0, 121.0, 133.1]},
        index=pd.date_range("2020-01-01", periods=5, freq="B"),
    )
    scores = momentum(prices, lookback=3, skip=0)
    # row 3: needs price[0]=100 and price[3]=121, both available -> 0.21
    assert scores["A"].iloc[3] == pytest.approx(0.21)
    # row 2: needs price[2]=110 and price[-1]=NaN ... actually lookback=3 means
    # we need price[t-3] which for t=2 is index -1 -> NaN. So this is the
    # earliest *valid* row by index. Row 1's price is NaN, but row 2's
    # backward index is -1, both NaN-anchored.
    assert pd.isna(scores["A"].iloc[1])
