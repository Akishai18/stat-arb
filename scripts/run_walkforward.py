"""Phase A2: walk-forward analysis.

Two sub-analyses on the locked headline strategy + the Phase 7 optimizer:

  1. Year-by-year Sharpe distribution for the baseline.
     "Is this a consistent edge or driven by a few good years?"
     Builds an annual table + bar chart with bootstrap CIs per year.

  2. Expanding-window walk-forward of the optimizer.
     Each year: re-fit the signal Sharpe-weights on all prior data, run
     the cvxpy optimizer for the test year. Concatenate the per-year OOS
     traces into one long OOS trace and bootstrap it.

    uv run python scripts/run_walkforward.py

Outputs:
    reports/charts/08_annual_sharpe_baseline.png
    reports/charts/08_walkforward_equity.png
    reports/08_annual_sharpe.csv
    reports/08_walkforward_summary.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
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
    annual_sharpe_table,
    bootstrap_sharpe,
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
ANNUAL_CSV = REPO_ROOT / "reports" / "08_annual_sharpe.csv"
WALKFORWARD_CSV = REPO_ROOT / "reports" / "08_walkforward_summary.csv"
BASELINE_WF_CSV = REPO_ROOT / "reports" / "08_walkforward_baseline.csv"

# Locked baseline parameters
MOM_LOOKBACK = 252
MOM_SKIP = 21
REV_LOOKBACK = 5
TS_MOM_LOOKBACK = 126
CARRY_LOOKBACK = 21
COT_LOOKBACK_WEEKS = 156
INVENTORY_SEASONAL_YEARS = 5
COV_LOOKBACK = 63

GROSS_CAP = 1.0
NET_CAP = 0.05
POSITION_CAP = 0.40
RISK_AVERSION = 50.0
TURNOVER_CAP = None
LONG_Q = 0.4
SHORT_Q = 0.4
COST_BPS = 10
TRADING_DAYS = 252


# ----------------------------------------------------------------------------
# Shared loading
# ----------------------------------------------------------------------------


def load_signals_and_prices():
    pd_raw = PriceData.load()
    adj_clean = mask_known_anomalies(pd_raw.adj_close())
    pd_view = PriceData(adj_clean)
    futures = all_tradable_futures()
    fut_adj = adj_clean[futures]

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
        cot_panel, lookback_weeks=COT_LOOKBACK_WEEKS, target_index=adj_clean.index,
    ).reindex(columns=futures)

    try:
        eia_panel = load_eia_panel()
        inv_score = inventory_surprise(
            eia_panel, seasonal_years=INVENTORY_SEASONAL_YEARS, target_index=adj_clean.index,
        ).reindex(columns=futures)
    except (FileNotFoundError, EIAKeyMissing):
        inv_score = None

    signals = {
        "momentum": mom_score,
        "reversal": rev_score,
        "ts_momentum": ts_mom_score,
        "carry": carry_score,
        "cot": cot_score,
    }
    if inv_score is not None:
        signals["inventory"] = inv_score

    cand = [
        mom_score.index[mom_score.notna().sum(axis=1) >= 4][0],
        cot_score.index[cot_score.notna().sum(axis=1) >= 3][0],
    ]
    if inv_score is not None:
        cand.append(inv_score.index[inv_score.notna().sum(axis=1) >= 3][0])
    first_valid = max(cand)

    return pd_view, adj_clean, futures, signals, first_valid


def _is_sharpe(returns: pd.Series) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    s = r.std(ddof=1)
    if s == 0:
        return 0.0
    return float(r.mean() / s * np.sqrt(TRADING_DAYS))


def _quantile_backtest(score: pd.DataFrame, prices: PriceData, first_valid: pd.Timestamp) -> BacktestResult:
    weights = long_short_quantile_weights(
        score.loc[first_valid:],
        long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )
    bt = Backtester(prices, LinearCostModel(bps_per_side=COST_BPS))
    return bt.run(weights)


# ----------------------------------------------------------------------------
# Part 1: year-by-year Sharpe for the baseline
# ----------------------------------------------------------------------------


def part_1_annual_sharpe(prices, signals, first_valid):
    """Build the year-by-year Sharpe table + chart for the baseline."""
    print("\n" + "=" * 76)
    print("PART 1 — Year-by-year Sharpe of the baseline (equal-weight carry+cot)")
    print("=" * 76)

    baseline_alpha = eq_combine(
        {"carry": signals["carry"].loc[first_valid:], "cot": signals["cot"].loc[first_valid:]}
    )
    baseline_weights = long_short_quantile_weights(
        baseline_alpha, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )
    bt = Backtester(prices, LinearCostModel(bps_per_side=COST_BPS))
    baseline_res = bt.run(baseline_weights)

    table = annual_sharpe_table(
        baseline_res.net_returns,
        bootstrap_resamples=2000,
        block_length=5,
        min_days_per_year=60,
    )
    print(table.to_string(index=False))
    table.to_csv(ANNUAL_CSV, index=False)
    print(f"\nsaved {ANNUAL_CSV}")

    # Summary stats
    n_positive = int(table["is_positive"].sum())
    n_years = len(table)
    n_significant = int(table["is_significant_at_5pct"].sum())
    median_sh = float(table["sharpe"].median())
    worst_sh = float(table["sharpe"].min())
    best_sh = float(table["sharpe"].max())
    print()
    print(f"  Years positive:           {n_positive}/{n_years}")
    print(f"  Years significant (5%):   {n_significant}/{n_years}")
    print(f"  Sharpe range (median):    [{worst_sh:+.2f}, {best_sh:+.2f}]  (median {median_sh:+.2f})")

    # Chart
    fig, ax = plt.subplots(figsize=(10, 4.5))
    colors = ["#1f7a3a" if s > 0 else "#c0392b" for s in table["sharpe"]]
    ax.bar(table["year"], table["sharpe"], color=colors, alpha=0.85, edgecolor="black", linewidth=0.5)
    for _, row in table.iterrows():
        ax.plot([row["year"], row["year"]], [row["ci_low"], row["ci_high"]],
                color="black", linewidth=1.0, alpha=0.7)
        ax.plot([row["year"]], [row["ci_low"]], marker="_", color="black", markersize=10)
        ax.plot([row["year"]], [row["ci_high"]], marker="_", color="black", markersize=10)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_title("Annual Sharpe of baseline strategy (10 bps), bars with 95% bootstrap CI")
    ax.set_xlabel("year")
    ax.set_ylabel("annualized Sharpe")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    out = CHARTS_DIR / "08_annual_sharpe_baseline.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"saved chart: {out}")

    return baseline_res, table


# ----------------------------------------------------------------------------
# Part 2: expanding-window walk-forward optimizer
# ----------------------------------------------------------------------------


def part_2_walkforward_optimizer(prices, adj_clean, futures, signals, first_valid):
    """Expanding-window: at each OOS year, refit signal IS Sharpes on prior
    data, then run the optimizer for the test year."""
    print("\n" + "=" * 76)
    print("PART 2 — Expanding-window walk-forward optimizer")
    print("=" * 76)
    print("Each OOS year: refit IS Sharpes per signal on all prior data,")
    print("Sharpe-weight-blend, run cvxpy optimizer with locked hyperparams for the test year.")

    # Determine OOS year range: first OOS = first calendar year with >= 3 years
    # of signal data ending before it.
    first_year = max(2015, first_valid.year + 3)  # at least 3y training
    last_year = adj_clean.index.max().year  # current calendar year (partial OK)
    oos_years = list(range(first_year, last_year + 1))
    print(f"OOS years: {oos_years[0]} -> {oos_years[-1]} ({len(oos_years)} year(s))")

    # Pre-compute the full rolling-covariance lookup once (only the test
    # windows are used per iteration, but a single computation covers all).
    returns_panel = prices.returns()[futures]
    print(f"Pre-computing rolling covariance (lookback={COV_LOOKBACK})...")
    cov_cache = rolling_covariance(returns_panel, lookback=COV_LOOKBACK, min_periods=20)
    print(f"  {len(cov_cache)} dates with valid covariance")

    bt = Backtester(prices, LinearCostModel(bps_per_side=COST_BPS))

    # Walk-forward loop
    yearly_summary = []
    concatenated_oos_returns: list[pd.Series] = []
    for year in oos_years:
        train_end = pd.Timestamp(f"{year - 1}-12-31")
        test_start = pd.Timestamp(f"{year}-01-01")
        test_end = pd.Timestamp(f"{year}-12-31")

        # 1. Compute IS Sharpe per signal on data from first_valid to train_end
        is_sharpes_t: dict[str, float] = {}
        for name, sc in signals.items():
            train_score = sc.loc[first_valid:train_end]
            if train_score.empty or train_score.notna().sum().sum() == 0:
                is_sharpes_t[name] = 0.0
                continue
            standalone_res = _quantile_backtest(train_score, prices, first_valid)
            train_returns = standalone_res.net_returns.loc[:train_end]
            is_sharpes_t[name] = _is_sharpe(train_returns)

        # 2. Sharpe-weighted alpha for ALL dates (used to extract test-window slice)
        aligned = {n: s.loc[first_valid:] for n, s in signals.items()}
        alpha_full = sharpe_weighted_combine(aligned, is_sharpes=is_sharpes_t)
        # 3. Run optimizer over the test window only (need a small buffer
        # before test_start for the cov-cache lookup; the cov_cache is keyed
        # by date so no manipulation needed).
        alpha_test = alpha_full.loc[test_start:test_end]
        if alpha_test.empty:
            continue

        opt_weights = optimize_path(
            alpha_test,
            returns_panel.loc[test_start:test_end],
            gross_cap=GROSS_CAP,
            net_cap=NET_CAP,
            position_cap=POSITION_CAP,
            risk_aversion=RISK_AVERSION,
            cost_bps_per_side=COST_BPS,
            turnover_cap=TURNOVER_CAP,
            cov_cache=cov_cache,
        )
        if opt_weights.empty:
            continue

        # 4. Backtest the test window
        result_t = bt.run(opt_weights)
        net_t = result_t.net_returns.loc[test_start:test_end]
        concatenated_oos_returns.append(net_t)

        # Per-year summary row
        year_sharpe = _is_sharpe(net_t)
        surviving = [n for n, s in is_sharpes_t.items() if s > 0]
        yearly_summary.append({
            "year": year,
            "n_days": int(net_t.dropna().shape[0]),
            "oos_sharpe": round(year_sharpe, 3),
            "oos_cum_return": round(float((1.0 + net_t).prod() - 1.0), 4),
            "surviving_signals": "+".join(surviving),
            **{f"is_sharpe_{name}": round(v, 3) for name, v in is_sharpes_t.items()},
        })
        print(
            f"  year {year}: surviving={','.join(surviving) or 'none':<30s}  "
            f"OOS Sharpe = {year_sharpe:+.3f}  ({net_t.shape[0]} days)"
        )

    # Concatenate all OOS years
    if not concatenated_oos_returns:
        print("No OOS years had usable results.")
        return None

    wf_returns = pd.concat(concatenated_oos_returns).sort_index()
    wf_eq = (1.0 + wf_returns).cumprod()

    print()
    print(f"Concatenated OOS trace: {len(wf_returns)} days from "
          f"{wf_returns.index.min().date()} to {wf_returns.index.max().date()}")
    overall_sharpe = _is_sharpe(wf_returns)
    print(f"Walk-forward overall Sharpe: {overall_sharpe:+.3f}")

    # Bootstrap on the OOS trace
    boot = bootstrap_sharpe(wf_returns, n_resamples=5000, block_length=20, rng_seed=0)
    print(f"Bootstrap CI: [{boot.ci_low:+.3f}, {boot.ci_high:+.3f}]  "
          f"t-stat={boot.t_stat:+.2f}  p(Sharpe<=0)={boot.p_value_neg:.3f}  "
          f"{'**SIG**' if boot.is_significant_at_5pct else 'n.s.'}")

    # Save chart
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(wf_eq.index, wf_eq.values, color="#1f4e79", linewidth=1.6,
            label="walk-forward optimizer")
    ax.set_title("Expanding-window walk-forward optimizer (Phase A2) — OOS trace")
    ax.set_ylabel("growth of $1")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()
    out = CHARTS_DIR / "08_walkforward_equity.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"saved chart: {out}")

    # Save summary CSV
    df = pd.DataFrame(yearly_summary)
    df["walkforward_overall_sharpe"] = round(overall_sharpe, 3)
    df["walkforward_ci_low"] = round(boot.ci_low, 3)
    df["walkforward_ci_high"] = round(boot.ci_high, 3)
    df["walkforward_p_value_neg"] = round(boot.p_value_neg, 4)
    df["walkforward_significant"] = boot.is_significant_at_5pct
    df.to_csv(WALKFORWARD_CSV, index=False)
    print(f"saved {WALKFORWARD_CSV}")

    return {"sharpe": overall_sharpe, "boot": boot, "trace": wf_returns}


# ----------------------------------------------------------------------------
# Part 3: rolling walk-forward of the HEADLINE BASELINE (A-1)
# ----------------------------------------------------------------------------


def _baseline_walkforward_trace(prices, signals, first_valid, *, train_mode, train_years):
    """One walk-forward of the equal-weight survivor baseline.

    At each test year the surviving signals are re-selected using ONLY the
    trailing train window (positive standalone IS Sharpe), then equal-weighted
    into the alpha blend and traded out-of-sample on the next year. This is
    the SAME protocol Part 2 applies to the optimizer, so the two are directly
    comparable; the only difference is portfolio construction (eq-weight
    quantile vs cvxpy mean-variance).

    train_mode : "expanding" (all prior data) or "rolling" (last `train_years`).
    Returns (per_year_rows, concatenated_oos_returns).
    """
    bt = Backtester(prices, LinearCostModel(bps_per_side=COST_BPS))
    aligned = {n: s.loc[first_valid:] for n, s in signals.items()}

    last_year = prices.adj_close().index.max().year
    min_train = train_years if train_mode == "rolling" else 3
    first_year = max(first_valid.year + min_train, 2015)
    oos_years = list(range(first_year, last_year + 1))

    rows: list[dict] = []
    oos_returns: list[pd.Series] = []
    for year in oos_years:
        train_end = pd.Timestamp(f"{year - 1}-12-31")
        if train_mode == "rolling":
            train_start = pd.Timestamp(f"{year - train_years}-01-01")
        else:
            train_start = first_valid
        test_start = pd.Timestamp(f"{year}-01-01")
        test_end = pd.Timestamp(f"{year}-12-31")

        # 1. Standalone IS Sharpe of each signal on the trailing train window only.
        is_sharpes_t: dict[str, float] = {}
        for name, sc in signals.items():
            train_score = sc.loc[train_start:train_end]
            if train_score.empty or train_score.notna().sum().sum() == 0:
                is_sharpes_t[name] = 0.0
                continue
            standalone = _quantile_backtest(train_score, prices, max(first_valid, train_start))
            is_sharpes_t[name] = _is_sharpe(standalone.net_returns.loc[train_start:train_end])

        # 2. Survivors = positive train-IS-Sharpe. Equal-weight them (the headline
        #    construction). Skip the year if nothing survives.
        survivors = [n for n in signals if is_sharpes_t[n] > 0]
        if not survivors:
            continue
        blend = eq_combine({n: aligned[n] for n in survivors})
        weights = long_short_quantile_weights(
            blend, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
        )
        net_t = bt.run(weights).net_returns.loc[test_start:test_end]
        if net_t.dropna().empty:
            continue
        oos_returns.append(net_t)

        year_sharpe = _is_sharpe(net_t)
        rows.append({
            "year": year,
            "n_days": int(net_t.dropna().shape[0]),
            "oos_sharpe": round(year_sharpe, 3),
            "oos_cum_return": round(float((1.0 + net_t).prod() - 1.0), 4),
            "surviving_signals": "+".join(survivors),
            **{f"is_sharpe_{name}": round(v, 3) for name, v in is_sharpes_t.items()},
        })
        print(
            f"  {year}: survivors={'+'.join(survivors) or 'none':<22s}  "
            f"OOS Sharpe = {year_sharpe:+.3f}  ({net_t.dropna().shape[0]} days)"
        )
    return rows, oos_returns


def part_3_walkforward_baseline(prices, signals, first_valid):
    """Walk-forward the headline baseline under expanding AND rolling-5y train.

    This is the A-1 gap-closer: the deployable strategy (equal-weight
    carry+cot) gets the same rolling treatment the optimizer already got,
    instead of resting on a single static 2018-12-31 split.
    """
    print("\n" + "=" * 76)
    print("PART 3 — Walk-forward of the HEADLINE baseline (A-1)")
    print("=" * 76)
    print("Each test year: re-select survivors by trailing-window IS Sharpe,")
    print("equal-weight blend, trade next year OOS. Survivors re-chosen yearly.")

    results: dict[str, dict] = {}
    all_rows: list[dict] = []
    for train_mode, train_years in [("expanding", None), ("rolling", 5)]:
        label = train_mode if train_mode == "expanding" else f"rolling-{train_years}y"
        print(f"\n--- {label} train window ---")
        rows, oos_returns = _baseline_walkforward_trace(
            prices, signals, first_valid,
            train_mode=train_mode, train_years=train_years or 0,
        )
        if not oos_returns:
            print("  no usable OOS years")
            continue
        trace = pd.concat(oos_returns).sort_index()
        overall = _is_sharpe(trace)
        boot = bootstrap_sharpe(trace, n_resamples=5000, block_length=20, rng_seed=0)
        print(
            f"  OOS trace: {len(trace)} days "
            f"{trace.index.min().date()} -> {trace.index.max().date()}"
        )
        print(f"  Walk-forward Sharpe: {overall:+.3f}")
        print(
            f"  Bootstrap CI: [{boot.ci_low:+.3f}, {boot.ci_high:+.3f}]  "
            f"t-stat={boot.t_stat:+.2f}  p(Sharpe<=0)={boot.p_value_neg:.3f}  "
            f"{'**SIG**' if boot.is_significant_at_5pct else 'n.s.'}"
        )
        results[label] = {"trace": trace, "sharpe": overall, "boot": boot}
        for r in rows:
            all_rows.append({"train_mode": label, **r})

    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_csv(BASELINE_WF_CSV, index=False)
        print(f"\nsaved {BASELINE_WF_CSV}")

    # Overlay equity curves for the two walk-forward modes.
    if results:
        fig, ax = plt.subplots(figsize=(10, 4.5))
        palette = {"expanding": "#1f4e79", "rolling-5y": "#c0392b"}
        for label, res in results.items():
            eq = (1.0 + res["trace"]).cumprod()
            ax.plot(eq.index, eq.values, linewidth=1.6,
                    color=palette.get(label, "#555"),
                    label=f"{label}  (Sharpe {res['sharpe']:+.2f})")
        ax.set_title("Walk-forward of the headline baseline (A-1) — OOS traces")
        ax.set_ylabel("growth of $1")
        ax.grid(alpha=0.3)
        ax.legend(loc="best", frameon=False)
        fig.tight_layout()
        out = CHARTS_DIR / "08_walkforward_baseline_equity.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=140, bbox_inches="tight")
        plt.close(fig)
        print(f"saved chart: {out}")

    return results


def main() -> int:
    print("=" * 76)
    print("PHASE A2 — walk-forward analysis")
    print("=" * 76)

    prices, adj_clean, futures, signals, first_valid = load_signals_and_prices()
    print(f"\nfirst valid signal day: {first_valid.date()}")
    print(f"universe: {len(futures)} commodities")
    print(f"signals: {list(signals.keys())}")

    part_1_annual_sharpe(prices, signals, first_valid)
    part_2_walkforward_optimizer(prices, adj_clean, futures, signals, first_valid)
    part_3_walkforward_baseline(prices, signals, first_valid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
