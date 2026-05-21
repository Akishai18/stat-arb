"""Phase 5 runner: futures universe + carry signal.

Asks two questions:
  Q1: did switching from ETF proxies to clean front-month futures rescue
      the price-based signals (momentum, reversal) that failed in Phases 3-4?
  Q2: does the realized-carry signal (ETF-vs-futures return spread, our
      proxy for curve carry) add edge to the combination?

Re-runs momentum, reversal, combined-(mom+rev) on the futures universe,
then adds carry standalone and combined-(mom+rev+carry).

    uv run python scripts/run_carry_and_futures.py

Outputs:
    reports/charts/03_*.png
    reports/03_futures_and_carry_metrics.csv
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
from statarb.data import (
    ETF_FUTURES_PAIRS,
    PriceData,
    energy_futures,
    mask_known_anomalies,
)
from statarb.evaluation import (
    evaluate,
    evaluate_walkforward,
    plot_cost_sensitivity,
    plot_equity_curve,
)
from statarb.portfolio import long_short_quantile_weights
from statarb.signals import combine, momentum, realized_carry, reversal

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
METRICS_PATH = REPO_ROOT / "reports" / "03_futures_and_carry_metrics.csv"

MOM_LOOKBACK = 252
MOM_SKIP = 21
REV_LOOKBACK = 5
CARRY_LOOKBACK = 21
LONG_Q = 0.4
SHORT_Q = 0.4
COST_LEVELS_BPS = (0, 5, 10, 25)
HEADLINE_COST_BPS = 10


def _futures_only(adj: pd.DataFrame) -> pd.DataFrame:
    return adj[energy_futures()]


def _build(score: pd.DataFrame, first_valid: pd.Timestamp) -> pd.DataFrame:
    return long_short_quantile_weights(
        score.loc[first_valid:],
        long_quantile=LONG_Q,
        short_quantile=SHORT_Q,
        gross_leverage=1.0,
    )


def _run(weights: pd.DataFrame, prices: PriceData, bps: int) -> BacktestResult:
    return Backtester(prices, LinearCostModel(bps_per_side=bps)).run(weights)


def _row(label: str, window: str, rep) -> dict:
    return {
        "strategy": label,
        "window": window,
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


def _plot_corr(returns_by_name: dict[str, pd.Series], save_path: Path) -> None:
    df = pd.DataFrame(returns_by_name).dropna(how="any")
    corr = df.corr()
    fig, ax = plt.subplots(figsize=(6.0, 5.0))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=30, ha="right")
    ax.set_yticklabels(corr.index)
    for i in range(len(corr)):
        for j in range(len(corr)):
            v = corr.iat[i, j]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center",
                    color="black" if abs(v) < 0.5 else "white", fontsize=9)
    ax.set_title("Net-return correlation (futures universe)")
    fig.colorbar(im, ax=ax, shrink=0.85)
    fig.tight_layout()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    pd_view_raw = PriceData.load()
    adj_clean = mask_known_anomalies(pd_view_raw.adj_close())
    # Wrap the cleaned panel as a fresh PriceData so the engine uses the
    # cleaned returns. (PriceData computes returns on the fly from adj_close.)
    pd_view = PriceData(adj_clean)
    print(f"data span: {adj_clean.index.min().date()} -> {adj_clean.index.max().date()}")
    print(f"masked anomalies: {[(t, d) for t, d, _ in __import__('statarb.data', fromlist=['KNOWN_ANOMALIES']).KNOWN_ANOMALIES]}")

    futures_universe = energy_futures()
    print(f"futures universe: {futures_universe}")
    fut_adj = _futures_only(adj_clean)
    spy = pd_view.returns()["SPY"]

    # --- Signals on the FUTURES universe ---
    mom_score = momentum(fut_adj, lookback=MOM_LOOKBACK, skip=MOM_SKIP)
    rev_score = reversal(fut_adj, lookback=REV_LOOKBACK)
    carry_score = realized_carry(adj_clean, pairs=ETF_FUTURES_PAIRS, lookback=CARRY_LOOKBACK)

    # First valid day: when momentum has >=4 valid scores (slowest signal).
    first_valid = mom_score.index[mom_score.notna().sum(axis=1) >= 4][0]
    print(f"first valid day for backtest: {first_valid.date()}")

    # --- Standalone backtests ---
    standalone = {
        "futures_momentum_12-1": _run(_build(mom_score, first_valid), pd_view, HEADLINE_COST_BPS),
        "futures_reversal_5d": _run(_build(rev_score, first_valid), pd_view, HEADLINE_COST_BPS),
    }

    # Carry covers only 4 of 5 futures (HO=F has no ETF pair). Pad the score
    # panel with NaN for HO=F so it composes with mom/rev panels.
    carry_full = pd.DataFrame(
        index=mom_score.index, columns=mom_score.columns, dtype=float,
    )
    for c in carry_score.columns:
        if c in carry_full.columns:
            carry_full[c] = carry_score[c]
    standalone["futures_carry_21d"] = _run(_build(carry_full, first_valid), pd_view, HEADLINE_COST_BPS)

    # --- Combined: mom + rev (Phase 4 reproduction on futures universe) ---
    mom_rev = combine(
        {"momentum": mom_score.loc[first_valid:], "reversal": rev_score.loc[first_valid:]}
    )
    mom_rev_weights = long_short_quantile_weights(
        mom_rev, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )
    mom_rev_by_cost: dict[int, BacktestResult] = {
        bps: _run(mom_rev_weights, pd_view, bps) for bps in COST_LEVELS_BPS
    }

    # --- Combined: mom + rev + carry ---
    all_three = combine(
        {
            "momentum": mom_score.loc[first_valid:],
            "reversal": rev_score.loc[first_valid:],
            "carry": carry_full.loc[first_valid:],
        }
    )
    all_three_weights = long_short_quantile_weights(
        all_three, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )
    all_three_by_cost: dict[int, BacktestResult] = {
        bps: _run(all_three_weights, pd_view, bps) for bps in COST_LEVELS_BPS
    }

    # --- Reporting ---
    rows: list[dict] = []
    print()
    print("=" * 76)
    print(f"Standalone signals on FUTURES universe @ {HEADLINE_COST_BPS} bps/side")
    print("=" * 76)
    for name, res in standalone.items():
        rep = evaluate(res, benchmark_returns=spy)
        print(f"  {name:>26}: {rep}")
        rows.append(_row(name, "full", rep))

    print()
    print("=" * 76)
    print(f"Combined (mom + rev), futures universe @ {HEADLINE_COST_BPS} bps")
    print("=" * 76)
    wf_mr = evaluate_walkforward(mom_rev_by_cost[HEADLINE_COST_BPS], benchmark_returns=spy)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {wf_mr[w]}")
        rows.append(_row("futures_combined_mom+rev", w, wf_mr[w]))

    print()
    print("=" * 76)
    print(f"Combined (mom + rev + carry), futures universe @ {HEADLINE_COST_BPS} bps")
    print("=" * 76)
    wf_all = evaluate_walkforward(all_three_by_cost[HEADLINE_COST_BPS], benchmark_returns=spy)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {wf_all[w]}")
        rows.append(_row("futures_combined_all3", w, wf_all[w]))

    # Cost sensitivity for the all-three combination
    print()
    print("All-three combination cost sensitivity:")
    for bps in sorted(all_three_by_cost):
        rep = evaluate(all_three_by_cost[bps], benchmark_returns=spy)
        print(f"  {bps:>3} bps -> Sharpe={rep.sharpe:+.2f}, CAGR={rep.cagr:+.2%}, MaxDD={rep.max_drawdown:.2%}")
        rows.append(_row("futures_combined_all3", f"full @ {bps} bps", rep))

    # Correlation matrix
    return_series = {name: res.net_returns for name, res in standalone.items()}
    return_series["combined_mom+rev"] = mom_rev_by_cost[HEADLINE_COST_BPS].net_returns
    return_series["combined_all3"] = all_three_by_cost[HEADLINE_COST_BPS].net_returns
    print()
    corr = pd.DataFrame(return_series).dropna(how="any").corr().round(3)
    print("Net-return correlation matrix:")
    print(corr.to_string())

    # --- Charts ---
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_equity_curve(
        all_three_by_cost[HEADLINE_COST_BPS],
        benchmark=spy,
        title=f"Combined (mom+rev+carry) on futures @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "03_all_three_equity_curve.png",
    )
    plot_cost_sensitivity(
        all_three_by_cost,
        title="Combined (mom+rev+carry) on futures: equity vs transaction cost",
        save_path=CHARTS_DIR / "03_all_three_cost_sensitivity.png",
    )
    _plot_corr(return_series, CHARTS_DIR / "03_signal_correlation.png")

    # Side-by-side: ETF universe combined (Phase 4) vs futures universe combined
    plot_equity_curve(
        mom_rev_by_cost[HEADLINE_COST_BPS],
        benchmark=spy,
        title=f"Combined (mom+rev) on FUTURES @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "03_mom_rev_futures_equity.png",
    )
    plot_equity_curve(
        standalone["futures_carry_21d"],
        benchmark=spy,
        title=f"Carry 21d standalone on futures @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "03_carry_standalone_equity.png",
    )

    print(f"\ncharts saved to {CHARTS_DIR}/")
    pd.DataFrame(rows).to_csv(METRICS_PATH, index=False)
    print(f"metrics saved to {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
