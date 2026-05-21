"""Realized-carry signal via ETF-vs-futures return spread.

Background. Cross-sectional curve carry is normally computed as
`(P_far - P_near) / P_near`, annualized -- it captures whether the futures
curve is in backwardation (positive) or contango (negative). Computing
this directly requires a clean historical series of both front-month and
second-nearby contract prices.

In this project we cannot build that for free (Yahoo doesn't preserve
expired single-contract data, and clean continuous futures with multiple
delivery months are paywalled). So we use a proxy:

    realized_carry[t] = ETF_return[t-lookback..t]  -  futures_return[t-lookback..t]

The ETF holds (and rolls) front-month futures; the front-month continuous
series approximates being permanently in the front contract without roll
cost. The DIFFERENCE between the two is the realized roll yield -- which
IS the curve carry, sampled by the ETF's roll mechanics. Negative spread
means the ETF underperformed the futures, i.e. it paid contango. Positive
spread means backwardation.

The output score is indexed by FUTURES ticker (not ETF ticker), so it
composes naturally with momentum and reversal signals computed on the
futures universe.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def realized_carry(
    adj_close: pd.DataFrame,
    *,
    pairs: Mapping[str, str],
    lookback: int = 21,
) -> pd.DataFrame:
    """Realized-carry score per futures contract.

    Parameters
    ----------
    adj_close : DataFrame
        Price panel containing BOTH the ETF tickers (keys of `pairs`) and
        the futures tickers (values of `pairs`).
    pairs : mapping
        ETF ticker -> paired futures ticker. The output is indexed by the
        futures tickers.
    lookback : int
        Trailing window in trading days for the return computation.
        Default 21 (~1 month, matching typical futures roll cadence).

    Returns
    -------
    DataFrame
        Same row index as `adj_close`; columns are the futures tickers
        (values of `pairs`). A value of -0.02 means the ETF underperformed
        the futures by 2% over the trailing `lookback` days (contango);
        a value of +0.02 means the ETF outperformed (backwardation).
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    if not pairs:
        raise ValueError("pairs must be non-empty")

    missing = []
    for etf_t, fut_t in pairs.items():
        if etf_t not in adj_close.columns:
            missing.append(etf_t)
        if fut_t not in adj_close.columns:
            missing.append(fut_t)
    if missing:
        raise ValueError(f"tickers missing from price panel: {sorted(set(missing))}")

    futures_cols = list(pairs.values())
    scores = pd.DataFrame(index=adj_close.index, columns=futures_cols, dtype=float)
    for etf_t, fut_t in pairs.items():
        etf_ret = adj_close[etf_t] / adj_close[etf_t].shift(lookback) - 1.0
        fut_ret = adj_close[fut_t] / adj_close[fut_t].shift(lookback) - 1.0
        scores[fut_t] = etf_ret - fut_ret
    return scores
