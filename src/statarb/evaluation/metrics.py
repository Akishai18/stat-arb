"""Performance metrics for daily-return series.

Annualization factor is 252 trading days throughout the project.

All Sharpe/Sortino numbers are annualized with `ddof=1` (sample std), no
risk-free adjustment by default. Pass `rf` (annualized rate, e.g. 0.04 for
4%) to subtract it from excess returns first.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from statarb.backtest.result import BacktestResult

TRADING_DAYS = 252

# Threshold below which a sample std is treated as numerically zero. Daily
# returns are O(0.01); floating-point variance error on a constant-valued
# input lands around 1e-18. 1e-12 sits comfortably between them.
_VOL_TOL = 1e-12


# ---------------------------------------------------------------------------
# Atomic metric functions
# ---------------------------------------------------------------------------


def annualized_return(returns: pd.Series) -> float:
    r = returns.dropna()
    return float(r.mean() * TRADING_DAYS) if len(r) else float("nan")


def annualized_vol(returns: pd.Series) -> float:
    r = returns.dropna()
    return float(r.std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(r) > 1 else float("nan")


def sharpe(returns: pd.Series, *, rf: float = 0.0) -> float:
    """Annualized Sharpe. `rf` is annualized risk-free rate (e.g. 0.04)."""
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    excess = r - rf / TRADING_DAYS
    s = excess.std(ddof=1)
    if s < _VOL_TOL:
        return float("nan")
    return float(excess.mean() / s * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, *, rf: float = 0.0) -> float:
    """Annualized Sortino: excess.mean / downside_dev * sqrt(252).

    Downside deviation is sqrt(mean(min(excess, 0)^2)) -- i.e. zero-min'd
    excess returns, then RMS over all days (not just down days). This is
    the standard definition; using only down days inflates the metric.
    """
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    excess = r - rf / TRADING_DAYS
    downside = np.minimum(excess, 0.0)
    dd = np.sqrt(float((downside**2).mean()))
    if dd < _VOL_TOL:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS))


def cagr(returns: pd.Series) -> float:
    r = returns.dropna()
    if len(r) == 0:
        return float("nan")
    equity_final = float((1.0 + r).prod())
    n_years = len(r) / TRADING_DAYS
    if n_years <= 0 or equity_final <= 0:
        return float("nan")
    return equity_final ** (1.0 / n_years) - 1.0


def max_drawdown(returns: pd.Series) -> dict[str, float]:
    """Returns max drawdown (negative number) and the longest drawdown
    duration in trading days.

    Drawdown duration = longest consecutive stretch where the equity curve
    sits below its running maximum. Counted from the first below-peak day
    to the day equity recovers to (or exceeds) the prior peak.
    """
    r = returns.dropna()
    if len(r) == 0:
        return {"max_drawdown": float("nan"), "drawdown_days": 0}
    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    max_dd = float(dd.min())

    in_dd = dd < 0
    if not in_dd.any():
        return {"max_drawdown": max_dd, "drawdown_days": 0}

    # Group consecutive in/out-of-drawdown runs; pick the longest in-DD run.
    groups = (in_dd != in_dd.shift()).cumsum()
    run_lengths = in_dd.groupby(groups).sum()
    longest = int(run_lengths.max())
    return {"max_drawdown": max_dd, "drawdown_days": longest}


def daily_hit_rate(returns: pd.Series) -> float:
    """Fraction of non-zero days with positive return.

    Excludes exact-zero days because the pre-lag boundary day always has
    gross_return = 0 by convention -- including it would systematically
    pull the hit rate toward 50%.
    """
    r = returns.dropna()
    nonzero = r[r != 0]
    return float((nonzero > 0).mean()) if len(nonzero) else float("nan")


def monthly_hit_rate(returns: pd.Series) -> float:
    """Resample to month-end and report fraction of positive months."""
    r = returns.dropna()
    if len(r) == 0:
        return float("nan")
    monthly = (1.0 + r).resample("ME").prod() - 1.0
    return float((monthly > 0).mean())


def beta_alpha(strategy: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    """OLS regression: strategy = alpha + beta * benchmark. Alpha annualized."""
    df = pd.concat([strategy.rename("s"), benchmark.rename("b")], axis=1).dropna()
    if len(df) < 30:
        return {"beta": float("nan"), "alpha_ann": float("nan")}
    cov = df.cov()
    var_b = cov.loc["b", "b"]
    if var_b == 0:
        return {"beta": float("nan"), "alpha_ann": float("nan")}
    beta = cov.loc["s", "b"] / var_b
    alpha_daily = df["s"].mean() - beta * df["b"].mean()
    return {"beta": float(beta), "alpha_ann": float(alpha_daily * TRADING_DAYS)}


# ---------------------------------------------------------------------------
# Bundled report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerformanceReport:
    n_days: int
    cagr: float
    ann_return: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    drawdown_days: int
    daily_hit_rate: float
    monthly_hit_rate: float
    ann_turnover: float
    cost_drag_ann: float
    beta: float | None
    alpha_ann: float | None

    def to_dict(self) -> dict[str, float | int | None]:
        return self.__dict__.copy()

    def __repr__(self) -> str:
        parts = [
            f"days={self.n_days}",
            f"CAGR={self.cagr:.2%}",
            f"vol={self.ann_vol:.2%}",
            f"Sharpe={self.sharpe:.2f}",
            f"Sortino={self.sortino:.2f}",
            f"MaxDD={self.max_drawdown:.2%}",
            f"hit/d={self.daily_hit_rate:.1%}",
            f"turnover/yr={self.ann_turnover:.1f}x",
        ]
        if self.beta is not None:
            parts.append(f"beta={self.beta:.2f}")
            parts.append(f"alpha={self.alpha_ann:.2%}")
        return "PerformanceReport(" + ", ".join(parts) + ")"


def evaluate(
    result: BacktestResult,
    *,
    benchmark_returns: pd.Series | None = None,
) -> PerformanceReport:
    """Compute the full PerformanceReport from a BacktestResult."""
    net = result.net_returns
    nyears = len(net.dropna()) / TRADING_DAYS if len(net.dropna()) else 0.0
    dd = max_drawdown(net)
    if benchmark_returns is not None:
        ba = beta_alpha(net, benchmark_returns)
        beta_v, alpha_v = ba["beta"], ba["alpha_ann"]
    else:
        beta_v, alpha_v = None, None
    return PerformanceReport(
        n_days=len(net.dropna()),
        cagr=cagr(net),
        ann_return=annualized_return(net),
        ann_vol=annualized_vol(net),
        sharpe=sharpe(net),
        sortino=sortino(net),
        max_drawdown=dd["max_drawdown"],
        drawdown_days=int(dd["drawdown_days"]),
        daily_hit_rate=daily_hit_rate(net),
        monthly_hit_rate=monthly_hit_rate(net),
        ann_turnover=float(result.turnover.sum() / nyears) if nyears > 0 else float("nan"),
        cost_drag_ann=float(result.costs.sum() / nyears) if nyears > 0 else float("nan"),
        beta=beta_v,
        alpha_ann=alpha_v,
    )
