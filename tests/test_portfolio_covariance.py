"""Rolling-covariance estimator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.portfolio.covariance import rolling_covariance


def _returns(n_days: int = 100, n_assets: int = 4, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.normal(0, 0.01, size=(n_days, n_assets)),
        index=pd.date_range("2020-01-01", periods=n_days, freq="B"),
        columns=[f"A{i}" for i in range(n_assets)],
    )


def test_covariance_matches_numpy_for_full_window():
    """At date t, cov should equal numpy cov of the prior `lookback` rows."""
    ret = _returns(n_days=100)
    out = rolling_covariance(ret, lookback=30, min_periods=10)
    date = ret.index[40]
    window = ret.iloc[11:41]  # rows 11..40, that's 30 rows ending at index 40
    expected = window.cov().to_numpy()
    actual = out[date].to_numpy()
    np.testing.assert_allclose(actual, expected, rtol=1e-12)


def test_covariance_dates_skip_until_lookback_filled():
    """No covariance is returned until `lookback` history exists."""
    ret = _returns(n_days=50)
    out = rolling_covariance(ret, lookback=30, min_periods=30)
    first_date = min(out.keys())
    # First valid output corresponds to index 29 (the 30th row, 0-indexed).
    assert first_date == ret.index[29]


def test_covariance_symmetric_and_correct_shape():
    ret = _returns(n_days=80, n_assets=3)
    out = rolling_covariance(ret, lookback=30, min_periods=10)
    cov = next(iter(out.values()))
    assert cov.shape == (3, 3)
    np.testing.assert_allclose(cov.to_numpy(), cov.to_numpy().T, atol=1e-12)


def test_covariance_min_periods_validation():
    ret = _returns()
    with pytest.raises(ValueError):
        rolling_covariance(ret, lookback=30, min_periods=1)
    with pytest.raises(ValueError):
        rolling_covariance(ret, lookback=30, min_periods=31)
    with pytest.raises(ValueError):
        rolling_covariance(ret, lookback=1)
