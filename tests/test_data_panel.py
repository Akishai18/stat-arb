"""PriceData enforces point-in-time access -- the no-lookahead foundation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.data import PriceData


@pytest.fixture
def sample_panel() -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=10, freq="B")
    return pd.DataFrame(
        {
            "USO": np.linspace(10.0, 12.0, 10),
            "UNG": np.linspace(20.0, 18.0, 10),
        },
        index=idx,
    )


def test_full_panel_returned_when_as_of_is_none(sample_panel):
    pd_view = PriceData(sample_panel)
    out = pd_view.adj_close()
    pd.testing.assert_frame_equal(out, sample_panel)


def test_as_of_strictly_limits_index(sample_panel):
    pd_view = PriceData(sample_panel)
    cutoff = sample_panel.index[4]
    out = pd_view.adj_close(as_of=cutoff)
    assert out.index.max() == cutoff
    assert (out.index <= cutoff).all()
    assert len(out) == 5


def test_as_of_excludes_future_rows(sample_panel):
    """Asking as-of a date must not return rows dated after it."""
    pd_view = PriceData(sample_panel)
    for cutoff in sample_panel.index:
        out = pd_view.adj_close(as_of=cutoff)
        assert (out.index <= cutoff).all(), f"leaked future row at as_of={cutoff}"


def test_as_of_accepts_string(sample_panel):
    pd_view = PriceData(sample_panel)
    out = pd_view.adj_close(as_of="2020-01-05")
    assert out.index.max() <= pd.Timestamp("2020-01-05")


def test_returns_match_manual_pct_change(sample_panel):
    pd_view = PriceData(sample_panel)
    expected = sample_panel.pct_change()
    pd.testing.assert_frame_equal(pd_view.returns(), expected)


def test_log_returns_close_to_simple_for_small_moves(sample_panel):
    pd_view = PriceData(sample_panel)
    simple = pd_view.returns(kind="simple").dropna()
    log_r = pd_view.returns(kind="log").dropna()
    # For ~1% moves the two should agree to within ~1e-4
    assert (log_r - simple).abs().max().max() < 1e-3


def test_unknown_return_kind_raises(sample_panel):
    with pytest.raises(ValueError):
        PriceData(sample_panel).returns(kind="weird")  # type: ignore[arg-type]


def test_unsorted_input_is_sorted(sample_panel):
    shuffled = sample_panel.iloc[[3, 0, 5, 1, 4, 2, 6, 7, 9, 8]]
    pd_view = PriceData(shuffled)
    assert pd_view.adj_close().index.is_monotonic_increasing


def test_rejects_non_datetime_index():
    bad = pd.DataFrame({"USO": [1.0, 2.0]}, index=[0, 1])
    with pytest.raises(TypeError):
        PriceData(bad)


def test_tickers_property(sample_panel):
    assert PriceData(sample_panel).tickers == ["USO", "UNG"]
