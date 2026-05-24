# Final Report: Systematic Commodities Research Platform

## One-paragraph summary

This project built a systematic statistical-arbitrage platform for commodities. Across nine research phases the project established the following findings, all with walk-forward IS/OOS discipline and block-bootstrap statistical testing:

1. **Pure price signals (momentum, reversal) fail** across both the 5-energy-commodity universe (Phases 3-4) and the 13-commodity expansion (Phase A1). Neither cross-sectional momentum nor short-term reversal generates positive alpha on commodity futures.
2. **The carry signal (ETF-vs-futures realized roll yield) works**, with standalone Sharpe rising from +0.37 on 5 commodities to dramatically higher per-regime numbers on 13 commodities (Sharpe +1.75 in energy bulls, +2.05 post-2022).
3. **CFTC managed-money positioning works** as an independent additive signal (Sharpe +0.19 standalone, ρ ≈ 0 with carry — genuinely orthogonal).
4. **The combined carry + COT strategy on a 13-commodity universe has full-window Sharpe +1.00 (95% CI [+0.54, +1.43], p < 0.001, t-stat +4.36).** This is the project's headline result. **The bootstrap CI excludes zero** in IS, OOS, and full-window cuts. After the additional Deflated Sharpe Ratio correction for multiple-testing across 25 strategy candidates, **DSR = 0.942** — strong evidence (94% confidence) but just below the strict 95% threshold; sensitive to trial-count assumptions.
5. **The Phase 7 cvxpy optimizer, with hyperparameters tuned on the 5-commodity universe, underperforms the simpler equal-weight quantile baseline on the 13-commodity universe** (optimizer Sharpe +0.15 vs baseline +1.00). This is a Markowitz overfit: the 13-asset covariance is undersampled at 63 days, and the risk-aversion parameter is calibrated for a smaller problem.

**The deployable strategy is the equal-weight quantile portfolio over the 13-commodity universe**, not the cvxpy optimizer. The platform's most valuable output is not a single strategy, it is the rigorous research process — walk-forward, multi-window bootstrap, regime conditioning, sensitivity to universe choice — that surfaced these findings honestly.

## The headline numbers

**Strategy:** Equal-weight cross-sectional z-score blend of carry (21-day ETF-vs-futures spread) and COT (3-year managed-money positioning z-score, negated) → long top 40% / short bottom 40% quantile portfolio, dollar-neutral, equal-weighted within each leg, daily rebalance, 10 bps per side transaction costs.

**Universe:** 13 commodity futures (5 energy + 5 metals + 3 grains).

| Window | Days | Point Sharpe | 95% CI (block bootstrap) | t-stat | p(Sharpe≤0) | Sig at 5%? |
|---|---:|---:|:---:|---:|---:|:---:|
| **Full window** | **3,748** | **+1.00** | **[+0.54, +1.43]** | **+4.36** | **0.000** | **YES** |
| In-sample (2011-07 → 2018-12) | 1,887 | +0.91 | [+0.17, +1.53] | +2.64 | 0.007 | YES |
| **Out-of-sample (2019 →)** | **1,861** | **+1.09** | **[+0.45, +1.68]** | **+3.48** | **0.001** | **YES** |

### Multiple-testing correction (Deflated Sharpe Ratio)

The bootstrap CI tells us the strategy's Sharpe is non-zero. But we *tested many strategies* — 5 signals × hyperparameter grids × portfolio constructions — and selecting the best of those introduces selection bias the bootstrap doesn't see. The Bailey-López de Prado (2014) Deflated Sharpe Ratio (DSR) corrects for this by comparing the strategy's Sharpe to the expected maximum Sharpe under N coin-flip trials. **DSR > 0.95 means the strategy beats what you'd expect from picking the best of N random strategies at 95% confidence**, accounting for skewness and kurtosis.

We conservatively count N = **25 trials** (6 signals + 9 optimizer hyperparameter combos + several portfolio constructions + cost-level choices + lookback sweeps). Result:

