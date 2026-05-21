"""Single-day portfolio optimizer (cvxpy QP).

Objective: maximize  alpha . w  -  lambda * w' Sigma w  -  cost * ||w - w_prev||_1
Subject to:
  sum(|w_i|)        <= gross_cap        (total gross exposure)
  |sum(w_i)|        <= net_cap          (close to dollar-neutral)
  |w_i|             <= position_cap     (per-asset concentration)
  ||w - w_prev||_1  <= turnover_cap     (optional; hard cap on rebalance)

Solver: OSQP (installed with cvxpy). For 5 assets each solve takes ~1 ms,
so daily QPs over 16 years run in ~10 seconds.

Conventions:
  - `cost_bps_per_side` enters the objective as a fraction (e.g. 10 bps =
    0.001). Same units as the LinearCostModel.bps_per_side / 10_000.
  - `alpha`, `cov`, `prev_weights` are pandas indexed by ticker; they are
    aligned to a common ordered index before being passed to cvxpy.
  - NaN alpha is coerced to 0 (the optimizer will then assign small or zero
    weight unless the covariance structure favors it).
  - If the problem is infeasible, raises OptimizerInfeasible.
"""

from __future__ import annotations

import cvxpy as cp
import numpy as np
import pandas as pd


class OptimizerInfeasible(RuntimeError):
    """Raised when cvxpy returns a non-optimal status."""


def optimize_one_day(
    alpha: pd.Series,
    cov: pd.DataFrame,
    prev_weights: pd.Series,
    *,
    gross_cap: float = 1.0,
    net_cap: float = 0.05,
    position_cap: float = 0.40,
    risk_aversion: float = 1.0,
    cost_bps_per_side: float = 0.0,
    turnover_cap: float | None = None,
) -> pd.Series:
    """Solve the QP for one day's target weights.

    Returns a Series indexed by ticker matching `alpha.index`.
    """
    tickers = list(alpha.index)
    a = alpha.reindex(tickers).fillna(0.0).to_numpy(dtype=float)
    sigma = cov.reindex(index=tickers, columns=tickers).fillna(0.0).to_numpy(dtype=float)
    # Symmetrize and project to PSD by clipping tiny negative eigenvalues that
    # arise from sample-covariance numerics. This keeps cvxpy happy.
    sigma = 0.5 * (sigma + sigma.T)
    eigvals, eigvecs = np.linalg.eigh(sigma)
    eigvals = np.clip(eigvals, 0.0, None)
    sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T
    w_prev = prev_weights.reindex(tickers).fillna(0.0).to_numpy(dtype=float)

    n = len(tickers)
    w = cp.Variable(n)
    cost_rate = float(cost_bps_per_side) / 10_000.0

    objective = cp.Maximize(
        a @ w
        - risk_aversion * cp.quad_form(w, cp.psd_wrap(sigma))
        - cost_rate * cp.norm1(w - w_prev)
    )
    constraints = [
        cp.norm1(w) <= gross_cap,
        cp.abs(cp.sum(w)) <= net_cap,
        cp.abs(w) <= position_cap,
    ]
    if turnover_cap is not None:
        constraints.append(cp.norm1(w - w_prev) <= turnover_cap)

    problem = cp.Problem(objective, constraints)
    problem.solve(solver=cp.OSQP, warm_start=True)

    if problem.status not in ("optimal", "optimal_inaccurate"):
        raise OptimizerInfeasible(f"cvxpy status: {problem.status}")

    return pd.Series(w.value, index=tickers, name=pd.NA)
