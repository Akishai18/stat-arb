"""Loop the single-day optimizer over a date range.

The output is a weights DataFrame ready to feed into the backtest engine
(`statarb.backtest.Backtester`). The engine handles the standard one-day
lag, so this runner produces weights dated by the day the signal was
computed -- same convention as every other portfolio-construction utility.

Convention recap:
  - weights[t] = the optimizer's solution USING data up to close of day t.
  - The engine lags by 1, so weights[t] earn returns[t+1].
  - cov[t] is the trailing-window covariance ending day t (also lag-safe).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

import pandas as pd

from statarb.portfolio.covariance import rolling_covariance
from statarb.portfolio.optimizer import OptimizerInfeasible, optimize_one_day

log = logging.getLogger(__name__)


def optimize_path(
    alpha_panel: pd.DataFrame,
    returns_panel: pd.DataFrame,
    *,
    gross_cap: float = 1.0,
    net_cap: float = 0.05,
    position_cap: float = 0.40,
    risk_aversion: float = 1.0,
    cost_bps_per_side: float = 0.0,
    turnover_cap: float | None = None,
    cov_lookback: int = 63,
    cov_min_periods: int = 20,
    cov_cache: Mapping[pd.Timestamp, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Solve the per-day QP across `alpha_panel`'s index.

    Parameters
    ----------
    alpha_panel : DataFrame
        Daily score panel, rows = dates, columns = tickers.
    returns_panel : DataFrame
        Daily returns panel covering at least `alpha_panel.index` plus
        `cov_lookback` days of history before it. Same column set as
        `alpha_panel`.
    cov_cache : optional precomputed cov lookup
        If supplied, the runner skips rolling_covariance and reads
        directly. Useful when sweeping hyperparameters: compute once,
        reuse across solves.

    Returns
    -------
    DataFrame of target weights with the same index/columns as
    `alpha_panel`. Days where the optimizer is infeasible or the cov
    matrix is missing produce all-zero weights (no position).
    """
    if not alpha_panel.columns.equals(returns_panel.columns):
        raise ValueError(
            f"alpha_panel columns {list(alpha_panel.columns)} != "
            f"returns_panel columns {list(returns_panel.columns)}"
        )

    cov_lookup = cov_cache or rolling_covariance(
        returns_panel, lookback=cov_lookback, min_periods=cov_min_periods
    )

    weights = pd.DataFrame(
        0.0,
        index=alpha_panel.index,
        columns=alpha_panel.columns,
    )
    prev = pd.Series(0.0, index=alpha_panel.columns)

    n_solved = n_infeasible = n_skipped = 0
    for date in alpha_panel.index:
        cov = cov_lookup.get(date)
        if cov is None:
            n_skipped += 1
            continue
        try:
            w = optimize_one_day(
                alpha=alpha_panel.loc[date],
                cov=cov,
                prev_weights=prev,
                gross_cap=gross_cap,
                net_cap=net_cap,
                position_cap=position_cap,
                risk_aversion=risk_aversion,
                cost_bps_per_side=cost_bps_per_side,
                turnover_cap=turnover_cap,
            )
        except OptimizerInfeasible:
            n_infeasible += 1
            continue
        weights.loc[date] = w
        prev = w
        n_solved += 1

    log.info(
        "optimizer ran %d solved, %d infeasible, %d skipped (no cov yet)",
        n_solved, n_infeasible, n_skipped,
    )
    return weights
