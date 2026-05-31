# Phase A2 (research-firming): Rigorous Deflated-Sharpe Trial Accounting

> _Snapshot: numbers computed by `scripts/run_dsr_trials.py`. OOS data accumulates daily, so point estimates may drift slightly on re-run; the qualitative verdict is stable._

**TL;DR.** The Deflated Sharpe Ratio's only free parameter is `N`, the number of trials run during model selection. Previous reporting hand-waved `N = 25`. This phase replaces that with an **explicit line-item ledger of every backtest config the project ever examined**, which brackets the honest trial count at **N ∈ [18, 47]** (effective-independent → naive-upper-bound). Under that bracket the deployable baseline is **borderline on the strict 0.95 bar**: the static full-window result (Sharpe +1.00) clears 0.95 only up to **N = 21**, and the walk-forward OOS trace (Sharpe +1.05) clears it only up to **N = 10**. **The honest verdict is YELLOW, not GREEN** — the bootstrap CI excludes zero robustly, but after a fully-honest multiple-testing correction the strategy sits right on the significance threshold rather than comfortably past it.

## Why this matters

The block-bootstrap CI (in `FINAL.md`) establishes that the strategy's Sharpe is non-zero *given the one strategy we settled on*. It cannot see the **selection bias** from having tested many strategies and reported the best-looking one. The DSR (Bailey & López de Prado 2014) is the standard correction: it compares the realized Sharpe to `E[max Sharpe | N coin-flip trials under no-skill]`. The entire result hinges on `N` — and `N` is a judgement call. The only intellectually honest way to report it is to (a) enumerate the trials transparently and (b) show the DSR across the whole plausible range of `N` rather than at one convenient point.

## The trial ledger

Every distinct backtest configuration examined during the search (Phases 3-7 + A6 sensitivity), reconstructed from the per-phase reports. Two counts:

- **naive** — every config that could, had it read best, have become the headline. Conservative **upper bound**.
- **effective** — independent-trial estimate after collapsing near-duplicate return streams (same signal at a different lookback, leave-one-out drops correlated at ρ > 0.9, the same strategy merely re-reported on a different IS/OOS split). Defensible **lower bound**.

| Phase | Config family | naive | effective |
|---|---|---:|---:|
| P3 | 12-1 cross-sectional momentum (ETF) | 1 | 1 |
| P4 | reversal lookback {1,5,21}d (ETF) | 3 | 1 |
| P4 | momentum+reversal blend (ETF) | 1 | 1 |
| P5 | momentum & reversal-5d re-run on futures universe | 2 | 0 |
| P5 | realized-carry 21d | 1 | 1 |
| P5 | mom+rev and mom+rev+carry blends | 2 | 1 |
| P6 | COT managed-money 3y positioning z-score | 1 | 1 |
| P6 | EIA inventory 5yr-seasonal surprise | 1 | 1 |
| P6 | carry+cot and all-5 blends | 2 | 1 |
| P7 | time-series momentum 126d | 1 | 1 |
| P7 | sharpe-weighted alpha blend | 1 | 1 |
| P7 | cvxpy optimizer λ{0.5,5,50} × turnover{none,.5,.2} | 9 | 3 |
| A6 | leave-one-commodity-out (drop each of 13) | 13 | 2 |
| A6 | alt IS/OOS cutoff {2017,2019,2020} (ex-2018) | 3 | 0 |
| A6 | quantile threshold {30,50}% (ex-40) | 2 | 1 |
| A6 | carry lookback {10,42}d (ex-21) | 2 | 1 |
| A6 | COT lookback {104,208}w (ex-156) | 2 | 1 |
| | **TOTAL** | **47** | **18** |

The raw ledger is in `reports/10_dsr_trial_ledger.csv`.

**The honest trial count is N ∈ [18, 47].** The effective count collapses the families that are not independent experiments: the 13 leave-one-out drops produce return streams ~0.95 correlated with the full strategy (≈ 2 independent trials, not 13); the three alternate IS/OOS cutoffs are the *same strategy* reported on different windows (0 new trials); re-running momentum/reversal on the futures universe is the same signal hypothesis (0 new). The naive count assumes every config is a fully independent shot on goal, which over-penalizes.

## DSR across the trial count

