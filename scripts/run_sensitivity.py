"""Phase A6: sensitivity sweeps on the headline strategy.

Four perturbations of the baseline (equal-weight quantile carry+cot on
13 commodities at 10 bps/side):

  1. Leave-one-out commodity  - does any single instrument drive the result?
  2. Alternate IS/OOS splits  - robust across {2017,2018,2019,2020} cutoffs?
  3. Alternate quantile thresholds - {30%, 40%, 50%} long/short
  4. Alternate signal lookbacks   - carry {10,21,42d}, COT {104,156,208w}

For each perturbation: report full-window Sharpe, bootstrap 95% CI low/high,
delta-from-baseline. If the range is narrow (e.g. all within +/-0.2 of
baseline) -> robust. If wide -> fragile.

    uv run python scripts/run_sensitivity.py

Outputs:
    reports/07_sensitivity_table.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

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
from statarb.evaluation import (
    bootstrap_sharpe,
    evaluate,
    split_in_out_sample,
)
from statarb.portfolio import long_short_quantile_weights
from statarb.signals import combine, cot_positioning, realized_carry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "reports" / "07_sensitivity_table.csv"

# Baseline parameters (locked from FINAL.md)
CARRY_LOOKBACK = 21
COT_LOOKBACK_WEEKS = 156
LONG_Q = 0.4
SHORT_Q = 0.4
COST_BPS = 10
DEFAULT_IS_END_LOCAL = "2018-12-31"
BOOTSTRAP_N = 5000
BOOTSTRAP_BLOCK = 20


def _run_baseline(
    *,
    universe: list[str] | None = None,
    carry_lookback: int = CARRY_LOOKBACK,
    cot_lookback_weeks: int = COT_LOOKBACK_WEEKS,
    long_q: float = LONG_Q,
    short_q: float = SHORT_Q,
    cost_bps: int = COST_BPS,
) -> tuple[BacktestResult, pd.Timestamp]:
    """Run the baseline strategy under one specific parameter combo."""
    pd_raw = PriceData.load()
    adj_clean = mask_known_anomalies(pd_raw.adj_close())
    pd_view = PriceData(adj_clean)

    futures = universe or all_tradable_futures()
    # Carry only includes ETF-paired futures
    pairs = {etf: fut for etf, fut in ETF_FUTURES_PAIRS.items() if fut in futures}

    # Signals
    carry_raw = realized_carry(adj_clean, pairs=pairs, lookback=carry_lookback)
    carry_score = pd.DataFrame(
        index=adj_clean.index, columns=futures, dtype=float,
    )
    for c in carry_raw.columns:
        if c in carry_score.columns:
            carry_score[c] = carry_raw[c]

    cot_panel = load_cot_panel()
    cot_score = cot_positioning(
        cot_panel, lookback_weeks=cot_lookback_weeks, target_index=adj_clean.index,
    ).reindex(columns=futures)

    # First valid day
    first_valid = max(
        carry_score.index[carry_score.notna().sum(axis=1) >= max(2, len(futures) // 4)][0],
        cot_score.index[cot_score.notna().sum(axis=1) >= max(2, len(futures) // 4)][0],
    )

    # Combine + portfolio + backtest
    blend = combine(
        {"carry": carry_score.loc[first_valid:], "cot": cot_score.loc[first_valid:]}
    )
    weights = long_short_quantile_weights(
        blend, long_quantile=long_q, short_quantile=short_q, gross_leverage=1.0,
    )
    bt = Backtester(pd_view, LinearCostModel(bps_per_side=cost_bps))
    return bt.run(weights), first_valid


def _row(label: str, kind: str, res: BacktestResult, baseline_sharpe: float) -> dict:
    rep = evaluate(res)
    boot = bootstrap_sharpe(
        res.net_returns, n_resamples=BOOTSTRAP_N, block_length=BOOTSTRAP_BLOCK, rng_seed=0,
    )
    return {
        "perturbation_kind": kind,
        "perturbation": label,
        "sharpe": round(rep.sharpe, 3),
        "sharpe_delta_vs_baseline": round(rep.sharpe - baseline_sharpe, 3),
        "ci_low_95": round(boot.ci_low, 3),
        "ci_high_95": round(boot.ci_high, 3),
        "sig_at_5pct": boot.is_significant_at_5pct,
        "ann_vol": round(rep.ann_vol, 4),
        "max_dd": round(rep.max_drawdown, 4),
        "n_days": rep.n_days,
    }


def main() -> int:
    print("=" * 76)
    print("PHASE A6 - sensitivity sweeps on the headline baseline strategy")
    print("=" * 76)

    # --- Baseline ---
    base_res, base_first_valid = _run_baseline()
    base_sharpe = evaluate(base_res).sharpe
    print(f"\nBASELINE: full-window Sharpe = {base_sharpe:+.3f}")
    print("  universe: 13 commodities, carry=21d, cot=156w, quantile=40/40, cost=10bps")
    print(f"  first valid day: {base_first_valid.date()}")

    rows: list[dict] = [_row("baseline_13c_carry21_cot156_q40_10bps", "baseline", base_res, base_sharpe)]

    # --- 1. Leave-one-out commodity ---
    print("\n--- (1) Leave-one-out commodity ---")
    full_universe = all_tradable_futures()
    for drop in full_universe:
        reduced = [t for t in full_universe if t != drop]
        res, _ = _run_baseline(universe=reduced)
        sh = evaluate(res).sharpe
        print(f"  drop {drop:6s}: Sharpe = {sh:+.3f}  (delta {sh - base_sharpe:+.3f})")
        rows.append(_row(f"drop_{drop}", "leave_one_out", res, base_sharpe))

    # --- 2. Alternate IS/OOS splits ---
    print("\n--- (2) Alternate IS/OOS splits (full-window unchanged; OOS Sharpe varies) ---")
    splits = ["2017-12-31", "2018-12-31", "2019-12-31", "2020-12-31"]
    for split_end in splits:
        is_net, oos_net = split_in_out_sample(base_res.net_returns, in_sample_end=split_end)
        is_rep = evaluate(BacktestResult(
            weights_applied=base_res.weights_applied,
            turnover=base_res.turnover,
            gross_returns=base_res.gross_returns,
            costs=base_res.costs,
            net_returns=is_net,
            equity_curve=(1.0 + is_net.fillna(0)).cumprod(),
            meta={"window": f"is_<={split_end}"},
        ))
        oos_rep = evaluate(BacktestResult(
            weights_applied=base_res.weights_applied,
            turnover=base_res.turnover,
            gross_returns=base_res.gross_returns,
            costs=base_res.costs,
            net_returns=oos_net,
            equity_curve=(1.0 + oos_net.fillna(0)).cumprod(),
            meta={"window": f"oos_>{split_end}"},
        ))
        print(f"  split {split_end}: IS Sharpe = {is_rep.sharpe:+.3f}  OOS Sharpe = {oos_rep.sharpe:+.3f}  "
              f"(IS days {is_rep.n_days}, OOS days {oos_rep.n_days})")
        rows.append({
            "perturbation_kind": "split",
            "perturbation": f"is_end={split_end}",
            "sharpe": round(oos_rep.sharpe, 3),
            "sharpe_delta_vs_baseline": round(oos_rep.sharpe - base_sharpe, 3),
            "ci_low_95": None,
            "ci_high_95": None,
            "sig_at_5pct": None,
            "ann_vol": round(oos_rep.ann_vol, 4),
            "max_dd": round(oos_rep.max_drawdown, 4),
            "n_days": oos_rep.n_days,
        })

    # --- 3. Alternate quantile thresholds ---
    print("\n--- (3) Alternate quantile thresholds ---")
    for q in (0.30, 0.40, 0.50):
        res, _ = _run_baseline(long_q=q, short_q=q)
        sh = evaluate(res).sharpe
        print(f"  quantile {int(q*100):>2}%: Sharpe = {sh:+.3f}  (delta {sh - base_sharpe:+.3f})")
        rows.append(_row(f"quantile={int(q*100)}", "quantile", res, base_sharpe))

    # --- 4. Alternate carry lookbacks ---
    print("\n--- (4) Alternate carry lookbacks ---")
    for lb in (10, 21, 42):
        res, _ = _run_baseline(carry_lookback=lb)
        sh = evaluate(res).sharpe
        print(f"  carry lookback {lb:>2}d: Sharpe = {sh:+.3f}  (delta {sh - base_sharpe:+.3f})")
        rows.append(_row(f"carry_lookback={lb}", "carry_lookback", res, base_sharpe))

    # --- 5. Alternate COT z-score windows ---
    print("\n--- (5) Alternate COT z-score lookback windows ---")
    for cw in (104, 156, 208):
        res, _ = _run_baseline(cot_lookback_weeks=cw)
        sh = evaluate(res).sharpe
        print(f"  cot lookback {cw:>3}w (~{cw // 52:.0f}y): Sharpe = {sh:+.3f}  (delta {sh - base_sharpe:+.3f})")
        rows.append(_row(f"cot_lookback={cw}w", "cot_lookback", res, base_sharpe))

    # --- Summary ---
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nsaved {OUTPUT_PATH}")

    print()
    print("=" * 76)
    print("SUMMARY: Sharpe range under each perturbation")
    print("=" * 76)
    for kind in df["perturbation_kind"].unique():
        if kind == "baseline":
            continue
        sub = df[df["perturbation_kind"] == kind]
        print(f"  {kind:>18}: Sharpe range [{sub.sharpe.min():+.3f}, {sub.sharpe.max():+.3f}]  "
              f"(baseline {base_sharpe:+.3f})")

    print()
    print(f"  baseline:           {base_sharpe:+.3f}")
    print(f"  worst-case Sharpe:  {df[df.perturbation_kind != 'baseline'].sharpe.min():+.3f}")
    print(f"  best-case Sharpe:   {df[df.perturbation_kind != 'baseline'].sharpe.max():+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