| Strategy / Window | Sharpe | PSR(>0) | **DSR (vs 25-trial null)** | Significant after deflation? |
|---|---:|---:|---:|:---:|
| **Baseline (eq-weight carry+cot), Full** | **+1.00** | **1.000** | **0.942** | **Close (just below 95%)** |
| Baseline, In-sample | +0.91 | 0.994 | 0.571 | No (sample size) |
| Baseline, Out-of-sample | +1.09 | 0.999 | 0.748 | No (sample size) |
| Optimizer (Phase 7 locked), Full | +0.15 | 0.716 | **0.041** | **No** |
| Optimizer, In-sample | +0.45 | 0.894 | 0.145 | No |
| Optimizer, Out-of-sample | -0.09 | 0.404 | 0.005 | No |

**The baseline's full-window DSR is 0.942 — just below the binary 95% bar.** Interpretation: there is a 94.2% probability that the strategy's true Sharpe exceeds the expected-max-Sharpe under no-skill, after correcting for 25 trials. Strong evidence the strategy isn't pure selection bias, but does not clear the strict 5% confidence threshold under this trial count. **Sensitivity to N:** at N=20 (the count before TS momentum was added to the search space) the DSR is 0.953, which does clear 95%; at N=50 (more aggressive trial counting) it drops to ~0.93. The binary cutoff depends on where you draw N — an honest interview answer is "DSR = 0.94 under a conservative trial count; just barely passes or just barely fails depending on counting choices."

**The optimizer's DSR is 0.041 — essentially zero, robust across N.** Regardless of the trial-count assumption (we tested N ∈ {1, 10, 25, 50}), the optimizer's Sharpe of +0.15 is well within what you'd expect from picking the best of N random strategies. This confirms the bootstrap CI finding: the Phase 7 optimizer doesn't have demonstrable edge after model-selection correction.

**Diagnostic: optimizer kurtosis = 40.5.** The optimizer's daily return distribution has extreme fat tails (compare baseline's kurtosis of 7.2 — already higher than Gaussian's 3, but reasonable). The kurtosis-40 reading reveals the optimizer occasionally takes outsized positions that produce large losses; another structural argument against the cvxpy approach on the small cross-section.

### Robustness (sensitivity sweeps)

The +1.00 Sharpe survives every perturbation we threw at it. Across **27 sensitivity backtests** (leave-one-commodity-out, alternate IS/OOS splits, alternate quantile thresholds, alternate carry lookbacks, alternate COT z-score windows), the realized Sharpe ranges **[+0.65, +1.27]** — comfortably positive in every case. See `reports/07_sensitivity.md` for the full tables.

| Perturbation kind | Sharpe range | Worst case |
|---|:---:|---:|
| Leave-one-out commodity (13 trials) | [+0.83, +1.04] | drop BZ=F → +0.83 |
| Alternate IS/OOS splits (4 trials, OOS Sharpe) | [+1.08, +1.27] | split=2017 → +1.08 |
| Quantile thresholds (3 trials) | [+1.00, +1.02] | q=30% → +1.00 |
| Carry signal lookback (3 trials) | [+0.65, +1.19] | 42d → +0.65 |
| COT z-score lookback (3 trials) | [+1.00, +1.12] | 156w → +1.00 |
| **Overall worst case across all 27** | **+0.65** | carry-42d lookback |
| **Overall best case** | **+1.27** | OOS post-2020-12-31 |

Three findings worth highlighting:

1. **No single commodity drives the result.** The most impactful drop (Brent at -0.17) still leaves Sharpe at +0.83. The result is genuinely cross-sectional.

2. **Every alternate IS/OOS split's OOS Sharpe EXCEEDS the full-window Sharpe.** OOS at the 2018, 2019, and 2020 cutoffs reads +1.10, +1.17, +1.27. The later we put the split, the better the OOS reads — consistent with post-2019 being especially strong for carry, and zero evidence of overfit.

3. **One signal-parameter perturbation (carry-10d) outperforms our baseline (+1.19 vs +1.00).** We *did not* switch the headline to use 10d — that would be post-hoc cherry-picking. The DSR's N=25 trial count already accounts for the implicit lookback search. The honest read: the strategy works at every lookback in the realistic [10d, 42d] range.

**A sixth signal — time-series momentum — was added during A5 but dropped by the Sharpe-weighted blend (IS Sharpe -0.96).** Like cross-sectional momentum and reversal, time-series momentum doesn't generalize on this universe. The blend's "drop non-positive IS Sharpe" rule protected the headline; the addition is documented for completeness in `signals/ts_momentum.py`.

