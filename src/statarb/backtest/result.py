"""BacktestResult: immutable output of a single backtest run.

All time series are aligned to the same DatetimeIndex.

Field meanings (using `t` for day index, after the engine has applied the
one-day signal lag):

  weights_applied[t]  : weights actually in effect on day t (lagged from
                        the signal panel by one day).
  turnover[t]         : sum_i |w_{t,i} - w_{t-1,i}|. Two-sided.
  gross_returns[t]    : sum_i w_{t,i} * r_{t,i} -- daily portfolio return
                        before costs.
  costs[t]            : transaction cost on day t (fraction of NAV).
  net_returns[t]      : gross_returns[t] - costs[t].
  equity_curve[t]     : cumulative product (1 + net_returns) starting at 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    weights_applied: pd.DataFrame
    turnover: pd.Series
    gross_returns: pd.Series
    costs: pd.Series
    net_returns: pd.Series
    equity_curve: pd.Series
    meta: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, float]:
        """Quick high-level metrics. Detailed evaluation lives in statarb.evaluation."""
        nr = self.net_returns.dropna()
        if len(nr) == 0:
            return {"n_days": 0}
        ann_factor = 252.0
        mean = nr.mean() * ann_factor
        std = nr.std(ddof=1) * np.sqrt(ann_factor)
        sharpe = mean / std if std > 0 else float("nan")
        total = float(self.equity_curve.iloc[-1] - 1.0)
        n_years = len(nr) / ann_factor
        cagr = (1.0 + total) ** (1.0 / n_years) - 1.0 if n_years > 0 else float("nan")
        ann_turnover = float(self.turnover.sum() / n_years) if n_years > 0 else float("nan")
        return {
            "n_days": len(nr),
            "total_return": total,
            "cagr": float(cagr),
            "ann_vol": float(std),
            "sharpe": float(sharpe),
            "ann_turnover": ann_turnover,
            "cost_drag_ann": float(self.costs.sum() / n_years) if n_years > 0 else float("nan"),
        }

    def __repr__(self) -> str:
        s = self.summary()
        if s.get("n_days", 0) == 0:
            return "BacktestResult(empty)"
        return (
            "BacktestResult("
            f"days={s['n_days']}, "
            f"CAGR={s['cagr']:.2%}, "
            f"vol={s['ann_vol']:.2%}, "
            f"Sharpe={s['sharpe']:.2f}, "
            f"turnover/yr={s['ann_turnover']:.1f}x"
            ")"
        )
