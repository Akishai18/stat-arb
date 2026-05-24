"""Block-bootstrap confidence intervals for the Sharpe ratio.

Why block bootstrap and not iid bootstrap: daily strategy returns are
serially correlated (a positioning strategy holds the same trade across
multiple days; a momentum signal's P&L is auto-correlated by construction).
An iid bootstrap underestimates the sampling variance of the Sharpe
because it destroys this serial dependence -- consecutive observations
contain less independent information than iid bootstrap pretends.

The block bootstrap fixes this by resampling fixed-length blocks of
consecutive observations with replacement, then concatenating to a series
of the original length. The block length should be long enough to capture
the dominant autocorrelation horizon. For our project's daily horizon
strategies, ~1 month (20 trading days) is a safe default; for the
slowest-moving signal (12-1 momentum) 1 month is roughly the holding period.

The point estimate (`point_sharpe`) is the actual realized Sharpe; the
bootstrap distribution gives its sampling uncertainty around the
underlying population value.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class BootstrapResult:
    """Result of a block-bootstrap Sharpe analysis."""

    point_sharpe: float
    bootstrap_mean: float
    bootstrap_std: float
    ci_low: float       # 2.5 percentile of bootstrap distribution
    ci_high: float      # 97.5 percentile
    p_value_neg: float  # fraction of bootstrap Sharpes <= 0
    t_stat: float       # point_sharpe / bootstrap_std
    n_resamples: int
    block_length: int
    n_obs: int

    def __repr__(self) -> str:
        return (
            "BootstrapResult("
            f"Sharpe={self.point_sharpe:+.3f}, "
            f"95% CI=[{self.ci_low:+.3f}, {self.ci_high:+.3f}], "
            f"t={self.t_stat:+.2f}, "
            f"P(Sharpe≤0)={self.p_value_neg:.3f}, "
            f"n={self.n_obs} obs, block={self.block_length}d, B={self.n_resamples}"
            ")"
        )

    @property
    def is_significant_at_5pct(self) -> bool:
        """Is the strategy distinguishable from a zero-Sharpe coin flip at 5%?

        Equivalent to: does the 95% CI exclude zero?
        """
        return self.ci_low > 0 or self.ci_high < 0


def bootstrap_sharpe(
    returns: pd.Series,
    *,
    n_resamples: int = 5000,
    block_length: int = 20,
    rng_seed: int = 0,
) -> BootstrapResult:
    """Block-bootstrap the annualized Sharpe ratio.

    Parameters
    ----------
    returns : Series
        Daily strategy returns (net of costs). NaN values are dropped.
    n_resamples : int
        Number of bootstrap replications. 5000 gives stable percentile CIs.
    block_length : int
        Block size for the bootstrap. Default 20 (~1 month). Use 1 for an
        iid bootstrap (incorrect for autocorrelated series but useful as a
        check).
    rng_seed : int
        Seed for the bootstrap RNG. Determinism is critical here so that
        the same returns + same seed produce the same CI.

    Returns
    -------
    BootstrapResult
    """
    if block_length < 1:
        raise ValueError(f"block_length must be >= 1, got {block_length}")
    if n_resamples < 100:
        raise ValueError(f"n_resamples must be >= 100, got {n_resamples}")

    r = returns.dropna().to_numpy(dtype=float)
    n = len(r)
    if n < block_length * 5:
        raise ValueError(
            f"need at least {block_length * 5} observations for a "
            f"block_length={block_length} bootstrap; got {n}"
        )

    # Point estimate (the actual Sharpe)
    pt_mean = r.mean()
    pt_std = r.std(ddof=1)
    if pt_std == 0:
        return BootstrapResult(
            point_sharpe=float("nan"),
            bootstrap_mean=float("nan"),
            bootstrap_std=float("nan"),
            ci_low=float("nan"),
            ci_high=float("nan"),
            p_value_neg=float("nan"),
            t_stat=float("nan"),
            n_resamples=n_resamples,
            block_length=block_length,
            n_obs=n,
        )
    point_sharpe = pt_mean / pt_std * np.sqrt(TRADING_DAYS)

    rng = np.random.default_rng(rng_seed)
    n_blocks = int(np.ceil(n / block_length))
    max_start = n - block_length  # inclusive upper bound for block start
    block_starts = rng.integers(0, max_start + 1, size=(n_resamples, n_blocks))

    # Expand each block start into block_length consecutive indices, then
    # concat across blocks and trim to n. Shape: (n_resamples, n).
    offsets = np.arange(block_length)
    all_indices = (
        block_starts[:, :, None] + offsets[None, None, :]
    ).reshape(n_resamples, -1)[:, :n]

    samples = r[all_indices]  # (n_resamples, n)
    sample_means = samples.mean(axis=1)
    sample_stds = samples.std(axis=1, ddof=1)
    # Avoid division by zero on degenerate resamples (extremely rare with
    # block bootstrap on real return data; defensive).
    sample_stds = np.where(sample_stds == 0, np.nan, sample_stds)
    sharpes = sample_means / sample_stds * np.sqrt(TRADING_DAYS)

    valid = sharpes[~np.isnan(sharpes)]
    if len(valid) < 100:
        raise RuntimeError("bootstrap produced too few valid Sharpes; check input")

    bootstrap_std = float(valid.std(ddof=1))
    return BootstrapResult(
        point_sharpe=float(point_sharpe),
        bootstrap_mean=float(valid.mean()),
        bootstrap_std=bootstrap_std,
        ci_low=float(np.percentile(valid, 2.5)),
        ci_high=float(np.percentile(valid, 97.5)),
        p_value_neg=float((valid <= 0).mean()),
        t_stat=float(point_sharpe / bootstrap_std) if bootstrap_std > 0 else float("nan"),
        n_resamples=n_resamples,
        block_length=block_length,
        n_obs=n,
    )


__all__ = ["BootstrapResult", "bootstrap_sharpe"]
