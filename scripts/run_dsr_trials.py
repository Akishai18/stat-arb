"""Phase A2 (research-firming): rigorous Deflated-Sharpe trial accounting.

The DSR's only free parameter is N, the number of trials run during model
selection. FINAL.md previously used a hand-waved N=25. This script replaces
that with an explicit, line-item trial ledger reconstructed from the actual
research phases (3-7 + A6 sensitivity), then reports the DSR across the full
N sweep so the result is judged honestly rather than at one convenient N.

Two return series are deflated:
  1. STATIC full-window baseline (eq-weight carry+cot)  -- comparable to FINAL.md
  2. WALK-FORWARD expanding OOS trace (the A-1 deliverable) -- the honest
     out-of-sample number, where survivors are re-selected each year.

    uv run python scripts/run_dsr_trials.py

Outputs:
    reports/10_dsr_trials.csv           (DSR at every N for both series)
    reports/10_dsr_trial_ledger.csv     (the line-item trial ledger)
    reports/charts/10_dsr_vs_ntrials.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from statarb.backtest import Backtester
from statarb.costs import LinearCostModel
from statarb.evaluation import deflated_sharpe_ratio
from statarb.signals import combine as eq_combine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_walkforward import (
    COST_BPS,
    LONG_Q,
    SHORT_Q,
    _baseline_walkforward_trace,
    _is_sharpe,
    load_signals_and_prices,
    long_short_quantile_weights,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
DSR_CSV = REPO_ROOT / "reports" / "10_dsr_trials.csv"
LEDGER_CSV = REPO_ROOT / "reports" / "10_dsr_trial_ledger.csv"

# ----------------------------------------------------------------------------
# The trial ledger.
#
# `naive` = every distinct backtest config examined during the search that
#   could, had it read best, have become the headline. This is the
#   conservative UPPER BOUND on N.
# `effective` = independent-trial estimate after collapsing configs whose
#   return streams are near-duplicates (same signal at a different lookback,
#   leave-one-out drops at rho>0.9, the same strategy reported on a different
#   IS/OOS split). This is the defensible LOWER BOUND on N.
# Bailey-Lopez de Prado define N as the number of *independent* trials, so the
# truth sits between these two columns.
# ----------------------------------------------------------------------------
TRIAL_LEDGER = [
    # phase, description, naive, effective
    ("P3", "12-1 cross-sectional momentum (ETF universe)", 1, 1),
    ("P4", "reversal lookback {1,5,21}d (ETF)", 3, 1),
    ("P4", "momentum+reversal blend (ETF)", 1, 1),
    ("P5", "momentum & reversal-5d re-run on futures universe", 2, 0),
    ("P5", "realized-carry 21d", 1, 1),
    ("P5", "mom+rev and mom+rev+carry blends", 2, 1),
    ("P6", "COT managed-money 3y positioning z-score", 1, 1),
    ("P6", "EIA inventory 5yr-seasonal surprise", 1, 1),
    ("P6", "carry+cot and all-5 blends", 2, 1),
    ("P7", "time-series momentum 126d", 1, 1),
    ("P7", "sharpe-weighted alpha blend", 1, 1),
    ("P7", "cvxpy optimizer lambda{0.5,5,50} x turnover{none,.5,.2}", 9, 3),
    ("A6", "leave-one-commodity-out (drop each of 13)", 13, 2),
    ("A6", "alt IS/OOS cutoff {2017,2019,2020} (ex-2018)", 3, 0),
    ("A6", "quantile threshold {30,50}% (ex-40)", 2, 1),
    ("A6", "carry lookback {10,42}d (ex-21)", 2, 1),
    ("A6", "COT lookback {104,208}w (ex-156)", 2, 1),
]

N_GRID = [1, 5, 10, 15, 18, 20, 25, 30, 40, 47, 50, 60, 75, 100]


def build_static_baseline(prices, signals, first_valid) -> pd.Series:
    """Equal-weight carry+cot quantile portfolio over the full window."""
    alpha = eq_combine(
        {"carry": signals["carry"].loc[first_valid:], "cot": signals["cot"].loc[first_valid:]}
    )
    weights = long_short_quantile_weights(
        alpha, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )
    bt = Backtester(prices, LinearCostModel(bps_per_side=COST_BPS))
    return bt.run(weights).net_returns


def breakeven_n(series: pd.Series, *, lo: int = 1, hi: int = 200) -> float | None:
    """Largest integer N at which DSR(series) still clears 0.95 (binary search
    on the monotonically-decreasing DSR-vs-N curve). None if it fails even at N=1."""
    if deflated_sharpe_ratio(series, n_trials=lo).dsr < 0.95:
        return None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if deflated_sharpe_ratio(series, n_trials=mid).dsr >= 0.95:
            lo = mid
        else:
            hi = mid - 1
    return lo


def main() -> int:
    print("=" * 76)
    print("PHASE A2 (research-firming) — rigorous DSR trial accounting")
    print("=" * 76)

    # ---- Trial ledger ----
    ledger = pd.DataFrame(TRIAL_LEDGER, columns=["phase", "description", "naive", "effective"])
    n_naive = int(ledger["naive"].sum())
    n_effective = int(ledger["effective"].sum())
    print("\nTRIAL LEDGER (every backtest config examined during the search)")
    print("-" * 76)
    print(ledger.to_string(index=False))
    print("-" * 76)
    print(f"  naive trial count (upper bound)        N = {n_naive}")
    print(f"  effective-independent count (lower bd) N = {n_effective}")
    ledger.to_csv(LEDGER_CSV, index=False)
    print(f"  saved {LEDGER_CSV}")

    # ---- Return series ----
    prices, _adj_clean, _futures, signals, first_valid = load_signals_and_prices()
    static = build_static_baseline(prices, signals, first_valid).dropna()
    _rows, oos = _baseline_walkforward_trace(
        prices, signals, first_valid, train_mode="expanding", train_years=0,
    )
    wf = pd.concat(oos).sort_index()

    series = {
        "static_full_window": static,
        "walkforward_oos": wf,
    }
    print("\nReturn series under test:")
    for name, s in series.items():
        print(f"  {name:>22}: Sharpe {_is_sharpe(s):+.3f}  ({len(s)} days)")

    # ---- DSR sweep ----
    out_rows: list[dict] = []
    for name, s in series.items():
        for n in N_GRID:
            d = deflated_sharpe_ratio(s, n_trials=n)
            out_rows.append({
                "series": name,
                "n_trials": n,
                "point_sharpe": round(d.point_sharpe, 3),
                "expected_max_sharpe_null": round(d.expected_max_sharpe, 3),
                "psr_vs_zero": round(d.psr, 4),
                "dsr": round(d.dsr, 4),
                "passes_95": d.is_significant_at_5pct,
            })
    dsr_df = pd.DataFrame(out_rows)
    dsr_df.to_csv(DSR_CSV, index=False)
    print(f"\nsaved {DSR_CSV}")

    print("\nDSR vs N (deflated Sharpe, 0.95 = passes after multiple-testing):")
    for name in series:
        sub = dsr_df[dsr_df["series"] == name]
        be = breakeven_n(series[name])
        print(f"\n  [{name}]  breakeven N (DSR=0.95) = {be}")
        for _, r in sub.iterrows():
            flag = "PASS" if r["passes_95"] else "fail"
            mark = ""
            if n_effective <= r["n_trials"] <= n_naive:
                mark = "  <- inside honest [eff,naive] bracket"
            print(f"    N={int(r['n_trials']):>3}: DSR={r['dsr']:.3f} [{flag}]"
                  f"  E[max|null]={r['expected_max_sharpe_null']:+.2f}{mark}")

    # ---- Chart ----
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = {"static_full_window": "#1f4e79", "walkforward_oos": "#1f7a3a"}
    labels = {"static_full_window": "static full-window baseline",
              "walkforward_oos": "walk-forward OOS trace (A-1)"}
    for name in series:
        sub = dsr_df[dsr_df["series"] == name].sort_values("n_trials")
        ax.plot(sub["n_trials"], sub["dsr"], marker="o", linewidth=1.6,
                color=colors[name], label=f"{labels[name]} (SR {_is_sharpe(series[name]):+.2f})")
    ax.axhline(0.95, color="#c0392b", linewidth=1.0, linestyle="--", label="0.95 significance bar")
    ax.axvspan(n_effective, n_naive, color="#cccccc", alpha=0.35,
               label=f"honest N bracket [{n_effective}, {n_naive}]")
    ax.set_xlabel("N (assumed number of selection trials)")
    ax.set_ylabel("Deflated Sharpe Ratio")
    ax.set_title("DSR sensitivity to trial count — deployable baseline")
    ax.set_ylim(0.55, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    fig.tight_layout()
    out = CHARTS_DIR / "10_dsr_vs_ntrials.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"\nsaved chart: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
