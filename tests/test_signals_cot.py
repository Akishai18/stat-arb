"""COT positioning signal: z-score correctness, sign, release-date timing."""

from __future__ import annotations

import pandas as pd
import pytest

from statarb.signals.cot import cot_positioning


def _build_cot_panel(values_by_ticker: dict[str, list[float]], start: str = "2020-01-07") -> pd.DataFrame:
    """Build a synthetic long-form COT panel.

    Each list is weekly mm_net_pct values. as_of is Tuesday-spaced; release
    is as_of + 3 business days.
    """
    rows = []
    for ticker, vals in values_by_ticker.items():
        for i, v in enumerate(vals):
            as_of = pd.Timestamp(start) + pd.Timedelta(weeks=i)
            release = as_of + pd.tseries.offsets.BDay(3)
            rows.append(
                {"as_of": as_of, "release": release, "ticker": ticker, "mm_net_pct": v}
            )
    return pd.DataFrame(rows)


def test_zscore_sign_crowded_long_is_negative_score():
    """With monotonically rising MM net %, every in-window value is above
    its rolling mean -> positive z -> negative negated score. Strongest
    "crowded" reading should be at the END."""
    panel = _build_cot_panel({"CL=F": list(range(160))})
    score = cot_positioning(panel, lookback_weeks=156)
    valid = score["CL=F"].dropna()
    # Every valid score should be negative (always above rolling mean).
    assert (valid < 0).all()
    # The most negative score should be the LAST (most crowded).
    assert valid.iloc[-1] == valid.min()


def test_zscore_sign_unwinding_to_crowded_short_is_positive():
    """Inverse: monotonically falling MM net % -> below rolling mean ->
    negative z -> positive negated score."""
    panel = _build_cot_panel({"CL=F": list(range(160, 0, -1))})
    score = cot_positioning(panel, lookback_weeks=156)
    valid = score["CL=F"].dropna()
    assert (valid > 0).all()
    # The MOST positive should be at the end (most "crowded short").
    assert valid.iloc[-1] == valid.max()


def test_zscore_constant_input_is_nan():
    """All-equal positioning -> std=0 -> NaN score (no information)."""
    panel = _build_cot_panel({"CL=F": [5.0] * 160})
    score = cot_positioning(panel, lookback_weeks=156)
    assert score["CL=F"].dropna().isna().all() or score["CL=F"].isna().all()


def test_signal_is_indexed_by_release_not_asof():
    panel = _build_cot_panel({"CL=F": list(range(160))}, start="2020-01-07")
    score = cot_positioning(panel, lookback_weeks=156)
    # First as_of was 2020-01-07 (Tuesday). Release = Tue + 3 BDays = Friday 2020-01-10.
    expected_first_release = pd.Timestamp("2020-01-07") + pd.tseries.offsets.BDay(3)
    assert score.index[0] == expected_first_release


def test_target_index_forward_fills():
    """When target_index is a daily span, the weekly score should be held.

    With 160 weekly inputs starting 2020-01-07, the first release lands
    around 2020-01-10 and the last around 2023-01. So a 2022 target window
    will be inside the forward-fillable range.
    """
    panel = _build_cot_panel({"CL=F": list(range(160))}, start="2020-01-07")
    daily_index = pd.date_range("2022-06-01", "2022-06-30", freq="D")
    daily = cot_positioning(panel, lookback_weeks=156, target_index=daily_index)
    # All days in this span should have a value (forward-filled from prior release).
    assert daily["CL=F"].notna().all()
    # Adjacent weekdays inside a Friday-to-Thursday block hold the same value.
    monday = pd.Timestamp("2022-06-13")
    tuesday = pd.Timestamp("2022-06-14")
    assert daily.loc[monday, "CL=F"] == daily.loc[tuesday, "CL=F"]


def test_panel_missing_columns_raises():
    bad = pd.DataFrame({"x": [1, 2, 3]})
    with pytest.raises(ValueError, match="missing columns"):
        cot_positioning(bad)


def test_multiple_tickers_independent():
    """Z-score is per ticker; one ticker's scaling shouldn't affect another."""
    panel = _build_cot_panel(
        {
            "CL=F": list(range(160)),  # increasing
            "NG=F": list(range(160, 0, -1)),  # decreasing
        }
    )
    score = cot_positioning(panel, lookback_weeks=156)
    last_cl = score["CL=F"].dropna().iloc[-1]
    last_ng = score["NG=F"].dropna().iloc[-1]
    # CL had highest -> most-negative score. NG had lowest -> most-positive.
    assert last_cl < 0 < last_ng
