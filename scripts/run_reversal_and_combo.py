"""Phase 4 runner: reversal standalone + reversal-momentum combination.

Reproduces every number and chart in reports/02_reversal_and_combo.md.

    uv run python scripts/run_reversal_and_combo.py

Outputs:
    reports/charts/02_reversal_lookback_comparison.png
    reports/charts/02_combined_equity_curve.png
    reports/charts/02_combined_cost_sensitivity.png
    reports/charts/02_signal_correlation.png
    reports/02_reversal_and_combo_metrics.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from statarb.backtest import Backtester
from statarb.backtest.result import BacktestResult
from statarb.costs import LinearCostModel
from statarb.data import PriceData, energy_tickers
from statarb.evaluation import (
    DEFAULT_IS_END,
    evaluate,
    evaluate_walkforward,
    plot_cost_sensitivity,
    plot_equity_curve,
)
from statarb.portfolio import long_short_quantile_weights
from statarb.signals import combine, momentum, reversal

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
METRICS_PATH = REPO_ROOT / "reports" / "02_reversal_and_combo_metrics.csv"

MOM_LOOKBACK = 252
MOM_SKIP = 21
REV_LOOKBACKS = (1, 5, 21)
HEADLINE_REV_LOOKBACK = 5
LONG_Q = 0.4
SHORT_Q = 0.4
COST_LEVELS_BPS = (0, 5, 10, 25)
HEADLINE_COST_BPS = 10


def _universe() -> list[str]:
    return [t for t in energy_tickers() if t != "UHN"]


def _build_weights(score: pd.DataFrame, first_valid: pd.Timestamp) -> pd.DataFrame:
    return long_short_quantile_weights(
        score.loc[first_valid:],
        long_quantile=LONG_Q,
        short_quantile=SHORT_Q,
        gross_leverage=1.0,
    )


def _run(weights: pd.DataFrame, prices: PriceData, bps: int) -> BacktestResult:
    return Backtester(prices, LinearCostModel(bps_per_side=bps)).run(weights)


def _row(label: str, rep) -> dict:
    return {
        "strategy": label,
        "n_days": rep.n_days,
        "CAGR": round(rep.cagr, 4),
        "ann_vol": round(rep.ann_vol, 4),
        "Sharpe": round(rep.sharpe, 3),
        "Sortino": round(rep.sortino, 3),
        "max_dd": round(rep.max_drawdown, 4),
        "monthly_hit": round(rep.monthly_hit_rate, 3),
        "ann_turnover": round(rep.ann_turnover, 2),
        "cost_drag_ann": round(rep.cost_drag_ann, 4),
        "beta_SPY": round(rep.beta, 3) if rep.beta is not None else None,
        "alpha_SPY_ann": round(rep.alpha_ann, 4) if rep.alpha_ann is not None else None,
    }


def _plot_correlation(returns_by_name: dict[str, pd.Series], save_path: Path) -> None:
    df = pd.DataFrame(returns_by_name).dropna(how="any")
    corr = df.corr()
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=30, ha="right")
    ax.set_yticklabels(corr.index)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iat[i, j]:+.2f}", ha="center", va="center",
                    color="black" if abs(corr.iat[i, j]) < 0.5 else "white", fontsize=9)
    ax.set_title("Net-return correlation between strategies")
    fig.colorbar(im, ax=ax, shrink=0.85)
    fig.tight_layout()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=140, bbox_inches="tight")


def main() -> int:
    prices = PriceData.load()
    universe = _universe()
    print(f"universe: {universe}")
    adj = prices.adj_close()[universe]
    spy = prices.returns()["SPY"]

    # --- Signals ---
    mom_score = momentum(adj, lookback=MOM_LOOKBACK, skip=MOM_SKIP)
    rev_scores = {lb: reversal(adj, lookback=lb) for lb in REV_LOOKBACKS}

    # First valid day = >=4 valid scores in momentum (the slowest signal).
    first_valid = mom_score.index[mom_score.notna().sum(axis=1) >= 4][0]
    print(f"first valid day: {first_valid.date()}")

    # --- Standalone backtests ---
    standalone: dict[str, BacktestResult] = {}
    standalone["momentum_12-1"] = _run(_build_weights(mom_score, first_valid), prices, HEADLINE_COST_BPS)
    for lb, rev in rev_scores.items():
        standalone[f"reversal_{lb}d"] = _run(_build_weights(rev, first_valid), prices, HEADLINE_COST_BPS)

    # --- Combined (equal-weight z-score) momentum + 5-day reversal ---
    headline_rev_score = rev_scores[HEADLINE_REV_LOOKBACK]
    aligned_panel = mom_score.loc[first_valid:].copy()
    aligned_panel_rev = headline_rev_score.reindex_like(aligned_panel)
    combined_score = combine({"momentum": aligned_panel, "reversal": aligned_panel_rev})
    combined_weights = long_short_quantile_weights(
        combined_score, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )

    combined_by_cost: dict[int, BacktestResult] = {
        bps: _run(combined_weights, prices, bps) for bps in COST_LEVELS_BPS
    }
    combined_headline = combined_by_cost[HEADLINE_COST_BPS]

    # --- Reporting ---
    rows: list[dict] = []
    print()
    print("=" * 72)
    print(f"Standalone signals @ {HEADLINE_COST_BPS} bps/side, full window")
    print("=" * 72)
    for name, res in standalone.items():
        rep = evaluate(res, benchmark_returns=spy)
        print(f"  {name:>18}: {rep}")
        rows.append({"window": "full", **_row(name, rep)})

    print()
    print("=" * 72)
    print(f"Combined (momentum + 5-day reversal, equal-weight z-score) @ {HEADLINE_COST_BPS} bps")
    print("=" * 72)
    wf = evaluate_walkforward(combined_headline, benchmark_returns=spy, in_sample_end=DEFAULT_IS_END)
    for window in ("in_sample", "out_of_sample", "full"):
        print(f"  {window:>14}: {wf[window]}")
        rows.append({"window": window, **_row("combined_mom+rev5", wf[window])})

    print()
    print("Combined-strategy cost sensitivity:")
    for bps in sorted(combined_by_cost):
        rep = evaluate(combined_by_cost[bps], benchmark_returns=spy)
        print(f"  {bps:>3} bps -> Sharpe={rep.sharpe:+.2f}, CAGR={rep.cagr:+.2%}, MaxDD={rep.max_drawdown:.2%}")
        rows.append({"window": f"full @ {bps} bps", **_row("combined_mom+rev5", rep)})

    # --- Correlation matrix ---
    return_series = {name: res.net_returns for name, res in standalone.items()}
    return_series["combined_mom+rev5"] = combined_headline.net_returns
    print()
    corr = pd.DataFrame(return_series).dropna(how="any").corr().round(3)
    print("Net-return correlations (full window, 10 bps):")
    print(corr.to_string())

    # --- Charts ---
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_equity_curve(
        combined_headline,
        benchmark=spy,
        title=f"Combined (mom + 5d reversal) @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "02_combined_equity_curve.png",
    )
    plot_cost_sensitivity(
        combined_by_cost,
        title="Combined (mom + 5d reversal): equity vs transaction cost",
        save_path=CHARTS_DIR / "02_combined_cost_sensitivity.png",
    )
    _plot_correlation(return_series, CHARTS_DIR / "02_signal_correlation.png")

    # Reversal-lookback comparison chart
    fig, ax = plt.subplots(figsize=(10, 4.5))
    palette = ["#1f4e79", "#2e75b6", "#9dc3e6"]
    for (lb, _), color in zip(rev_scores.items(), palette, strict=False):
        res = standalone[f"reversal_{lb}d"]
        ax.plot(res.equity_curve.index, res.equity_curve.values,
                label=f"reversal_{lb}d", color=color, linewidth=1.3)
    ax.set_title(f"Reversal lookback comparison @ {HEADLINE_COST_BPS} bps/side")
    ax.set_ylabel("growth of $1")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "02_reversal_lookback_comparison.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    print(f"\ncharts saved to {CHARTS_DIR}/")
    pd.DataFrame(rows).to_csv(METRICS_PATH, index=False)
    print(f"metrics saved to {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
