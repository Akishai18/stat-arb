"""Block-bootstrap Sharpe-ratio confidence intervals."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.evaluation import bootstrap_sharpe


def _make_returns(n: int, mean: float, std: float, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    vals = rng.normal(mean, std, size=n)
    return pd.Series(vals, index=pd.date_range("2010-01-01", periods=n, freq="B"))


# ---------------------------------------------------------------------------
# Sanity: iid synthetic with known true Sharpe
# ---------------------------------------------------------------------------


def test_bootstrap_distribution_centers_on_point_estimate():
    """The bootstrap distribution's mean should land near the point Sharpe
    (centering property). The realized Sharpe of a finite sample is NOT
    expected to equal the population Sharpe -- that's a different claim
    that requires unrealistically large samples to test.
    """
    r = _make_returns(n=2000, mean=0.001, std=0.01, seed=42)
    out = bootstrap_sharpe(r, n_resamples=2000, block_length=20, rng_seed=0)
    # Bootstrap distribution should center near the point estimate
    assert abs(out.bootstrap_mean - out.point_sharpe) < 0.3
    # 95% CI should contain the point estimate (by construction)
    assert out.ci_low <= out.point_sharpe <= out.ci_high
    # CI width should be in a reasonable range -- not pathologically tight
    # or wide. For 2000 daily obs with iid bootstrap the rough scale is
    # ~2 * Sharpe_SE = ~2 / sqrt(2000/252) ~= 0.7.
    width = out.ci_high - out.ci_low
    assert 0.5 < width < 3.0


def test_bootstrap_zero_mean_returns_includes_zero_in_ci():
    """For zero-population-mean returns the 95% CI must straddle zero --
    i.e. we can't reject H0: Sharpe = 0. (The p_value_neg is NOT
    expected to be ~0.5 unless the realized sample mean is exactly zero,
    which it generally won't be.)"""
    r = _make_returns(n=2000, mean=0.0, std=0.01, seed=7)
    out = bootstrap_sharpe(r, n_resamples=2000, block_length=20, rng_seed=0)
    assert out.ci_low < 0 < out.ci_high
    assert not out.is_significant_at_5pct


def test_bootstrap_strong_positive_signal_rejects_zero():
    """For clearly positive returns the p-value should be essentially zero."""
    r = _make_returns(n=2000, mean=0.005, std=0.01, seed=11)  # Sharpe ~7.9
    out = bootstrap_sharpe(r, n_resamples=2000, block_length=20, rng_seed=0)
    assert out.p_value_neg < 0.01
    assert out.is_significant_at_5pct
    assert out.ci_low > 0


def test_bootstrap_strong_negative_signal_rejects_zero():
    r = _make_returns(n=2000, mean=-0.005, std=0.01, seed=11)
    out = bootstrap_sharpe(r, n_resamples=2000, block_length=20, rng_seed=0)
    assert out.p_value_neg > 0.99
    assert out.is_significant_at_5pct
    assert out.ci_high < 0


# ---------------------------------------------------------------------------
# Determinism + edge cases
# ---------------------------------------------------------------------------


def test_bootstrap_is_deterministic_with_seed():
    r = _make_returns(n=1500, mean=0.001, std=0.01, seed=3)
    a = bootstrap_sharpe(r, n_resamples=1000, block_length=20, rng_seed=42)
    b = bootstrap_sharpe(r, n_resamples=1000, block_length=20, rng_seed=42)
    assert a.point_sharpe == b.point_sharpe
    assert a.bootstrap_mean == b.bootstrap_mean
    assert a.ci_low == b.ci_low
    assert a.ci_high == b.ci_high


def test_bootstrap_different_seeds_give_close_but_different_cis():
    r = _make_returns(n=1500, mean=0.001, std=0.01, seed=3)
    a = bootstrap_sharpe(r, n_resamples=2000, block_length=20, rng_seed=1)
    b = bootstrap_sharpe(r, n_resamples=2000, block_length=20, rng_seed=2)
    # Different seeds should produce slightly different CIs...
    assert a.ci_low != b.ci_low
    # ...but the CIs should overlap substantially (both sample the same
    # underlying distribution).
    assert abs(a.bootstrap_mean - b.bootstrap_mean) < 0.2


# ---------------------------------------------------------------------------
# Block length effect on autocorrelated series
# ---------------------------------------------------------------------------


def test_block_bootstrap_widens_ci_on_autocorrelated_series():
    """On a strongly persistent AR(1) returns series, the block bootstrap
    should produce a WIDER CI than an iid (block=1) bootstrap, because
    iid bootstrap underestimates sampling variance by ignoring
    autocorrelation."""
    n = 2000
    rng = np.random.default_rng(0)
    eps = rng.normal(0, 0.01, size=n)
    # AR(1) with phi=0.8 (strong persistence)
    r_vals = np.zeros(n)
    r_vals[0] = eps[0]
    for i in range(1, n):
        r_vals[i] = 0.8 * r_vals[i - 1] + eps[i]
    r = pd.Series(r_vals, index=pd.date_range("2010-01-01", periods=n, freq="B"))

    iid_boot = bootstrap_sharpe(r, n_resamples=2000, block_length=1, rng_seed=0)
    block_boot = bootstrap_sharpe(r, n_resamples=2000, block_length=20, rng_seed=0)

    iid_width = iid_boot.ci_high - iid_boot.ci_low
    block_width = block_boot.ci_high - block_boot.ci_low
    # Block bootstrap CI should be meaningfully wider (at least 1.3x).
    assert block_width > iid_width * 1.3


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_bootstrap_rejects_too_short_series():
    r = _make_returns(n=10, mean=0.0, std=0.01)
    with pytest.raises(ValueError, match="observations"):
        bootstrap_sharpe(r, block_length=20)


def test_bootstrap_rejects_bad_block_length():
    r = _make_returns(n=200, mean=0.0, std=0.01)
    with pytest.raises(ValueError, match="block_length"):
        bootstrap_sharpe(r, block_length=0)


def test_bootstrap_rejects_too_few_resamples():
    r = _make_returns(n=200, mean=0.0, std=0.01)
    with pytest.raises(ValueError, match="n_resamples"):
        bootstrap_sharpe(r, n_resamples=50)
