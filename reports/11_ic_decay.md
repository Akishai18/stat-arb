# Phase A3 (research-firming): Information Coefficient + Signal Decay

> _Snapshot: numbers computed by `scripts/run_ic_analysis.py`. OOS data accumulates daily, so point estimates may drift slightly on re-run; the qualitative reading is stable._

**TL;DR.** The DSR (A-2) and bootstrap say the *portfolio* has edge. This phase asks the question one rung down: do the *individual signals* actually predict cross-sectional forward returns, and over what horizon? The honest answer is **weak-but-coherent, not strong**. No single signal clears a |t| ≥ 2 information coefficient in the direction it is traded. COT is the standout: a small, consistently-positive IC that *rises* with horizon (peak IC-IR +0.124 at 63d) on an extremely persistent signal (rank autocorrelation 0.75 at 21d) — the textbook profile of a slow positioning factor. Carry's cross-sectional IC is essentially zero at every horizon despite its contribution to a profitable book. The only statistically-significant IC in the whole panel is **ts_momentum at 21d, and it is *negative* (t = −2.18)** — i.e. cross-sectionally contrarian, which is exactly why it was correctly *excluded* from the survivor set. **Verdict: this is consistent with the YELLOW from A-2.** The edge is real but thin; it lives more in the carry+COT *combination* and the tails the quantile book actually trades than in a strong monotone ranking of any one signal.

## Why this matters

A profitable backtest can come from three places: (1) genuine cross-sectional prediction, (2) a lucky construction that happens to exploit noise, or (3) the diversification of combining mediocre signals. The IC is the standard tool (Grinold-Kahn) for separating (1) from (2)/(3): it measures, day by day, whether the signal's *ranking* of the universe lines up with realized forward returns. A signal with a real IC that decays slowly justifies a low rebalance frequency; one with zero IC is just noise that the portfolio construction is monetising indirectly. Pairing IC (does it predict?) with rank autocorrelation (how fast does the ranking change?) tells us both *whether* there is signal and *what holding period* it implies.

## Method (lookahead-free, mirrors the backtester)

- **IC_t(h)** = cross-sectional Spearman rank correlation between the signal **known at t−1** (lagged one day, exactly as the backtester trades it) and the realized **h-day forward return** from t to t+h. Signal uses data ≤ t−1; return uses prices ≥ t. No lookahead.
- Aggregated to **mean IC**, **IC-IR** (mean/std), and an **overlap-adjusted t-stat**. The overlap correction matters: h-day forward returns on consecutive days share h−1 days of data, so the daily IC series is autocorrelated. We deflate the effective sample size to `n_eff = n_days / h` for an honest t-stat — without this, long-horizon t-stats would be wildly overstated.
- **Persistence** = mean cross-sectional rank autocorrelation at lags {1, 5, 21, 63}: how similar today's ranking is to the ranking `lag` days ago. ≈1 ⇒ very persistent (slow signal); ≈0 ⇒ the ranking has fully refreshed.

## Information coefficient (signal vs h-day forward return)

| Signal | h=1d | h=5d | h=21d | h=63d | peak IC-IR | reading |
|---|---:|---:|---:|---:|---|---|
| **carry** | +0.006 (t+0.98) | +0.008 (t+0.60) | −0.012 (t−0.46) | −0.008 (t−0.17) | −0.034 @21d | ≈ zero everywhere |
| **cot** | +0.010 (t+1.77) | +0.012 (t+1.03) | +0.035 (t+1.43) | +0.042 (t+0.95) | **+0.124 @63d** | right sign, rises with horizon |
| inventory | −0.008 (t−0.79) | −0.008 (t−0.34) | −0.013 (t−0.29) | −0.012 (t−0.16) | −0.021 @21d | ≈ zero |
| ts_momentum | −0.003 (t−0.42) | −0.025 (t−1.69) | **−0.065 (t−2.18\*)** | −0.085 (t−1.58) | −0.206 @63d | **significant & contrarian** |
| momentum | +0.009 (t+1.35) | −0.000 (t−0.02) | −0.018 (t−0.57) | −0.013 (t−0.23) | −0.043 @21d | ≈ zero |
| reversal | −0.007 (t−1.17) | +0.007 (t+0.46) | +0.019 (t+0.66) | +0.035 (t+0.69) | +0.090 @63d | weak, noisy |

`*` = |overlap-adjusted t| ≥ 2.0. Values are mean cross-sectional Spearman IC; t-stats are overlap-adjusted (n_eff = n_days/h). Full table in `reports/11_ic_analysis.csv`; chart `reports/charts/11_ic_by_horizon.png`.

## Signal persistence (cross-sectional rank autocorrelation)

