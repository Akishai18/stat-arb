"""Portfolio construction: quantile selection, leverage targets, NaN policy."""

import numpy as np
import pandas as pd
import pytest

from statarb.portfolio import equal_weight, long_short_quantile_weights


@pytest.fixture
def scores_5x4() -> pd.DataFrame:
    # Rows = 5 days, cols = 4 assets. Easy hand-traceable values.
    return pd.DataFrame(
        [
            [1.0, 2.0, 3.0, 4.0],   # day 0: A < B < C < D
            [4.0, 3.0, 2.0, 1.0],   # day 1: reversed
            [1.0, np.nan, 3.0, 4.0],  # day 2: B missing
            [0.0, 0.0, 0.0, 0.0],   # day 3: ties everywhere
            [-1.0, 0.0, 0.0, 1.0],  # day 4: clear extremes only
        ],
        index=pd.date_range("2020-01-01", periods=5, freq="B"),
        columns=list("ABCD"),
    )


def test_equal_weight_long_only_sums_to_gross(scores_5x4):
    w = equal_weight(scores_5x4, gross_leverage=1.0)
    sums = w.sum(axis=1)
    # day 2 has one NaN -> 3 assets equal-weighted, still sums to 1
    assert (sums.round(10) == 1.0).all()


def test_equal_weight_handles_nan(scores_5x4):
    w = equal_weight(scores_5x4, gross_leverage=1.0)
    # B is NaN on day 2 -> weight 0
    assert w.loc[scores_5x4.index[2], "B"] == 0.0
    np.testing.assert_allclose(
        w.loc[scores_5x4.index[2], ["A", "C", "D"]].values,
        1 / 3,
    )


def test_long_short_top_bottom_selection(scores_5x4):
    # quantile=0.25 with 4 assets -> n_long = n_short = ceil(4*0.25) = 1
    w = long_short_quantile_weights(scores_5x4, long_quantile=0.25, short_quantile=0.25)
    d0 = scores_5x4.index[0]
    # Day 0: D is top, A is bottom
    assert w.loc[d0, "D"] > 0
    assert w.loc[d0, "A"] < 0
    assert w.loc[d0, "B"] == 0
    assert w.loc[d0, "C"] == 0


def test_long_short_is_dollar_neutral(scores_5x4):
    w = long_short_quantile_weights(scores_5x4, long_quantile=0.25, short_quantile=0.25)
    # Day 3 has all-zero scores -> sort is unstable but still dollar-neutral
    nets = w.sum(axis=1)
    assert (nets.abs() < 1e-12).all()


def test_long_short_respects_gross_leverage(scores_5x4):
    w = long_short_quantile_weights(
        scores_5x4, long_quantile=0.5, short_quantile=0.5, gross_leverage=2.0
    )
    gross = w.abs().sum(axis=1)
    # gross = 2.0 on all days where ranking is well-defined
    assert (gross.round(10) >= 0).all()
    # Day 0: 2 longs (C,D) + 2 shorts (A,B), gross_lev=2 -> |w|=0.5 each, gross=2.0
    assert gross.iloc[0] == pytest.approx(2.0)


def test_long_short_handles_missing_assets(scores_5x4):
    # Day 2: B is NaN, so only A, C, D are ranked. With quantile=0.5:
    # n_long = ceil(3*0.5) = 2, n_short = 2. They overlap -> trimmed.
    w = long_short_quantile_weights(scores_5x4, long_quantile=0.5, short_quantile=0.5)
    d2 = scores_5x4.index[2]
    assert w.loc[d2, "B"] == 0  # NaN asset never gets a weight


def test_long_short_too_few_assets_returns_zero_row():
    scores = pd.DataFrame(
        [[1.0, np.nan, np.nan, np.nan]],
        index=pd.date_range("2020-01-01", periods=1, freq="B"),
        columns=list("ABCD"),
    )
    w = long_short_quantile_weights(scores, long_quantile=0.5, short_quantile=0.5)
    assert (w.iloc[0] == 0).all()


def test_long_short_rejects_bad_quantiles():
    scores = pd.DataFrame([[1.0]], index=pd.date_range("2020-01-01", periods=1, freq="B"), columns=["A"])
    with pytest.raises(ValueError):
        long_short_quantile_weights(scores, long_quantile=0)
    with pytest.raises(ValueError):
        long_short_quantile_weights(scores, short_quantile=1.5)
    with pytest.raises(ValueError):
        long_short_quantile_weights(scores, gross_leverage=-1)


def test_equal_weight_rejects_bad_leverage():
    scores = pd.DataFrame([[1.0]], index=pd.date_range("2020-01-01", periods=1, freq="B"), columns=["A"])
    with pytest.raises(ValueError):
        equal_weight(scores, gross_leverage=0)
