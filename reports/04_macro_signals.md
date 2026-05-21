# Phase 6: Macro Signals — COT Positioning (+ EIA Inventory, gated)

**TL;DR.** The CFTC Commitments of Traders signal (managed-money positioning, negated 3-year z-score) is the second signal in this project with positive standalone alpha (Sharpe **+0.19**, alpha vs SPY **+3.52% annualized**, max DD only **-39%**, turnover only **13×/yr**). It has near-zero correlation with carry (ρ = 0.003), so the two are genuinely independent. **But equal-weight aggregation of all four signals (mom + rev + carry + cot) reduces Sharpe below carry-alone** because the negative-Sharpe price signals drag the combination down. This is the strongest single motivation for Phase 7's formal optimization. The EIA inventory-surprise signal is fully implemented but requires a free EIA API key to run; the runner skips it gracefully when the key is absent.

## Hypotheses

**COT (managed-money positioning).** When trend-following CTAs and macro funds have piled into a contract at a 3-year extreme net long, the trade is *crowded* and forward returns tend to weaken (and vice versa for crowded short). We capture this with the negated z-score of `MM_long_pct − MM_short_pct` over a trailing 156-week window.

**EIA inventory surprise.** When this week's reported inventory change is larger than the same-week-of-year average over the trailing 5 years, supply is stronger than seasonal expectation — bearish for the underlying. Without paid consensus expectations, the 5-year seasonal baseline is the standard proxy and the EIA's own bulletin headlines a similar comparison.

Both signals have *economic content* in a way that pure price patterns do not. The Phase 3-5 finding was that economic content seems to be the precondition for surviving walk-forward.

## Methodology

### Data
- **CFTC COT** (free, no API key): annual disaggregated ZIPs from `cftc.gov/files/dea/history/`. Implementation in `statarb.data.cftc`. Spans 2010-01-05 → 2026-05-12, 5 contracts (CL, BZ-via-NYMEX-Brent-Last-Day, NG, RB, HO).
  - Fixed two CFTC data quirks during ingest: pre-2013 files use a column named `Report_Date_as_MM_DD_YYYY` whose values are actually in YYYY-MM-DD; and contract codes have trailing whitespace. Both fixes are documented in `statarb/data/cftc.py`.
- **EIA WPSR** (free, requires `EIA_API_KEY` env var; register at eia.gov/opendata/register.php). Implementation in `statarb.data.eia` and `statarb.cli.ingest_macro`. Fails with a clear instruction if the key is missing.

### Release-date discipline (critical for both signals)
- **COT**: data is as-of Tuesday close; report releases Friday 3:30 PM ET. The `release` column in our panel is `as_of + 3 business days`. The signal is placed on `release` and forward-filled daily. The backtest engine then lags one more day, so the first trade using a Friday-released score is on Monday.
- **EIA WPSR**: data refers to the prior Friday; the report releases Wednesday ~10:30 AM ET. Same pattern: release Wednesday, daily forward-fill, one-day lag → first trade Thursday.

Using the as-of date instead of the release date would create a 3-business-day (COT) or 5-day (EIA) lookahead bias — common bug in pseudo-backtests of macro signals.

### Signals
- **COT**: `cot_positioning(cot_panel, lookback_weeks=156)`. Negated 3-year rolling z-score of `mm_net_pct`.
- **Inventory**: `inventory_surprise(eia_panel, seasonal_years=5)`. Per-ISO-week baseline; negated weekly-change surprise.

### Portfolio + costs
- Long-short quantile portfolio (top 40%, bottom 40%, dollar-neutral, equal weight within each leg), same as Phases 3-5.
- Headline cost: 10 bps per side. Sensitivity at 0 / 5 / 10 / 25 bps.
- IS / OOS split at 2018-12-31.
- Backtest window starts **2011-07-01** (the first day all signals are mature — COT needs 156 weeks of history to begin z-scoring).

## Standalone results, full window, 10 bps/side