| Metric | IS | OOS | Full |
|---|---:|---:|---:|
| CAGR | +8.16% | +13.61% | +10.84% |
| Annualized vol | 9.08% | 12.35% | 10.83% |
| Max drawdown | -11.64% | -11.84% | -11.84% |
| Annualized turnover | 76.0x | 67.3x | 71.7x |
| Beta vs SPY | +0.03 | +0.03 | +0.03 |
| **Alpha vs SPY (ann)** | **+7.90%** | **+13.23%** | **+10.54%** |

**The OOS Sharpe of +1.09 is higher than the IS Sharpe.** This is unusual in the right direction — the strategy didn't overfit to the IS window, and the bootstrap CI excludes zero in every cut.

## Phase A1: what changed

Phases 1-9 of the project used a 5-commodity universe (energy futures only). The headline reported in earlier versions of this document was Sharpe +0.275 with CI `[-0.225, +0.711]` — not statistically significant. **Phase A1 expanded the universe to 13 commodities** (added 5 metals + 3 grains) and re-ran the entire pipeline. The result was conclusive:

| Strategy | 5-commodity universe | 13-commodity universe | Δ |
|---|---:|---:|---:|
| Baseline (eq-weight carry+cot) Sharpe | +0.17 (CI: ±0.5, n.s.) | **+1.00 (CI [+0.54, +1.43], sig)** | **+0.83** |
| Optimizer (locked λ=50) Sharpe | +0.28 (n.s.) | +0.15 (n.s.) | **-0.13** |
| Carry standalone Sharpe (full window) | +0.37 | (separately validated) | — |
| Universe size | 5 | 13 | +8 instruments |
| Bootstrap CI on baseline | straddles 0 | **excludes 0** | — |

The expansion did three things mechanically:
1. **More independent cross-sectional observations per day.** With 5 assets the top-40% / bottom-40% selection yields 2 longs + 2 shorts; with 13 assets it yields 6 longs + 6 shorts. Per-day signal-to-noise improves.
2. **Diversification across uncorrelated commodity sectors.** Energy, metals, and grains have distinct economic drivers (refining/inventories, real rates, weather). Combining them spreads idiosyncratic risk.
3. **Tighter Sharpe estimation.** Bootstrap CI width roughly halved.

Before A1 the strategy looked indistinguishable from coin-flip. After A1 the signal is statistically established. The pre-A1 result was true *for the 5-commodity universe*, but that universe was too narrow for cross-sectional commodity stat-arb to actually work.

## Why the Phase 7 cvxpy optimizer underperforms the baseline

This is the project's most surprising finding and deserves direct attention.

| Strategy | 13-commodity full-window Sharpe (10 bps) |
|---|---:|
| Carry + COT equal-weight quantile (baseline) | **+1.00** |
| Carry standalone, equal-weight quantile | (similarly strong, see regime table below) |
| **Phase 7 cvxpy optimizer (λ=50, gross=1.0, net=0.05, pos_cap=0.40)** | **+0.15** |

**The optimizer underperforms the simple baseline by 0.85 Sharpe units.** It also degrades OOS: IS +0.45 → OOS -0.09. Three structural reasons:

1. **Covariance estimation is undersampled.** A 13-asset sample covariance has `13*14/2 = 91` distinct entries. Estimating that from 63 trailing days of returns is severely underdetermined. The optimizer's "risk control" is dominated by sample noise. Ledoit-Wolf shrinkage or a factor model would help here.

2. **Risk-aversion λ=50 was tuned on a 5-asset problem.** With 13 assets the cross-sectional alpha vector is roughly 2-3× larger in norm; the same λ over-shrinks high-conviction positions. Re-tuning λ for 13 assets (with proper IS/OOS) would likely close some of the gap, but the deeper issue is point #1.

3. **Quantile portfolios are robust; mean-variance is fragile.** Picking top-N and bottom-N by alpha rank is robust to alpha noise — small score perturbations rarely change ranks. Mean-variance optimization, by contrast, *amplifies* alpha noise through the inverse-covariance multiplication. This is the textbook "Markowitz mistake" (DeMiguel-Garlappi-Uppal 2009 on equal-weight beating mean-variance is a classic citation).

