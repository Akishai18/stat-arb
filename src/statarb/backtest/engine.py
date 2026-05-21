"""Vectorized close-to-close backtester.

THE ANTI-LOOKAHEAD CONTRACT (locked across the project)

  A weight panel `W` is dated by the day its signal was computed (close of
  day `t`). The engine lags `W` by exactly one day before applying. Weights
  W[t-1] earn returns r[t] on day `t`. Equivalently:

      W_applied = W.shift(1)
      gross_returns[t] = sum_i W_applied[t, i] * r[t, i]

  Authors of signals and portfolio-construction functions therefore should
  NOT pre-lag their output. The engine is the only place lagging happens.

CONVENTIONS

  - Returns are simple daily returns computed from the PriceData panel.
  - Turnover at day t = sum_i |W_applied[t,i] - W_applied[t-1,i]|. Two-sided.
    On the first day, previous weights are treated as zero, so initial
    turnover = sum(|W_applied[0]|).
  - Cost on day t is `cost_model.cost(turnover)[t]` and is subtracted from
    gross to produce net.
  - Net returns compound geometrically into the equity curve, starting at 1.0.

KNOWN LIMITATIONS (documented intentionally; refined in later phases)

  - No intra-rebalance drift: between rebalances, the portfolio's actual
    weights drift with asset returns. The engine ignores this for now, which
    is exact for daily rebalance and a small bias for lower frequencies.
    Phase 7 may add iterative state to handle this.
  - Returns NaN with non-zero weight contributes 0 to that day's P&L
    (via fillna on the product). This avoids NaN contamination at the cost
    of silently assuming "we held but couldn't measure" -- acceptable for
    sparse data, but should be rare in the cleaned ETF universe.
"""

from __future__ import annotations

import pandas as pd

from statarb.backtest.result import BacktestResult
from statarb.costs.linear import CostModel
from statarb.data.panel import PriceData


class Backtester:
    def __init__(self, prices: PriceData, cost_model: CostModel) -> None:
        self.prices = prices
        self.cost_model = cost_model

    def run(
        self,
        weights: pd.DataFrame,
        *,
        start: pd.Timestamp | str | None = None,
        end: pd.Timestamp | str | None = None,
    ) -> BacktestResult:
        """Run a backtest on the given target-weight panel.

        Parameters
        ----------
        weights : DataFrame
            Target weights dated by the signal day. Rows = dates, cols =
            tickers (must be a subset of self.prices.tickers). NaN treated
            as zero. The engine lags this by one day internally.
        start, end : optional timestamps
            Restrict the evaluation window. The engine still uses one prior
            day of weights to enforce the lag, so the very first row of
            output may have non-zero initial-turnover cost.
        """
        self._validate(weights)

        # Restrict the result to the dates the user passed weights for.
        # We reindex returns onto weights.index so the output dates exactly
        # match the input -- no phantom rows from the price panel.
        weights = weights.fillna(0.0)
        ret_panel = self.prices.returns().reindex(weights.index)[weights.columns]

        # Lag: weights chosen at close of day t earn returns on day t+1.
        applied = weights.shift(1)

        if start is not None:
            applied = applied.loc[pd.Timestamp(start):]
            ret_panel = ret_panel.loc[pd.Timestamp(start):]
        if end is not None:
            applied = applied.loc[:pd.Timestamp(end)]
            ret_panel = ret_panel.loc[:pd.Timestamp(end)]

        # Turnover: |w_t - w_{t-1}|, with initial previous weights = 0.
        # The first row's `applied` is NaN (no signal exists before t=0);
        # NaN propagates through abs() but is dropped by sum(skipna=True),
        # so turnover[0] = 0 -- matching the convention "no trade before
        # any signal".
        prev = applied.shift(1).fillna(0.0)
        turnover = (applied - prev).abs().sum(axis=1)

        # Gross daily portfolio return. fillna(0) on the product so that a
        # missing return on an asset we held contributes nothing rather
        # than propagating NaN through the portfolio.
        gross = (applied * ret_panel).fillna(0.0).sum(axis=1).astype(float)

        costs = self.cost_model.cost(turnover).astype(float)
        net = gross - costs
        equity = (1.0 + net).cumprod()

        return BacktestResult(
            weights_applied=applied,
            turnover=turnover,
            gross_returns=gross,
            costs=costs,
            net_returns=net,
            equity_curve=equity,
            meta={
                "cost_model": repr(self.cost_model),
                "n_assets": int(weights.shape[1]),
            },
        )

    def _validate(self, weights: pd.DataFrame) -> None:
        if not isinstance(weights, pd.DataFrame):
            raise TypeError("weights must be a DataFrame")
        if not isinstance(weights.index, pd.DatetimeIndex):
            raise TypeError("weights must have a DatetimeIndex")
        missing = set(weights.columns) - set(self.prices.tickers)
        if missing:
            raise ValueError(
                f"weights contain tickers not in price universe: {sorted(missing)}"
            )
