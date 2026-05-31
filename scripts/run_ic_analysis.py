"""Phase A3 (research-firming): Information-Coefficient + signal-decay analysis.

The DSR and bootstrap tell us the *portfolio* has edge. This asks the more
fundamental question one rung down: do the individual signals actually
*predict* cross-sectional forward returns, and over what horizon? A signal
with a real IC that decays slowly justifies a low rebalance frequency; one
with zero IC is just noise the portfolio construction happens to exploit.

Method (Grinold-Kahn information coefficient, lookahead-free):
  - IC_t(h) = cross-sectional Spearman rank correlation between the signal
    known at t-1 (lagged one day, exactly as the backtester trades it) and
    the realized h-day forward return from t to t+h.
  - The signal uses data <= t-1; the return uses prices >= t. No lookahead.
  - Aggregate the daily IC series: mean IC, IC-IR (mean/std), an
    overlap-adjusted t-stat (effective n = n_days / h, since h-day forward
    returns on consecutive days overlap), and the share of days IC > 0.
  - Signal persistence: cross-sectional rank autocorrelation at lags
    {1,5,21,63} -- how stable the ranking is -> the natural holding period.

    uv run python scripts/run_ic_analysis.py

Outputs:
    reports/11_ic_analysis.csv          (IC stats per signal x horizon)
    reports/11_signal_autocorr.csv      (rank autocorrelation per signal x lag)
    reports/charts/11_ic_by_horizon.png
    reports/charts/11_signal_decay.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_walkforward import load_signals_and_prices

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
IC_CSV = REPO_ROOT / "reports" / "11_ic_analysis.csv"
AUTOCORR_CSV = REPO_ROOT / "reports" / "11_signal_autocorr.csv"

HORIZONS = [1, 5, 21, 63]
LAGS = [1, 5, 21, 63]
TRADING_DAYS = 252
# Order the signals most-economic-first so the table reads as a narrative.
SIGNAL_ORDER = ["carry", "cot", "inventory", "ts_momentum", "momentum", "reversal"]


def forward_return(prices: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """h-day forward return aligned to the decision date: value at t is the
    return from close[t] to close[t+h]."""
    return prices.shift(-horizon) / prices - 1.0


def daily_ic(signal: pd.DataFrame, fwd: pd.DataFrame) -> pd.Series:
    """Per-day cross-sectional Spearman IC between the one-day-lagged signal
    and the forward return. Lagging the signal mirrors the backtester's
    one-day trade lag, so IC measures genuinely actionable prediction."""
    sig_lag = signal.shift(1)
    common = sig_lag.columns.intersection(fwd.columns)
    return sig_lag[common].corrwith(fwd[common], axis=1, method="spearman")


def summarize_ic(ic: pd.Series, horizon: int) -> dict:
    s = ic.dropna()
    n = len(s)
    mean = float(s.mean())
    std = float(s.std(ddof=1))
    ic_ir = mean / std if std > 0 else float("nan")
    # Overlap correction: h-day forward returns on consecutive days share
    # h-1 days of data, so the IC series is autocorrelated. Deflate the
    # effective sample size by the horizon for an honest t-stat.
    n_eff = max(n / horizon, 1.0)
    t_stat = mean / std * np.sqrt(n_eff) if std > 0 else float("nan")
    return {
        "horizon": horizon,
        "mean_ic": round(mean, 4),
        "ic_std": round(std, 4),
        "ic_ir": round(ic_ir, 4),
        "t_stat_overlap_adj": round(float(t_stat), 3),
        "pct_days_positive": round(float((s > 0).mean()), 3),
        "n_days": n,
        "n_eff": int(n_eff),
    }


def rank_autocorr(signal: pd.DataFrame, lag: int) -> float:
    """Mean cross-sectional rank autocorrelation: how similar today's ranking
    is to the ranking `lag` days ago. ~1 = very persistent (slow signal)."""
    ac = signal.corrwith(signal.shift(lag), axis=1, method="spearman")
    return float(ac.dropna().mean())


def main() -> int:
    print("=" * 76)
    print("PHASE A3 (research-firming) — Information Coefficient + signal decay")
    print("=" * 76)

    _prices_view, adj_clean, futures, signals, first_valid = load_signals_and_prices()
    fut_prices = adj_clean[futures].loc[first_valid:]
    signals = {n: s.loc[first_valid:] for n, s in signals.items()}
    ordered = [s for s in SIGNAL_ORDER if s in signals]
    print(f"\nfirst valid day: {first_valid.date()}   universe: {len(futures)} futures")
    print(f"signals: {ordered}")

    fwd_panels = {h: forward_return(fut_prices, h) for h in HORIZONS}

    # ---- IC per signal x horizon ----
    rows: list[dict] = []
    for name in ordered:
        for h in HORIZONS:
            ic = daily_ic(signals[name], fwd_panels[h])
            rows.append({"signal": name, **summarize_ic(ic, h)})
    ic_df = pd.DataFrame(rows)
    ic_df.to_csv(IC_CSV, index=False)

    print("\nINFORMATION COEFFICIENT (lagged signal vs h-day forward return)")
    print("-" * 76)
    for name in ordered:
        sub = ic_df[ic_df["signal"] == name]
        print(f"\n  {name}")
        for _, r in sub.iterrows():
            star = "*" if abs(r["t_stat_overlap_adj"]) >= 2.0 else " "
            print(
                f"    h={int(r['horizon']):>2}d: IC={r['mean_ic']:+.4f}  "
                f"IC-IR={r['ic_ir']:+.3f}  t={r['t_stat_overlap_adj']:+.2f}{star}  "
                f"pos={r['pct_days_positive']:.0%}  (n_eff={int(r['n_eff'])})"
            )
        # natural horizon = peak |IC-IR|
        peak = sub.loc[sub["ic_ir"].abs().idxmax()]
        print(f"    -> peak IC-IR at h={int(peak['horizon'])}d (IC-IR {peak['ic_ir']:+.3f})")
    print(f"\nsaved {IC_CSV}")

    # ---- Signal persistence (rank autocorrelation) ----
    ac_rows: list[dict] = []
    for name in ordered:
        ac_rows.append({"signal": name, **{f"autocorr_lag{lag}": round(rank_autocorr(signals[name], lag), 3)
                                           for lag in LAGS}})
    ac_df = pd.DataFrame(ac_rows)
    ac_df.to_csv(AUTOCORR_CSV, index=False)
    print("\nSIGNAL PERSISTENCE (cross-sectional rank autocorrelation)")
    print("-" * 76)
    print(ac_df.to_string(index=False))
    print(f"\nsaved {AUTOCORR_CSV}")

    # ---- Charts ----
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    palette = {
        "carry": "#1f7a3a", "cot": "#1f4e79", "inventory": "#8e44ad",
        "ts_momentum": "#e67e22", "momentum": "#c0392b", "reversal": "#7f8c8d",
    }

    # IC-IR by horizon
    fig, ax = plt.subplots(figsize=(9, 5))
    for name in ordered:
        sub = ic_df[ic_df["signal"] == name].sort_values("horizon")
        ax.plot(sub["horizon"], sub["ic_ir"], marker="o", linewidth=1.6,
                color=palette.get(name, "#555"), label=name)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xlabel("forward-return horizon (trading days)")
    ax.set_ylabel("IC information ratio (mean IC / std IC)")
    ax.set_title("Signal IC-IR by forward horizon — A3")
    ax.set_xticks(HORIZONS)
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "11_ic_by_horizon.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Signal decay (rank autocorrelation vs lag)
    fig, ax = plt.subplots(figsize=(9, 5))
    for name in ordered:
        ys = [ac_df.loc[ac_df["signal"] == name, f"autocorr_lag{lag}"].iloc[0] for lag in LAGS]
        ax.plot(LAGS, ys, marker="s", linewidth=1.6, color=palette.get(name, "#555"), label=name)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xlabel("lag (trading days)")
    ax.set_ylabel("cross-sectional rank autocorrelation")
    ax.set_title("Signal persistence / decay — A3")
    ax.set_xticks(LAGS)
    ax.grid(alpha=0.3)
    ax.legend(loc="best", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "11_signal_decay.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"\nsaved charts: {CHARTS_DIR}/11_ic_by_horizon.png, 11_signal_decay.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
