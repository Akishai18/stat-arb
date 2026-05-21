"""Performance evaluation.

Metrics (Sharpe, Sortino, drawdown, turnover, hit rate, beta/alpha vs
benchmark), walk-forward splits, and plots.
"""

from statarb.evaluation.metrics import (
    PerformanceReport,
    annualized_return,
    annualized_vol,
    beta_alpha,
    cagr,
    daily_hit_rate,
    evaluate,
    max_drawdown,
    monthly_hit_rate,
    sharpe,
    sortino,
)
from statarb.evaluation.plots import plot_cost_sensitivity, plot_drawdown, plot_equity_curve
from statarb.evaluation.walk_forward import (
    DEFAULT_IS_END,
    evaluate_walkforward,
    split_in_out_sample,
)

__all__ = [
    "DEFAULT_IS_END",
    "PerformanceReport",
    "annualized_return",
    "annualized_vol",
    "beta_alpha",
    "cagr",
    "daily_hit_rate",
    "evaluate",
    "evaluate_walkforward",
    "max_drawdown",
    "monthly_hit_rate",
    "plot_cost_sensitivity",
    "plot_drawdown",
    "plot_equity_curve",
    "sharpe",
    "sortino",
    "split_in_out_sample",
]
