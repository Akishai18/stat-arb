"""Score -> weight transformations (portfolio construction).

A score panel has rows = dates, columns = assets, values = "how attractive
is this asset today". Higher = more long. This module turns scores into
weights that the backtest engine can consume.

Phase 2 functions:
  - equal_weight: equal long-only weights across non-NaN assets
  - long_short_quantile_weights: long top quantile, short bottom quantile,
        dollar-neutral, equal-weighted within each side

Convention:
  - Output dollar-neutral L/S portfolios have sum(longs) = +gross_leverage/2
    and sum(shorts) = -gross_leverage/2, so gross = sum(|w|) = gross_leverage
    and net = 0.
  - NaN in the score panel means "asset not available today" -> excluded
    from both ranking and weight assignment.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def equal_weight(scores: pd.DataFrame, *, gross_leverage: float = 1.0) -> pd.DataFrame:
    """Equal-weight long-only portfolio across the non-NaN assets each day.

    Score values are ignored aside from NaN-vs-not. Useful for baselines.
    """
    if gross_leverage <= 0:
        raise ValueError(f"gross_leverage must be positive, got {gross_leverage}")
    mask = scores.notna()
    n = mask.sum(axis=1)
    weights = mask.astype(float).div(n.replace(0, np.nan), axis=0) * gross_leverage
    return weights.fillna(0.0)


def long_short_quantile_weights(
    scores: pd.DataFrame,
    *,
    long_quantile: float = 0.2,
    short_quantile: float = 0.2,
    gross_leverage: float = 1.0,
) -> pd.DataFrame:
    """Long top quantile, short bottom quantile, equal-weighted within each side.

    Parameters
    ----------
    scores : DataFrame
        Rows = dates, columns = assets. Higher score = more long.
    long_quantile : float in (0, 1]
        Fraction of available assets to go long each day.
    short_quantile : float in (0, 1]
        Fraction of available assets to go short each day.
    gross_leverage : float
        sum(|weights|) target each day. The portfolio is dollar-neutral, so
        long book = +gross/2 and short book = -gross/2.

    Notes
    -----
    - Available = non-NaN score that day. Quantile is computed over the
      available subset only.
    - When there are too few assets to fill both books (e.g. n < 2), weights
      collapse to zero that day rather than raising.
    """
    if not 0 < long_quantile <= 1:
        raise ValueError(f"long_quantile must be in (0, 1], got {long_quantile}")
    if not 0 < short_quantile <= 1:
        raise ValueError(f"short_quantile must be in (0, 1], got {short_quantile}")
    if gross_leverage <= 0:
        raise ValueError(f"gross_leverage must be positive, got {gross_leverage}")

    weights = pd.DataFrame(0.0, index=scores.index, columns=scores.columns)
    half_gross = gross_leverage / 2.0

    for date, row in scores.iterrows():
        available = row.dropna()
        n = len(available)
        if n < 2:
            continue

        # ceil so that at small n we still get at least one name per side.
        n_long = max(1, int(np.ceil(n * long_quantile)))
        n_short = max(1, int(np.ceil(n * short_quantile)))

        # Edge case: overlap when long_quantile + short_quantile > 1. Resolve
        # by giving priority to extreme ranks: top n_long by score, bottom
        # n_short by score; if they overlap, we shrink toward the center.
        ranked = available.sort_values()
        shorts = ranked.iloc[:n_short].index
        longs = ranked.iloc[-n_long:].index
        overlap = set(longs) & set(shorts)
        if overlap:
            # Trim from whichever side has more, taking from the inner edge.
            # In practice this only fires when long_q + short_q >= 1.
            keep_long = [t for t in longs if t not in overlap]
            keep_short = [t for t in shorts if t not in overlap]
            longs = pd.Index(keep_long)
            shorts = pd.Index(keep_short)
            if len(longs) == 0 or len(shorts) == 0:
                continue

        weights.loc[date, longs] = half_gross / len(longs)
        weights.loc[date, shorts] = -half_gross / len(shorts)

    return weights
