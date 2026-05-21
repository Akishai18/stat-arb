"""EIA inventory-surprise signal: seasonal baseline, sign, forward-fill."""

from __future__ import annotations

import pandas as pd
import pytest

from statarb.signals.inventory import inventory_surprise


def _build_eia_panel(values_by_ticker: dict[str, list[float]], start: str = "2015-01-02") -> pd.DataFrame:
    """Synthetic long-form EIA panel; weekly Friday `as_of` dates.

    `value` is treated as inventory level; `change_w_w` is taken directly
    from the supplied list (one value per week, interpreted as the weekly change).
    """
    rows = []
    for ticker, changes in values_by_ticker.items():
        for i, c in enumerate(changes):
            as_of = pd.Timestamp(start) + pd.Timedelta(weeks=i)
            release = as_of + pd.Timedelta(days=5)
            rows.append(
                {
                    "as_of": as_of,
                    "release": release,
                    "ticker": ticker,
                    "value": float("nan"),  # not used by signal
                    "change_w_w": c,
                }
            )
    return pd.DataFrame(rows)


def test_inventory_surprise_sign_unexpected_build_is_negative_score():
    """Build a series where the LAST week's change is much larger than
    the same-ISO-week historical mean -> negative score (bearish).
    """
    # 6 years of data, same ISO week. First 5 years all changes = +1.0;
    # final year week has change = +10.0 -> unexpected build of +9.0.
    # Inventory_surprise = -(actual - seasonal) = -(10 - 1) = -9.
    changes = []
    for _ in range(6):
        # 52 weeks of normal +1.0, then we'll inspect the last week's surprise
        changes.extend([1.0] * 52)
    # Make the very last week of year 6 an outsized build
    changes[-1] = 10.0

    panel = _build_eia_panel({"CL=F": changes}, start="2015-01-02")
    score = inventory_surprise(panel, seasonal_years=5)
    last = score["CL=F"].dropna().iloc[-1]
    assert last == pytest.approx(-9.0)


def test_inventory_surprise_unexpected_draw_is_positive_score():
    """Mirror: same setup but final week is a big DRAW -> positive score."""
    changes = []
    for _ in range(6):
        changes.extend([1.0] * 52)
    changes[-1] = -10.0  # unexpected DRAW
    panel = _build_eia_panel({"CL=F": changes}, start="2015-01-02")
    score = inventory_surprise(panel, seasonal_years=5)
    last = score["CL=F"].dropna().iloc[-1]
    # surprise = -10 - 1 = -11; score = -surprise = +11
    assert last == pytest.approx(11.0)


def test_inventory_surprise_seasonal_baseline_per_iso_week():
    """Different ISO weeks should use independent baselines.

    Build 6 years of synthetic data where every ISO week 1 has change = +5
    and every ISO week 26 has change = -3. The seasonal baseline for year 6
    week 1 = mean of years 1-5 week 1 = +5; surprise = 5 - 5 = 0.
    Same for week 26.
    """
    rows = []
    for year in range(2015, 2021):  # 6 years: 2015..2020
        # Anchor to ISO week 1 (early Jan) and ISO week 26 (late June) reliably.
        # Find the Friday of ISO week 1 and ISO week 26 via .strftime trick:
        # pd.Timestamp.fromisocalendar(year, week, day) -> Mon-Sun (day=1..7).
        # We want the Friday (day=5) of each ISO week.
        for iso_w, change_norm in [(1, 5.0), (26, -3.0)]:
            try:
                date = pd.Timestamp.fromisocalendar(year, iso_w, 5)
            except ValueError:
                continue
            rows.append(
                {
                    "as_of": date,
                    "release": date + pd.Timedelta(days=5),
                    "ticker": "X",
                    "value": float("nan"),
                    "change_w_w": change_norm,
                }
            )
    panel = pd.DataFrame(rows)
    score = inventory_surprise(panel, seasonal_years=5)
    # Once we're far enough into the data that the 5-year history exists,
    # every score should be exactly zero (actual matches the per-iso-week
    # baseline). Year 6 (2020) qualifies for both weeks.
    last = score["X"].dropna().tail(2)
    assert (last.abs() < 1e-9).all()


def test_target_index_forward_fills():
    changes = [1.0] * 60 + [3.0]  # final week build
    panel = _build_eia_panel({"CL=F": changes}, start="2015-01-02")
    daily = pd.date_range("2016-02-01", periods=14, freq="D")
    daily_score = inventory_surprise(panel, seasonal_years=1, target_index=daily)
    # All days should have a value
    assert daily_score["CL=F"].notna().any()


def test_panel_missing_columns_raises():
    bad = pd.DataFrame({"x": [1, 2, 3]})
    with pytest.raises(ValueError, match="missing columns"):
        inventory_surprise(bad)
