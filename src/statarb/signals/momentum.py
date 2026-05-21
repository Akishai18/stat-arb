"""Trailing-return momentum signal.

Standard cross-sectional momentum: at the close of day t, the score for
each asset is its trailing return from `t - lookback` to `t - skip` trading
days. Higher score = stronger momentum.

In daily approximation, `lookback=252` and `skip=21` reproduce the canonical
"12-1 momentum" used in the literature: 12-month formation period, last
month dropped to avoid short-term reversal contamination.

The signal at row t depends ONLY on prices at rows t-skip and t-lookback,
so the output is point-in-time-safe by construction. The backtest engine
applies a further one-day lag before trading.
"""

from __future__ import annotations

import pandas as pd


def momentum(
    adj_close: pd.DataFrame,
    *,
    lookback: int = 252,
    skip: int = 21,
) -> pd.DataFrame:
    """Trailing return from `t - lookback` to `t - skip`, per asset.

    Parameters
    ----------
    adj_close : DataFrame
        Adjusted-close panel, rows = dates, columns = assets.
    lookback : int
        Total formation window, in trading days. Default 252 (~1 year).
    skip : int
        Number of most-recent days to drop from the window. Default 21
        (~1 month). Set to 0 for a "no-skip" variant.

    Notes
    -----
    The first `lookback` rows of output are NaN by construction (no history
    available yet). Cross-sectional ranking will skip them.
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    if skip < 0:
        raise ValueError(f"skip must be non-negative, got {skip}")
    if lookback <= skip:
        raise ValueError(
            f"lookback ({lookback}) must exceed skip ({skip}) so the window "
            "has non-zero length"
        )

    recent = adj_close.shift(skip)
    older = adj_close.shift(lookback)
    return recent / older - 1.0