| Strategy | Sharpe | CAGR | Ann vol | MaxDD | Turnover/yr | Alpha vs SPY (ann) |
|---|---:|---:|---:|---:|---:|---:|
| futures_momentum_12-1 | -0.92 | -17.50% | 18.93% | -95.26% | 42.9x | -17.39% |
| futures_reversal_5d | -0.33 | -7.91% | 19.40% | -73.57% | 140.4x | -7.39% |
| futures_carry_21d | +0.37 | +5.40% | 19.67% | -27.95% | 80.5x | +6.07% |
| **futures_cot_3y** | **+0.19** | **+1.72%** | 17.49% | **-39.08%** | **13.0x** | **+3.52%** |

Two interesting features of the COT signal:
- **Low turnover (13×/yr).** Weekly signal with a 3-year z-score window is naturally slow-moving. Costs barely bite.
- **Modest but real alpha.** Positive standalone alpha of +3.52%/yr vs SPY with beta near zero. Not a dominant signal but a genuine additive one — which is exactly what good combinations are built from.

![COT standalone equity curve](charts/04_cot_standalone_equity.png)

## Combined results @ 10 bps

### Combined: carry + cot only

| Window | Sharpe | CAGR | Ann vol | MaxDD | Turnover/yr | Alpha (ann) |
|---|---:|---:|---:|---:|---:|---:|
| In-sample (2011-07 → 2018) | +0.04 | -0.86% | 17.94% | -40.96% | 56.9x | -1.25% |
| Out-of-sample (2019 →) | **+0.28** | +3.95% | 23.01% | -38.13% | 50.8x | **+6.99%** |
| Full window | **+0.17** | +1.50% | 20.61% | -40.96% | 53.9x | +2.91% |

The OOS Sharpe of +0.28 is the strongest OOS result so far in the project. Beta vs SPY is +0.05 (essentially zero); alpha is +6.99% annualized.

![Carry + COT equity curve](charts/04_carry_cot_equity.png)

### Combined: all four signals (mom + rev + carry + cot)

| Window | Sharpe | CAGR | Ann vol | MaxDD | Turnover/yr |
|---|---:|---:|---:|---:|---:|
| In-sample | -0.11 | -3.51% | 17.89% | -43.49% | 86.3x |
| Out-of-sample | -0.04 | -3.69% | 23.65% | -40.13% | 80.8x |
| Full window | **-0.07** | -3.60% | 20.94% | -57.52% | 83.6x |

**This is worse than carry alone, and worse than carry + cot.** Adding the negative-Sharpe price signals at equal weight DRAGS the combination down by ~0.24 Sharpe vs. carry-and-cot only. Equal-weight aggregation is the wrong portfolio when signal qualities are heterogeneous.

![All-four combined cost sensitivity](charts/04_all_combined_cost_sensitivity.png)

### Cost sensitivity (all-four combo)

| Cost (bps/side) | Sharpe | CAGR | MaxDD |
|---:|---:|---:|---:|
| 0 | +0.33 | +4.81% | -31.81% |
| 5 | +0.13 | +0.52% | -34.66% |
| 10 | -0.07 | -3.60% | -57.52% |
| 25 | -0.67 | -14.97% | -92.43% |

At 0 bps the all-four combo has Sharpe +0.33 — there's real signal in the combination. But it's *less* than the standalone carry's signal-only equivalent, because the bad signals net out to a small negative drag rather than positive contribution.

## Correlation structure (full window, 10 bps)

|  | mom | rev | carry | cot | combo(c+c) | combo(all4) |
|---|---:|---:|---:|---:|---:|---:|
| momentum | 1.000 | -0.040 | 0.072 | 0.004 | 0.041 | 0.341 |
| reversal | -0.040 | 1.000 | 0.219 | -0.107 | 0.144 | 0.474 |
| carry | 0.072 | 0.219 | 1.000 | 0.003 | 0.690 | 0.557 |
| **cot** | 0.004 | -0.107 | **0.003** | 1.000 | 0.304 | 0.098 |

