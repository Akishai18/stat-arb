"""EIA inventory-surprise signal.

Hypothesis: when this week's inventory build is larger than the same-week-
of-year average over the trailing 5 years, supply is stronger than
seasonal expectation -- bearish for the underlying commodity. Vice versa
for unexpected draws.

Without a paid consensus-expectations feed we use a 5-year same-week-of-
year seasonal average as the baseline. This is the standard public-data
proxy and the EIA's own weekly bulletin headlines a similar comparison
("inventories are X above/below the 5-year average for this time of year").

Release-date discipline:
  - Raw EIA data has `as_of` = the Friday week-ending date.
  - The WPSR releases the following Wednesday at 10:30 AM ET (`release`
    column already encodes this offset).
  - Score is indexed by `release` date and forward-filled daily until the
    next release.
  - Engine lag = 1 day, so the first trade using a Wednesday-released
    score is on Thursday.

Sign convention: `score = -(actual_change - seasonal_average_change)` --
unexpected build = bearish (negative score), unexpected draw = bullish.
"""

from __future__ import annotations

import pandas as pd


def inventory_surprise(
    eia_panel: pd.DataFrame,
    *,
    seasonal_years: int = 5,
    target_index: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """Daily score panel from the EIA long DataFrame.

    Parameters
    ----------
    eia_panel : DataFrame
        Long-form output of `statarb.data.eia.build_eia_panel`. Must have
        columns: `release`, `ticker`, `change_w_w`, `as_of`.
    seasonal_years : int
        Number of trailing years to average for the same-week-of-year
        seasonal baseline. Default 5.
    target_index : DatetimeIndex, optional
        If given, the score panel is reindexed to this daily index with
        forward-fill of weekly scores. If omitted, output is indexed by
        release date.
    """
    required = {"release", "as_of", "ticker", "change_w_w"}
    missing = required - set(eia_panel.columns)
    if missing:
        raise ValueError(f"eia_panel missing columns: {sorted(missing)}")

    panel = eia_panel.sort_values(["ticker", "as_of"]).copy()
    # Same-week-of-year baseline. ISO week labels by (year, week).
    panel["iso_week"] = panel["as_of"].dt.isocalendar().week

    surprises = []
    # For seasonal_years=1, "the prior year's same-week change" is one value;
    # require at least 1 prior observation rather than the default 2.
    min_p = min(2, seasonal_years)
    for _ticker, sub in panel.groupby("ticker", sort=False):
        sub = sub.sort_values("as_of").reset_index(drop=True)
        # For each row, compute the mean change_w_w over the same ISO week
        # in the prior `seasonal_years` years. Vectorized via groupby on
        # iso_week + rolling on the per-week series.
        baseline = (
            sub.groupby("iso_week")["change_w_w"]
            .transform(lambda s: s.shift(1).rolling(seasonal_years, min_periods=min_p).mean())
        )
        sub = sub.assign(seasonal=baseline)
        sub["surprise"] = sub["change_w_w"] - sub["seasonal"]
        sub["score"] = -sub["surprise"]
        surprises.append(sub[["release", "ticker", "score"]])

    long = pd.concat(surprises, ignore_index=True)
    wide = long.pivot(index="release", columns="ticker", values="score").sort_index()

    if target_index is None:
        return wide

    return wide.reindex(target_index, method="ffill")
