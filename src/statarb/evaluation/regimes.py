"""Regime-classification utilities for Phase 8 final evaluation.

Each regime mask returns a boolean Series aligned to a date index, where
True means "in this regime". Regimes are descriptive lenses, not signals
themselves -- they are used to slice the strategy's net returns and ask
"does the strategy still work in this regime?"

The masks are point-in-time-safe in the sense that they use ONLY data
available at or before each date. (For backtest hygiene, anyway: in
Phase 8 we use them only on already-realized strategy returns, so the
PIT property is more of a convention than a strict necessity.)
"""

from __future__ import annotations

import pandas as pd

from statarb.backtest.result import BacktestResult
from statarb.evaluation.metrics import PerformanceReport, evaluate


def vix_regime(vix: pd.Series, *, threshold: float | None = None) -> pd.Series:
    """High-VIX (stressed) regime mask.

    If `threshold` is None, uses an expanding-median: True when the day's
    VIX exceeds the median of all VIX values up to and including that day.
    Otherwise uses a fixed numeric threshold.
    """
    v = vix.dropna()
    if threshold is None:
        median_to_date = v.expanding().median()
        return v > median_to_date
    return v > threshold


def trailing_return_regime(
    prices: pd.Series,
    *,
    lookback: int = 126,
) -> pd.Series:
    """Bull/bear regime via sign of trailing N-day return on a benchmark.

    Returns True when the benchmark's `lookback`-day return is positive
    (bull). First `lookback` rows are False by default (insufficient
    history).
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    ret = prices / prices.shift(lookback) - 1.0
    return (ret > 0).fillna(False)


def period_regime(
    index: pd.DatetimeIndex,
    *,
    split_date: str,
) -> pd.Series:
    """Pre/post date split. Returns True for dates strictly AFTER split_date."""
    ts = pd.Timestamp(split_date)
    return pd.Series(index > ts, index=index)


def strategy_vol_regime(
    net_returns: pd.Series,
    *,
    lookback: int = 63,
    threshold: float | None = None,
) -> pd.Series:
    """High-realized-vol regime for the strategy itself.

    Computes the trailing `lookback`-day annualized vol of the strategy's
    net returns. If `threshold` is None, uses expanding median of those
    realized vols.
    """
    r = net_returns.dropna()
    rolling_vol = r.rolling(lookback, min_periods=max(10, lookback // 3)).std(ddof=1) * (252**0.5)
    if threshold is None:
        threshold_series = rolling_vol.expanding().median()
        return rolling_vol > threshold_series
    return rolling_vol > threshold


def evaluate_by_regime(
    result: BacktestResult,
    *,
    regime_mask: pd.Series,
    benchmark_returns: pd.Series | None = None,
) -> dict[str, PerformanceReport]:
    """Split a BacktestResult by a boolean regime mask; report each side.

    Days where the mask is NaN are excluded from both reports (treated as
    "regime unknown" -- a defensible default that doesn't bias either side).

    Returns a dict with keys "in_regime" (mask=True) and "out_regime" (mask=False).
    """
    net = result.net_returns
    aligned = regime_mask.reindex(net.index)
    # Explicit equality avoids the `~bool` deprecation and handles
    # object-dtype masks (booleans + NaN -> object) without converting
    # NaN to True/False ambiguously.
    in_mask = (aligned == True).fillna(False).astype(bool)  # noqa: E712
    out_mask = (aligned == False).fillna(False).astype(bool)  # noqa: E712

    in_net = net.where(in_mask, other=float("nan"))
    out_net = net.where(out_mask, other=float("nan"))
    in_turnover = result.turnover.where(in_mask, other=0.0)
    out_turnover = result.turnover.where(out_mask, other=0.0)
    in_costs = result.costs.where(in_mask, other=0.0)
    out_costs = result.costs.where(out_mask, other=0.0)

    def _make(net_sub, turn, costs):
        return BacktestResult(
            weights_applied=result.weights_applied,
            turnover=turn,
            gross_returns=result.gross_returns,
            costs=costs,
            net_returns=net_sub,
            equity_curve=(1.0 + net_sub.fillna(0)).cumprod(),
            meta={**result.meta, "regime": "subset"},
        )

    in_res = _make(in_net, in_turnover, in_costs)
    out_res = _make(out_net, out_turnover, out_costs)

    bench_in = bench_out = None
    if benchmark_returns is not None:
        bench_in = benchmark_returns.where(in_mask.reindex(benchmark_returns.index).fillna(False), other=float("nan"))
        bench_out = benchmark_returns.where(out_mask.reindex(benchmark_returns.index).fillna(False), other=float("nan"))

    return {
        "in_regime": evaluate(in_res, benchmark_returns=bench_in),
        "out_regime": evaluate(out_res, benchmark_returns=bench_out),
    }


def regime_table(
    results_by_name: dict[str, BacktestResult],
    *,
    regimes: dict[str, pd.Series],
    benchmark_returns: pd.Series | None = None,
    metric: str = "sharpe",
) -> pd.DataFrame:
    """Build a long-form (strategy x regime x in/out) table for a single metric.

    Useful for "how does signal X perform in regime Y?" comparisons.
    """
    rows: list[dict] = []
    for strat_name, res in results_by_name.items():
        for regime_name, mask in regimes.items():
            split = evaluate_by_regime(res, regime_mask=mask, benchmark_returns=benchmark_returns)
            rows.append({
                "strategy": strat_name,
                "regime": regime_name,
                "in_regime": getattr(split["in_regime"], metric),
                "out_regime": getattr(split["out_regime"], metric),
            })
    return pd.DataFrame(rows)


__all__ = [
    "evaluate_by_regime",
    "period_regime",
    "regime_table",
    "strategy_vol_regime",
    "trailing_return_regime",
    "vix_regime",
]