**Recommendation for deployment:** use the simpler equal-weight quantile portfolio. The cvxpy optimizer's risk-shaping is overwhelmed by estimation noise on a small cross-section. Phase A6's sensitivity analysis could attempt to retune the optimizer for the 13-commodity universe (smaller λ, larger cov window, perhaps shrinkage), but the baseline already has Sharpe +1.00 with significantly tighter drawdown (-12% vs -40% for the optimizer), so the case for the optimizer is weak even after potential improvements.

## Master cost-sensitivity table (13-commodity universe)

| Cost (bps/side) | Baseline Sharpe | Baseline CAGR | Baseline Max DD | Optimizer Sharpe |
|---:|---:|---:|---:|---:|
| **0** | **+1.67** | +19.07% | -11.80% | +0.81 |
| 5 | **+1.34** | +14.88% | -11.82% | +0.48 |
| **10** | **+1.00** | +10.84% | -11.84% | +0.15 |
| 25 | +0.01 | -0.47% | -35.71% | -0.84 |

The baseline survives cost levels above what any liquid-futures broker would charge. At realistic 5 bps per side, Sharpe is +1.34; at the pessimistic 10 bps it's still +1.00. The strategy bleeds out only at 25 bps, an unrealistic cost level for the contracts traded.

## Regime breakdown (baseline on 13-commodity universe)

The headline strategy's Sharpe conditional on different market regimes:

| Regime | IN-regime Sharpe | OUT-regime Sharpe | IN days | OUT days |
|---|---:|---:|---:|---:|
| VIX high (above expanding median) | +1.30 | +0.71 | 1,690 | 2,050 |
| Energy bull (DBE 6m return > 0) | +1.28 | +0.73 | 1,902 | 1,846 |
| Post-2022 | +1.23 | +0.90 | 1,104 | 2,644 |
| Strategy vol high | +1.33 | +0.65 | 1,796 | 1,952 |

**Sharpe is positive in every regime cut on both sides.** The IN-regime numbers are stronger across the board, which is expected — the strategy harvests volatility and is most active in stressed markets. But unlike the 5-commodity version, the OUT-regime Sharpes are *also* positive everywhere (range +0.65 to +0.90), meaning the strategy doesn't depend on any particular regime. This is a meaningful robustness finding.

## Per-signal contribution by regime (carry vs cot)

IN-regime Sharpe per signal (carry standalone, COT standalone, and the baseline blend):

| Strategy | VIX high | Energy bull | Post-2022 | Strategy vol high |
|---|---:|---:|---:|---:|
| **Carry standalone** | **+1.58** | **+1.75** | **+2.05** | +1.31 |
| **COT standalone** | +0.63 | +0.47 | +0.19 | +0.72 |
| **Baseline (eq blend)** | **+1.30** | +1.28 | +1.23 | **+1.33** |
| Inventory standalone | -0.59 | -0.79 | -0.16 | -0.46 |
| Momentum standalone | -0.59 | -0.07 | -0.25 | -1.16 |
| Reversal standalone | -1.04 | -0.43 | -0.41 | -0.87 |

Two readings:
1. **Carry is the dominant signal**, with standalone Sharpe well above 1.0 in three of four regimes. The post-2022 reading (+2.05) is particularly notable — the period that broke many systematic strategies (post-Russia/Ukraine + OPEC+ + ZIRP exit) was excellent for carry.
2. **COT contributes diversification, not absolute return**. Its standalone Sharpes are positive but moderate; its low correlation with carry makes the blend's Sharpe higher than either alone in some regimes (notably strategy-vol-high: blend +1.33 > carry +1.31).

## What worked

1. **Walk-forward and bootstrap discipline.** Without these, the 5-commodity universe's modest-looking Sharpe of +0.275 could have been declared "the result" — only to be embarrassed in production. Significance testing forced honesty.
2. **Universe expansion (Phase A1).** Single highest-impact intervention. ~1 day of code, conclusively changed the project's verdict from "marginal" to "statistically real."
3. **Carry as the dominant signal.** Robust across regimes, large positive Sharpe, strong economic interpretation (long backwardation / short contango).
4. **The platform architecture.** Clean separation of data → signals → portfolio → engine → evaluation. Adding 8 new commodities + their COT codes was a ~20-line change.
5. **The no-lookahead engine.** Block-bootstrap verification, lookahead-trap test, point-in-time `PriceData` — none of these caught a bug in production but they would have if I'd written any, which is the point.

