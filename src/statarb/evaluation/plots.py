"""Plot helpers for backtest results.

Each function returns the matplotlib Figure and, if `save_path` is given,
also writes a PNG. Plots are intentionally minimal and report-ready:
white background, grid, single accent color per series, no gimmicks.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from statarb.backtest.result import BacktestResult


def _finalize(fig: plt.Figure, save_path: Path | str | None) -> plt.Figure:
    fig.tight_layout()
    if save_path is not None:
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=140, bbox_inches="tight")
    return fig


def plot_equity_curve(
    result: BacktestResult,
    *,
    benchmark: pd.Series | None = None,
    title: str = "Strategy equity curve",
    save_path: Path | str | None = None,
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(result.equity_curve.index, result.equity_curve.values, label="strategy (net)", color="#1f4e79", linewidth=1.5)
    if benchmark is not None:
        bench = benchmark.dropna()
        bench_eq = (1.0 + bench).cumprod()
        # Align both curves to start at 1.0 on the same first date
        first = max(result.equity_curve.index.min(), bench_eq.index.min())
        ax.plot(
            bench_eq.loc[first:].index,
            bench_eq.loc[first:].values / bench_eq.loc[first:].iloc[0],
            label="benchmark",
            color="#a6a6a6",
            linewidth=1.2,
            linestyle="--",
        )
    ax.set_title(title)
    ax.set_ylabel("growth of $1")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False)
    return _finalize(fig, save_path)


def plot_drawdown(
    result: BacktestResult,
    *,
    title: str = "Strategy drawdown",
    save_path: Path | str | None = None,
) -> plt.Figure:
    equity = result.equity_curve
    dd = equity / equity.cummax() - 1.0
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.fill_between(dd.index, dd.values, 0, color="#c0392b", alpha=0.4)
    ax.plot(dd.index, dd.values, color="#7b241c", linewidth=1.0)
    ax.set_title(title)
    ax.set_ylabel("drawdown")
    ax.set_ylim(min(-0.05, float(dd.min()) * 1.1), 0.02)
    ax.grid(alpha=0.3)
    return _finalize(fig, save_path)


def plot_cost_sensitivity(
    results_by_bps: Mapping[int, BacktestResult],
    *,
    title: str = "Cost sensitivity",
    save_path: Path | str | None = None,
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    palette = ["#1f4e79", "#2e75b6", "#9dc3e6", "#c00000"]
    for (bps, res), color in zip(sorted(results_by_bps.items()), palette, strict=False):
        ax.plot(
            res.equity_curve.index,
            res.equity_curve.values,
            label=f"{bps} bps/side",
            color=color,
            linewidth=1.3,
        )
    ax.set_title(title)
    ax.set_ylabel("growth of $1")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False)
    return _finalize(fig, save_path)
