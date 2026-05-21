"""Performance metrics on hand-traced inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.evaluation.metrics import (
    TRADING_DAYS,
    annualized_return,
    annualized_vol,
    beta_alpha,
    cagr,
    daily_hit_rate,
    max_drawdown,
    monthly_hit_rate,
    sharpe,
    sortino,
)


def _series(values: list[float], start: str = "2020-01-01") -> pd.Series:
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="B"))


# ---------------------------------------------------------------------------
# Annualized return / vol / Sharpe / Sortino
# ---------------------------------------------------------------------------


def test_annualized_return_constant_input():
    r = _series([0.001] * 252)
    assert annualized_return(r) == pytest.approx(0.001 * 252)


def test_annualized_vol_constant_input_is_zero():
    """Pandas' variance algorithm leaks ~1e-18 of floating-point noise on
    a constant series; the metric reports it as numerical zero."""
    r = _series([0.001] * 100)
    assert annualized_vol(r) < 1e-10


def test_sharpe_constant_returns_is_nan_or_inf_friendly():
    """Zero-variance returns: Sharpe must be NaN (not raise, not inf)."""
    r = _series([0.001] * 100)
    assert np.isnan(sharpe(r))


def test_sharpe_known_value():
    """Known mean/std -> hand-checkable annualized Sharpe."""
    rng = np.random.default_rng(seed=42)
    daily = rng.normal(0.001, 0.01, size=2000)
    r = _series(daily.tolist())
    expected = daily.mean() / daily.std(ddof=1) * np.sqrt(TRADING_DAYS)
    assert sharpe(r) == pytest.approx(expected, rel=1e-9)


def test_sortino_penalizes_only_downside():
    """A purely-positive return stream has finite Sharpe but undefined
    Sortino (downside dev = 0)."""
    r = _series([0.001] * 100)
    assert np.isnan(sortino(r))


def test_sortino_handles_mix_of_up_and_down():
    r = _series([0.01, -0.01, 0.02, -0.02, 0.005])
    result = sortino(r)
    assert np.isfinite(result)


# ---------------------------------------------------------------------------
# CAGR
# ---------------------------------------------------------------------------


def test_cagr_exact_one_year_constant():
    """252 days of constant return r -> CAGR ~ (1+r)^252 - 1."""
    r = _series([0.001] * 252)
    expected = (1.001) ** 252 - 1.0
    assert cagr(r) == pytest.approx(expected, rel=1e-9)


def test_cagr_two_years_constant():
    """504 days of constant return r -> still CAGR ~ (1+r)^252 - 1 (per-year)."""
    r = _series([0.001] * 504)
    expected = (1.001) ** 252 - 1.0
    assert cagr(r) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown_hand_traced():
    """Equity goes 1.0 -> 1.1 -> 0.99 -> 1.05 -> 1.20.
    Peak after day 1 = 1.1. Trough at day 2 = 0.99. MaxDD = 0.99/1.1 - 1 ~ -10%.
    Duration: 2 days (day 2 and day 3 below 1.1, recovery on day 4).
    """
    # Returns that produce that equity curve:
    # 1.0 -> 1.1 (+10%), 1.1 -> 0.99 (-10%), 0.99 -> 1.05 (+~6.06%), 1.05 -> 1.20 (+~14.3%)
    r = pd.Series(
        [0.10, -0.10, 1.05 / 0.99 - 1, 1.20 / 1.05 - 1],
        index=pd.date_range("2020-01-01", periods=4, freq="B"),
    )
    out = max_drawdown(r)
    assert out["max_drawdown"] == pytest.approx(0.99 / 1.10 - 1)
    assert out["drawdown_days"] == 2


def test_max_drawdown_no_drawdown():
    r = _series([0.01, 0.02, 0.005])
    out = max_drawdown(r)
    assert out["max_drawdown"] == 0
    assert out["drawdown_days"] == 0


# ---------------------------------------------------------------------------
# Hit rate
# ---------------------------------------------------------------------------


def test_daily_hit_rate_ignores_zeros():
    r = _series([0.01, -0.01, 0.0, 0.02, 0.0, -0.01])
    # nonzero = [0.01, -0.01, 0.02, -0.01] -> 2 positive of 4 -> 0.5
    assert daily_hit_rate(r) == 0.5


def test_monthly_hit_rate():
    # 4 months: 3 positive, 1 negative (~drawdown month)
    idx = pd.date_range("2020-01-01", "2020-04-30", freq="B")
    # Make all days flat except one negative day in march that's big enough
    # to make the march compounded return negative.
    r = pd.Series(0.001, index=idx)
    r.loc[r.index[(r.index.month == 3)][5]] = -0.10  # one big down day in march
    rate = monthly_hit_rate(r)
    # Expect 3/4 = 0.75
    assert rate == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Beta / alpha
# ---------------------------------------------------------------------------


def test_beta_alpha_identity():
    """strategy = benchmark -> beta = 1, alpha = 0."""
    rng = np.random.default_rng(0)
    b = pd.Series(rng.normal(0.001, 0.01, 500), index=pd.date_range("2020-01-01", periods=500, freq="B"))
    out = beta_alpha(b, b)
    assert out["beta"] == pytest.approx(1.0, abs=1e-10)
    assert out["alpha_ann"] == pytest.approx(0.0, abs=1e-10)


def test_beta_alpha_doubled_strategy():
    """strategy = 2 * benchmark -> beta = 2, alpha = 0."""
    rng = np.random.default_rng(1)
    b = pd.Series(rng.normal(0.001, 0.01, 500), index=pd.date_range("2020-01-01", periods=500, freq="B"))
    s = 2 * b
    out = beta_alpha(s, b)
    assert out["beta"] == pytest.approx(2.0, abs=1e-10)
    assert out["alpha_ann"] == pytest.approx(0.0, abs=1e-9)


def test_beta_alpha_pure_alpha():
    """strategy = benchmark + constant -> beta = 1, alpha > 0."""
    rng = np.random.default_rng(2)
    b = pd.Series(rng.normal(0.001, 0.01, 500), index=pd.date_range("2020-01-01", periods=500, freq="B"))
    s = b + 0.0005  # add 5 bps daily alpha
    out = beta_alpha(s, b)
    assert out["beta"] == pytest.approx(1.0, abs=1e-10)
    assert out["alpha_ann"] == pytest.approx(0.0005 * 252, abs=1e-9)