Computed on two return series: the **static full-window baseline** (eq-weight carry+cot, the FINAL.md headline) and the **walk-forward expanding OOS trace** (the A-1 deliverable, where survivors are re-selected each year — the genuinely out-of-sample number).

| N | static full-window (SR +1.00, 3748d) | walk-forward OOS (SR +1.05, 2867d) |
|---:|:---:|:---:|
| 1 | 1.000 | 1.000 |
| 5 | 0.992 | 0.981 |
| 10 | 0.978 ✅ | **0.951 ✅** |
| 15 | 0.964 ✅ | 0.927 |
| **18** (eff.) | **0.957 ✅** | 0.915 |
| 20 | 0.953 ✅ | 0.907 |
| **21** | **0.950 ← breakeven** | 0.904 |
| 25 | 0.942 | 0.889 |
| 30 | 0.932 | 0.874 |
| 40 | 0.916 | 0.848 |
| **47** (naive) | **0.905** | **0.833** |
| 50 | 0.901 | 0.827 |
| 75 | 0.872 | 0.785 |
| 100 | 0.849 | 0.754 |

✅ = clears the 0.95 bar. Full table in `reports/10_dsr_trials.csv`; chart in `reports/charts/10_dsr_vs_ntrials.png`.

**Breakeven N (largest N still clearing 0.95):**
- static full-window: **N = 21**
- walk-forward OOS: **N = 10**

## The findings

1. **The static baseline passes only at the very bottom of the honest bracket.** It clears 0.95 up to N = 21, and our effective-independent count is N = 18 (DSR 0.957). So under the most defensible (correlation-adjusted) trial count it *just* passes; under naive counting (N = 47, DSR 0.905) it *just* fails. The result is genuinely borderline — not a clean pass, not a clean fail.

2. **The walk-forward trace has a higher Sharpe but a *lower* DSR.** This is counter-intuitive and worth internalizing: the walk-forward trace reads +1.05 vs the static +1.00, yet its DSR is uniformly lower and it fails 0.95 for any N ≥ 11. The reason is sample size: `E[max Sharpe | null]` scales with `√(252 / T)`, and the walk-forward trace has only 2867 days (starts 2015) vs the static window's 3748 (starts 2011). Fewer observations → higher no-skill benchmark → harder to beat. **More-honest out-of-sample evaluation costs statistical power, and the strict DSR bar exposes that directly.**

3. **The previous N = 25 / DSR = 0.942 figure reproduces exactly** — it was inside the honest bracket but on the failing side. The earlier write-up's "N = 50 → ~0.93" was loosely rounded; the precise value is **0.901**.

## Verdict and what it means for the decision gate

| Test | Result | Reading |
|---|---|---|
| Block-bootstrap CI excludes zero (full / IS / OOS) | **PASS** (robust) | The Sharpe is not zero. |
| DSR > 0.95 at effective N (18) | **PASS** (0.957, static) | Survives multiple-testing under correlation-adjusted counting. |
| DSR > 0.95 at naive N (47) | **FAIL** (0.905, static) | Fails under the most conservative counting. |
| DSR > 0.95 on walk-forward trace | **FAIL** for N ≥ 11 | The cleanest OOS number doesn't clear the strict bar. |

**This is a YELLOW, not a GREEN.** The strategy is real in the sense that matters most for deployment — its Sharpe is reliably positive and the bootstrap CI excludes zero in every window — but it does **not** comfortably clear the strict multiple-testing bar. The honest one-line summary for an interview or a memo: *"Bootstrap-significant with CI [+0.54, +1.43]; DSR ≈ 0.91–0.96 depending on how you count the ~18–47 trials, so it sits right on the 95% multiple-testing threshold rather than clearly past it."*

The practical consequence for the roadmap: this is **not** a reason to abandon the strategy, but it **is** a reason to treat the live/paper-trading phase (Layer B) as the real out-of-sample test. Fresh, post-publication data accrues no selection bias and is the only way to push past the borderline DSR. It also argues for **not** mining further configs — every additional trial we run raises N and pushes the DSR down.

## Reproducibility

```bash
uv run python scripts/run_dsr_trials.py
```

Outputs `reports/10_dsr_trials.csv`, `reports/10_dsr_trial_ledger.csv`, and `reports/charts/10_dsr_vs_ntrials.png`. The DSR machinery is `src/statarb/evaluation/deflated_sharpe.py` (Bailey-López de Prado 2014, with skewness/kurtosis correction).
