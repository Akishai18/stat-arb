"""COT managed-money positioning signal.

Hypothesis: managed-money speculators (CTAs, macro funds, trend followers)
tend to herd. When their net long position is at a 3-year extreme high,
the trade is crowded and forward returns are weaker; when their net short
position is at a 3-year extreme low, the same. The signal is the negated
z-score of managed money's net positioning as fraction of open interest,
computed per commodity vs a trailing 156-week (3-year) window.

Release-date discipline:
  - Raw CFTC data has `as_of` = Tuesday (data collection).
  - The release goes public Friday at 3:30 PM ET (`release` column already
    encodes this offset).
  - We index the daily score panel by `release` and forward-fill: a score
    becomes effective on its release Friday and is held daily through the
    following Thursday, when the next report's score replaces it.
  - The backtest engine then applies its standard one-day lag, so the
    first trade using a Friday-released score occurs on Monday.

Sign convention: `score = -zscore(mm_net_pct)` -- crowded long = bearish
(negative score), crowded short = bullish (positive score).
"""

from __future__ import annotations

import pandas as pd


def cot_positioning(
    cot_panel: pd.DataFrame,
    *,
    lookback_weeks: int = 156,
    target_index: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    """Daily score panel from the COT long DataFrame.

    Parameters
    ----------
    cot_panel : DataFrame
        Long-form output of `statarb.data.cftc.build_cot_panel`. Must have
        columns: `release`, `ticker`, `mm_net_pct`.
    lookback_weeks : int
        Rolling z-score window. Default 156 weeks ~= 3 years.
    target_index : DatetimeIndex, optional
        If given, the score panel is reindexed to this daily index (with
        forward-fill of weekly scores). If omitted, the output is indexed
        by release date.
    """
    required = {"release", "ticker", "mm_net_pct"}
    missing = required - set(cot_panel.columns)
    if missing:
        raise ValueError(f"cot_panel missing columns: {sorted(missing)}")

    # One row per (release, ticker). De-dup just in case.
    panel = cot_panel.sort_values(["ticker", "release"]).drop_duplicates(
        subset=["ticker", "release"], keep="last"
    )

    # Pivot to wide: index=release, columns=ticker, values=mm_net_pct.
    wide = panel.pivot(index="release", columns="ticker", values="mm_net_pct").sort_index()

    # Rolling z-score per ticker (axis=0 = time).
    mean = wide.rolling(lookback_weeks, min_periods=lookback_weeks // 2).mean()
    std = wide.rolling(lookback_weeks, min_periods=lookback_weeks // 2).std(ddof=1)
    std = std.where(std > 0)
    z = (wide - mean) / std
    score = -z  # crowded long = bearish

    if target_index is None:
        return score

    # Reindex to daily, forward-fill weekly values.
    daily = score.reindex(target_index, method="ffill")
    return daily
