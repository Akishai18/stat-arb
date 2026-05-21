"""Short-term reversal signal.

The hypothesis: assets that moved sharply over the past few days tend to
partially mean-revert -- short-term moves are often liquidity-driven
overreactions rather than information-driven trends. The score is the
NEGATIVE of the trailing N-day return, so an oversold asset (large recent
loss) gets a high (positive) score and is targeted for the long book.

Common lookbacks: 1, 5, 21 trading days. 5-day is the canonical "weekly"
reversal in the cross-sectional equity literature.

The signal at row t uses prices at rows t and t-lookback, so it is
point-in-time-safe by construction. The backtest engine applies a further
one-day lag before trading.
"""

from __future__ import annotations

import pandas as pd


def reversal(adj_close: pd.DataFrame, *, lookback: int = 5) -> pd.DataFrame:
    """Negative trailing-`lookback`-day return, per asset.

    Parameters
    ----------
    adj_close : DataFrame
        Adjusted-close panel, rows = dates, columns = assets.
    lookback : int
        Window in trading days. Default 5 (~1 week). Must be positive.
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    return -(adj_close / adj_close.shift(lookback) - 1.0)