| Signal | lag 1d | lag 5d | lag 21d | lag 63d | implied holding period |
|---|---:|---:|---:|---:|---|
| carry | 0.721 | 0.569 | 0.126 | 0.116 | ~1–2 weeks (fast) |
| **cot** | **0.985** | **0.927** | **0.750** | **0.490** | **~2–3 months (slow)** |
| inventory | 0.807 | 0.066 | 0.033 | −0.048 | ~days (spiky) |
| ts_momentum | 0.969 | 0.902 | 0.707 | 0.342 | ~months |
| momentum | 0.978 | 0.935 | 0.818 | 0.608 | ~months |
| reversal | 0.709 | −0.008 | 0.004 | −0.010 | ~days (fast) |

Full table in `reports/11_signal_autocorr.csv`; chart `reports/charts/11_signal_decay.png`.

## The findings

1. **COT is the most legitimate single signal — and the IC and persistence agree.** Its IC is small but consistently positive and *grows monotonically with horizon* (+0.010 → +0.042 IC-IR +0.029 → +0.124), and the ranking is extremely persistent (autocorr still 0.75 at 21d, 0.49 at 63d). These are two independent measurements telling the same story: managed-money positioning is a *slow* factor whose information accrues over weeks-to-months. That is precisely what you'd expect from a real positioning/sentiment effect — and it justifies a **low rebalance frequency** on this leg. The caveat is honesty about significance: even at its best the overlap-adjusted t is only +1.43 (21d) / +0.95 (63d). It points the right way; it does not clear t = 2.

2. **Carry's cross-sectional IC is ≈ 0 at every horizon, yet it earns in the book.** This is the uncomfortable, must-not-spin result. Three legitimate reconciliations, in order of how much weight I put on them: (a) **low power** — full-universe Spearman over only 13 names per day is a noisy per-day statistic; (b) **the book trades the tails, not the ranking** — the quantile portfolio only takes the top/bottom 40%, and it trades the carry+COT *blend*, so full-cross-section single-signal IC is not the quantity being monetised; (c) carry decays fast (autocorr 0.72 → 0.13 by 21d), so any edge is short-horizon and a daily-rebalanced book can still harvest it even with a weak *average* IC. I am explicitly **not** claiming this rescues carry — it means carry's contribution is real in the portfolio but **not demonstrable as a standalone cross-sectional predictor at this sample size**.

3. **The only significant IC is ts_momentum at 21d, and it is negative (t = −2.18).** Cross-sectionally, the strongest-trending names *underperform* over the next month — a contrarian/mean-reversion effect. This is a genuine result, and it validates the survivor selection: ts_momentum was dropped, and had it been included as a momentum-*direction* bet it would have been wrong-signed. (It would only help if traded as a reversal, which the `reversal` signal already attempts — and reversal's own IC is weak.)

4. **Persistent ≠ predictive.** momentum and ts_momentum are the *most* persistent signals (autocorr 0.82 / 0.71 at 21d) but have zero or wrong-signed IC. Persistence alone is not edge — it only tells you how often you'd need to retrade. The combination that matters is *positive IC × high persistence*, and only COT has both.

## Verdict and what it means for the gate

| Question | Answer |
|---|---|
| Does any single signal clear |t| ≥ 2 in its traded direction? | **No.** |
| Does the surviving COT leg have a coherent, right-signed, slow IC? | **Yes** (IC-IR +0.124 @63d, autocorr 0.75 @21d) — but sub-significant. |
| Does carry stand alone as a cross-sectional predictor? | **No** (IC ≈ 0); it contributes only inside the blend/tails. |
| Any signal significant *against* its use? | **Yes** — ts_momentum @21d (t −2.18, contrarian), correctly excluded. |

**This corroborates the A-2 YELLOW.** The portfolio edge is real (bootstrap CI excludes zero) but **thin and concentrated**: it rests on the carry+COT *combination* and the tails the quantile book trades, not on a strong monotone ranking from either signal in isolation. That is not a reason to abandon the strategy — small, slow, sub-significant single-signal ICs that combine into a positive portfolio is a *normal* profile for a real low-Sharpe cross-sectional book — but it is a reason to be precise about how much is claimed, and it reinforces the A-2 conclusion that **paper/live trading (Layer B) is the real out-of-sample test** and that **mining more configs only hurts** (raises the DSR trial count without adding demonstrable signal).

**Actionable for Layer B (rebalance cadence):** the persistence profile says the COT leg can be rebalanced **weekly or even monthly** with almost no information loss (ranking is 75% stable at 21d) — daily rebalancing on COT just pays turnover for noise. Carry is genuinely faster (information gone by ~21d) and benefits from more frequent rebalancing. A split cadence — fast carry, slow COT — is the natural design the decay curves point to, and worth testing as a turnover-reduction lever once live.

## Reproducibility

```bash
uv run python scripts/run_ic_analysis.py
```

Outputs `reports/11_ic_analysis.csv`, `reports/11_signal_autocorr.csv`, `reports/charts/11_ic_by_horizon.png`, and `reports/charts/11_signal_decay.png`. IC is lookahead-free by construction: the signal is lagged one day (mirroring the backtester's trade lag) before correlating against strictly-forward returns.
