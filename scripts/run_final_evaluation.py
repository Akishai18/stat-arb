"""Phase 8 final evaluation runner.

Builds the locked Phase 7 strategy from scratch, then runs four kinds of
analysis on it:

  1. Walk-forward equity curve (the project's headline chart)
  2. Regime breakdowns: VIX high/low, energy bull/bear, pre/post-2022,
     strategy-vol high/low
  3. Signal-contribution table (each standalone signal evaluated by regime)
  4. Master cost-sensitivity table: baseline (eq-weight) vs optimizer x cost

    uv run python scripts/run_final_evaluation.py

Outputs:
    reports/charts/06_*.png
    reports/06_final_metrics.csv
    reports/06_regime_table.csv
    reports/06_master_cost_table.csv
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
    all_tradable_futures,
    mask_known_anomalies,
)
from statarb.data.cftc import load_cot_panel
from statarb.data.eia import EIAKeyMissing, load_eia_panel
from statarb.evaluation import (
    DEFAULT_IS_END,
    bootstrap_sharpe,
    deflated_sharpe_ratio,
    evaluate,
    evaluate_by_regime,
    evaluate_walkforward,
    period_regime,
    plot_drawdown,
    plot_equity_curve,
    split_in_out_sample,
    strategy_vol_regime,
    trailing_return_regime,
    vix_regime,
)
from statarb.portfolio import (
    long_short_quantile_weights,
    optimize_path,
    rolling_covariance,
)
from statarb.signals import (
    combine as eq_combine,
)
from statarb.signals import (
    cot_positioning,
    inventory_surprise,
    momentum,
    realized_carry,
    reversal,
    sharpe_weighted_combine,
    ts_momentum,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
METRICS_PATH = REPO_ROOT / "reports" / "06_final_metrics.csv"
REGIME_TABLE_PATH = REPO_ROOT / "reports" / "06_regime_table.csv"
COST_TABLE_PATH = REPO_ROOT / "reports" / "06_master_cost_table.csv"

# Locked Phase 7 hyperparameters
MOM_LOOKBACK = 252
MOM_SKIP = 21
REV_LOOKBACK = 5
TS_MOM_LOOKBACK = 126  # 6-month trailing return (Moskowitz-Ooi-Pedersen 2012)
CARRY_LOOKBACK = 21
COT_LOOKBACK_WEEKS = 156
INVENTORY_SEASONAL_YEARS = 5
COV_LOOKBACK = 63

GROSS_CAP = 1.0
NET_CAP = 0.05
POSITION_CAP = 0.40
RISK_AVERSION = 50.0          # Phase 7 IS-best
TURNOVER_CAP = None           # Phase 7 IS-best (no hard cap)
LONG_Q = 0.4
SHORT_Q = 0.4
COST_LEVELS_BPS = (0, 5, 10, 25)
HEADLINE_COST_BPS = 10


def _build_q(score: pd.DataFrame, first_valid: pd.Timestamp) -> pd.DataFrame:
    return long_short_quantile_weights(
        score.loc[first_valid:],
        long_quantile=LONG_Q,
        short_quantile=SHORT_Q,
        gross_leverage=1.0,
    )


def _run(weights: pd.DataFrame, prices: PriceData, bps: int) -> BacktestResult:
    return Backtester(prices, LinearCostModel(bps_per_side=bps)).run(weights)


def _is_sharpe(returns: pd.Series) -> float:
    is_part, _ = split_in_out_sample(returns, in_sample_end=DEFAULT_IS_END)
    r = is_part.dropna()
    if len(r) < 2:
        return 0.0
    s = r.std(ddof=1)
    if s == 0:
        return 0.0
    return float(r.mean() / s * (252**0.5))


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
    print("=" * 76)
    print("PHASE 8 — final evaluation")
    print("=" * 76)
    pd_view_raw = PriceData.load()
    adj_clean = mask_known_anomalies(pd_view_raw.adj_close())
    pd_view = PriceData(adj_clean)
    futures = all_tradable_futures()
    fut_adj = adj_clean[futures]
    spy = pd_view.returns()["SPY"]
    daily_index = adj_clean.index

    # --- Compute the 5 signals (same as Phase 7) ---
    mom_score = momentum(fut_adj, lookback=MOM_LOOKBACK, skip=MOM_SKIP)
    rev_score = reversal(fut_adj, lookback=REV_LOOKBACK)
    ts_mom_score = ts_momentum(fut_adj, lookback=TS_MOM_LOOKBACK)
    carry_raw = realized_carry(adj_clean, pairs=ETF_FUTURES_PAIRS, lookback=CARRY_LOOKBACK)
    carry_score = pd.DataFrame(index=mom_score.index, columns=mom_score.columns, dtype=float)
    for c in carry_raw.columns:
        if c in carry_score.columns:
            carry_score[c] = carry_raw[c]
    cot_panel = load_cot_panel()
    cot_score = cot_positioning(
        cot_panel, lookback_weeks=COT_LOOKBACK_WEEKS, target_index=daily_index
    ).reindex(columns=futures)

    try:
        eia_panel = load_eia_panel()
        inv_score = inventory_surprise(
            eia_panel,
            seasonal_years=INVENTORY_SEASONAL_YEARS,
            target_index=daily_index,
        ).reindex(columns=futures)
    except (FileNotFoundError, EIAKeyMissing):
        inv_score = None

    all_signals = {
        "momentum": mom_score,
        "reversal": rev_score,
        "ts_momentum": ts_mom_score,
        "carry": carry_score,
        "cot": cot_score,
    }
    if inv_score is not None:
        all_signals["inventory"] = inv_score

    # --- First valid day ---
    cand = [
        mom_score.index[mom_score.notna().sum(axis=1) >= 4][0],
        cot_score.index[cot_score.notna().sum(axis=1) >= 3][0],
    ]
    if inv_score is not None:
        cand.append(inv_score.index[inv_score.notna().sum(axis=1) >= 3][0])
    first_valid = max(cand)
    print(f"\nfirst valid day: {first_valid.date()}")

    # --- Step 1: IS Sharpes ---
    print("\nIS Sharpes per signal:")
    is_sharpes: dict[str, float] = {}
    standalone_results: dict[str, BacktestResult] = {}
    for name, sc in all_signals.items():
        res = _run(_build_q(sc, first_valid), pd_view, HEADLINE_COST_BPS)
        standalone_results[name] = res
        is_sharpes[name] = _is_sharpe(res.net_returns)
        print(f"  {name:>10}: IS Sharpe = {is_sharpes[name]:+.3f}")

    # --- Step 2: Sharpe-weighted alpha ---
    aligned = {n: s.loc[first_valid:] for n, s in all_signals.items()}
    alpha = sharpe_weighted_combine(aligned, is_sharpes=is_sharpes)
    surviving = [n for n, s in is_sharpes.items() if s > 0]
    print(f"\nSurviving signals (positive IS Sharpe): {surviving}")

    # --- Step 3: Optimizer with locked hyperparameters ---
    returns_panel = pd_view.returns()[futures]
    print(f"\nPre-computing rolling covariance (lookback={COV_LOOKBACK})...")
    cov_cache = rolling_covariance(returns_panel, lookback=COV_LOOKBACK, min_periods=20)
    print(f"  {len(cov_cache)} dates with valid covariance")

    opt_weights = optimize_path(
        alpha,
        returns_panel,
        gross_cap=GROSS_CAP,
        net_cap=NET_CAP,
        position_cap=POSITION_CAP,
        risk_aversion=RISK_AVERSION,
        cost_bps_per_side=HEADLINE_COST_BPS,
        turnover_cap=TURNOVER_CAP,
        cov_cache=cov_cache,
    )

    # --- Baseline for comparison ---
    baseline_alpha = eq_combine(
        {"carry": carry_score.loc[first_valid:], "cot": cot_score.loc[first_valid:]}
    )
    baseline_weights = long_short_quantile_weights(
        baseline_alpha, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0
    )

    # --- Run all backtests at multiple cost levels ---
    rows: list[dict] = []
    optimizer_by_cost: dict[int, BacktestResult] = {}
    baseline_by_cost: dict[int, BacktestResult] = {}
    for bps in COST_LEVELS_BPS:
        optimizer_by_cost[bps] = _run(opt_weights, pd_view, bps)
        baseline_by_cost[bps] = _run(baseline_weights, pd_view, bps)

    headline_opt = optimizer_by_cost[HEADLINE_COST_BPS]
    headline_baseline = baseline_by_cost[HEADLINE_COST_BPS]

    # --- Walk-forward IS/OOS for the headline strategy ---
    print("\n" + "=" * 76)
    print(f"HEADLINE strategy (optimizer, lambda={RISK_AVERSION:g}, 10 bps)")
    print("=" * 76)
    wf = evaluate_walkforward(headline_opt, benchmark_returns=spy)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {wf[w]}")
        rows.append(_row("optimizer_locked", w, wf[w]))

    # --- Walk-forward for baseline ---
    print("\nBaseline (eq-weight carry+cot, 10 bps)")
    wf_b = evaluate_walkforward(headline_baseline, benchmark_returns=spy)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {wf_b[w]}")
        rows.append(_row("baseline_eq_carry+cot", w, wf_b[w]))

    # --- Block-bootstrap Sharpe CIs for the headline ---
    print("\n" + "=" * 76)
    print("BLOCK-BOOTSTRAP SHARPE CONFIDENCE INTERVALS")
    print("=" * 76)
    print("Block-bootstrap (block=20 days, 5000 resamples) -- accounts for")
    print("serial dependence in daily strategy returns.")
    print()
    bootstrap_rows: list[dict] = []
    for strategy_label, res in (
        ("optimizer_locked (full window)", headline_opt),
        ("baseline_eq_carry+cot (full window)", headline_baseline),
    ):
        net = res.net_returns
        is_net, oos_net = split_in_out_sample(net, in_sample_end=DEFAULT_IS_END)
        for window_label, returns in (
            ("Full", net),
            ("In-sample", is_net),
            ("Out-of-sample", oos_net),
        ):
            b = bootstrap_sharpe(returns, n_resamples=5000, block_length=20, rng_seed=0)
            sig = "**SIG**" if b.is_significant_at_5pct else "n.s."
            print(f"  {strategy_label:>38} | {window_label:>13}: {b}  {sig}")
            bootstrap_rows.append({
                "strategy": strategy_label,
                "window": window_label,
                "point_sharpe": round(b.point_sharpe, 3),
                "bootstrap_mean": round(b.bootstrap_mean, 3),
                "ci_low_95": round(b.ci_low, 3),
                "ci_high_95": round(b.ci_high, 3),
                "t_stat": round(b.t_stat, 3),
                "p_value_sharpe_leq_0": round(b.p_value_neg, 4),
                "significant_at_5pct": b.is_significant_at_5pct,
                "n_obs": b.n_obs,
            })
    pd.DataFrame(bootstrap_rows).to_csv(
        REPO_ROOT / "reports" / "06_bootstrap_sharpe.csv", index=False,
    )

    # --- Deflated Sharpe Ratio (multiple-testing correction) ---
    print("\n" + "=" * 76)
    print("DEFLATED SHARPE RATIO (Bailey-Lopez de Prado 2014)")
    print("=" * 76)
    print("DSR penalizes the headline Sharpe for the number of trials run during")
    print("model selection (signal choice, hyperparameter sweep). DSR > 0.95 = the")
    print("strategy beats the expected-max-Sharpe under no-skill at 95% confidence.")
    print()
    # Trial-count choice (documented and conservative):
    #   6 signals + 9 optimizer-hyperparam combos + 3 portfolio constructions
    #   + 4 cost levels + sweep across lookbacks ~= 25 "trials" worth tracking.
    # Sensitivity at N=10 and N=50 reported below.
    N_TRIALS_HEADLINE = 25
    dsr_rows: list[dict] = []
    for strategy_label, res in (
        ("optimizer_locked", headline_opt),
        ("baseline_eq_carry+cot", headline_baseline),
    ):
        net = res.net_returns
        is_net, oos_net = split_in_out_sample(net, in_sample_end=DEFAULT_IS_END)
        for window_label, returns in (
            ("Full", net),
            ("In-sample", is_net),
            ("Out-of-sample", oos_net),
        ):
            for n_trials in (1, 10, N_TRIALS_HEADLINE, 50):
                d = deflated_sharpe_ratio(returns, n_trials=n_trials)
                sig = "**SIG**" if d.is_significant_at_5pct else "n.s."
                if n_trials == N_TRIALS_HEADLINE:
                    print(f"  {strategy_label:>26} | {window_label:>13} | "
                          f"N={n_trials:>3}: {d}  {sig}")
                dsr_rows.append({
                    "strategy": strategy_label,
                    "window": window_label,
                    "n_trials": n_trials,
                    "point_sharpe": round(d.point_sharpe, 3),
                    "expected_max_sharpe_null": round(d.expected_max_sharpe, 3),
                    "psr_vs_zero": round(d.psr, 4),
                    "dsr": round(d.dsr, 4),
                    "skewness": round(d.skewness, 3),
                    "kurtosis": round(d.kurtosis, 3),
                    "significant_at_5pct": d.is_significant_at_5pct,
                })
    pd.DataFrame(dsr_rows).to_csv(
        REPO_ROOT / "reports" / "06_deflated_sharpe.csv", index=False,
    )

    # --- Master cost table ---
    print("\n" + "=" * 76)
    print("MASTER COST-SENSITIVITY TABLE")
    print("=" * 76)
    cost_rows = []
    for bps in COST_LEVELS_BPS:
        opt_rep = evaluate(optimizer_by_cost[bps], benchmark_returns=spy)
        base_rep = evaluate(baseline_by_cost[bps], benchmark_returns=spy)
        cost_rows.append({
            "cost_bps": bps,
            "optimizer_sharpe": round(opt_rep.sharpe, 3),
            "optimizer_cagr": round(opt_rep.cagr, 4),
            "optimizer_max_dd": round(opt_rep.max_drawdown, 4),
            "baseline_sharpe": round(base_rep.sharpe, 3),
            "baseline_cagr": round(base_rep.cagr, 4),
            "baseline_max_dd": round(base_rep.max_drawdown, 4),
        })
    cost_df = pd.DataFrame(cost_rows)
    print(cost_df.to_string(index=False))
    cost_df.to_csv(COST_TABLE_PATH, index=False)

    # --- Regime breakdowns ---
    print("\n" + "=" * 76)
    print("REGIME BREAKDOWNS (headline strategy, 10 bps)")
    print("=" * 76)
    regime_masks: dict[str, pd.Series] = {
        "vix_high": vix_regime(pd_view.adj_close()["^VIX"]),
        "energy_bull": trailing_return_regime(pd_view.adj_close()["DBE"], lookback=126),
        "post_2022": period_regime(daily_index, split_date="2021-12-31"),
        "strategy_vol_high": strategy_vol_regime(headline_opt.net_returns, lookback=63),
    }
    # Reindex masks to the strategy's own index
    for name in regime_masks:
        regime_masks[name] = regime_masks[name].reindex(headline_opt.net_returns.index)

    regime_table_rows: list[dict] = []
    for regime_name, mask in regime_masks.items():
        split = evaluate_by_regime(headline_opt, regime_mask=mask, benchmark_returns=spy)
        in_r, out_r = split["in_regime"], split["out_regime"]
        print(
            f"  {regime_name:>20}  | "
            f"IN:  Sharpe={in_r.sharpe:+.2f}  CAGR={in_r.cagr:+.2%}  MaxDD={in_r.max_drawdown:.2%}  days={in_r.n_days}\n"
            f"  {'':>20}  | OUT: Sharpe={out_r.sharpe:+.2f}  CAGR={out_r.cagr:+.2%}  MaxDD={out_r.max_drawdown:.2%}  days={out_r.n_days}"
        )
        regime_table_rows.append({
            "regime": regime_name,
            "in_sharpe": round(in_r.sharpe, 3),
            "in_cagr": round(in_r.cagr, 4),
            "in_max_dd": round(in_r.max_drawdown, 4),
            "in_days": in_r.n_days,
            "out_sharpe": round(out_r.sharpe, 3),
            "out_cagr": round(out_r.cagr, 4),
            "out_max_dd": round(out_r.max_drawdown, 4),
            "out_days": out_r.n_days,
        })
    regime_df = pd.DataFrame(regime_table_rows)
    regime_df.to_csv(REGIME_TABLE_PATH, index=False)

    # --- Signal-contribution by regime ---
    print("\n" + "=" * 76)
    print("PER-SIGNAL SHARPE BY REGIME")
    print("=" * 76)
    signal_regime_rows = []
    strategies = {**standalone_results, "OPTIMIZER": headline_opt, "BASELINE": headline_baseline}
    for strat_name, res in strategies.items():
        for regime_name, mask in regime_masks.items():
            mask_aligned = mask.reindex(res.net_returns.index)
            split = evaluate_by_regime(res, regime_mask=mask_aligned)
            signal_regime_rows.append({
                "strategy": strat_name,
                "regime": regime_name,
                "in_sharpe": round(split["in_regime"].sharpe, 3),
                "out_sharpe": round(split["out_regime"].sharpe, 3),
            })
    sig_regime_df = pd.DataFrame(signal_regime_rows)
    # Pivot to wide for legibility (strategy x regime, in/out columns)
    pivot_in = sig_regime_df.pivot(index="strategy", columns="regime", values="in_sharpe")
    pivot_out = sig_regime_df.pivot(index="strategy", columns="regime", values="out_sharpe")
    print("\nIN-regime Sharpe (rows=strategy, cols=regime):")
    print(pivot_in.to_string())
    print("\nOUT-regime Sharpe (rows=strategy, cols=regime):")
    print(pivot_out.to_string())

    # --- Charts ---
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_equity_curve(
        headline_opt,
        benchmark=spy,
        title=f"Headline strategy (Phase 7 optimizer, {HEADLINE_COST_BPS} bps) vs SPY",
        save_path=CHARTS_DIR / "06_headline_equity_curve.png",
    )
    plot_drawdown(
        headline_opt,
        title=f"Headline strategy drawdown ({HEADLINE_COST_BPS} bps)",
        save_path=CHARTS_DIR / "06_headline_drawdown.png",
    )

    # Equity by regime: 4 panels
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    for ax, (regime_name, mask) in zip(axes.flat, regime_masks.items(), strict=False):
        mask_aligned = mask.reindex(headline_opt.net_returns.index).fillna(False).astype(bool)
        in_net = headline_opt.net_returns.where(mask_aligned, other=0.0).fillna(0.0)
        out_net = headline_opt.net_returns.where(~mask_aligned, other=0.0).fillna(0.0)
        in_eq = (1.0 + in_net).cumprod()
        out_eq = (1.0 + out_net).cumprod()
        ax.plot(in_eq.index, in_eq.values, label=f"in {regime_name}", color="#1f4e79", linewidth=1.3)
        ax.plot(out_eq.index, out_eq.values, label=f"out {regime_name}", color="#a6a6a6", linewidth=1.3, linestyle="--")
        ax.set_title(regime_name.replace("_", " "))
        ax.grid(alpha=0.3)
        ax.legend(loc="best", frameon=False, fontsize=9)
    fig.suptitle("Headline strategy: equity contribution by regime", y=1.0)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "06_regime_equity_panels.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Per-signal Sharpe heatmaps
    for kind, frame in (("in", pivot_in), ("out", pivot_out)):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        im = ax.imshow(frame.values.astype(float), cmap="RdBu_r", vmin=-1.0, vmax=1.0, aspect="auto")
        ax.set_xticks(range(frame.shape[1]))
        ax.set_yticks(range(frame.shape[0]))
        ax.set_xticklabels(frame.columns, rotation=15)
        ax.set_yticklabels(frame.index)
        for i in range(frame.shape[0]):
            for j in range(frame.shape[1]):
                v = frame.iat[i, j]
                ax.text(j, i, f"{v:+.2f}", ha="center", va="center",
                        color="black" if abs(v) < 0.6 else "white", fontsize=9)
        ax.set_title(f"Sharpe by strategy x regime ({kind}-regime)")
        fig.colorbar(im, ax=ax, shrink=0.85)
        fig.tight_layout()
        fig.savefig(CHARTS_DIR / f"06_signal_regime_heatmap_{kind}.png", dpi=140, bbox_inches="tight")
        plt.close(fig)

    # Master cost-sensitivity comparison plot
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bps_arr = list(COST_LEVELS_BPS)
    ax.plot(bps_arr, [evaluate(optimizer_by_cost[b]).sharpe for b in bps_arr],
            marker="o", linewidth=1.6, color="#1f4e79", label="Phase 7 optimizer (locked)")
    ax.plot(bps_arr, [evaluate(baseline_by_cost[b]).sharpe for b in bps_arr],
            marker="o", linewidth=1.4, color="#a6a6a6", label="Baseline: eq-weight carry+cot")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("transaction cost (bps per side)")
    ax.set_ylabel("Sharpe (full window)")
    ax.set_title("Master cost sensitivity: optimizer vs baseline")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "06_master_cost_comparison.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    pd.DataFrame(rows).to_csv(METRICS_PATH, index=False)
    print(f"\ncharts saved to {CHARTS_DIR}/")
    print(f"main metrics: {METRICS_PATH}")
    print(f"regime table: {REGIME_TABLE_PATH}")
    print(f"cost table: {COST_TABLE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
