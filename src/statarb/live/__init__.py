"""Live paper-trading layer (Layer B).

`pipeline`  -- single source of truth for the headline target weights, shared
              by the dashboard and the daily live job so the paper book trades
              exactly the strategy the backtest validated.
`portfolio` -- LivePortfolio: incremental, parquet-persisted paper book whose
              cumulative P&L reconciles with the vectorized Backtester.
"""

from __future__ import annotations

from statarb.live.pipeline import (
    CARRY_LOOKBACK,
    COST_BPS,
    COT_LOOKBACK_WEEKS,
    LONG_Q,
    SHORT_Q,
    headline_signals,
    headline_target_weights,
    headline_weights_from_signals,
    latest_target,
)
from statarb.live.portfolio import LivePortfolio

__all__ = [
    "CARRY_LOOKBACK",
    "COST_BPS",
    "COT_LOOKBACK_WEEKS",
    "LONG_Q",
    "SHORT_Q",
    "LivePortfolio",
    "headline_signals",
    "headline_target_weights",
    "headline_weights_from_signals",
    "latest_target",
]
