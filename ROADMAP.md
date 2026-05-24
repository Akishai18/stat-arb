# Roadmap: From "research platform" to "trade-the-thing"

The 9-phase project produced a research platform and a not-statistically-significant Sharpe (+0.275, 95% CI `[-0.225, +0.711]`). Before building execution we need to either tighten the CI until it excludes zero **or** honestly conclude this signal set doesn't have edge. Only then do we build the live trading layer.

---

## Layer A — Firming up the research

**Goal:** answer "does the strategy have a real, statistically distinguishable edge?" with a Yes / No / What's-Needed.

**Decision gate at the end of Layer A:**
- If bootstrap CI on full-window OOS Sharpe **excludes zero at 5%** → proceed to Layer B
- If CI still straddles zero but point estimate is clearly positive and stable across more windows → consider a small Layer B with tight risk limits
- If CI straddles zero and point estimate degraded with wider universe → stop, document, treat as research finding

### Phase A1 — Universe expansion (highest leverage)

**Hypothesis:** the biggest reason the CI is wide is N=5 commodities × 15 years. Adding instruments increases the effective sample size for cross-sectional signals more than time does. The CI should tighten substantially.

**Add 8-10 new commodities + their ETF pairs (for carry):**

| Category | Futures | ETF pair |
|---|---|---|
| Metals | GC=F (gold), SI=F (silver), HG=F (copper), PL=F (platinum), PA=F (palladium) | GLD, SLV, CPER, PPLT, PALL |
| Grains | ZC=F (corn), ZW=F (wheat), ZS=F (soybeans) | CORN, WEAT, SOYB |
| Softs | (skip — no clean ETF pairs) | — |

Universe becomes ~13 commodities (5 energy + 5 metals + 3 grains). For commodities without ETF pairs (some softs, livestock), use COT and momentum signals only.

**Specific tasks:**
1. Add to `data/universe.py`: `METALS_FUTURES`, `GRAIN_FUTURES`, and matching ETF pairings in `ETF_FUTURES_PAIRS`.
2. Add CFTC contract codes for each new commodity (lookup once, verify open-interest sanity check).
3. Re-run `cli/ingest` and `cli/ingest_macro` (auto-handles new tickers).
4. Re-run the full Phase 8 evaluation pipeline.
5. Re-run the bootstrap.

**Effort:** ~1 day of code + verification. Mostly data-engineering plumbing already in place.

**Done when:** bootstrap CI on the full-window optimizer Sharpe is reported on the 13-commodity universe, with a side-by-side comparison to the 5-commodity version.

**Expected outcome (honest):** if the signal is genuinely real, the CI should narrow by roughly `√(13/5) ≈ 1.6×` for cross-sectional signals. The point estimate might go up or down — depends on whether non-energy commodities have similar carry dynamics.

### Phase A2 — Rolling walk-forward (replace single IS/OOS split)

**Hypothesis:** the current single 2018-12-31 split is a single experiment. A rolling walk-forward produces a much longer effective OOS trace and reveals whether the signal is stable or just lucky for one regime.

**Method:**
- Walk-forward windows: 5-year IS, 1-year OOS, **step monthly**.
- At each step: re-compute IS Sharpes for signal weighting, rebuild the optimizer's Sharpe-weighted blend, run optimizer on the next 1-month OOS period.
- Concatenate OOS results into one long OOS trace.
- Bootstrap that OOS trace.

**Specific tasks:**
1. `evaluation/walk_forward.py`: add `rolling_walkforward(returns_provider, train_years=5, test_months=1, step_months=1)` that yields (train_window, test_window) pairs.
2. `scripts/run_walkforward_evaluation.py`: re-runs the headline strategy under rolling walk-forward.
3. Report the bootstrap CI on the concatenated OOS trace.

**Effort:** ~1-2 days. Some engine refactoring required since IS Sharpes (currently a one-time computation) become time-varying.

**Done when:** a long OOS trace (10+ years of rolling-OOS days) is reported with its own bootstrap CI.

**Critical honesty check:** if the rolling-walk-forward Sharpe is materially worse than the single-split OOS Sharpe, that's a sign the single-split number was lucky.

### Phase A3 — Deflated Sharpe Ratio (multiple-testing correction)

**Hypothesis:** we tested 5 signals × 3 lookbacks × 3 lambda values × 3 turnover caps ≈ 135 implicit trials. Some "wins" are selection bias. Deflated Sharpe Ratio (Bailey & López de Prado 2014) corrects for this.

