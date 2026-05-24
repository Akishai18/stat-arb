"""Time-series momentum signal.

Different from `signals.momentum` (cross-sectional). Time-series momentum
asks "is THIS asset trending up?" independently of other assets, by
sign-and-magnitude of its own trailing N-day return. Long if positive,
short if negative.

This is the classic CTA / trend-following construction (Moskowitz-Ooi-
Pedersen 2012, "Time Series Momentum"). It works on small cross-sections
where cross-sectional momentum's ranking is unreliable, because each
asset's signal stands alone.

Output convention: continuous score = trailing return. Higher = more
long. The cross-sectional z-score in `signals.combine` will normalize
this against the day's other signals before blending.
"""

from __future__ import annotations

import pandas as pd


def ts_momentum(
    adj_close: pd.DataFrame,
    *,
    lookback: int = 126,
) -> pd.DataFrame:
    """Per-asset trailing-`lookback`-day return.

    Parameters
    ----------
    adj_close : DataFrame
        Adjusted-close panel, rows = dates, columns = assets.
    lookback : int
        Window in trading days. Default 126 (~6 months), the canonical
        choice for time-series momentum on commodities (Moskowitz et al
        report Sharpes typically peak around 6-12 month lookbacks).
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    return adj_close / adj_close.shift(lookback) - 1.0
