"""Walk-forward / in-sample-out-of-sample utilities.

Project default: IS = 2010-01-01 through 2018-12-31; OOS = 2019-01-01 onward.
The split is shared across all signals so reported metrics are comparable.

Also provides:
  - annual_sharpe_table: per-calendar-year Sharpe + bootstrap CI for any
    daily return series. Used to defend "the strategy is consistent
    year-by-year, not driven by a few good years."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

import numpy as np
import pandas as pd

from statarb.backtest.result import BacktestResult
from statarb.evaluation.bootstrap import bootstrap_sharpe
from statarb.evaluation.metrics import TRADING_DAYS, PerformanceReport, evaluate

DEFAULT_IS_END = "2018-12-31"

PD = TypeVar("PD", pd.Series, pd.DataFrame)


def split_in_out_sample(obj: PD, *, in_sample_end: str = DEFAULT_IS_END) -> tuple[PD, PD]:
    """Split a Series or DataFrame at `in_sample_end` (inclusive in IS)."""
    end = pd.Timestamp(in_sample_end)
    is_part = obj.loc[:end]
    oos_part = obj.loc[end + pd.Timedelta(days=1):]
    return is_part, oos_part


def evaluate_walkforward(
    result: BacktestResult,
    *,
    benchmark_returns: pd.Series | None = None,
    in_sample_end: str = DEFAULT_IS_END,
) -> dict[str, PerformanceReport]:
    """Compute PerformanceReport on IS, OOS, and the full window.

    Walk-forward discipline for this project: parameter choices may only
    be tuned on IS; OOS is reported as-is for honest evaluation.
    """
    full_net = result.net_returns
    is_net, oos_net = split_in_out_sample(full_net, in_sample_end=in_sample_end)
    is_turn, oos_turn = split_in_out_sample(result.turnover, in_sample_end=in_sample_end)
    is_cost, oos_cost = split_in_out_sample(result.costs, in_sample_end=in_sample_end)
    is_w, oos_w = split_in_out_sample(result.weights_applied, in_sample_end=in_sample_end)
    is_eq = (1.0 + is_net.fillna(0)).cumprod()
    oos_eq = (1.0 + oos_net.fillna(0)).cumprod()
    is_g, oos_g = split_in_out_sample(result.gross_returns, in_sample_end=in_sample_end)

    is_result = BacktestResult(
        weights_applied=is_w,
        turnover=is_turn,
        gross_returns=is_g,
        costs=is_cost,
        net_returns=is_net,
        equity_curve=is_eq,
        meta={**result.meta, "window": "in_sample"},
    )
    oos_result = BacktestResult(
        weights_applied=oos_w,
        turnover=oos_turn,
        gross_returns=oos_g,
        costs=oos_cost,
        net_returns=oos_net,
        equity_curve=oos_eq,
        meta={**result.meta, "window": "out_of_sample"},
    )

    bench_is = bench_oos = None
    if benchmark_returns is not None:
        bench_is, bench_oos = split_in_out_sample(benchmark_returns, in_sample_end=in_sample_end)

    return {
        "in_sample": evaluate(is_result, benchmark_returns=bench_is),
        "out_of_sample": evaluate(oos_result, benchmark_returns=bench_oos),
        "full": evaluate(result, benchmark_returns=benchmark_returns),
    }


@dataclass(frozen=True)
class AnnualSharpeRow:
    """One year of a strategy's performance + uncertainty."""
    year: int
    n_days: int
    sharpe: float
    ci_low: float       # bootstrap 95% CI lower bound
    ci_high: float      # bootstrap 95% CI upper bound
    ann_return: float
    ann_vol: float
    cumulative_return: float    # raw cumulative return for the year
    is_significant_at_5pct: bool  # CI excludes zero
    is_positive: bool             # point Sharpe > 0


def annual_sharpe_table(
    returns: pd.Series,
    *,
    bootstrap_resamples: int = 2000,
    block_length: int = 5,
    min_days_per_year: int = 60,
    rng_seed: int = 0,
) -> pd.DataFrame:
    """Per-calendar-year Sharpe + bootstrap CI table.

    Splits `returns` by calendar year. For each year with at least
    `min_days_per_year` non-NaN observations, computes:
      - annualized Sharpe
      - bootstrap CI (block_length default 5 days since one-year windows
        contain ~250 obs; longer blocks would leave too few re-sample units)
      - significance flag

    The bootstrap CI inside a single year is necessarily wide -- one year
    of data isn't much to estimate a Sharpe from. The point of this table
    is not "is each year individually significant" (mostly no), but
    "is the DIRECTION of the realized Sharpe consistent across years?"
    """
    r = returns.dropna()
    if r.empty:
        return pd.DataFrame(columns=[f.name for f in AnnualSharpeRow.__dataclass_fields__.values()])

    rows: list[AnnualSharpeRow] = []
    for year, sub in r.groupby(r.index.year):
        if len(sub) < min_days_per_year:
            continue
        mean = sub.mean()
        std = sub.std(ddof=1)
        sharpe = (mean / std * np.sqrt(TRADING_DAYS)) if std > 0 else float("nan")
        # Use a smaller block for the year-level bootstrap (5 days ~ a week)
        # so we don't run out of sample units.
        boot = bootstrap_sharpe(
            sub,
            n_resamples=bootstrap_resamples,
            block_length=block_length,
            rng_seed=rng_seed,
        )
        cumret = float((1.0 + sub).prod() - 1.0)
        rows.append(AnnualSharpeRow(
            year=int(year),
            n_days=len(sub),
            sharpe=float(sharpe),
            ci_low=float(boot.ci_low),
            ci_high=float(boot.ci_high),
            ann_return=float(mean * TRADING_DAYS),
            ann_vol=float(std * np.sqrt(TRADING_DAYS)),
            cumulative_return=cumret,
            is_significant_at_5pct=bool(boot.is_significant_at_5pct),
            is_positive=bool(sharpe > 0),
        ))
    return pd.DataFrame([r.__dict__ for r in rows])


__all__ = [
    "DEFAULT_IS_END",
    "AnnualSharpeRow",
    "annual_sharpe_table",
    "evaluate_walkforward",
    "split_in_out_sample",
]
