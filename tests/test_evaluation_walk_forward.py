"""Walk-forward + year-by-year Sharpe analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd

from statarb.evaluation import annual_sharpe_table, split_in_out_sample


def _returns(year_means: dict[int, float], std: float = 0.01, seed: int = 0) -> pd.Series:
    """Build a multi-year returns series with a specified per-year mean."""
    rng = np.random.default_rng(seed)
    rows = []
    for year, mean in sorted(year_means.items()):
        idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="B")
        vals = rng.normal(mean, std, size=len(idx))
        rows.append(pd.Series(vals, index=idx))
    return pd.concat(rows)


def test_annual_sharpe_table_one_row_per_year():
    r = _returns({2019: 0.001, 2020: 0.002, 2021: -0.001})
    table = annual_sharpe_table(r, bootstrap_resamples=500, block_length=5)
    assert set(table["year"].tolist()) == {2019, 2020, 2021}


def test_annual_sharpe_recovers_sign_per_year():
    """Each year's realized Sharpe should be roughly the right sign."""
    r = _returns({2019: 0.002, 2020: -0.002, 2021: 0.0})
    table = annual_sharpe_table(r, bootstrap_resamples=500)
    by_year = {row.year: row for _, row in table.iterrows()}
    assert by_year[2019].sharpe > 0
    assert by_year[2020].sharpe < 0
    # 2021 mean ~ 0; sharpe could be either sign in any one sample.
    # Don't assert direction, just that the table reported it.
    assert "sharpe" in by_year[2021].index.tolist() or hasattr(by_year[2021], "sharpe")


def test_annual_sharpe_ci_columns_present():
    r = _returns({2019: 0.001})
    table = annual_sharpe_table(r, bootstrap_resamples=500)
    for col in ("ci_low", "ci_high", "n_days", "sharpe", "ann_vol", "cumulative_return"):
        assert col in table.columns


def test_annual_sharpe_skips_short_years():
    """If a year has fewer than min_days_per_year observations, skip it."""
    r = _returns({2019: 0.001})
    # Add a stub 2020 with only 10 days
    short_2020 = pd.Series(
        [0.001] * 10,
        index=pd.date_range("2020-01-01", periods=10, freq="B"),
    )
    combined = pd.concat([r, short_2020])
    table = annual_sharpe_table(combined, bootstrap_resamples=500, min_days_per_year=60)
    # 2020 should be skipped
    assert 2020 not in table["year"].tolist()


def test_annual_sharpe_significance_flag_correct():
    """A clearly-positive-mean year should be flagged significant; a
    near-zero-mean year usually shouldn't be."""
    # Strong positive: daily Sharpe = 0.005 / 0.01 * sqrt(252) ~ 7.9
    r = _returns({2019: 0.005}, std=0.01, seed=7)
    table = annual_sharpe_table(r, bootstrap_resamples=2000)
    assert table.iloc[0]["is_significant_at_5pct"]


def test_annual_sharpe_empty_input_returns_empty_dataframe():
    r = pd.Series([], dtype=float, index=pd.DatetimeIndex([]))
    table = annual_sharpe_table(r)
    assert table.empty


def test_split_in_out_sample_still_works():
    """Make sure the original split function wasn't broken by our additions."""
    idx = pd.date_range("2018-12-28", periods=5, freq="B")
    s = pd.Series(range(5), index=idx)
    is_part, oos_part = split_in_out_sample(s, in_sample_end="2018-12-31")
    assert len(is_part) + len(oos_part) == 5
