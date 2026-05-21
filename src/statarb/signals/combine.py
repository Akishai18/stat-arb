"""Linear combination of cross-sectionally normalized signals.

Each input signal is first z-scored across assets (per day) so signals
with different magnitudes can be combined on the same scale. Then the
z-scores are linearly combined per weights.

Convention: any NaN-only row in an individual signal becomes NaN in that
signal's z-score; the combined output is NaN for an asset if any of the
contributing signals are NaN for that asset on that day. This is strict
but appropriate -- partially-missing signals would systematically bias
the cross-sectional ranking.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from statarb.signals._normalize import cross_sectional_zscore


def combine(
    scores_by_name: Mapping[str, pd.DataFrame],
    *,
    weights: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Z-score each input signal cross-sectionally, then linearly combine.

    Parameters
    ----------
    scores_by_name : mapping name -> score panel
        All panels must share the same row index and column set.
    weights : mapping name -> weight, optional
        If None, signals are equally weighted. Otherwise weights are
        normalized to sum to 1.0 by absolute value (so weights of (2, 1)
        and (4, 2) behave the same after re-scaling).

    Returns
    -------
    DataFrame
        Combined score panel with the same shape as any input.
    """
    if not scores_by_name:
        raise ValueError("scores_by_name must be non-empty")
    if weights is not None:
        missing = set(scores_by_name) - set(weights)
        if missing:
            raise ValueError(f"weights missing for signals: {sorted(missing)}")
        total = sum(abs(weights[k]) for k in scores_by_name)
        if total == 0:
            raise ValueError("weights cannot all be zero")
        norm = {k: weights[k] / total for k in scores_by_name}
    else:
        n = len(scores_by_name)
        norm = {k: 1.0 / n for k in scores_by_name}

    # Verify alignment up front -- silent misalignment would propagate
    # through pandas arithmetic and produce wrong scores.
    first_name, first_panel = next(iter(scores_by_name.items()))
    for name, panel in scores_by_name.items():
        if not panel.index.equals(first_panel.index):
            raise ValueError(f"signal {name!r} index does not match {first_name!r}")
        if list(panel.columns) != list(first_panel.columns):
            raise ValueError(f"signal {name!r} columns do not match {first_name!r}")

    z_scores = {name: cross_sectional_zscore(panel) for name, panel in scores_by_name.items()}
    combined = sum(norm[name] * z_scores[name] for name in scores_by_name)
    return combined


def sharpe_weighted_combine(
    scores_by_name: Mapping[str, pd.DataFrame],
    is_sharpes: Mapping[str, float],
    *,
    floor_at_zero: bool = True,
) -> pd.DataFrame:
    """Combine signals with weights proportional to their in-sample Sharpe.

    The standard recipe for heterogeneous signal quality: signals that
    didn't work in-sample (Sharpe <= 0) get weight 0; positive-Sharpe
    signals get weights proportional to their Sharpes; result is the
    Sharpe-weighted z-score blend.

    If every signal has Sharpe <= 0 (and `floor_at_zero=True`), this
    falls back to equal-weight rather than producing an all-zero alpha.

    Parameters
    ----------
    scores_by_name : mapping name -> score panel
    is_sharpes : mapping name -> in-sample Sharpe ratio
        Must contain a value for every signal. The Sharpes themselves
        come from running each signal standalone on the IS window.
    floor_at_zero : bool
        If True (default), negative Sharpes become weight 0. If False,
        negative Sharpes flip the signal (long becomes short and vice
        versa). Default `True` is safer -- we don't believe IS estimates
        precisely enough to flip a sign based on them.
    """
    if not scores_by_name:
        raise ValueError("scores_by_name must be non-empty")
    missing = set(scores_by_name) - set(is_sharpes)
    if missing:
        raise ValueError(f"is_sharpes missing entries for: {sorted(missing)}")

    if floor_at_zero:
        raw_weights = {k: max(0.0, is_sharpes[k]) for k in scores_by_name}
    else:
        raw_weights = {k: float(is_sharpes[k]) for k in scores_by_name}

    total = sum(abs(v) for v in raw_weights.values())
    if total == 0:
        # All-zero (or all-negative w/ floor) -> equal-weight fallback.
        return combine(scores_by_name)
    return combine(scores_by_name, weights=raw_weights)
