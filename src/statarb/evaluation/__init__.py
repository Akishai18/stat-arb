"""Performance evaluation.

Metrics (Sharpe, Sortino, drawdown, turnover, hit rate, beta/alpha vs
benchmark), walk-forward splits, and plots.
"""

from statarb.evaluation.bootstrap import BootstrapResult, bootstrap_sharpe
from statarb.evaluation.deflated_sharpe import (
    DSRResult,
    deflated_sharpe_ratio,
    expected_max_sharpe_under_null,
    probabilistic_sharpe_ratio,
)
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
from statarb.evaluation.regimes import (
    evaluate_by_regime,
    period_regime,
    regime_table,
    strategy_vol_regime,
    trailing_return_regime,
    vix_regime,
)
from statarb.evaluation.walk_forward import (
    DEFAULT_IS_END,
    AnnualSharpeRow,
    annual_sharpe_table,
    evaluate_walkforward,
    split_in_out_sample,
)

__all__ = [
    "DEFAULT_IS_END",
    "AnnualSharpeRow",
    "BootstrapResult",
    "DSRResult",
    "PerformanceReport",
    "annual_sharpe_table",
    "annualized_return",
    "annualized_vol",
    "beta_alpha",
    "bootstrap_sharpe",
    "cagr",
    "daily_hit_rate",
    "deflated_sharpe_ratio",
    "evaluate",
    "evaluate_by_regime",
    "evaluate_walkforward",
    "expected_max_sharpe_under_null",
    "max_drawdown",
    "monthly_hit_rate",
    "period_regime",
    "plot_cost_sensitivity",
    "plot_drawdown",
    "plot_equity_curve",
    "probabilistic_sharpe_ratio",
    "regime_table",
    "sharpe",
    "sortino",
    "split_in_out_sample",
    "strategy_vol_regime",
    "trailing_return_regime",
    "vix_regime",
]
