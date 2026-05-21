"""Linear (proportional) transaction-cost model.

Convention (locked across the project):

  - `turnover_t = sum_i |w_{t,i} - w_{t-1,i}|`  -- two-sided. A full 100% rotation
    counts as turnover = 2.0 (sold 1.0 of old + bought 1.0 of new).
  - `bps_per_side` is the cost in basis points charged on each side of a trade.
    For a full rotation: cost = 2.0 * bps_per_side / 10_000.
  - Cost is a fraction of NAV, subtracted from gross portfolio return on the
    day the rebalance occurs.

This matches the industry slippage convention where "10 bps slippage" means
10 bps per dollar traded, applied to each side of a round-trip.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class CostModel(Protocol):
    """Anything that maps a turnover series to a daily cost series."""

    def cost(self, turnover: pd.Series) -> pd.Series: ...


class LinearCostModel:
    """Cost is linear in (two-sided) turnover.

    Examples
    --------
    >>> LinearCostModel(bps_per_side=10).cost(pd.Series([2.0])).iloc[0]
    0.002
    """

    def __init__(self, bps_per_side: float) -> None:
        if bps_per_side < 0:
            raise ValueError(f"bps_per_side must be non-negative, got {bps_per_side}")
        self.bps_per_side = bps_per_side
        self._rate = bps_per_side / 10_000.0

    def cost(self, turnover: pd.Series) -> pd.Series:
        return turnover.astype(float) * self._rate

    def __repr__(self) -> str:
        return f"LinearCostModel(bps_per_side={self.bps_per_side})"


class ZeroCostModel:
    """No-cost model -- useful for gross-return analysis and tests."""

    def cost(self, turnover: pd.Series) -> pd.Series:
        return pd.Series(0.0, index=turnover.index)

    def __repr__(self) -> str:
        return "ZeroCostModel()"
