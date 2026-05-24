# Phase A6: Sensitivity Sweeps

**TL;DR.** The headline +1.00 Sharpe survives every perturbation tested. Across leave-one-commodity-out, alternate IS/OOS splits, quantile choices, and signal-parameter lookbacks, the realized Sharpe ranges from **+0.65 to +1.27** — comfortably positive in every case. No single instrument, time period, or hyperparameter choice carries the result.

## What this tests

The strongest critique of a backtest is "you got lucky on the specifics." Sensitivity sweeps rule that out by perturbing each axis the strategy could be over-fit to and reporting the Sharpe under each perturbation. If results are clustered tightly, the strategy is robust; if a single perturbation kills the Sharpe, the result was fragile.

Five perturbation families tested, ~30 backtests total:

1. **Leave-one-out commodity** — drop each of the 13 commodities individually and re-run.
2. **Alternate IS/OOS splits** — vary the IS-end cutoff date across {2017-12-31, 2018-12-31, 2019-12-31, 2020-12-31} and report OOS Sharpe.
3. **Quantile thresholds** — vary {30%, 40%, 50%} long-quantile and short-quantile.
4. **Carry signal lookback** — vary {10, 21, 42} days.
5. **COT z-score lookback** — vary {104, 156, 208} weeks (~2/3/4 years).

## Results

### Baseline
Full-window Sharpe **+1.004** (13 commodities, carry=21d, cot=156w, quantile=40/40, cost=10bps).

### 1. Leave-one-out commodity (range [+0.83, +1.04])

| Dropped | Sharpe | Δ vs baseline |
|---|---:|---:|
| CL=F (WTI) | +1.007 | +0.003 |
| **BZ=F (Brent)** | **+0.833** | **-0.171** |
| NG=F (nat gas) | +0.896 | -0.108 |
| RB=F (gasoline) | +0.977 | -0.027 |
| HO=F (heating oil) | +0.992 | -0.012 |
| GC=F (gold) | +1.007 | +0.003 |
| **SI=F (silver)** | +0.863 | -0.141 |
| HG=F (copper) | +1.013 | +0.009 |
| PL=F (platinum) | +0.905 | -0.099 |
| **PA=F (palladium)** | +0.878 | -0.126 |
| ZC=F (corn) | +0.989 | -0.015 |
| ZW=F (wheat) | +1.035 | +0.031 |
| ZS=F (soybeans) | +1.021 | +0.017 |

**Every drop still produces Sharpe ≥ +0.83.** The three most impactful commodities (BZ, SI, PA) contribute most to the result, but no single asset drives it. Grains barely matter (dropping them moves Sharpe by ≤ 0.03).

### 2. Alternate IS/OOS splits (every OOS > full)

| Split cutoff | IS Sharpe | OOS Sharpe |
|---|---:|---:|
| 2017-12-31 | +0.899 | **+1.080** |
| 2018-12-31 | +0.909 | **+1.095** |
| 2019-12-31 | +0.855 | **+1.174** |
| 2020-12-31 | +0.827 | **+1.268** |

**Every alternate split's OOS Sharpe exceeds the full-window +1.00.** This is striking — typically OOS underperforms IS. Here, the more we hold out (later IS cutoff, less data to fit), the stronger the OOS reads. This is consistent with the strategy being un-tuned (no IS-driven parameter selection in the baseline) and the post-2019 environment being particularly good for carry.

### 3. Quantile thresholds (essentially insensitive)

| Long/short quantile | Sharpe |
|---|---:|
| 30% (4 longs + 4 shorts) | +0.999 |
| 40% (6 longs + 6 shorts) | +1.004 |
| 50% (7 longs + 7 shorts) | +1.015 |

Insensitive to the quantile choice in a meaningful range.

### 4. Carry signal lookback (wider range, 21d is reasonable)

| Carry lookback | Sharpe | Δ |
|---|---:|---:|
| 10 days | +1.189 | +0.185 |
| **21 days (baseline)** | **+1.004** | 0 |
| 42 days | +0.649 | -0.355 |

10d is the strongest reading; 42d is the weakest. The signal apparently captures faster carry dynamics better than slower ones. We deliberately do NOT switch to 10d for the headline — that would be post-hoc parameter tuning, exactly the selection bias the DSR was built to penalize. The honest read: even the worst lookback (+0.65) still produces healthy positive Sharpe.

### 5. COT z-score lookback (insensitive)

| COT z-score window | Sharpe | Δ |
|---|---:|---:|
| 104 weeks (~2y) | +1.070 | +0.066 |
| **156 weeks (~3y, baseline)** | **+1.004** | 0 |
| 208 weeks (~4y) | +1.122 | +0.118 |

All in [+1.00, +1.12]. The 3-year choice is slightly conservative but well within the stable range.

## Summary table

| Perturbation kind | Sharpe range |
|---|:---:|
| Leave-one-out commodity | [+0.833, +1.035] |
| IS/OOS split | [+1.080, +1.268] (OOS Sharpes) |
| Quantile threshold | [+0.999, +1.015] |
| Carry lookback | [+0.649, +1.189] |
| COT lookback | [+1.004, +1.122] |
| **Overall worst case** | **+0.649** |
| **Baseline** | **+1.004** |
| **Overall best case** | **+1.268** |

**Every single backtest in the sweep produces positive Sharpe.** The result is robust to perturbation in every direction tested.

## What we did NOT do (and why)

- **No hyperparameter retuning of the headline.** The carry-10d result (+1.19) is better than the baseline carry-21d (+1.00), but switching to 10d after seeing the data is post-hoc selection bias. The DSR's N=25 trial count already accounts for this kind of search.
- **No claim that 10d is "better."** The improvement could be sample noise; the wider sample variance of shorter-window signals tends to make their realized Sharpe more variable.

## Reproducibility

```bash
uv run python scripts/run_sensitivity.py
```

Outputs `reports/07_sensitivity_table.csv` with all 27 perturbations side-by-side.
