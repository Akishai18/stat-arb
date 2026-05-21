"""Covariance-matrix estimation for the portfolio optimizer.

Simple rolling sample covariance: at each date t, the covariance matrix
is computed from the trailing `lookback` daily returns.

We deliberately do NOT use anything fancier (no Ledoit-Wolf shrinkage, no
EWMA, no factor model). The universe is small (5 commodities), so sample
covariance is well-conditioned, and the optimizer's risk-aversion knob
already provides regularization. Adding shrinkage would be a Phase 9
extension if needed.
"""

from __future__ import annotations

import pandas as pd


def rolling_covariance(
    returns: pd.DataFrame,
    *,
    lookback: int = 63,
    min_periods: int = 20,
) -> dict[pd.Timestamp, pd.DataFrame]:
    """Return a per-date covariance-matrix lookup.

    Parameters
    ----------
    returns : DataFrame
        Daily returns panel, rows = dates, columns = assets.
    lookback : int
        Trailing window length in days. Default 63 (~3 months).
    min_periods : int
        Minimum number of non-NaN rows required to compute a cov matrix.
        Dates with fewer valid observations are omitted from the output.

    Returns
    -------
    dict mapping each date to an N x N covariance DataFrame indexed by
    asset. Dates without enough history are absent.
    """
    if lookback <= 1:
        raise ValueError(f"lookback must be > 1, got {lookback}")
    if min_periods < 2:
        raise ValueError(f"min_periods must be >= 2, got {min_periods}")
    if min_periods > lookback:
        raise ValueError(f"min_periods ({min_periods}) cannot exceed lookback ({lookback})")

    out: dict[pd.Timestamp, pd.DataFrame] = {}
    # rolling.cov() returns a MultiIndex (date, asset) -> asset DataFrame; the
    # iter-by-date approach below is more legible for downstream consumers.
    for i in range(lookback, len(returns) + 1):
        window = returns.iloc[i - lookback : i]
        if window.notna().sum().min() < min_periods:
            continue
        cov = window.cov()
        date = returns.index[i - 1]
        out[date] = cov
    return out
