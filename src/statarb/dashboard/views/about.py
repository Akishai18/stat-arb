"""About tab: methodology summary + links to phase reports + reproducibility."""

from __future__ import annotations

import streamlit as st

from statarb.dashboard.state import DashboardState


def render(state: DashboardState) -> None:
    st.subheader("About this dashboard")
    st.markdown(
        """
        Systematic commodities long/short across 13 futures
        (5 energy + 5 metals + 3 grains). Pure price signals
        (momentum, reversal, time-series momentum) failed on this universe;
        economically grounded signals — curve carry (ETF-vs-futures proxy)
        and CFTC managed-money positioning — produced statistically
        significant alpha. The deployable headline strategy is the simple
        equal-weight quantile portfolio; the cvxpy mean-variance optimizer
        is shown alongside as a documented underperformer (Markowitz overfit
        on a small cross-section with sample-covariance noise).
        """
    )

    st.markdown("##### Headline strategy parameters")
    st.code(
        """
Universe: 13 commodity futures
  Energy:  CL=F, BZ=F, NG=F, RB=F, HO=F
  Metals:  GC=F, SI=F, HG=F, PL=F, PA=F
  Grains:  ZC=F, ZW=F, ZS=F

Signal blend (Sharpe-weighted; negative-IS signals dropped):
  Tested:    6 signals (mom, rev, ts_momentum, carry, cot, inventory)
  Surviving: carry + cot  (positive IS Sharpe)
  Dropped:   mom (-0.92), rev (-0.41), ts_momentum (-0.96), inventory (-0.60)

Portfolio construction (HEADLINE = baseline):
  Top 40% long / bottom 40% short, equal-weight within each leg.
  Dollar-neutral, daily rebalance, 10 bps/side transaction cost.

Phase 7 cvxpy optimizer (NOT headline -- underperforms baseline):
  Objective: alpha . w - 50 * w' Sigma w - cost * ||w - w_prev||_1
  Constraints: |w_i| <= 0.4, sum(|w_i|) <= 1.0, |sum(w_i)| <= 0.05
  Covariance: 63-day rolling sample.
  Result: Sharpe +0.15 vs baseline +1.00 -- documented Markowitz overfit.

Backtest engine:
  Single one-day lag enforced (weights set at close t earn returns t+1).
  176 unit tests including 'cheat signal' anti-lookahead trap.

Statistical defense:
  Block-bootstrap 95% CI excludes zero (p < 0.001, t-stat +4.36)
  Deflated Sharpe Ratio = 0.94 at N=25 trials
  15/16 calendar years positive (median annual Sharpe +0.78)
  27 sensitivity perturbations -- range [+0.65, +1.27], all positive
""",
        language="text",
    )

    st.markdown("##### What's in this universe")
    st.markdown(
        f"""
        - Tradable futures ({len(state.futures)}): {', '.join(state.futures)}
        - Backtest span: **{state.first_valid.date()} → {state.opt_weights.index.max().date()}**
        - Surviving signals in the blend: **{', '.join(state.surviving_signals)}**
        - EIA inventory data: **{"loaded" if state.has_inventory else "not loaded (no EIA_API_KEY)"}**
        """
    )

    st.markdown("##### Phase reports")
    st.markdown(
        """
        Each phase has its own narrative report under `reports/`:

        - `01_momentum.md` — 12-1 momentum: weak IS, negative OOS
        - `02_reversal_and_combo.md` — 5d reversal: negative; combination math validated
        - `03_futures_and_carry.md` — switching to futures + carry: first positive signal
        - `04_macro_signals.md` — COT works, inventory has wrong sign
        - `05_portfolio_construction.md` — Sharpe-weighted blend + cvxpy QP
        - `07_sensitivity.md` — Phase A6 robustness sweeps (27 perturbations)
        - `08_walkforward.md` — Phase A2 year-by-year + walk-forward optimizer
        - `09_calendar_carry_validation.md` — Phase A4 carry-proxy validation
        - `FINAL.md` — synthesis: what worked, what didn't, limitations
        - `ROADMAP.md` — Layer A complete; Layer B (live paper trading) pending
        """
    )

    st.markdown("##### Reproducibility")
    st.code(
        """
# Setup
uv sync --extra dev --extra opt --extra dashboard

# Optional: EIA inventory data
# Register a free key at https://www.eia.gov/opendata/register.php
# Put it in a .env file at the repo root:
#   EIA_API_KEY=your_key_here

# Ingest data (one-time, ~1 minute)
uv run python -m statarb.cli.ingest         # yfinance ETF + futures
uv run python -m statarb.cli.ingest_macro   # CFTC always; EIA if key set

# Run this dashboard
uv run streamlit run scripts/dashboard.py

# Reproduce all phase reports
uv run python scripts/run_momentum.py                # Phase 3
uv run python scripts/run_reversal_and_combo.py      # Phase 4
uv run python scripts/run_carry_and_futures.py       # Phase 5
uv run python scripts/run_macro_signals.py           # Phase 6
uv run python scripts/run_optimization.py            # Phase 7
uv run python scripts/run_final_evaluation.py        # Phase 8 + A1 + A3
uv run python scripts/run_walkforward.py             # Phase A2
uv run python scripts/run_sensitivity.py             # Phase A6
uv run python scripts/run_calendar_carry_validation.py  # Phase A4

# Verify
uv run pytest    # 176 tests
""",
        language="bash",
    )

    st.markdown("##### Stack")
    st.markdown(
        """
        - **Python 3.11+** managed by `uv`
        - **pandas + numpy + scipy + statsmodels** for data and metrics
        - **cvxpy + OSQP** for the (documented-failure) optimizer
        - **yfinance + requests** for data ingestion
        - **streamlit + plotly** for this dashboard (Bloomberg-terminal-styled)
        - **pytest + ruff** for tests + lint
        - **python-dotenv** for `.env` loading
        """
    )

    st.markdown("##### Caveats and limitations")
    st.markdown(
        """
        - Carry signal is a proxy (ETF-vs-futures return spread), not direct
          curve observation — paid data would tighten this. Validated at Pearson +0.58
          against direct calendar-spread carry on a recent 163-day window.
        - WTI's 2020-04-20 negative-oil-day is masked (auditable in code).
        - yfinance front-month continuous has ~20-30 roll-induced
          discontinuities over 16 years.
        - Inventory signal has the "wrong" sign as implemented; deliberately
          NOT sign-flipped post-hoc.
        - Small cross-section (13 commodities; expanded from an earlier 5-energy
          universe in Phase A1).  Real production would diversify across many more.
        - DSR = 0.94 sits just below the strict 95% multiple-testing bar at N=25.
          Sensitive to trial-count assumptions; at N=20 it passes.
        """
    )