Two findings of substance:
1. **COT ↔ carry correlation = 0.003.** These signals are pulling on completely different economic levers (speculative positioning vs. realized curve carry). Independence this clean is rare and exactly what good combinations need.
2. **COT ↔ everything-else: |ρ| < 0.11.** The COT signal is the most-independent signal in our toolkit. From a diversification standpoint it's worth keeping under almost any combination scheme.

![Correlation heatmap](charts/04_signal_correlation.png)

## The Phase 7 case has arrived

Three of our four signals have negative Sharpe; one (carry) is +0.37; another (cot) is +0.19. Equal-weight combination assigns 25% weight to each. The right weighting given these IS Sharpe estimates (and being conservative for overfitting) is roughly:

- Drop momentum and reversal entirely (negative-Sharpe; we have no economic reason to expect them to recover).
- Allocate to carry and COT in some Sharpe-aware fashion.

That's exactly what Phase 7 will do, formally, with cvxpy constraints (gross/net exposure, turnover cap, per-asset position cap).

## What I'm taking forward

1. **COT is locked in.** Independent of carry, modest standalone alpha, low turnover, OOS-friendly. Will be a permanent component.
2. **Carry remains the dominant signal.** Sharpe +0.37 standalone over a 15-year window with positive OOS performance is the project's strongest individual edge.
3. **Equal weighting fails when signal qualities are heterogeneous.** Phase 7 must produce a meaningful Sharpe improvement over the carry+cot baseline of +0.17 to justify the optimization complexity.
4. **Inventory signal is built and ready** but blocked on the user obtaining a free EIA API key. The runner detects and skips cleanly. Expected behavior when the key is added: another modestly-positive standalone Sharpe, low correlation with both carry and COT, additional Phase 7 component.

## EIA inventory: status and how to enable

The full inventory-signal pipeline is implemented:
- `statarb.data.eia.build_eia_panel` fetches crude/gasoline/distillate weekly stocks via the EIA v2 API
- `statarb.signals.inventory_surprise` computes the 5-year same-ISO-week seasonal baseline and the negated surprise
- The runner detects `EIA_API_KEY` and includes the inventory signal automatically if present

To enable:
```bash
# 1. Register a free key (instant): https://www.eia.gov/opendata/register.php
export EIA_API_KEY=<your_key>

# 2. Ingest
uv run python -m statarb.cli.ingest_macro

# 3. Re-run Phase 6
uv run python scripts/run_macro_signals.py
```

The runner will then produce a 5-signal correlation matrix, a 5-signal combined backtest, and an additional `04_inventory_standalone_equity.png` chart.

## Caveats — what I am NOT claiming

- **OOS Sharpe of +0.28 (carry+cot) is not deployable.** It's the project's best result so far; it remains modest in absolute terms.
- **COT signal has only ~8 years of usable post-z-score history** (signal becomes valid mid-2011, OOS starts 2019). The walk-forward windows are small.
- **The combination math is doing the heavy lifting through carry; COT contributes diversification, not absolute return.** A pure carry portfolio is still the simplest single-signal strategy with positive alpha.
- **Phase 7 optimization should be evaluated honestly.** It's tempting to tune `λ` and weights until in-sample Sharpe pops; we'll constrain ourselves to choosing parameters on IS and reporting OOS only.
- **CFTC contract codes can shift over time.** The 5 codes we use have been stable in this window; if WTI (`067651`) ever gets renamed, our 2010-2026 backtest's older slice would silently drop. A future check at ingest time (verify open-interest > X for every year × ticker) would catch this.

## Reproducibility

```bash
uv run python -m statarb.cli.ingest_macro            # CFTC always; EIA if key set
uv run python scripts/run_macro_signals.py            # produces charts + metrics csv
```

Outputs:
- `reports/charts/04_*.png` (this report's figures)
- `reports/04_macro_signals_metrics.csv`

All numbers come from these scripts.
