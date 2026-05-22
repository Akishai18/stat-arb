"""About tab: methodology summary + links to phase reports + reproducibility."""

from __future__ import annotations

import streamlit as st

from statarb.dashboard.state import DashboardState


def render(state: DashboardState) -> None:
    st.subheader("About this dashboard")
    st.markdown(
        """
        This dashboard surfaces the locked Phase 7 strategy from a multi-phase
        systematic energy-commodities research project. Pure price signals
        (momentum, reversal) failed on this universe; economically grounded
        signals (curve carry, CFTC managed-money positioning) produced positive
        standalone alpha. A `cvxpy` mean-variance optimizer with constraints
        combines the surviving signals into the headline strategy you see here.
        """
    )

    st.markdown("##### Headline strategy parameters (locked from Phase 7)")
    st.code(
        """
Signal blend:
  Sharpe-weighted combine of 5 signals (mom, rev, carry, cot, inventory),
  with weights proportional to max(0, IS Sharpe).  Negative-Sharpe signals
  are dropped entirely.  Surviving signals: carry, cot.

Portfolio construction (cvxpy daily QP):
  Objective: alpha . w - lambda * w' Sigma w - cost * ||w - w_prev||_1
  Constraints:
    sum(|w_i|)       <= 1.0          (gross cap)
    |sum(w_i)|       <= 0.05         (dollar-near-neutral)
    |w_i|            <= 0.40         (concentration cap)
  lambda = 50
  Cost in objective = 10 bps per side
  Covariance: 63-day rolling sample, PSD-projected
  No hard turnover cap (soft penalty via the objective)

Backtest engine:
  Single one-day lag enforced (weights set at close t earn returns t+1).
  133 unit tests including a 'cheat signal' anti-lookahead trap.
""",
        language="text",
    )

    st.markdown("##### What's in this universe")
    st.markdown(
        f"""
        - Energy futures (5): {', '.join(state.futures)}
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
        - `FINAL.md` — synthesis: what worked, what didn't, limitations
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

# Ingest data (one-time)
uv run python -m statarb.cli.ingest         # yfinance ETF + futures
uv run python -m statarb.cli.ingest_macro   # CFTC always; EIA if key set

# Run this dashboard
uv run streamlit run scripts/dashboard.py

# Reproduce all phase reports
uv run python scripts/run_momentum.py
uv run python scripts/run_reversal_and_combo.py
uv run python scripts/run_carry_and_futures.py
uv run python scripts/run_macro_signals.py
uv run python scripts/run_optimization.py
uv run python scripts/run_final_evaluation.py

# Verify
uv run pytest
""",
        language="bash",
    )

    st.markdown("##### Stack")
    st.markdown(
        """
        - **Python 3.11+** managed by `uv`
        - **pandas + numpy + scipy + statsmodels** for data and metrics
        - **cvxpy + OSQP** for the optimizer
        - **yfinance + requests** for data ingestion
        - **streamlit + plotly** for this dashboard
        - **pytest + ruff** for tests + lint
        - **python-dotenv** for `.env` loading
        """
    )

    st.markdown("##### Caveats and limitations")
    st.markdown(
        """
        - Carry signal is a proxy (ETF-vs-futures return spread), not direct
          curve observation — paid data would tighten this.
        - WTI's 2020-04-20 negative-oil-day is masked (auditable in code).
        - yfinance front-month continuous has ~20-30 roll-induced
          discontinuities over 16 years.
        - Inventory signal has the "wrong" sign as implemented; deliberately
          NOT fixed post-hoc.
        - Small cross-section (5 commodities).  Real production would
          diversify across many more contracts.
        """
    )