**Specific tasks:**
1. `evaluation/dsr.py`: implement DSR formula (closed-form, no bootstrap needed).
2. Apply to the headline strategy's Sharpe given the number of trials we actually ran.
3. Report Probabilistic Sharpe Ratio (PSR) and DSR alongside the bootstrap CI.

**Effort:** ~half a day.

**Done when:** DSR is reported alongside the bootstrap CI in the updated `FINAL.md`.

### Phase A4 — Calendar-spread carry (if Phase A1 doesn't tighten enough)

**Hypothesis:** the ETF-vs-futures spread proxy for carry is noisy. A real curve-shape signal would have a cleaner Sharpe and tighter CI.

**Approach 1: Use yfinance's currently-active contracts.** Build a "front vs. 3-month-forward" series from the contracts that ARE in yfinance's database, even though pre-2010 contracts are missing. Use only the post-2018 portion where the longer-dated contracts exist, accept the shorter sample, see if signal-per-day improves.

**Approach 2: Pay for clean continuous-futures data.** Nasdaq Data Link CME continuous futures or Polygon historical futures. ~$50-100/mo for 2-year history; one-time purchase for full history can be more.

**Specific tasks:**
1. Probe yfinance contract availability across the wider universe.
2. If usable contracts exist post-2018: build a calendar-spread carry signal that operates only on the post-2018 sample.
3. Backtest, bootstrap.
4. Compare to ETF-spread carry.

**Effort:** 1-2 days for Approach 1; longer with paid data.

**Done when:** calendar-spread carry signal is built and its Sharpe + CI are reported.

### Phase A5 — Time-series momentum (additional uncorrelated signal)

**Hypothesis:** cross-sectional momentum failed, but time-series momentum (long if own trailing return > 0, short if < 0) is a different signal that's known to work in commodities. It's uncorrelated with cross-sectional and uncorrelated with carry. If it has positive Sharpe, adding it to the blend should tighten the combined CI.

**Specific tasks:**
1. `signals/ts_momentum.py`: `ts_momentum(returns, lookback=126)` — sign of trailing N-day return per asset.
2. Backtest standalone, on wider universe.
3. Add to the Sharpe-weighted blend.

**Effort:** ~half a day (mostly free given existing framework).

**Done when:** TS momentum reported and either dropped (negative IS Sharpe) or included.

### Phase A6 — Sensitivity sweeps + robustness checks

**Goal:** prove the result isn't fragile to choices.

**Sweeps:**
- Drop one commodity at a time (`leave-one-out`) — is Sharpe stable?
- Different IS/OOS splits (2017, 2018, 2019 cutoffs) — same answer?
- Different cov lookback (30, 63, 126 days) — does optimizer overfit?
- Different position cap (20%, 40%, 60%) — does CI tighten with looser cap?

**Specific tasks:**
1. `scripts/run_sensitivity.py` — generates a table of "Sharpe under perturbation X."
2. Report range; if any single perturbation moves Sharpe by >0.2, that's fragile.

**Effort:** ~1 day.

**Done when:** sensitivity table is reported; "robust" claim is defensible OR fragility is documented.

### Layer A decision gate

After A1-A6, look at:
- Bootstrap CI on the rolling-walk-forward OOS Sharpe
- DSR-deflated Sharpe
- Sensitivity range

**Three possible outcomes:**

| Outcome | Decision |
|---|---|
| CI excludes zero at 5% AND DSR > 0 AND robust under sensitivity | **GREEN** — proceed to Layer B |
| CI straddles zero but point estimate consistent + DSR > 0 + robust | **YELLOW** — Layer B with minimum-size paper trading; reassess after 6 months |
| CI straddles zero AND point estimate degrades under perturbation | **RED** — stop; document research finding; the signal set doesn't have edge on this universe |

---

## Layer B — Live trading system (gated on Layer A = GREEN/YELLOW)

**Goal:** convert the strategy from "backtest verified" to "live paper-traded with real-time P&L."

### Phase B1 — Live state + scheduler (no broker yet)

**Build a paper portfolio that accumulates real elapsed-time P&L without ever placing an order.**

**Components:**
1. `statarb/live/portfolio.py` — `LivePortfolio` class:
   - State: current weights, current notional, daily P&L history
   - Methods: `apply_target_weights(new_weights, date) → trades_implied`, `mark_to_market(prices, date) → daily_pnl`
   - Persists to `data/live/portfolio.parquet`
