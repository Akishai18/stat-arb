"""Probabilistic and Deflated Sharpe Ratio.

Both metrics are from Bailey & López de Prado, "The Sharpe Ratio Efficient
Frontier" (Journal of Risk, 2012/2014). They correct two well-known problems
with the plain Sharpe ratio as a "is the strategy real?" test:

1. **Non-normal returns.** The standard error of the Sharpe estimator
   assumes returns are iid Gaussian. Real return distributions are skewed
   and fat-tailed; the SE correction needs to include those moments.

2. **Multiple testing / selection bias.** If you tested N strategies and
   report the best one, the headline Sharpe is biased upward. The DSR
   compares the observed Sharpe to the expected maximum across N trials
   under the null hypothesis of no skill.

Reference formula (notation follows Bailey-LdP):

    PSR(SR*) = Phi( (SR - SR*) * sqrt(T-1)
                    / sqrt(1 - gamma3 * SR + (gamma4 - 1) / 4 * SR**2) )

    DSR        = PSR(SR0)     where SR0 = expected max Sharpe under null
    E[max SR | N trials, null] ~= sqrt(2 * ln(N))
                                  - gamma_em / sqrt(2 * ln(N))
    gamma_em   = Euler-Mascheroni constant ~= 0.5772

T is the sample size, gamma3 is skewness of returns, gamma4 is kurtosis
(non-excess; i.e. 3 for Gaussian).

The DSR's biggest practical caveat is **picking N**: it's the number of
*independent* trials you would have run. Sweeping the same hyperparameter
on different signals counts more than once; choices made before seeing
any data count zero. We document our N choice explicitly in the runner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

TRADING_DAYS = 252
EULER_MASCHERONI = 0.5772156649015329


@dataclass(frozen=True)
class DSRResult:
    """Probabilistic + deflated Sharpe ratio with the inputs that produced them."""

    point_sharpe: float          # the realized Sharpe (annualized)
    psr: float                   # probability true Sharpe > 0
    dsr: float                   # probability true Sharpe > E[max | null]
    expected_max_sharpe: float   # E[max Sharpe | null hypothesis, N trials] (annualized)
    skewness: float
    kurtosis: float              # NON-excess kurtosis (=3 for Gaussian)
    n_obs: int
    n_trials: int

    def __repr__(self) -> str:
        return (
            "DSRResult("
            f"Sharpe={self.point_sharpe:+.3f}, "
            f"PSR(>0)={self.psr:.3f}, "
            f"DSR(>{self.expected_max_sharpe:+.2f})={self.dsr:.3f}, "
            f"skew={self.skewness:+.2f}, kurt={self.kurtosis:.2f}, "
            f"n={self.n_obs}, N_trials={self.n_trials}"
            ")"
        )

    @property
    def is_significant_at_5pct(self) -> bool:
        """DSR > 0.95 = strategy beats expected-max-under-null at 95% confidence."""
        return self.dsr >= 0.95


def _annualized_sharpe(returns: np.ndarray) -> float:
    mean = returns.mean()
    std = returns.std(ddof=1)
    if std == 0:
        return float("nan")
    return mean / std * math.sqrt(TRADING_DAYS)


def _moments(returns: np.ndarray) -> tuple[float, float]:
    """Returns (skewness, non-excess kurtosis) using the sample moments
    conventions used by Bailey-LdP (population skewness; non-excess
    kurtosis = excess + 3). Inputs are daily returns; the formula is
    scale/annualization-invariant.
    """
    n = len(returns)
    if n < 4:
        return (float("nan"), float("nan"))
    mean = returns.mean()
    centered = returns - mean
    m2 = (centered**2).mean()
    if m2 == 0:
        return (float("nan"), float("nan"))
    m3 = (centered**3).mean()
    m4 = (centered**4).mean()
    skew = m3 / (m2**1.5)
    kurt = m4 / (m2**2)  # NON-excess
    return (float(skew), float(kurt))


def probabilistic_sharpe_ratio(
    returns: pd.Series,
    *,
    sr_benchmark: float = 0.0,
) -> tuple[float, float, float, float, int]:
    """Compute PSR(SR_benchmark) and return diagnostic moments.

    Returns: (psr, point_sharpe, skewness, kurtosis, n_obs).
    All Sharpe values are ANNUALIZED (multiplied by sqrt(252)).
    """
    r = returns.dropna().to_numpy(dtype=float)
    n = len(r)
    if n < 30:
        raise ValueError(f"need at least 30 observations for PSR, got {n}")
    sr_hat = _annualized_sharpe(r)
    skew, kurt = _moments(r)
    if any(math.isnan(x) for x in (sr_hat, skew, kurt)):
        return (float("nan"), sr_hat, skew, kurt, n)

    # Sharpe-ratio standard error correction with skewness + kurtosis.
    # NOTE: the formula uses Sharpe ratios in their NON-annualized form
    # internally; we de-annualize for the calculation and re-annualize
    # the inputs/outputs for reporting consistency.
    sr_daily = sr_hat / math.sqrt(TRADING_DAYS)
    sr_bench_daily = sr_benchmark / math.sqrt(TRADING_DAYS)
    se_correction = 1.0 - skew * sr_daily + (kurt - 1.0) / 4.0 * sr_daily**2
    if se_correction <= 0:
        # Pathological combinations of high Sharpe + extreme moments can
        # push this negative; PSR is undefined in that regime.
        return (float("nan"), sr_hat, skew, kurt, n)
    psr = norm.cdf(
        (sr_daily - sr_bench_daily) * math.sqrt(n - 1) / math.sqrt(se_correction)
    )
    return (float(psr), sr_hat, skew, kurt, n)


def expected_max_sharpe_under_null(n_trials: int, *, n_obs: int) -> float:
    """E[max annualized Sharpe across N trials | true Sharpe = 0].

    Bailey-LdP approximation:
        E[max SR_n] = SE(SR) * [sqrt(2 ln N) - gamma_em / sqrt(2 ln N)]

    where SE(SR) is the standard error of the Sharpe estimator under the
    null. For iid Gaussian returns with T daily observations, the SE of
    the ANNUALIZED Sharpe is sqrt(252 / T). The benchmark therefore
    SHRINKS as T grows -- with more data, beating "max of N coin flips"
    becomes easier in absolute Sharpe units.

    Parameters
    ----------
    n_trials : int
        Number of independent trials (strategies / hyperparameter combos).
    n_obs : int
        Sample size used to compute the realized Sharpe (daily obs count).
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if n_obs < 2:
        raise ValueError(f"n_obs must be >= 2, got {n_obs}")
    if n_trials == 1:
        # Special case: with a single trial there's no selection bias.
        return 0.0
    two_log_n = 2.0 * math.log(n_trials)
    se_annual_sharpe = math.sqrt(TRADING_DAYS / n_obs)
    sr_max_normalized = math.sqrt(two_log_n) - EULER_MASCHERONI / math.sqrt(two_log_n)
    return se_annual_sharpe * sr_max_normalized


def deflated_sharpe_ratio(
    returns: pd.Series,
    *,
    n_trials: int,
) -> DSRResult:
    """Deflated Sharpe Ratio: PSR with benchmark = E[max SR | null, N trials].

    The DSR is the probability that the strategy's true Sharpe exceeds
    what you would expect from the best of N coin-flip strategies under
    no-skill. DSR > 0.95 is the conventional bar for "skilled."
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    psr_zero, sharpe, skew, kurt, n = probabilistic_sharpe_ratio(returns, sr_benchmark=0.0)
    expected_max = expected_max_sharpe_under_null(n_trials, n_obs=n)
    dsr, _, _, _, _ = probabilistic_sharpe_ratio(returns, sr_benchmark=expected_max)
    return DSRResult(
        point_sharpe=sharpe,
        psr=float(psr_zero),
        dsr=float(dsr),
        expected_max_sharpe=expected_max,
        skewness=skew,
        kurtosis=kurt,
        n_obs=n,
        n_trials=n_trials,
    )


__all__ = [
    "DSRResult",
    "deflated_sharpe_ratio",
    "expected_max_sharpe_under_null",
    "probabilistic_sharpe_ratio",
]
