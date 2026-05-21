"""Cross-sectional normalization utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd

from statarb.signals import cross_sectional_rank, cross_sectional_zscore


def test_zscore_each_row_has_mean_zero():
    df = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]],
        index=pd.date_range("2020-01-01", periods=2, freq="B"),
    )
    z = cross_sectional_zscore(df)
    np.testing.assert_allclose(z.mean(axis=1).values, 0.0, atol=1e-12)


def test_zscore_each_row_has_unit_std():
    df = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]],
        index=pd.date_range("2020-01-01", periods=2, freq="B"),
    )
    z = cross_sectional_zscore(df)
    np.testing.assert_allclose(z.std(axis=1, ddof=1).values, 1.0, atol=1e-12)


def test_zscore_zero_variance_row_is_nan():
    df = pd.DataFrame(
        [[5.0, 5.0, 5.0]],
        index=pd.date_range("2020-01-01", periods=1, freq="B"),
    )
    z = cross_sectional_zscore(df)
    assert z.iloc[0].isna().all()


def test_zscore_ignores_nans():
    df = pd.DataFrame(
        [[1.0, 2.0, np.nan, 4.0]],
        index=pd.date_range("2020-01-01", periods=1, freq="B"),
    )
    z = cross_sectional_zscore(df)
    # NaN stays NaN; others normalize across the 3 available values
    assert pd.isna(z.iloc[0, 2])
    valid = z.iloc[0].dropna()
    assert valid.mean() == 0.0 or abs(valid.mean()) < 1e-12
    assert abs(valid.std(ddof=1) - 1.0) < 1e-12


def test_rank_pct_in_unit_interval():
    df = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0]],
        index=pd.date_range("2020-01-01", periods=1, freq="B"),
    )
    r = cross_sectional_rank(df, pct=True)
    assert (r.iloc[0] > 0).all() and (r.iloc[0] <= 1).all()
    # Highest value gets highest rank
    assert r.iloc[0, 3] == 1.0


def test_rank_preserves_nans():
    df = pd.DataFrame(
        [[1.0, np.nan, 3.0]],
        index=pd.date_range("2020-01-01", periods=1, freq="B"),
    )
    r = cross_sectional_rank(df)
    assert pd.isna(r.iloc[0, 1])
