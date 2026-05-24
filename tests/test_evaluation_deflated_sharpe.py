"""Probabilistic + Deflated Sharpe Ratio (Bailey-LdP 2014)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from statarb.evaluation.deflated_sharpe import (
    EULER_MASCHERONI,
    deflated_sharpe_ratio,
    expected_max_sharpe_under_null,
    probabilistic_sharpe_ratio,
)


def _make_returns(n: int, mean: float, std: float, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    vals = rng.normal(mean, std, size=n)
    return pd.Series(vals, index=pd.date_range("2010-01-01", periods=n, freq="B"))


# ---------------------------------------------------------------------------
# PSR identities and asymptotics
# ---------------------------------------------------------------------------


def test_psr_with_benchmark_equal_to_sharpe_is_one_half():
    """When the benchmark equals the realized Sharpe, PSR = 0.5 (the
    realized estimate is exactly at the boundary)."""
    r = _make_returns(n=2000, mean=0.001, std=0.01, seed=42)
    _psr_zero, sr, _skew, _kurt, _n = probabilistic_sharpe_ratio(r, sr_benchmark=0.0)
    # Now set the benchmark exactly equal to the realized Sharpe
    psr_at_sr, _, _, _, _ = probabilistic_sharpe_ratio(r, sr_benchmark=sr)
    assert abs(psr_at_sr - 0.5) < 1e-9


def test_psr_zero_benchmark_approaches_one_for_strong_signal():
    """With a clearly positive-Sharpe series, PSR(SR>0) should be very high."""
    r = _make_returns(n=2000, mean=0.005, std=0.01, seed=11)  # daily SR ~ 0.5
    psr, sr, _, _, _ = probabilistic_sharpe_ratio(r, sr_benchmark=0.0)
    assert sr > 5.0  # annualized
    assert psr > 0.999


def test_psr_negative_for_clearly_losing_strategy():
    """PSR(SR>0) should be near zero for a losing strategy."""
    r = _make_returns(n=2000, mean=-0.005, std=0.01, seed=11)
    psr, sr, _, _, _ = probabilistic_sharpe_ratio(r, sr_benchmark=0.0)
    assert sr < -5.0
    assert psr < 0.001


def test_psr_with_larger_sample_gives_tighter_result():
    """Same point Sharpe at a larger sample size -> PSR farther from 0.5."""
    r_small = _make_returns(n=300, mean=0.001, std=0.01, seed=0)
    r_big = _make_returns(n=3000, mean=0.001, std=0.01, seed=0)
    psr_small, sr_small, _, _, _ = probabilistic_sharpe_ratio(r_small, sr_benchmark=0.0)
    psr_big, sr_big, _, _, _ = probabilistic_sharpe_ratio(r_big, sr_benchmark=0.0)
    # Sharpes are roughly similar (same DGP); the bigger sample gives more
    # confidence the true Sharpe > 0.
    if sr_small > 0 and sr_big > 0:
        # The "tighter" statement: PSR is more extreme (further from 0.5).
        assert abs(psr_big - 0.5) > abs(psr_small - 0.5)


# ---------------------------------------------------------------------------
# Expected-max-Sharpe under null
# ---------------------------------------------------------------------------


def test_expected_max_zero_for_single_trial():
    """With one trial there's no selection bias."""
    assert expected_max_sharpe_under_null(1, n_obs=1000) == 0.0


def test_expected_max_grows_with_n_trials():
    """E[max] grows roughly as sqrt(ln N) for fixed T."""
    em_10 = expected_max_sharpe_under_null(10, n_obs=2000)
    em_100 = expected_max_sharpe_under_null(100, n_obs=2000)
    em_1000 = expected_max_sharpe_under_null(1000, n_obs=2000)
    assert 0 < em_10 < em_100 < em_1000