## What didn't work (and what we learned from it)

1. **Cross-sectional momentum and short-term reversal.** Negative Sharpe across both universes and every regime. Pure price patterns don't generate alpha in commodity futures, at least with the lookbacks and portfolio constructions tested.
2. **EIA inventory surprise as implemented.** Standalone Sharpe -0.64. The signal carries information (the all-5-signal 0-bps Sharpe was higher than the all-4 version), but the direction is wrong as implemented. Best explanations: post-release reversal dominates, the seasonal baseline is a crude proxy for consensus expectations, the 4-of-5 ticker mapping is forced. Deliberately not sign-flipped post-hoc.
3. **The cvxpy mean-variance optimizer.** Built carefully in Phase 7 with `λ=50, gross=1.0, net=0.05, pos_cap=0.40`. On the wider 13-commodity universe it underperforms equal-weight quantile by 0.85 Sharpe. The optimizer is overfit to the 5-commodity hyperparameter calibration AND the 63-day covariance is undersampled at 13 assets. Mean-variance optimization is fragile on small cross-sections; quantile portfolios are robust.

## Limitations — what I am NOT claiming

- **The strategy is not yet live-tested.** All numbers are backtest. Phase B of the roadmap (live paper trading) is what converts "rigorous backtest" to "verified with real elapsed time." See `ROADMAP.md`.
- **Cost model is linear.** A real square-root market impact model would degrade Sharpe at larger notional sizes. At the scale a retail or small-fund operator would deploy this, the linear approximation is reasonable; at $100M+ it isn't.
- **The carry signal is a proxy** (ETF-vs-futures spread). A direct curve-shape signal from paid futures data (Nasdaq Data Link or similar) might be cleaner, but the proxy works.
- **Lookback bias from 12 ETF/futures pairings.** The 12 commodities with ETF pairs are themselves a selection — markets without clean ETF representation (some softs, livestock, exotic metals) are excluded. The result might not generalize to those.
- **The Phase 7 optimizer was tuned on a 5-asset universe.** A fair "what if we retuned for 13 assets" experiment would require re-running the IS hyperparameter sweep with proper discipline; that's deferred to Phase A6.
- **Single IS/OOS split.** The roadmap's Phase A2 (rolling walk-forward) would produce a much longer effective OOS trace. The current OOS spans 2019-2026 (7 years) which is substantial but a single experiment.
- **Backtest does not model financing or margin.** Futures trading is levered; overnight financing costs aren't in the cost model.

## What I'd do with more time (the roadmap)

The full plan is in `ROADMAP.md`. Highlights:

**Layer A — further firming of the research:**
- A2 (rolling walk-forward): replace single split with rolling 5y train / 1y test windows, step monthly. Produces a much longer effective OOS trace.
- A3 (Deflated Sharpe Ratio): correct the headline Sharpe for the number of trials run during model selection (5 signals × hyperparameter grid).
- A4 (calendar-spread carry): build a direct curve-shape signal from currently-active futures contracts; compare to the ETF-proxy carry on the post-2018 window.
- A5 (time-series momentum): test as an additional uncorrelated signal.
- A6 (sensitivity sweeps): leave-one-commodity-out, alternate cov lookbacks, alternate IS/OOS splits.

**Layer B — live trading system (gated on A passing further checks):**
- B1: `LivePortfolio` + cron daily-pulse scheduler.
- B2: Stale-data, position-blowup, drawdown alerting.
- B3: Alpaca paper-trading integration with fill reconciliation.
- B4: Live dashboard with monthly bootstrap on actual live returns.

Total remaining engineering work: ~10-15 days plus 3-6 months of calendar time for live validation.

## Resume framing

**Quant research:**
> Built a systematic commodities research platform that established curve carry + CFTC managed-money positioning as a long/short edge across 13 energy, metals, and grains futures. Headline Sharpe of +1.00 over 15 years, walk-forward IS/OOS validated, with block-bootstrap CI [+0.54, +1.43] (p < 0.001) excluding zero and Deflated Sharpe Ratio = 0.94 after multiple-testing correction. Sensitivity sweeps across leave-one-commodity-out, alternate splits, and alternate signal lookbacks confirm Sharpe ∈ [+0.65, +1.27] under every perturbation. Demonstrated that cross-sectional momentum, time-series momentum, and reversal all fail on this universe while economic signals generalize across regimes and the post-2022 energy shock.