2. `scripts/daily_pulse.py`:
   - Refresh yfinance prices, CFTC COT, EIA inventory
   - Re-run the headline pipeline through the optimizer
   - Compute today's target weights
   - Update LivePortfolio
   - Log to `data/live/log.txt`
3. `cron` setup documentation: `0 17 * * 1-5 cd /path && uv run python scripts/daily_pulse.py`
4. Dashboard "Live" tab: shows the live P&L curve and today's positions.

**Done when:** the cron has run for 5 trading days and the live P&L trace exists.

**Effort:** ~2-3 days.

### Phase B2 — Live monitoring + alerting

**Build the things you'd want if you cared about NOT losing money silently.**

**Components:**
1. Data-freshness check in `daily_pulse.py`: if yfinance returns stale prices or CFTC/EIA hasn't released this week's data, log a warning and SKIP the rebalance (don't trade on stale signals).
2. Position-size sanity check: if today's optimizer produces weights wildly different from yesterday's, page the user for review (defensive against optimizer instability or data corruption).
3. P&L watchdog: if cumulative drawdown exceeds 15%, page the user for a manual review.
4. Slack / email alerts via webhook URL stored in `.env`.

**Done when:** alerts fire correctly on synthetic stale-data / position-blowup / drawdown scenarios.

**Effort:** ~1-2 days.

### Phase B3 — Broker integration (paper trading)

**Alpaca paper API** (free, instant signup) submits orders against the daily targets.

**Components:**
1. `statarb/live/alpaca.py` — wrapper:
   - Fetch current positions from Alpaca paper account
   - Compute trades needed to reach target weights
   - Submit market orders
   - Reconcile fills with target
2. `daily_pulse.py` calls this if `ALPACA_API_KEY` is set.
3. Track slippage: `target_price` vs `fill_price` per trade, log to `data/live/fills.parquet`.

**Done when:** 1 month of Alpaca paper-traded P&L accumulated and reconciles with the LivePortfolio simulation.

**Effort:** ~2-3 days.

### Phase B4 — Live trading dashboard + research feedback loop

**Make the live data answer "is the signal still working?"**

**Components:**
1. Dashboard "Live" tab: shows live P&L vs. backtest projection; flags divergence.
2. Monthly bootstrap on the cumulative live OOS returns: is the Sharpe drifting away from the backtest CI?
3. Automated email/Slack monthly summary with Sharpe + max DD + the deflated Sharpe.

**Done when:** the dashboard's Live tab is the canonical source for "how is the strategy doing right now."

**Effort:** ~2 days.

### Layer B decision gate (after 3-6 months of live paper P&L)

Compare live Sharpe to backtest projection:
- Live Sharpe within backtest CI → strategy generalizes, consider real money with tight caps
- Live Sharpe outside CI on the low end → strategy is degrading or backtest was overfit, stop
- Live Sharpe outside CI on the high end → suspicious, audit for data leak

---

## Summary: order of operations

```
Layer A:  Firm the research (Sharpe is real?)
  A1 wider universe              ~1 day
  A2 rolling walk-forward        ~1-2 days
  A3 deflated Sharpe ratio       ~0.5 day
  A4 calendar-spread carry       ~1-2 days (optional)
  A5 time-series momentum        ~0.5 day
  A6 sensitivity sweeps          ~1 day
  ─────────────────────────────
  ~5-7 days total. Then decision gate.

Layer B:  Build the live system (only if A passes)
  B1 live portfolio + cron       ~2-3 days
  B2 monitoring + alerting       ~1-2 days
  B3 Alpaca paper trading        ~2-3 days
  B4 live dashboard + feedback   ~2 days
  ─────────────────────────────
  ~7-10 days total + 3-6 months of live paper trade.
```

Total: **12-17 engineering days** plus 3-6 months of calendar time for live validation.

## What we should do RIGHT NOW

Phase **A1 (wider universe)** is the single highest-leverage move. It's also the cheapest. It does three things at once:
1. Tightens the bootstrap CI mechanically (more independent observations)
2. Tests whether the signal generalizes beyond energy
3. Provides a stronger base for everything else (rolling walk-forward, sensitivity, eventually live trading)

If Phase A1 produces a still-not-significant Sharpe, the path forward is honest: document the finding, move on, don't build execution. If it tightens the CI to exclude zero, the rest of Layer A is mostly insurance against overfitting, and Layer B becomes a real prospect.

**Recommended first action:** Phase A1. ~1 day of work, conclusively answers "did N=5 matter?"
