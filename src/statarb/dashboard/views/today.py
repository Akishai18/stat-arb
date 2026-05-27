"""Today tab: latest signal scores + current baseline weights + rebalance diff.

Shows the BASELINE strategy's weights (the headline). The optimizer is
documented as underperforming this on the wider universe (FINAL.md).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from statarb.dashboard.state import DashboardState
from statarb.dashboard.style import BAD, GOOD


def render(state: DashboardState) -> None:
    weights = state.baseline_weights

    # Last day with non-zero target weights
    non_empty = weights.abs().sum(axis=1) > 0
    if not non_empty.any():
        st.error("No baseline weights found in the cached pipeline.")
        return
    last_day = non_empty[non_empty].index.max()
    prev_day_candidates = non_empty[non_empty].index
    prev_day = prev_day_candidates[prev_day_candidates < last_day].max() if len(prev_day_candidates) > 1 else last_day

    st.subheader(f"Latest snapshot — {last_day.date()}")
    st.caption(f"Baseline strategy's target weights for the most recent trading day. Previous day: {prev_day.date()}.")

    # Current optimizer weights
    today_w = weights.loc[last_day]
    prev_w = weights.loc[prev_day]
    diff = today_w - prev_w

    w_df = pd.DataFrame({
        "Asset": today_w.index,
        "Yesterday weight": prev_w.round(3).values,
        "Today weight": today_w.round(3).values,
        "Change": diff.round(3).values,
    })
    st.markdown("##### Target weights (baseline = headline strategy)")
    st.dataframe(w_df, width='stretch', hide_index=True)

    gross = today_w.abs().sum()
    net = today_w.sum()
    turnover = diff.abs().sum()
    cols = st.columns(3)
    cols[0].metric("Gross exposure", f"{gross:.2%}")
    cols[1].metric("Net exposure", f"{net:+.2%}")
    cols[2].metric("Today's turnover", f"{turnover:.2%}")

    st.divider()

    # Latest signal scores per asset
    st.markdown("##### Latest signal scores (z-scored cross-sectionally per day)")
    score_rows: list[dict] = []
    for asset in state.futures:
        row = {"Asset": asset}
        for sig_name, panel in state.signals.items():
            if asset in panel.columns:
                # use last available non-NaN value for this asset
                series = panel[asset].loc[:last_day].dropna()
                row[sig_name] = round(float(series.iloc[-1]), 4) if len(series) else None
            else:
                row[sig_name] = None
        score_rows.append(row)
    st.dataframe(pd.DataFrame(score_rows), width='stretch', hide_index=True)

    st.divider()

    # IS Sharpe per signal -- so user sees which signals are weighted into the alpha
    st.markdown("##### Signal IS Sharpe (used as combine weights)")
    sharpe_rows = []
    for name, val in state.is_sharpes.items():
        used = name in state.surviving_signals
        sharpe_rows.append({
            "Signal": name,
            "IS Sharpe (2011-07 → 2018-12)": round(val, 3),
            "Weight in blend": "positive" if used else "DROPPED (negative or zero)",
        })
    st.dataframe(pd.DataFrame(sharpe_rows), width='stretch', hide_index=True)

    # The blended alpha for the latest day
    if last_day in state.alpha_panel.index:
        alpha_today = state.alpha_panel.loc[last_day]
        alpha_df = pd.DataFrame({
            "Asset": alpha_today.index,
            "Combined alpha (z-score)": alpha_today.round(3).values,
            "Sign": [
                f"<span style='color:{GOOD};font-weight:600'>LONG</span>" if v > 0
                else f"<span style='color:{BAD};font-weight:600'>SHORT</span>" if v < 0
                else "FLAT"
                for v in alpha_today.values
            ],
        })
        st.markdown("##### Combined alpha for today (Sharpe-weighted blend)")
        st.write(alpha_df.to_html(escape=False, index=False), unsafe_allow_html=True)
