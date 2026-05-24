"""Time-series momentum signal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.signals import ts_momentum


def _prices(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"A": values},
        index=pd.date_range("2020-01-01", periods=len(values), freq="B"),
    )


def test_ts_momentum_hand_traced():
    """Per-asset trailing return: price 100 -> 110 over 2 days = +10%."""
    p = _prices([100, 105, 110, 95])
    s = ts_momentum(p, lookback=2)
    assert s["A"].iloc[2] == pytest.approx(0.10)        # 110/100 - 1
    assert s["A"].iloc[3] == pytest.approx(95 / 105 - 1)  # -0.0952


def test_ts_momentum_first_rows_are_nan():
    p = _prices([100, 105, 110])
    s = ts_momentum(p, lookback=2)
    assert pd.isna(s["A"].iloc[0])
    assert pd.isna(s["A"].iloc[1])


def test_ts_momentum_independent_across_assets():
    """Two assets with opposite trends should produce opposite-sign signals."""
    df = pd.DataFrame(
        {"UP": [100, 105, 110], "DOWN": [100, 95, 90]},
        index=pd.date_range("2020-01-01", periods=3, freq="B"),
    )
    s = ts_momentum(df, lookback=2)
    assert s["UP"].iloc[2] > 0
    assert s["DOWN"].iloc[2] < 0


def test_ts_momentum_point_in_time_safe():
    """Truncating the future must not change scores up to the cutoff."""
    rng = np.random.default_rng(0)
    n = 40
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    prices = pd.DataFrame(
        np.cumprod(1 + rng.normal(0, 0.01, (n, 3)), axis=0) * 100,
        index=idx, columns=list("ABC"),
    )
    full = ts_momentum(prices, lookback=10)
    cutoff = prices.index[20]
    trunc = ts_momentum(prices.loc[:cutoff], lookback=10)
    pd.testing.assert_frame_equal(
        full.loc[:cutoff].dropna(),
        trunc.loc[:cutoff].dropna(),
    )


def test_ts_momentum_rejects_bad_lookback():
    p = _prices([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        ts_momentum(p, lookback=0)
    with pytest.raises(ValueError):
        ts_momentum(p, lookback=-5)
