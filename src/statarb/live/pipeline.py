"""Single source of truth for the live headline target weights.

The deployable strategy (FINAL.md): equal-weight cross-sectional z-score blend
of carry (21-day ETF-vs-futures spread) and COT (3-year managed-money
positioning z-score) -> long top 40% / short bottom 40% quantile portfolio,
dollar-neutral, daily rebalance.

Both the Streamlit dashboard (`dashboard/state.py`) and the daily live job
(`scripts/daily_pulse.py`) call into here, so the paper book trades exactly the
strategy the backtest validated. Do NOT re-derive the pipeline anywhere else --
a second copy is how live silently drifts from the research.
"""

from __future__ import annotations

import pandas as pd

from statarb.data import ETF_FUTURES_PAIRS, all_tradable_futures
from statarb.portfolio import long_short_quantile_weights
from statarb.signals import combine as eq_combine
from statarb.signals import cot_positioning, realized_carry

# Locked headline parameters -- mirror dashboard/state.py and run_walkforward.py.
CARRY_LOOKBACK = 21
COT_LOOKBACK_WEEKS = 156
LONG_Q = 0.4
SHORT_Q = 0.4
COST_BPS = 10


def headline_signals(adj_clean: pd.DataFrame, cot_panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compute the two surviving signal panels (carry, cot) aligned to the
    tradable-futures universe and the daily price index."""
    futures = all_tradable_futures()
    carry_raw = realized_carry(adj_clean, pairs=ETF_FUTURES_PAIRS, lookback=CARRY_LOOKBACK)
    carry_score = pd.DataFrame(index=adj_clean.index, columns=futures, dtype=float)
    for col in carry_raw.columns:
        if col in carry_score.columns:
            carry_score[col] = carry_raw[col]
    cot_score = cot_positioning(
        cot_panel, lookback_weeks=COT_LOOKBACK_WEEKS, target_index=adj_clean.index,
    ).reindex(columns=futures)
    return {"carry": carry_score, "cot": cot_score}


def headline_weights_from_signals(
    carry_score: pd.DataFrame,
    cot_score: pd.DataFrame,
    *,
    first_valid: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """The combine + quantile step. Pulled out so the dashboard (which already
    holds the signal panels) and the live job share one definition.

    `first_valid` slices both signals before combining, reproducing the
    dashboard's behaviour exactly. The latest row is identical with or without
    the slice (quantiles are per-day cross-sectional), so the live path may
    leave it None.
    """
    carry = carry_score if first_valid is None else carry_score.loc[first_valid:]
    cot = cot_score if first_valid is None else cot_score.loc[first_valid:]
    alpha = eq_combine({"carry": carry, "cot": cot})
    return long_short_quantile_weights(
        alpha, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )


def headline_target_weights(
    adj_clean: pd.DataFrame,
    cot_panel: pd.DataFrame,
    *,
    first_valid: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Full target-weight panel (dates x futures) from raw cleaned prices + COT.

    This is what the live job calls: it owns no signal state, only the cleaned
    inputs. Returns the same panel the backtester trades.
    """
    sigs = headline_signals(adj_clean, cot_panel)
    return headline_weights_from_signals(sigs["carry"], sigs["cot"], first_valid=first_valid)


def latest_target(weights: pd.DataFrame) -> pd.Series:
    """Most recent row with a live (non-zero) target -- today's book."""
    non_empty = weights.abs().sum(axis=1) > 0
    if not non_empty.any():
        raise ValueError("weight panel has no non-zero target rows")
    last_day = non_empty[non_empty].index.max()
    return weights.loc[last_day]
