"""Score normalization utilities.

Cross-sectional z-score: per row, subtract the row mean and divide by the
row std (computed across columns / assets, ddof=1). Used to put signals on
the same scale before combining (Phase 4 onward).

NaN policy: NaN inputs are excluded from the row's mean/std. Rows with
fewer than 2 non-NaN entries -- where std is undefined or zero -- produce
all-NaN output. Zero-variance rows likewise produce NaN.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cross_sectional_zscore(scores: pd.DataFrame) -> pd.DataFrame:
    """Z-score each row across columns. Returns a DataFrame with the same shape."""
    mean = scores.mean(axis=1)
    std = scores.std(axis=1, ddof=1)
    # std=0 (or undefined) -> mark row as NaN to avoid spurious infinities.
    std = std.where(std > 0)
    return scores.sub(mean, axis=0).div(std, axis=0)


def cross_sectional_rank(
    scores: pd.DataFrame,
    *,
    pct: bool = True,
) -> pd.DataFrame:
    """Per-row rank across assets.

    `pct=True` returns ranks normalized to [0, 1]. `pct=False` returns 1..n.
    NaN inputs stay NaN. Useful when you want a rank-based combination of
    signals that ignores absolute magnitudes.
    """
    ranks = scores.rank(axis=1, method="average", pct=pct)
    return ranks.where(scores.notna(), other=np.nan)
