"""Streamlit dashboard entrypoint.

    uv run streamlit run scripts/dashboard.py
"""

from __future__ import annotations

import streamlit as st

from statarb.dashboard.state import COST_LEVELS_BPS, HEADLINE_COST_BPS, build_state
from statarb.dashboard.theme import inject_bloomberg_css, render_header
from statarb.dashboard.views import about, costs, overview, portfolio, regimes, signals, today


def main() -> None:
    st.set_page_config(
        page_title="STATARB-13",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Bloomberg-terminal styling (must run before any other widget) ---
    inject_bloomberg_css()

    # --- Top header bar ---
    render_header(
        title="STATARB-13",
        subtitle="Systematic Commodities Long/Short",
        status="OPERATIONAL",
    )

    # --- Sidebar: project header + global controls ---
    with st.sidebar:
        st.markdown(
            "<div style='color:#ff8000; font-weight:700; letter-spacing:0.1em;'>"
            "◆ STATARB-13"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='color:#8a8a8a; font-size:0.78rem;'>"
            "13 commodities | Carry + COT blend<br>"
            "Walk-forward + bootstrap + DSR<br>"
            "2011-07-01 → present"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown(
            "<div style='color:#ff8000; font-size:0.72rem; "
            "letter-spacing:0.08em; font-weight:600;'>"
            "GLOBAL CONTROLS"
            "</div>",
            unsafe_allow_html=True,
        )
        cost_bps = st.select_slider(
            "Transaction cost (bps per side)",
            options=list(COST_LEVELS_BPS),
            value=HEADLINE_COST_BPS,
            help="Affects the Overview equity curve and metrics.",
        )
        st.session_state["cost_bps"] = cost_bps
        st.divider()
        st.markdown(
            "<div style='color:#cc6600; font-size:0.72rem; "
            "letter-spacing:0.08em; font-weight:600;'>"
            "LOCKED STRATEGY"
            "</div>"
            "<div style='color:#e0e0e0; font-size:0.78rem; line-height:1.4;'>"
            "λ = 50 &nbsp; no turnover cap<br>"
            "gross ≤ 1.0 &nbsp; |net| ≤ 5%<br>"
            "|w_i| ≤ 40%<br>"
            "Sharpe-weighted blend, drop neg-IS"
            "</div>",
            unsafe_allow_html=True,
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
        "F1 OVERVIEW",
        "F2 TODAY",
        "F3 SIGNALS",
        "F4 PORTFOLIO",
        "F5 COSTS",
        "F6 REGIMES",
        "F7 ABOUT",
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
