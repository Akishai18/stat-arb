"""Walk-forward / in-sample-out-of-sample utilities.

Project default: IS = 2010-01-01 through 2018-12-31; OOS = 2019-01-01 onward.
The split is shared across all signals so reported metrics are comparable.
"""

from __future__ import annotations

from typing import TypeVar

import pandas as pd

from statarb.backtest.result import BacktestResult
from statarb.evaluation.metrics import PerformanceReport, evaluate

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
