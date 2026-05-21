"""Phase 3 runner: 12-1 cross-sectional momentum on energy ETF proxies.

Reproduces every number and chart that goes into reports/01_momentum.md.

    uv run python scripts/run_momentum.py

Outputs:
    reports/charts/01_momentum_equity_curve.png
    reports/charts/01_momentum_drawdown.png
    reports/charts/01_momentum_cost_sensitivity.png
    reports/01_momentum_metrics.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import pandas as pd

from statarb.backtest import Backtester
from statarb.costs import LinearCostModel
from statarb.data import PriceData, energy_tickers
from statarb.evaluation import (
    DEFAULT_IS_END,
    evaluate,
    evaluate_walkforward,
    plot_cost_sensitivity,
    plot_drawdown,
    plot_equity_curve,
)
from statarb.portfolio import long_short_quantile_weights
from statarb.signals import momentum

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
METRICS_PATH = REPO_ROOT / "reports" / "01_momentum_metrics.csv"

# Strategy parameters: canonical 12-1 momentum on energy ETFs.
LOOKBACK = 252
SKIP = 21
LONG_Q = 0.4   # 5 assets -> ceil(2) = 2 longs
SHORT_Q = 0.4  # ceil(2) = 2 shorts
COST_LEVELS_BPS = (0, 5, 10, 25)
HEADLINE_COST_BPS = 10


def _select_universe() -> list[str]:
    # Drop UHN: delisted 2018, would distort the post-2018 OOS window.
    return [t for t in energy_tickers() if t != "UHN"]


def _backtest_at_cost(
    bps: int,
    weights: pd.DataFrame,
    prices: PriceData,
):
    bt = Backtester(prices, LinearCostModel(bps_per_side=bps))
    return bt.run(weights)


def _row_for_report(label: str, report) -> dict:
    return {
        "window": label,
        "n_days": report.n_days,
        "CAGR": round(report.cagr, 4),
        "ann_vol": round(report.ann_vol, 4),
        "Sharpe": round(report.sharpe, 3),
        "Sortino": round(report.sortino, 3),
        "max_dd": round(report.max_drawdown, 4),
        "dd_days": report.drawdown_days,
        "monthly_hit_rate": round(report.monthly_hit_rate, 3),
        "ann_turnover": round(report.ann_turnover, 2),
        "cost_drag_ann": round(report.cost_drag_ann, 4),
        "beta_vs_SPY": (round(report.beta, 3) if report.beta is not None else None),
        "alpha_vs_SPY_ann": (round(report.alpha_ann, 4) if report.alpha_ann is not None else None),
    }


def main() -> int:
    prices = PriceData.load()
    universe = _select_universe()
    print(f"universe: {universe}")
    adj = prices.adj_close()[universe]

    # 1. Compute the signal.
    scores = momentum(adj, lookback=LOOKBACK, skip=SKIP)

    # 2. Build the L/S quantile portfolio.
    # Start from the first row where at least 4 of the 5 assets have a valid
    # score (BNO begins 2010-06, so 12-1 momentum on BNO is ready by mid-2011).
    valid_mask = scores.notna().sum(axis=1) >= 4
    first_valid = scores.index[valid_mask][0]
    print(f"first day with >=4 valid scores: {first_valid.date()}")

    weights = long_short_quantile_weights(
        scores.loc[first_valid:],
        long_quantile=LONG_Q,
        short_quantile=SHORT_Q,
        gross_leverage=1.0,
    )
    print(f"weights span: {weights.index.min().date()} -> {weights.index.max().date()}, {len(weights)} rows")

    # 3. Backtest at every cost level.
    cost_results = {bps: _backtest_at_cost(bps, weights, prices) for bps in COST_LEVELS_BPS}
    headline = cost_results[HEADLINE_COST_BPS]

    # 4. Walk-forward evaluation against SPY.
    spy_returns = prices.returns()["SPY"]
    wf = evaluate_walkforward(
        headline,
        benchmark_returns=spy_returns,
        in_sample_end=DEFAULT_IS_END,
    )

    print()
    print("=" * 72)
    print(f"12-1 momentum L/S quantile @ {HEADLINE_COST_BPS} bps/side, IS end={DEFAULT_IS_END}")
    print("=" * 72)
    for window in ("in_sample", "out_of_sample", "full"):
        print(f"{window:>14}: {wf[window]}")

    print()
    print(f"Cost sensitivity ({COST_LEVELS_BPS} bps/side):")
    for bps in sorted(cost_results):
        rep = evaluate(cost_results[bps], benchmark_returns=spy_returns)
        print(f"  {bps:>3} bps -> Sharpe={rep.sharpe:+.2f}, CAGR={rep.cagr:+.2%}, MaxDD={rep.max_drawdown:.2%}")

    # 5. Save charts.
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_equity_curve(
        headline,
        benchmark=spy_returns,
        title=f"12-1 momentum L/S @ {HEADLINE_COST_BPS} bps/side vs SPY",
        save_path=CHARTS_DIR / "01_momentum_equity_curve.png",
    )
    plot_drawdown(
        headline,
        title=f"12-1 momentum L/S @ {HEADLINE_COST_BPS} bps/side -- drawdown",
        save_path=CHARTS_DIR / "01_momentum_drawdown.png",
    )
    plot_cost_sensitivity(
        cost_results,
        title="12-1 momentum L/S: equity curve vs transaction cost",
        save_path=CHARTS_DIR / "01_momentum_cost_sensitivity.png",
    )
    print(f"\ncharts saved to {CHARTS_DIR}/")

    # 6. Save the metrics table.
    rows = [
        _row_for_report("in_sample (-> 2018-12-31)", wf["in_sample"]),
        _row_for_report("out_of_sample (2019-)", wf["out_of_sample"]),
        _row_for_report("full window", wf["full"]),
    ]
    for bps in sorted(cost_results):
        rep = evaluate(cost_results[bps], benchmark_returns=spy_returns)
        rows.append(_row_for_report(f"full @ {bps} bps", rep))
    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(METRICS_PATH, index=False)
    print(f"metrics saved to {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
