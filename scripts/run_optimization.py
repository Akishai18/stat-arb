"""Phase 7 runner: Sharpe-weighted signal blend + cvxpy portfolio optimization.

Three-step build:
  1. Run each of the 5 signals standalone on IS only (-> 2018-12-31) to
     learn each one's IS Sharpe.
  2. Combine the signals with weights proportional to max(0, IS Sharpe).
     Negative-Sharpe signals (mom, rev, inventory in Phase 6) are dropped.
  3. Solve a daily cvxpy QP that maximizes alpha . w - lambda * w' Sigma w
     - cost * ||w - w_prev||_1 subject to gross/net/position/turnover
     constraints.

Sweeps lambda and turnover_cap on IS, picks the best by IS Sharpe, reports
OOS honestly. Compares to the Phase 6 equal-weight baseline (carry+cot).

    uv run python scripts/run_optimization.py

Outputs:
    reports/charts/05_*.png
    reports/05_portfolio_construction_metrics.csv
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
from statarb.data.cftc import load_cot_panel
from statarb.data.eia import EIAKeyMissing, load_eia_panel
from statarb.evaluation import (
    DEFAULT_IS_END,
    evaluate,
    evaluate_walkforward,
    plot_cost_sensitivity,
    plot_equity_curve,
    split_in_out_sample,
)
from statarb.portfolio import long_short_quantile_weights, optimize_path, rolling_covariance
from statarb.signals import (
    cot_positioning,
    inventory_surprise,
    momentum,
    realized_carry,
    reversal,
    sharpe_weighted_combine,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
METRICS_PATH = REPO_ROOT / "reports" / "05_portfolio_construction_metrics.csv"

MOM_LOOKBACK = 252
MOM_SKIP = 21
REV_LOOKBACK = 5
CARRY_LOOKBACK = 21
COT_LOOKBACK_WEEKS = 156
INVENTORY_SEASONAL_YEARS = 5
COV_LOOKBACK = 63

LONG_Q = 0.4
SHORT_Q = 0.4
COST_LEVELS_BPS = (0, 5, 10, 25)
HEADLINE_COST_BPS = 10

# Optimizer constraint defaults
GROSS_CAP = 1.0
NET_CAP = 0.05
POSITION_CAP = 0.40

# Hyperparameter sweep (small grid; IS-picks, OOS-reports)
LAMBDA_GRID = (0.5, 5.0, 50.0)
TURNOVER_GRID = (None, 0.5, 0.2)


def _build_q(score: pd.DataFrame, first_valid: pd.Timestamp) -> pd.DataFrame:
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


def main() -> int:
    pd_view_raw = PriceData.load()
    adj_clean = mask_known_anomalies(pd_view_raw.adj_close())
    pd_view = PriceData(adj_clean)
    futures_universe = energy_futures()
    fut_adj = adj_clean[futures_universe]
    daily_index = adj_clean.index
    spy = pd_view.returns()["SPY"]

    print(f"data span: {daily_index.min().date()} -> {daily_index.max().date()}")
    print(f"futures universe: {futures_universe}")

    # --- All 5 signals ---
    mom_score = momentum(fut_adj, lookback=MOM_LOOKBACK, skip=MOM_SKIP)
    rev_score = reversal(fut_adj, lookback=REV_LOOKBACK)

    carry_raw = realized_carry(adj_clean, pairs=ETF_FUTURES_PAIRS, lookback=CARRY_LOOKBACK)
    carry_score = pd.DataFrame(
        index=mom_score.index, columns=mom_score.columns, dtype=float
    )
    for c in carry_raw.columns:
        if c in carry_score.columns:
            carry_score[c] = carry_raw[c]

    cot_panel = load_cot_panel()
    cot_score = cot_positioning(
        cot_panel, lookback_weeks=COT_LOOKBACK_WEEKS, target_index=daily_index
    ).reindex(columns=futures_universe)

    try:
        eia_panel = load_eia_panel()
        inv_score = inventory_surprise(
            eia_panel,
            seasonal_years=INVENTORY_SEASONAL_YEARS,
            target_index=daily_index,
        ).reindex(columns=futures_universe)
    except (FileNotFoundError, EIAKeyMissing) as e:
        print(f"EIA inventory: SKIPPED ({e})")
        inv_score = None

    all_signals = {
        "momentum": mom_score,
        "reversal": rev_score,
        "carry": carry_score,
        "cot": cot_score,
    }
    if inv_score is not None:
        all_signals["inventory"] = inv_score

    # --- First valid day for the combined backtest ---
    first_valid_candidates = [
        mom_score.index[mom_score.notna().sum(axis=1) >= 4][0],
        cot_score.index[cot_score.notna().sum(axis=1) >= 3][0],
    ]
    if inv_score is not None:
        first_valid_candidates.append(
            inv_score.index[inv_score.notna().sum(axis=1) >= 3][0]
        )
    first_valid = max(first_valid_candidates)
    print(f"first valid day: {first_valid.date()}")

    # --- Step 1: compute IS Sharpe for each standalone signal ---
    print("\n--- Step 1: IS Sharpes (standalone, equal-weight quantile, 10 bps) ---")
    is_sharpes: dict[str, float] = {}
    for name, score in all_signals.items():
        res = _run(_build_q(score, first_valid), pd_view, HEADLINE_COST_BPS)
        is_part, _ = split_in_out_sample(res.net_returns, in_sample_end=DEFAULT_IS_END)
        is_sharpe = float(
            is_part.dropna().mean() / is_part.dropna().std(ddof=1) * (252**0.5)
        ) if len(is_part.dropna()) > 1 else 0.0
        is_sharpes[name] = is_sharpe
        print(f"  {name:>10}: IS Sharpe = {is_sharpe:+.3f}")

    # --- Step 2: Sharpe-weighted combine (negative Sharpes dropped) ---
    print("\n--- Step 2: Sharpe-weighted alpha blend ---")
    aligned = {n: s.loc[first_valid:] for n, s in all_signals.items()}
    alpha = sharpe_weighted_combine(aligned, is_sharpes=is_sharpes)
    surviving = [n for n, s in is_sharpes.items() if s > 0]
    print(f"  surviving signals: {surviving}")

    # --- Phase 6 baseline: equal-weight quantile on carry+cot ---
    print("\n--- Baseline: Phase 6 equal-weight quantile (carry + cot) at 10 bps ---")
    from statarb.signals import combine as eq_combine
    baseline_alpha = eq_combine(
        {"carry": carry_score.loc[first_valid:], "cot": cot_score.loc[first_valid:]}
    )
    baseline_weights = long_short_quantile_weights(
        baseline_alpha, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0
    )
    baseline_res = _run(baseline_weights, pd_view, HEADLINE_COST_BPS)
    baseline_wf = evaluate_walkforward(baseline_res, benchmark_returns=spy)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {baseline_wf[w]}")

    # --- Step 3: cvxpy optimizer sweep ---
    print("\n--- Step 3: optimizer sweep over (lambda, turnover_cap) ---")
    returns_panel = pd_view.returns()[futures_universe]
    print(f"  precomputing rolling covariance (lookback={COV_LOOKBACK})...")
    cov_cache = rolling_covariance(returns_panel, lookback=COV_LOOKBACK, min_periods=20)
    print(f"  computed cov for {len(cov_cache)} dates")

    rows: list[dict] = []
    rows.append(_row("baseline_eq_carry+cot", "in_sample", baseline_wf["in_sample"]))
    rows.append(_row("baseline_eq_carry+cot", "out_of_sample", baseline_wf["out_of_sample"]))
    rows.append(_row("baseline_eq_carry+cot", "full", baseline_wf["full"]))

    sweep_results: dict[tuple[float, float | None], BacktestResult] = {}
    for lam in LAMBDA_GRID:
        for tcap in TURNOVER_GRID:
            opt_weights = optimize_path(
                alpha,
                returns_panel,
                gross_cap=GROSS_CAP,
                net_cap=NET_CAP,
                position_cap=POSITION_CAP,
                risk_aversion=lam,
                cost_bps_per_side=HEADLINE_COST_BPS,
                turnover_cap=tcap,
                cov_cache=cov_cache,
            )
            res = _run(opt_weights, pd_view, HEADLINE_COST_BPS)
            sweep_results[(lam, tcap)] = res
            wf = evaluate_walkforward(res, benchmark_returns=spy)
            tcap_label = "inf" if tcap is None else f"{tcap:g}"
            label = f"opt_lam={lam:g}_tcap={tcap_label}"
            tcap_str = "none" if tcap is None else f"{tcap:g}"
            print(
                f"  lambda={lam:>4}, tcap={tcap_str:>5}: "
                f"IS Sharpe={wf['in_sample'].sharpe:+.2f}  "
                f"OOS Sharpe={wf['out_of_sample'].sharpe:+.2f}  "
                f"Full Sharpe={wf['full'].sharpe:+.2f}  "
                f"turnover/yr={wf['full'].ann_turnover:.1f}x"
            )
            rows.append(_row(label, "in_sample", wf["in_sample"]))
            rows.append(_row(label, "out_of_sample", wf["out_of_sample"]))
            rows.append(_row(label, "full", wf["full"]))

    # --- Step 4: pick the IS-best (no peeking at OOS), report it as headline ---
    is_best = max(
        sweep_results.items(),
        key=lambda kv: evaluate_walkforward(kv[1])["in_sample"].sharpe,
    )
    best_key, best_res = is_best
    best_wf = evaluate_walkforward(best_res, benchmark_returns=spy)
    print("\n=" * 1)
    print("=" * 76)
    best_tcap_str = "inf" if best_key[1] is None else f"{best_key[1]:g}"
    print(
        f"HEADLINE (IS-best): lambda={best_key[0]:g}, "
        f"turnover_cap={best_tcap_str}"
    )
    print("=" * 76)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {best_wf[w]}")

    # Cost sensitivity for the IS-best optimized strategy
    print("\nCost sensitivity for the IS-best optimized strategy:")
    best_opt_weights = optimize_path(
        alpha,
        returns_panel,
        gross_cap=GROSS_CAP,
        net_cap=NET_CAP,
        position_cap=POSITION_CAP,
        risk_aversion=best_key[0],
        cost_bps_per_side=HEADLINE_COST_BPS,
        turnover_cap=best_key[1],
        cov_cache=cov_cache,
    )
    cost_by_bps: dict[int, BacktestResult] = {}
    for bps in COST_LEVELS_BPS:
        res = _run(best_opt_weights, pd_view, bps)
        cost_by_bps[bps] = res
        r = evaluate(res, benchmark_returns=spy)
        print(f"  {bps:>3} bps -> Sharpe={r.sharpe:+.2f}, CAGR={r.cagr:+.2%}, MaxDD={r.max_drawdown:.2%}")
        rows.append(_row("opt_is_best", f"full @ {bps} bps", r))

    # --- Charts ---
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_equity_curve(
        best_res,
        benchmark=spy,
        title=f"Optimized (IS-best lambda={best_key[0]:g}) @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "05_optimized_equity.png",
    )
    plot_cost_sensitivity(
        cost_by_bps,
        title="IS-best optimized portfolio: equity vs transaction cost",
        save_path=CHARTS_DIR / "05_optimized_cost_sensitivity.png",
    )
    # Side-by-side: baseline equal-weight vs IS-best optimizer
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(
        baseline_res.equity_curve.index, baseline_res.equity_curve.values,
        label="baseline: eq-weight quantile (carry+cot)", color="#a6a6a6", linewidth=1.4,
    )
    ax.plot(
        best_res.equity_curve.index, best_res.equity_curve.values,
        label=f"optimizer (lam={best_key[0]:g})", color="#1f4e79", linewidth=1.6,
    )
    ax.set_title("Phase 7 optimizer vs Phase 6 equal-weight baseline")
    ax.set_ylabel("growth of $1")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "05_baseline_vs_optimizer.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Sharpe surface heatmap (lambda x turnover_cap, IS and OOS)
    for window_name in ("in_sample", "out_of_sample"):
        matrix = pd.DataFrame(
            index=[f"lam={lam:g}" for lam in LAMBDA_GRID],
            columns=["tcap=" + ("inf" if t is None else f"{t:g}") for t in TURNOVER_GRID],
            dtype=float,
        )
        for lam in LAMBDA_GRID:
            for tcap in TURNOVER_GRID:
                wf_lt = evaluate_walkforward(sweep_results[(lam, tcap)], benchmark_returns=spy)
                matrix.loc[f"lam={lam:g}", "tcap=" + ("inf" if tcap is None else f"{tcap:g}")] = wf_lt[window_name].sharpe
        fig, ax = plt.subplots(figsize=(5.5, 4.0))
        im = ax.imshow(matrix.values.astype(float), cmap="RdBu_r", vmin=-0.6, vmax=0.6, aspect="auto")
        ax.set_xticks(range(matrix.shape[1]))
        ax.set_yticks(range(matrix.shape[0]))
        ax.set_xticklabels(matrix.columns, rotation=15)
        ax.set_yticklabels(matrix.index)
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                v = matrix.iat[i, j]
                ax.text(j, i, f"{v:+.2f}", ha="center", va="center",
                        color="black" if abs(v) < 0.4 else "white", fontsize=10)
        ax.set_title(f"Sharpe surface ({window_name.replace('_', ' ')})")
        fig.colorbar(im, ax=ax, shrink=0.85)
        fig.tight_layout()
        fig.savefig(CHARTS_DIR / f"05_sharpe_surface_{window_name}.png", dpi=140, bbox_inches="tight")
        plt.close(fig)

    # Weight time series for the IS-best strategy
    fig, ax = plt.subplots(figsize=(10, 4.0))
    weights_to_plot = best_opt_weights.dropna(how="all")
    for col in weights_to_plot.columns:
        ax.plot(weights_to_plot.index, weights_to_plot[col], label=col, linewidth=1.0)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_title(f"Optimizer weights over time (lambda={best_key[0]:g})")
    ax.set_ylabel("position weight")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False, ncol=5, fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "05_weight_timeseries.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    print(f"\ncharts saved to {CHARTS_DIR}/")
    pd.DataFrame(rows).to_csv(METRICS_PATH, index=False)
    print(f"metrics saved to {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
