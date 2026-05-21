"""Walk-forward split logic."""

from __future__ import annotations

import pandas as pd

from statarb.evaluation import split_in_out_sample


def test_split_includes_boundary_in_is():
    s = pd.Series(
        range(10),
        index=pd.date_range("2018-12-28", periods=10, freq="B"),
    )
    is_part, oos_part = split_in_out_sample(s, in_sample_end="2018-12-31")
    # 2018-12-31 should be in IS
    assert pd.Timestamp("2018-12-31") in is_part.index
    # First OOS date must be strictly after 2018-12-31
    assert oos_part.index.min() > pd.Timestamp("2018-12-31")


def test_split_total_length_preserved():
    s = pd.Series(
        range(100),
        index=pd.date_range("2018-01-01", periods=100, freq="B"),
    )
    is_part, oos_part = split_in_out_sample(s, in_sample_end="2018-12-31")
    assert len(is_part) + len(oos_part) == len(s)


def test_split_dataframe():
    df = pd.DataFrame(
        {"A": range(10), "B": range(10)},
        index=pd.date_range("2018-12-28", periods=10, freq="B"),
    )
    is_df, oos_df = split_in_out_sample(df, in_sample_end="2018-12-31")
    assert is_df.shape[1] == 2 and oos_df.shape[1] == 2