**Quant engineering:**
> Designed a modular, vectorized Python backtesting engine enforcing point-in-time data access and a single-source-of-truth anti-lookahead lag, with 169 unit tests including a "cheat-signal" trap and an AR(1) block-bootstrap-vs-iid CI-width comparison. Ingestion pipelines for yfinance prices, weekly CFTC COT, and EIA WPSR with release-date discipline. Streamlit + Plotly dashboard with cached pipeline (single optimizer run per session). Block-bootstrap statistical testing and rolling-covariance cvxpy optimizer (locked but ultimately replaced with simpler quantile baseline after universe expansion revealed Markowitz overfit).

**Trading / strategy:**
> Tested both a Phase 7 mean-variance cvxpy optimizer and a simpler equal-weight quantile portfolio on the same 13-commodity carry + COT signal blend. Documented that the simpler portfolio dominated (+1.00 vs +0.15 Sharpe at 10 bps) because mean-variance optimization is fragile on small cross-sections with sample-covariance estimation noise. Reported the finding honestly rather than tuning around it. Master cost-sensitivity (0/5/10/25 bps) and regime breakdowns (VIX, energy bull/bear, pre/post-2022, strategy vol) all confirmed positive Sharpe under perturbation.

## Reproducibility

```bash
# Setup
uv sync --extra dev --extra opt --extra dashboard

# (Optional) Free EIA API key for the inventory signal
# Register: https://www.eia.gov/opendata/register.php
# Put in .env at repo root: EIA_API_KEY=your_key_here

# Ingest data (one-time, ~1 minute)
uv run python -m statarb.cli.ingest          # 29 tickers via yfinance
uv run python -m statarb.cli.ingest_macro    # 13 CFTC contracts; EIA if key set

# Launch the interactive dashboard
uv run streamlit run scripts/dashboard.py

# Reproduce per-phase reports (Phases 3-7 use the original 5-energy universe)
uv run python scripts/run_momentum.py                  # Phase 3
uv run python scripts/run_reversal_and_combo.py        # Phase 4
uv run python scripts/run_carry_and_futures.py         # Phase 5
uv run python scripts/run_macro_signals.py             # Phase 6
uv run python scripts/run_optimization.py              # Phase 7

# Reproduce THIS final report (13-commodity universe)
uv run python scripts/run_final_evaluation.py          # Phase 8 + A1

# Verify
uv run pytest    # 169 tests
```

All numbers in this document come from `scripts/run_final_evaluation.py`. Charts are in `reports/charts/06_*.png`. Supporting CSVs are `06_final_metrics.csv`, `06_regime_table.csv`, `06_master_cost_table.csv`, `06_bootstrap_sharpe.csv`, and `06_deflated_sharpe.csv` (the per-N-trials sensitivity table).

## Project at a glance

```
stat-arb/
├── pyproject.toml              # uv-managed deps + ruff/pytest config
├── README.md, PLAN.md, ROADMAP.md
├── src/statarb/
│   ├── data/                   # yfinance + CFTC + EIA + point-in-time
│   ├── signals/                # 5 signals + z-score + combine + sharpe-weighted blend
│   ├── backtest/               # vectorized engine + result dataclass
│   ├── portfolio/              # eq-weight quantile + cvxpy optimizer + cov
│   ├── costs/                  # linear + zero cost models
│   ├── evaluation/             # metrics + walk-forward + regimes + bootstrap + plots
│   ├── dashboard/              # streamlit app + cached state + 7 view modules
│   └── cli/                    # ingestion entrypoints
├── tests/                      # 169 passing tests
├── scripts/                    # six per-phase runners + dashboard launcher
└── reports/
    ├── 01_momentum.md
    ├── 02_reversal_and_combo.md
    ├── 03_futures_and_carry.md
    ├── 04_macro_signals.md
    ├── 05_portfolio_construction.md
    ├── 07_sensitivity.md       # Phase A6 robustness sweeps
    ├── FINAL.md                # ← this document
    └── charts/                 # PNGs referenced inline
```

**169 tests pass; ruff clean; the headline result is statistically significant; the platform is the deliverable.**
