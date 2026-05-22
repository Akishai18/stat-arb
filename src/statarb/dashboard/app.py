"""Streamlit dashboard entrypoint.

    uv run streamlit run scripts/dashboard.py
"""

from __future__ import annotations

import streamlit as st

from statarb.dashboard.state import COST_LEVELS_BPS, HEADLINE_COST_BPS, build_state
from statarb.dashboard.views import about, costs, overview, portfolio, regimes, signals, today


def main() -> None:
    st.set_page_config(
        page_title="stat-arb dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Sidebar: project header + global controls ---
    with st.sidebar:
        st.markdown("### Systematic Energy-Commodities")
        st.markdown("*A statistical-arbitrage research platform*")
        st.markdown(
            "Long/short energy futures portfolio combining curve carry, "
            "CFTC managed-money positioning, and (optional) EIA inventory "
            "surprises via a constrained `cvxpy` mean-variance optimizer."
        )
        st.divider()
        st.markdown("**Global controls**")
        cost_bps = st.select_slider(
            "Transaction cost (bps per side)",
            options=list(COST_LEVELS_BPS),
            value=HEADLINE_COST_BPS,
            help="Affects the Overview equity curve and metrics.",
        )
        st.session_state["cost_bps"] = cost_bps
        st.divider()
        st.markdown(
            "**Locked Phase 7 strategy:**\n"
            "- λ = 50, no turnover cap\n"
            "- gross ≤ 1.0, |net| ≤ 5%, |w_i| ≤ 40%\n"
            "- Sharpe-weighted blend of positive-IS-Sharpe signals only"
        )

    # --- Build cached state ---
    try:
        state = build_state()
    except FileNotFoundError as e:
        st.error(
            f"Cached data not found: {e}\n\n"
            "Run these commands once to populate the data layer:\n\n"
            "```\nuv run python -m statarb.cli.ingest\n"
            "uv run python -m statarb.cli.ingest_macro\n```"
        )
        st.stop()
        return

    # --- Tab navigation ---
    tabs = st.tabs([
        "Overview",
        "Today",
        "Signals",
        "Portfolio",
        "Costs",
        "Regimes",
        "About",
    ])
    with tabs[0]:
        overview.render(state)
    with tabs[1]:
        today.render(state)
    with tabs[2]:
        signals.render(state)
    with tabs[3]:
        portfolio.render(state)
    with tabs[4]:
        costs.render(state)
    with tabs[5]:
        regimes.render(state)
    with tabs[6]:
        about.render(state)


if __name__ == "__main__":
    main()