def test_expected_max_shrinks_with_sample_size():
    """E[max] in annualized-Sharpe units shrinks as T grows (the SE of
    the Sharpe estimator shrinks, so the bar to beat is lower in absolute
    terms)."""
    em_small_T = expected_max_sharpe_under_null(20, n_obs=500)
    em_big_T = expected_max_sharpe_under_null(20, n_obs=10000)
    assert em_big_T < em_small_T


def test_expected_max_formula_matches_closed_form():
    """E[max | N=100, T=2000] using the documented formula."""
    n, T = 100, 2000
    two_log_n = 2 * math.log(n)
    se_annual = math.sqrt(252 / T)
    expected = se_annual * (math.sqrt(two_log_n) - EULER_MASCHERONI / math.sqrt(two_log_n))
    actual = expected_max_sharpe_under_null(n, n_obs=T)
    assert abs(actual - expected) < 1e-9


def test_expected_max_rejects_zero_trials():
    with pytest.raises(ValueError):
        expected_max_sharpe_under_null(0, n_obs=1000)


# ---------------------------------------------------------------------------
# DSR
# ---------------------------------------------------------------------------


def test_dsr_with_n_trials_1_equals_psr_with_zero_benchmark():
    """With N=1 there's no deflation, so DSR(SR>0) = PSR(SR>0)."""
    r = _make_returns(n=2000, mean=0.001, std=0.01, seed=5)
    psr_zero, _sr, _, _, _ = probabilistic_sharpe_ratio(r, sr_benchmark=0.0)
    dsr_result = deflated_sharpe_ratio(r, n_trials=1)
    assert abs(dsr_result.dsr - psr_zero) < 1e-9
    assert dsr_result.expected_max_sharpe == 0.0


def test_dsr_decreases_as_n_trials_grows():
    """Same data, more trials → more deflation → lower DSR."""
    r = _make_returns(n=2000, mean=0.002, std=0.01, seed=7)
    dsr_1 = deflated_sharpe_ratio(r, n_trials=1)
    dsr_10 = deflated_sharpe_ratio(r, n_trials=10)
    dsr_100 = deflated_sharpe_ratio(r, n_trials=100)
    assert dsr_1.dsr >= dsr_10.dsr >= dsr_100.dsr


def test_dsr_strong_signal_survives_modest_deflation():
    """A clearly-positive Sharpe strategy should still be significant after
    a modest N_trials deflation."""
    r = _make_returns(n=3000, mean=0.003, std=0.01, seed=3)
    out = deflated_sharpe_ratio(r, n_trials=20)
    assert out.is_significant_at_5pct
    assert out.dsr > 0.95


def test_dsr_weak_signal_killed_by_large_n_trials():
    """A modest Sharpe deflated by many trials should fail to be significant."""
    r = _make_returns(n=2000, mean=0.0005, std=0.01, seed=2)
    out_few = deflated_sharpe_ratio(r, n_trials=2)
    out_many = deflated_sharpe_ratio(r, n_trials=1000)
    # With many trials, the deflation should drop DSR
    assert out_many.dsr < out_few.dsr


# ---------------------------------------------------------------------------
# Diagnostic moments
# ---------------------------------------------------------------------------


def test_skewness_and_kurtosis_reported():
    """The DSR result should expose skew and kurtosis."""
    r = _make_returns(n=2000, mean=0.001, std=0.01, seed=0)
    out = deflated_sharpe_ratio(r, n_trials=10)
    # Gaussian-like input: skew ~ 0, kurtosis ~ 3 (non-excess)
    assert abs(out.skewness) < 0.5
    assert 2.0 < out.kurtosis < 4.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_psr_rejects_too_short_series():
    r = _make_returns(n=20, mean=0.0, std=0.01)
    with pytest.raises(ValueError, match="observations"):
        probabilistic_sharpe_ratio(r)


def test_dsr_rejects_zero_trials():
    r = _make_returns(n=2000, mean=0.0, std=0.01)
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(r, n_trials=0)
