"""Phase 6 runner: COT positioning + (optional) EIA inventory surprise.

Asks three questions:
  Q1: does CFTC managed-money positioning predict commodity returns
      (negated z-score, crowded long = bearish)?
  Q2: if EIA_API_KEY is set, does the inventory-surprise signal add edge?
  Q3: does combining the new macro signals with the carry signal from
      Phase 5 produce a portfolio whose Sharpe meaningfully exceeds the
      best individual standalone Sharpe?

    uv run python scripts/run_macro_signals.py

Outputs:
    reports/charts/04_*.png
    reports/04_macro_signals_metrics.csv
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
    evaluate,
    evaluate_walkforward,
    plot_cost_sensitivity,
    plot_equity_curve,
)
from statarb.portfolio import long_short_quantile_weights
from statarb.signals import (
    combine,
    cot_positioning,
    inventory_surprise,
    momentum,
    realized_carry,
    reversal,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = REPO_ROOT / "reports" / "charts"
METRICS_PATH = REPO_ROOT / "reports" / "04_macro_signals_metrics.csv"

MOM_LOOKBACK = 252
MOM_SKIP = 21
REV_LOOKBACK = 5
CARRY_LOOKBACK = 21
COT_LOOKBACK_WEEKS = 156
INVENTORY_SEASONAL_YEARS = 5
LONG_Q = 0.4
SHORT_Q = 0.4
COST_LEVELS_BPS = (0, 5, 10, 25)
HEADLINE_COST_BPS = 10


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
    fig, ax = plt.subplots(figsize=(7.0, 5.5))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.index)))
    ax.set_xticklabels(corr.columns, rotation=30, ha="right")
    ax.set_yticklabels(corr.index)
    for i in range(len(corr)):
        for j in range(len(corr)):
            v = corr.iat[i, j]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center",
                    color="black" if abs(v) < 0.5 else "white", fontsize=8)
    ax.set_title("Net-return correlation across strategies")
    fig.colorbar(im, ax=ax, shrink=0.85)
    fig.tight_layout()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


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

    # --- Phase 5 signals (recompute) ---
    mom_score = momentum(fut_adj, lookback=MOM_LOOKBACK, skip=MOM_SKIP)
    rev_score = reversal(fut_adj, lookback=REV_LOOKBACK)
    carry_score_raw = realized_carry(adj_clean, pairs=ETF_FUTURES_PAIRS, lookback=CARRY_LOOKBACK)
    carry_score = pd.DataFrame(
        index=mom_score.index, columns=mom_score.columns, dtype=float
    )
    for c in carry_score_raw.columns:
        if c in carry_score.columns:
            carry_score[c] = carry_score_raw[c]

    # --- COT signal ---
    cot_panel = load_cot_panel()
    cot_score = cot_positioning(
        cot_panel, lookback_weeks=COT_LOOKBACK_WEEKS, target_index=daily_index
    )
    # cot_score columns are tickers; reindex to the futures universe order
    cot_score = cot_score.reindex(columns=futures_universe)

    # --- EIA inventory signal (optional) ---
    inv_score = None
    try:
        eia_panel = load_eia_panel()
        inv_score = inventory_surprise(
            eia_panel,
            seasonal_years=INVENTORY_SEASONAL_YEARS,
            target_index=daily_index,
        )
        inv_score = inv_score.reindex(columns=futures_universe)
        print(f"EIA inventory signal: loaded {inv_score.notna().sum().sum()} valid (ticker, day) cells")
    except (FileNotFoundError, EIAKeyMissing) as e:
        print(f"EIA inventory signal: SKIPPED ({e})")

    # --- First valid day for the backtest ---
    # Use whichever signal is the slowest to mature. COT needs 156 weeks, so
    # it's usually the constraint when included.
    first_valid_candidates = {
        "momentum": mom_score.index[mom_score.notna().sum(axis=1) >= 4][0],
        "cot": cot_score.index[cot_score.notna().sum(axis=1) >= 3][0],
    }
    if inv_score is not None:
        first_valid_candidates["inventory"] = inv_score.index[inv_score.notna().sum(axis=1) >= 3][0]
    first_valid = max(first_valid_candidates.values())
    print(f"first valid day (all signals ready): {first_valid.date()}")
    for k, v in first_valid_candidates.items():
        print(f"  {k:>10}: {v.date()}")

    # --- Standalone backtests ---
    standalone: dict[str, BacktestResult] = {
        "futures_momentum_12-1": _run(_build(mom_score, first_valid), pd_view, HEADLINE_COST_BPS),
        "futures_reversal_5d": _run(_build(rev_score, first_valid), pd_view, HEADLINE_COST_BPS),
        "futures_carry_21d": _run(_build(carry_score, first_valid), pd_view, HEADLINE_COST_BPS),
        "futures_cot_3y": _run(_build(cot_score, first_valid), pd_view, HEADLINE_COST_BPS),
    }
    if inv_score is not None:
        standalone["futures_inventory_5yr_seas"] = _run(
            _build(inv_score, first_valid), pd_view, HEADLINE_COST_BPS
        )

    # --- Combined: carry + cot ---
    components = {
        "carry": carry_score.loc[first_valid:],
        "cot": cot_score.loc[first_valid:],
    }
    cc = combine(components)
    cc_weights = long_short_quantile_weights(
        cc, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0
    )
    cc_by_cost = {bps: _run(cc_weights, pd_view, bps) for bps in COST_LEVELS_BPS}

    # --- Combined: all available (price + carry + macro) ---
    all_components = {
        "momentum": mom_score.loc[first_valid:],
        "reversal": rev_score.loc[first_valid:],
        "carry": carry_score.loc[first_valid:],
        "cot": cot_score.loc[first_valid:],
    }
    if inv_score is not None:
        all_components["inventory"] = inv_score.loc[first_valid:]
    all_combined = combine(all_components)
    all_weights = long_short_quantile_weights(
        all_combined, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0
    )
    all_by_cost = {bps: _run(all_weights, pd_view, bps) for bps in COST_LEVELS_BPS}

    # --- Reporting ---
    rows: list[dict] = []
    print()
    print("=" * 76)
    print(f"Standalone signals @ {HEADLINE_COST_BPS} bps/side, full window")
    print("=" * 76)
    for name, res in standalone.items():
        rep = evaluate(res, benchmark_returns=spy)
        print(f"  {name:>28}: {rep}")
        rows.append(_row(name, "full", rep))

    print()
    print("=" * 76)
    print(f"Combined (carry + cot) @ {HEADLINE_COST_BPS} bps")
    print("=" * 76)
    wf_cc = evaluate_walkforward(cc_by_cost[HEADLINE_COST_BPS], benchmark_returns=spy)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {wf_cc[w]}")
        rows.append(_row("combined_carry+cot", w, wf_cc[w]))

    print()
    label_all = "combined_all" + ("5" if inv_score is not None else "4")
    n_in_combo = "+ inventory" if inv_score is not None else "(no inventory)"
    print("=" * 76)
    print(f"Combined (mom + rev + carry + cot {n_in_combo}) @ {HEADLINE_COST_BPS} bps")
    print("=" * 76)
    wf_all = evaluate_walkforward(all_by_cost[HEADLINE_COST_BPS], benchmark_returns=spy)
    for w in ("in_sample", "out_of_sample", "full"):
        print(f"  {w:>14}: {wf_all[w]}")
        rows.append(_row(label_all, w, wf_all[w]))

    print()
    print(f"{label_all} cost sensitivity:")
    for bps in sorted(all_by_cost):
        rep = evaluate(all_by_cost[bps], benchmark_returns=spy)
        print(f"  {bps:>3} bps -> Sharpe={rep.sharpe:+.2f}, CAGR={rep.cagr:+.2%}, MaxDD={rep.max_drawdown:.2%}")
        rows.append(_row(label_all, f"full @ {bps} bps", rep))

    # Correlations
    return_series = {name: res.net_returns for name, res in standalone.items()}
    return_series["combined_carry+cot"] = cc_by_cost[HEADLINE_COST_BPS].net_returns
    return_series[label_all] = all_by_cost[HEADLINE_COST_BPS].net_returns
    print()
    corr = pd.DataFrame(return_series).dropna(how="any").corr().round(3)
    print("Net-return correlations:")
    print(corr.to_string())

    # Charts
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_equity_curve(
        all_by_cost[HEADLINE_COST_BPS],
        benchmark=spy,
        title=f"{label_all} @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "04_all_combined_equity.png",
    )
    plot_equity_curve(
        cc_by_cost[HEADLINE_COST_BPS],
        benchmark=spy,
        title=f"Carry + COT @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "04_carry_cot_equity.png",
    )
    plot_equity_curve(
        standalone["futures_cot_3y"],
        benchmark=spy,
        title=f"COT 3y z-score standalone @ {HEADLINE_COST_BPS} bps vs SPY",
        save_path=CHARTS_DIR / "04_cot_standalone_equity.png",
    )
    if inv_score is not None:
        plot_equity_curve(
            standalone["futures_inventory_5yr_seas"],
            benchmark=spy,
            title=f"Inventory surprise standalone @ {HEADLINE_COST_BPS} bps vs SPY",
            save_path=CHARTS_DIR / "04_inventory_standalone_equity.png",
        )
    plot_cost_sensitivity(
        all_by_cost,
        title=f"{label_all}: equity vs transaction cost",
        save_path=CHARTS_DIR / "04_all_combined_cost_sensitivity.png",
    )
    _plot_corr(return_series, CHARTS_DIR / "04_signal_correlation.png")

    print(f"\ncharts saved to {CHARTS_DIR}/")
    pd.DataFrame(rows).to_csv(METRICS_PATH, index=False)
    print(f"metrics saved to {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
